"""Cliente HTTP e normalização de respostas das Loterias Caixa."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

#: Mapa entre a chave interna e o slug usado nos endpoints.
SLUGS: dict[str, str] = {
    "mega-sena": "megasena",
    "lotofacil": "lotofacil",
    "quina": "quina",
    "lotomania": "lotomania",
    "timemania": "timemania",
    "dupla-sena": "duplasena",
    "dia-de-sorte": "diadesorte",
    "super-sete": "supersete",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}
TIMEOUT = 15
MAX_TENTATIVAS = 3
BASE_CAIXA = "https://servicebus2.caixa.gov.br/portaldeloterias/api"
BASE_FALLBACK = "https://loteriascaixa-api.herokuapp.com/api"

_LOTERIAS_POSICIONAIS = frozenset({"super-sete", "supersete", "super sete"})


def _chave_loteria(valor: str) -> str:
    """Converte chave ou slug para a chave interna canônica."""
    texto = str(valor).strip().lower()
    if texto in SLUGS:
        return texto
    for chave, slug in SLUGS.items():
        if texto == slug:
            return chave
    normalizado = re.sub(r"[\s_]+", "-", texto)
    if normalizado in SLUGS:
        return normalizado
    return normalizado


def _eh_posicional(loteria: str) -> bool:
    """Indica se a modalidade é posicional (Super Sete)."""
    return _chave_loteria(loteria) in _LOTERIAS_POSICIONAIS


def _para_int(valor: Any) -> int:
    """Converte um valor escalar em inteiro, tolerando strings da API."""
    if isinstance(valor, bool):
        raise ValueError(f"valor booleano não é dezena: {valor!r}")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    texto = str(valor).strip()
    if texto.lstrip("-").isdigit():
        return int(texto)
    achado = re.search(r"-?\d+", texto)
    if achado:
        return int(achado.group())
    raise ValueError(f"dezena inválida: {valor!r}")


def _normalizar_data(valor: Any) -> str | None:
    """Converte ``dd/mm/aaaa`` (ou ISO) para ``aaaa-mm-dd``."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    texto = str(valor).strip().split(" ")[0].split("T")[0]
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"data inválida: {valor!r}")


def _normalizar_acumulado(valor: Any) -> float | None:
    """Converte o acumulado para float, aceitando formato brasileiro."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValueError(f"acumulado inválido: {valor!r}")
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def _normalizar_premiacoes(valor: Any) -> Any:
    """Mantém premiações como lista/dict, decodificando JSON quando textual."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        return json.loads(valor)
    if isinstance(valor, (list, dict)):
        return valor
    raise ValueError(f"premiações inválidas: {valor!r}")


def _primeiro(payload: dict, *chaves: str) -> Any:
    """Devolve o primeiro valor presente e não vazio entre as chaves."""
    for chave in chaves:
        if chave in payload and payload[chave] not in (None, "", []):
            return payload[chave]
    return None


