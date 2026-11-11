"""Estatísticas sobre o histórico de concursos.

O histórico é sempre um ``pandas.DataFrame`` com as colunas ``concurso`` (int) e
``dezenas`` (list[int]), ordenado por concurso. Todas as funções toleram
DataFrame vazio/``None``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

import pandas as pd

__all__ = [
    "normalizar",
    "frequencia",
    "atraso",
    "dezenas_ultimo_concurso",
    "taxa_repeticao",
    "contaminacao",
    "filtrar_por_contaminacao",
    "resumo",
]

logger = logging.getLogger(__name__)

_COLUNAS = ["concurso", "dezenas"]


def _frame_vazio() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "concurso": pd.Series([], dtype="int64"),
            "dezenas": pd.Series([], dtype="object"),
        }
    )


def _converter_dezenas(valor: Any) -> list[int] | None:
    """Converte o campo de dezenas em ``list[int]`` ordenada; ``None`` se vazio."""
    if valor is None:
        return None
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        try:
            valor = json.loads(texto)
        except json.JSONDecodeError:
            # aceita "1,2,3" e "1 2 3"
            partes = texto.replace(",", " ").split()
            valor = [p for p in partes if p]
    if isinstance(valor, (bytes, bytearray)):
        return _converter_dezenas(valor.decode("utf-8", errors="ignore"))
    try:
        itens = list(valor)
    except TypeError:
        return None
    dezenas: list[int] = []
    for item in itens:
        if item is None:
            continue
        try:
            if isinstance(item, float) and pd.isna(item):
                continue
        except (TypeError, ValueError):
            pass
        try:
            dezenas.append(int(item))
        except (TypeError, ValueError):
            continue
    if not dezenas:
        return None
    return sorted(dezenas)


def _registros(df: pd.DataFrame | Sequence[dict] | dict | None) -> list[dict]:
    if df is None:
        return []
    if isinstance(df, pd.DataFrame):
        if df.empty:
            return []
        registros = df.to_dict("records")
    elif isinstance(df, dict):
        registros = [df]
    elif isinstance(df, (list, tuple)):
        registros = list(df)
    else:
        raise TypeError(
            "histórico deve ser None, lista de dicts ou pandas.DataFrame "
            f"(recebido {type(df).__name__})"
        )
    return [r for r in registros if isinstance(r, dict)]


def normalizar(
    df: pd.DataFrame | Sequence[dict] | dict | None,
) -> pd.DataFrame:
    """Normaliza o histórico para ``concurso:int`` + ``dezenas:list[int]``.

    Aceita ``None``, lista de dicts ou DataFrame. O resultado é ordenado por
    concurso e as dezenas de cada linha são ordenadas.
    """
    registros = _registros(df)
    linhas: list[dict] = []
    for posicao, registro in enumerate(registros, start=1):
        dezenas = _converter_dezenas(registro.get("dezenas"))
        if dezenas is None:
            logger.debug("registro sem dezenas ignorado: %r", registro)
            continue
        concurso = registro.get("concurso")
        try:
            concurso = int(concurso) if concurso is not None else posicao
        except (TypeError, ValueError):
            logger.debug("concurso inválido (%r); usando posição %s", concurso, posicao)
            concurso = posicao
        linhas.append({"concurso": concurso, "dezenas": dezenas})
    if not linhas:
        return _frame_vazio()
    resultado = pd.DataFrame(linhas, columns=_COLUNAS)
    resultado = resultado.sort_values("concurso", kind="mergesort")
    resultado = resultado.reset_index(drop=True)
    resultado["concurso"] = resultado["concurso"].astype("int64")
    resultado["dezenas"] = resultado["dezenas"].apply(list)
    return resultado[_COLUNAS]


def _lista_dezenas(df: pd.DataFrame | None) -> list[list[int]]:
    if df is None:
        return []
    if not isinstance(df, pd.DataFrame):
        df = normalizar(df)
    if df.empty or "dezenas" not in df.columns:
        return []
    return [list(item) for item in df["dezenas"].tolist() if item is not None]


def frequencia(df, universo: int, inicio: int = 1) -> dict[int, int]:
    """Quantas vezes cada dezena do universo apareceu no histórico."""
    if universo <= 0:
        return {}
    contagem = {d: 0 for d in range(inicio, inicio + universo)}
    for dezenas in _lista_dezenas(df):
        for dezena in dezenas:
            if dezena in contagem:
                contagem[dezena] += 1
    return contagem


def atraso(df, universo: int, inicio: int = 1) -> dict[int, int]:
    """Concursos desde a última aparição de cada dezena.

    ``0`` = saiu no último concurso; ``n`` = nunca saiu em ``n`` concursos.
    """
    if universo <= 0:
        return {}
    dezenas_por_concurso = _lista_dezenas(df)
    total = len(dezenas_por_concurso)
    ultimo_indice: dict[int, int] = {}
    for indice, dezenas in enumerate(dezenas_por_concurso):
        for dezena in dezenas:
            ultimo_indice[dezena] = indice
    resultado: dict[int, int] = {}
    for dezena in range(inicio, inicio + universo):
        indice = ultimo_indice.get(dezena)
        resultado[dezena] = total if indice is None else total - 1 - indice
    return resultado


def dezenas_ultimo_concurso(df) -> set[int]:
    """Conjunto de dezenas do concurso mais recente (vazio se não houver)."""
    dezenas = _lista_dezenas(df)
    if not dezenas:
        return set()
    return set(dezenas[-1])


def taxa_repeticao(df) -> float:
    """Média de dezenas repetidas entre concursos consecutivos."""
    dezenas = _lista_dezenas(df)
    if len(dezenas) < 2:
        return 0.0
    repeticoes = [
        len(set(anterior) & set(atual))
        for anterior, atual in zip(dezenas, dezenas[1:])
    ]
    return float(sum(repeticoes) / len(repeticoes))


def contaminacao(jogo: Sequence[int], df) -> int:
    """Maior sobreposição entre ``jogo`` e qualquer concurso do histórico."""
    alvo = {int(d) for d in jogo}
    if not alvo:
        return 0
    return max(
        (len(alvo & set(dezenas)) for dezenas in _lista_dezenas(df)),
        default=0,
    )


def filtrar_por_contaminacao(jogo, df, maximo: int | None) -> bool:
    """True se a contaminação respeitar o teto (``None`` = sem teto)."""
    if maximo is None:
        return True
    return contaminacao(jogo, df) <= int(maximo)


def resumo(df, universo: int, inicio: int = 1) -> dict:
    """Resumo do histórico: contagens, frequências, atrasos e repetição."""
    dezenas = _lista_dezenas(df)
    frequencias = frequencia(df, universo, inicio)
    ordenado = sorted(frequencias.items(), key=lambda item: (-item[1], item[0]))
    ultimo_concurso = None
    if dezenas:
        if isinstance(df, pd.DataFrame) and not df.empty and "concurso" in df.columns:
            ultimo_concurso = int(df["concurso"].iloc[-1])
        else:
            ultimo_concurso = len(dezenas)
    return {
        "concursos": len(dezenas),
        "ultimo_concurso": ultimo_concurso,
        "universo": int(universo),
        "frequencia": frequencias,
        "atraso": atraso(df, universo, inicio),
        "taxa_repeticao": taxa_repeticao(df),
        "ultimo": sorted(dezenas[-1]) if dezenas else [],
        "mais_frequentes": ordenado[:5],
        "menos_frequentes": ordenado[-5:][::-1] if ordenado else [],
    }
