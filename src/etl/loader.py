"""Orquestração do ETL: download, normalização e gravação no SQLite."""

from __future__ import annotations

import logging
import random
import re
from datetime import date, timedelta
from pathlib import Path

from ..utils import db
from . import scraper

logger = logging.getLogger(__name__)

#: Catálogo mínimo usado pelo gerador sintético (seção 2 do contrato).
CATALOGO: dict[str, dict] = {
    "mega-sena": {
        "universo": 60,
        "sorteadas": 6,
        "inicio": 1,
        "posicional": False,
    },
    "lotofacil": {
        "universo": 25,
        "sorteadas": 15,
        "inicio": 1,
        "posicional": False,
    },
    "quina": {
        "universo": 80,
        "sorteadas": 5,
        "inicio": 1,
        "posicional": False,
    },
    "lotomania": {
        "universo": 100,
        "sorteadas": 20,
        "inicio": 1,
        "posicional": False,
    },
    "timemania": {
        "universo": 80,
        "sorteadas": 10,
        "inicio": 1,
        "posicional": False,
    },
    "dupla-sena": {
        "universo": 50,
        "sorteadas": 6,
        "inicio": 1,
        "posicional": False,
    },
    "dia-de-sorte": {
        "universo": 31,
        "sorteadas": 7,
        "inicio": 1,
        "posicional": False,
    },
    "super-sete": {
        "universo": 10,
        "sorteadas": 7,
        "inicio": 0,
        "posicional": True,
    },
}

#: Quantidade padrão de concursos sintéticos quando não há histórico.
QUANTIDADE_PADRAO = 100


def _normalizar_key(key: str) -> str:
    """Normaliza a chave da modalidade (aceita chave, slug ou variações)."""
    texto = str(key).strip().lower()
    if texto in CATALOGO:
        return texto
    for chave, slug in scraper.SLUGS.items():
        if texto == slug:
            return chave
    normalizado = re.sub(r"[\s_]+", "-", texto)
    return normalizado


def _validar_key(key: str) -> str:
    """Valida e devolve a chave canônica da modalidade."""
    chave = _normalizar_key(key)
    if chave not in CATALOGO:
        raise ValueError(
            f"loteria desconhecida: {key!r}. "
            f"Válidas: {', '.join(CATALOGO)}"
        )
    return chave


def gerador_sintetico(
    loteria: str, quantidade: int, seed: int = 20260101
) -> list[dict]:
    """Gera histórico sintético determinístico para uso offline/testes.

    Os dados NÃO representam resultados reais. As dezenas seguem o
    universo e a quantidade de sorteadas do catálogo; a Super Sete usa sete
    dígitos posicionais de ``0..9``. As datas são sequenciais a partir de
    2020-01-01 e os concursos vão de 1 a ``quantidade``.
    """
    chave = _validar_key(loteria)
    quantidade = int(quantidade)
    if quantidade < 0:
        raise ValueError("quantidade deve ser maior ou igual a zero")

    info = CATALOGO[chave]
    rng = random.Random(seed)
    inicio = date(2020, 1, 1)
    registros: list[dict] = []

    for indice in range(quantidade):
        if info["posicional"]:
            dezenas = [rng.randrange(10) for _ in range(info["sorteadas"])]
        else:
            dezenas = sorted(
                rng.sample(
                    range(info["inicio"], info["universo"] + 1),
                    info["sorteadas"],
                )
            )
        registros.append(
            {
                "loteria": chave,
                "concurso": indice + 1,
                "data": (inicio + timedelta(days=indice)).isoformat(),
                "dezenas": dezenas,
                "premiacoes": None,
                "acumulado": None,
            }
        )
    return registros


def _semear(
    key: str, caminho: str | Path | None, quantidade: int
) -> int:
    """Grava histórico sintético e devolve quantos concursos são novos."""
    if quantidade <= 0:
        return 0
    antes = db.contar_concursos(key, caminho)
    db.upsert_concursos(gerador_sintetico(key, quantidade), caminho)
    depois = db.contar_concursos(key, caminho)
    return max(0, depois - antes)


