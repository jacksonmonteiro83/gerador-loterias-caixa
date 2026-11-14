"""Histórico versionado no repositório (``data/historico/<modalidade>.jsonl``).

O SQLite é descartável (``data/*.db`` está no ``.gitignore``) e, no GitHub
Actions, nasce vazio a cada execução. Sem persistência, o pipeline só conseguia
baixar os últimos 100 concursos e todas as estatísticas eram calculadas sobre
essa janela. Estes arquivos são a fonte de verdade acumulada:

* uma linha JSON por concurso, ordenada por número (diff e merge limpos);
* campos: ``n`` (concurso), ``d`` (data ISO), ``z`` (dezenas), ``g`` opcional
  (nº de ganhadores da 1ª faixa, quando a API informa);
* o fluxo é: hidratar o SQLite a partir dos arquivos, baixar só o que falta e
  gravar de volta.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..utils import db
from .scraper import normalizar_dezenas

logger = logging.getLogger(__name__)

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
DIR_PADRAO = RAIZ_PROJETO / "data" / "historico"

_CHAVES_GANHADORES = ("numeroDeGanhadores", "ganhadores", "numero_ganhadores", "qtdGanhadores")


def caminho(key: str, diretorio: str | Path | None = None) -> Path:
    return Path(diretorio or DIR_PADRAO) / f"{key}.jsonl"


def ganhadores_faixa1(premiacoes: Any) -> int | None:
    """Extrai o nº de ganhadores da 1ª faixa de uma lista de premiações."""
    if not isinstance(premiacoes, list) or not premiacoes:
        return None
    alvo = None
    for item in premiacoes:
        if isinstance(item, dict) and str(item.get("faixa")) == "1":
            alvo = item
            break
    if alvo is None and isinstance(premiacoes[0], dict):
        alvo = premiacoes[0]
    if alvo is None:
        return None
    for chave in _CHAVES_GANHADORES:
        valor = alvo.get(chave)
        if valor is None:
            continue
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            continue
        return numero if numero >= 0 else None
    return None


def ler(key: str, diretorio: str | Path | None = None) -> list[dict]:
    """Lê o histórico de uma modalidade (lista vazia se o arquivo não existe)."""
    arquivo = caminho(key, diretorio)
    if not arquivo.exists():
        return []
    registros: list[dict] = []
    with arquivo.open(encoding="utf-8") as fh:
        for numero_linha, linha in enumerate(fh, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                item = json.loads(linha)
                registros.append(
                    {
                        "n": int(item["n"]),
                        "d": item.get("d"),
                        "z": normalizar_dezenas(key, [int(v) for v in item["z"]]),
                        **({"g": int(item["g"])} if item.get("g") is not None else {}),
                    }
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{arquivo}:{numero_linha}: linha inválida ({exc})") from exc
    return sorted(registros, key=lambda r: r["n"])


def gravar(key: str, registros: list[dict], diretorio: str | Path | None = None) -> Path:
    """Grava o histórico (ordenado, sem duplicatas) em JSON Lines."""
    arquivo = caminho(key, diretorio)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    unicos = {int(r["n"]): r for r in registros}
    with arquivo.open("w", encoding="utf-8", newline="\n") as fh:
        for n in sorted(unicos):
            fh.write(json.dumps(unicos[n], ensure_ascii=False, separators=(",", ":")) + "\n")
    return arquivo


def hidratar(
    chaves: list[str],
    caminho_db: str | Path | None = None,
    diretorio: str | Path | None = None,
) -> dict[str, int]:
    """Carrega no SQLite os concursos dos arquivos que ainda não estão no banco.

    Nunca sobrescreve registros que o banco já tem (podem ter mais campos, como
    premiações completas). Devolve quantos concursos foram inseridos por chave.
    """
    db.init_db(caminho_db)
    inseridos: dict[str, int] = {}
    for key in chaves:
        existentes = db.numeros_concursos(key, caminho_db)
        novos = []
        for item in ler(key, diretorio):
            if item["n"] in existentes:
                continue
            novos.append(
                {
                    "loteria": key,
                    "concurso": item["n"],
                    "data": item.get("d"),
                    "dezenas": item["z"],
                    "premiacoes": (
                        [{"faixa": 1, "numeroDeGanhadores": item["g"]}]
                        if "g" in item
                        else None
                    ),
                    "acumulado": None,
                }
            )
        if novos:
            db.upsert_concursos(novos, caminho_db)
        inseridos[key] = len(novos)
    return inseridos


def exportar(
    chaves: list[str],
    caminho_db: str | Path | None = None,
    diretorio: str | Path | None = None,
) -> dict[str, int]:
    """Grava o conteúdo do SQLite nos arquivos, preservando ``g`` já conhecido."""
    totais: dict[str, int] = {}
    for key in chaves:
        df = db.carregar_df(key, caminho=caminho_db)
        anteriores = {r["n"]: r for r in ler(key, diretorio)}
        registros: dict[int, dict] = {}
        if df is not None and not df.empty:
            for _, linha in df.iterrows():
                n = int(linha["concurso"])
                item: dict = {
                    "n": n,
                    "d": linha["data"] if linha["data"] is not None else None,
                    "z": [int(v) for v in linha["dezenas"]],
                }
                g = ganhadores_faixa1(linha["premiacoes"])
                if g is None and n in anteriores and "g" in anteriores[n]:
                    g = anteriores[n]["g"]
                if g is not None:
                    item["g"] = g
                registros[n] = item
        # concursos só presentes no arquivo (banco parcial) são mantidos
        for n, item in anteriores.items():
            registros.setdefault(n, item)
        gravar(key, list(registros.values()), diretorio)
        totais[key] = len(registros)
    return totais


__all__ = [
    "DIR_PADRAO",
    "caminho",
    "ganhadores_faixa1",
    "ler",
    "gravar",
    "hidratar",
    "exportar",
]