def normalizar_resposta(payload: dict, loteria: str) -> dict | None:
    """Normaliza uma resposta bruta da Caixa para o formato do banco.

    Extrai ``concurso``, ``data``, ``dezenas``, ``premiacoes`` e
    ``acumulado``. Para a Super Sete preserva a ordem posicional das sete
    colunas; nas demais modalidades as dezenas são ordenadas.

    Devolve ``None`` quando o payload não é um dicionário ou não contém
    concurso/dezenas utilizáveis.
    """
    if not isinstance(payload, dict):
        return None

    chave = _chave_loteria(loteria)
    try:
        numero = _primeiro(payload, "numero", "concurso", "numeroConcurso")
        if numero is None:
            return None
        concurso = _para_int(numero)
        if concurso <= 0:
            return None
    except (TypeError, ValueError):
        return None

    bruto = _primeiro(payload, "listaDezenas", "dezenas")
    if not isinstance(bruto, (list, tuple)) or not bruto:
        return None
    try:
        dezenas = [_para_int(item) for item in bruto]
    except (TypeError, ValueError):
        logger.debug("Dezenas inválidas no concurso %s de %s", concurso, chave)
        return None
    if not _eh_posicional(chave):
        dezenas = sorted(set(dezenas))

    try:
        data = _normalizar_data(
            _primeiro(payload, "dataApuracao", "data", "dataSorteio")
        )
    except (TypeError, ValueError):
        data = None

    try:
        premiacoes = _normalizar_premiacoes(
            _primeiro(payload, "listaRateioPremio", "premiacoes")
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        premiacoes = None

    try:
        acumulado = _normalizar_acumulado(
            _primeiro(payload, "valorAcumuladoProximoConcurso", "acumulado")
        )
    except (TypeError, ValueError):
        acumulado = None

    return {
        "loteria": chave,
        "concurso": concurso,
        "data": data,
        "dezenas": dezenas,
        "premiacoes": premiacoes,
        "acumulado": acumulado,
    }


def _urls(slug: str, numero: int | None) -> list[str]:
    """Monta os endpoints a tentar, na ordem do contrato.

    A Super Sete não é publicada pelo endpoint oficial da Caixa (responde
    500 desde sempre), por isso a API espelho vem primeiro para essa
    modalidade e evita três tentativas inúteis por concurso.
    """
    caixa = f"{BASE_CAIXA}/{slug}"
    espelho = f"{BASE_FALLBACK}/{slug}"
    if _chave_loteria(slug) == "super-sete":
        if numero is None:
            return [espelho, caixa]
        return [f"{espelho}/{numero}", espelho, f"{caixa}/{numero}"]
    if numero is None:
        return [caixa, espelho]
    return [
        f"{caixa}/{numero}",
        f"{espelho}/{numero}",
        espelho,
    ]


def _get_json(session: requests.Session, url: str) -> Any:
    """Faz GET com até três tentativas e backoff exponencial."""
    for tentativa in range(MAX_TENTATIVAS):
        try:
            resposta = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as exc:
            logger.debug("Falha de rede em %s (tentativa %d): %s", url, tentativa + 1, exc)
        else:
            if resposta.status_code == 200:
                try:
                    return resposta.json()
                except ValueError as exc:
                    logger.debug("JSON inválido em %s: %s", url, exc)
            elif resposta.status_code in (429, 500, 502, 503, 504):
                logger.debug(
                    "HTTP %s em %s (tentativa %d)",
                    resposta.status_code,
                    url,
                    tentativa + 1,
                )
            else:
                logger.debug("HTTP %s em %s; endpoint descartado", resposta.status_code, url)
                return None

        if tentativa < MAX_TENTATIVAS - 1:
            time.sleep(0.5 * (2**tentativa))
    logger.warning("Não foi possível obter JSON de %s", url)
    return None


def _numero_candidato(item: dict) -> int:
    """Devolve o número do concurso de um item de lista; -1 se ilegível."""
    try:
        valor = _primeiro(item, "numero", "concurso", "numeroConcurso")
    except Exception:  # pragma: no cover - defensivo
        return -1
    if valor is None:
        return -1
    try:
        return _para_int(valor)
    except (TypeError, ValueError):
        return -1


def _extrair_registro(payload: Any, slug: str, numero: int | None) -> dict | None:
    """Seleciona o concurso desejado em payloads de objeto ou de lista."""
    chave = _chave_loteria(slug)
    if isinstance(payload, dict):
        for campo in ("concursos", "resultados"):
            if isinstance(payload.get(campo), list):
                payload = payload[campo]
                break
        else:
            return normalizar_resposta(payload, chave)

    if not isinstance(payload, list) or not payload:
        return None

    candidatos = [item for item in payload if isinstance(item, dict)]
    if not candidatos:
        return None
    if numero is None:
        # A API espelho devolve a lista do mais novo para o mais antigo, então
        # "último" é o maior número, não o último item da lista.
        return normalizar_resposta(max(candidatos, key=_numero_candidato), chave)
    for item in candidatos:
        try:
            valor = _primeiro(item, "numero", "concurso", "numeroConcurso")
            if valor is not None and _para_int(valor) == numero:
                return normalizar_resposta(item, chave)
        except (TypeError, ValueError):
            continue
    return None


def buscar_concurso(
    slug: str, numero: int | None = None, session: requests.Session | None = None
) -> dict | None:
    """Busca um concurso e devolve o registro já normalizado.

    Tenta os endpoints do contrato em ordem, com ``User-Agent`` de
    navegador, ``Accept: application/json``, timeout de 15s e três
    tentativas com backoff. Retorna ``None`` em falha definitiva.
    """
    propria = session is None
    sessao = session if session is not None else requests.Session()
    chave = _chave_loteria(slug)
    endpoint = SLUGS.get(chave, str(slug).strip().lower())
    try:
        for url in _urls(endpoint, numero):
            payload = _get_json(sessao, url)
            if payload is None:
                continue
            registro = _extrair_registro(payload, endpoint, numero)
            if registro is not None:
                return registro
        return None
    finally:
        if propria:
            sessao.close()


def obter_ultimo(slug: str) -> int | None:
    """Descobre o número do último concurso publicado."""
    registro = buscar_concurso(slug, None)
    if registro is None:
        return None
    return int(registro["concurso"])


def baixar_intervalo(slug: str, de: int, ate: int) -> list[dict]:
    """Baixa concursos de ``de`` até ``ate``, parando no primeiro vazio."""
    if de > ate:
        return []

    registros: list[dict] = []
    sessao = requests.Session()
    try:
        for numero in range(int(de), int(ate) + 1):
            registro = buscar_concurso(slug, numero, session=sessao)
            if registro is None:
                logger.warning(
                    "Concurso %s de %s indisponível; interrompendo o intervalo",
                    numero,
                    slug,
                )
                break
            registros.append(registro)
            if len(registros) % 50 == 0:
                logger.info(
                    "Baixados %d concursos de %s (até o %s)",
                    len(registros),
                    slug,
                    numero,
                )
    finally:
        sessao.close()
    return registros


__all__ = [
    "SLUGS",
    "normalizar_resposta",
    "buscar_concurso",
    "obter_ultimo",
    "baixar_intervalo",
]