def _resultado(
    key: str, novos: int, fonte: str, erro: str | None, caminho: str | Path | None
) -> dict:
    """Monta o dicionário de retorno do ``atualizar_loteria``."""
    ultimo = db.ultimo_concurso(key, caminho)
    return {
        "loteria": key,
        "novos": int(novos),
        "ultimo": int(ultimo) if ultimo is not None else 0,
        "fonte": fonte,
        "erro": erro,
    }


def atualizar_loteria(
    key: str,
    caminho: str | Path | None = None,
    maximo: int | None = None,
    offline: bool = False,
) -> dict:
    """Atualiza o histórico de uma modalidade.

    Fluxo: inicializa o banco, descobre o último concurso local e tenta
    baixar apenas os concursos novos. Se ``offline`` for verdadeiro (ou se
    houver qualquer falha de rede), usa o gerador sintético determinístico,
    sinalizando a fonte no retorno. Nunca propaga exceção de rede.

    Retorna ``{"loteria", "novos", "ultimo", "fonte", "erro"}``.
    """
    chave = _validar_key(key)
    if maximo is not None:
        maximo = int(maximo)
        if maximo <= 0:
            raise ValueError("maximo deve ser maior que zero")

    db.init_db(caminho)
    ultimo_local = db.ultimo_concurso(chave, caminho)

    if offline:
        if ultimo_local is None:
            quantidade = maximo if maximo is not None else QUANTIDADE_PADRAO
        elif maximo is not None and maximo > ultimo_local:
            quantidade = maximo
        else:
            quantidade = 0
        novos = _semear(chave, caminho, quantidade)
        return _resultado(chave, novos, "offline-sintetico", None, caminho)

    fonte = "caixa"
    erro: str | None = None
    novos = 0
    try:
        slug = scraper.SLUGS[chave]
        remoto = scraper.obter_ultimo(slug)
        if remoto is None:
            raise RuntimeError("não foi possível descobrir o último concurso na Caixa")

        if ultimo_local is None:
            limite = maximo if maximo is not None else QUANTIDADE_PADRAO
            de = max(1, int(remoto) - int(limite) + 1)
        else:
            de = int(ultimo_local) + 1
        ate = int(remoto)
        if maximo is not None:
            ate = min(ate, de + maximo - 1)

        registros: list[dict] = []
        if de <= ate:
            registros = scraper.baixar_intervalo(slug, de, ate)
        if registros:
            antes = db.contar_concursos(chave, caminho)
            db.upsert_concursos(registros, caminho)
            depois = db.contar_concursos(chave, caminho)
            novos = max(0, depois - antes)
        elif ultimo_local is None:
            raise RuntimeError("nenhum concurso pôde ser baixado da Caixa")
    except Exception as exc:  # rede/parsing: nunca propaga, cai para sintético
        logger.warning("Falha ao atualizar %s pela rede: %s", chave, exc)
        fonte = "fallback"
        erro = f"{type(exc).__name__}: {exc}"
        # Só semeia quando não há histórico real; nunca sobrescreve dados.
        if ultimo_local is None:
            quantidade = maximo if maximo is not None else QUANTIDADE_PADRAO
            novos = _semear(chave, caminho, quantidade)
        else:
            novos = 0

    return _resultado(chave, novos, fonte, erro, caminho)


def atualizar_todas(
    caminho: str | Path | None = None, offline: bool = False
) -> dict:
    """Atualiza as oito modalidades, continuando mesmo se uma falhar."""
    resultados: dict[str, dict] = {}
    for chave in CATALOGO:
        try:
            resultados[chave] = atualizar_loteria(
                chave, caminho=caminho, offline=offline
            )
        except Exception as exc:
            logger.exception("Falha inesperada ao atualizar %s", chave)
            resultados[chave] = {
                "loteria": chave,
                "novos": 0,
                "ultimo": 0,
                "fonte": "fallback",
                "erro": f"{type(exc).__name__}: {exc}",
            }
    return resultados


__all__ = [
    "CATALOGO",
    "gerador_sintetico",
    "atualizar_loteria",
    "atualizar_todas",
]
