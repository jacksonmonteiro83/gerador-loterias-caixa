"""Métricas puras (sem estado) usadas nos filtros de jogos.

Todas as funções recebem as dezenas e os parâmetros da malha
(``universo``, ``colunas``, ``inicio``) e devolvem valores simples. Nada aqui
altera os argumentos recebidos.
"""

from __future__ import annotations

import math
from typing import Sequence

from .models import FiltroConfig

__all__ = [
    "PRIMOS",
    "eh_primo",
    "contar_pares",
    "contar_impares",
    "contar_primos",
    "somar",
    "posicoes_moldura",
    "contar_moldura",
    "contar_miolo",
    "quadrantes",
    "contar_quadrantes",
    "metricas",
    "atende",
    "explicar_falha",
]


def eh_primo(n: int) -> bool:
    """Teste de primalidade por divisão (suficiente para dezenas ≤ 100)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return False
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    limite = math.isqrt(n)
    divisor = 3
    while divisor <= limite:
        if n % divisor == 0:
            return False
        divisor += 2
    return True


PRIMOS: frozenset[int] = frozenset(n for n in range(2, 101) if eh_primo(n))


def contar_pares(dezenas: Sequence[int]) -> int:
    return sum(1 for d in dezenas if int(d) % 2 == 0)


def contar_impares(dezenas: Sequence[int]) -> int:
    return sum(1 for d in dezenas if int(d) % 2 != 0)


def contar_primos(dezenas: Sequence[int]) -> int:
    return len({int(d) for d in dezenas} & PRIMOS)


def somar(dezenas: Sequence[int]) -> int:
    return sum(int(d) for d in dezenas)


def _celulas(universo: int, colunas: int, inicio: int = 1) -> list[list[int | None]]:
    """Malha ``linhas x colunas`` com ``None`` nas células fora do universo."""
    if universo <= 0:
        return []
    if colunas <= 0:
        raise ValueError("colunas deve ser maior que zero")
    linhas = math.ceil(universo / colunas)
    malha: list[list[int | None]] = []
    for linha in range(linhas):
        celulas: list[int | None] = []
        for coluna in range(colunas):
            indice = linha * colunas + coluna
            celulas.append(inicio + indice if indice < universo else None)
        malha.append(celulas)
    return malha


def posicoes_moldura(universo: int, colunas: int, inicio: int = 1) -> frozenset[int]:
    """Dezenas da borda da malha (primeira/última linha e coluna)."""
    malha = _celulas(universo, colunas, inicio)
    if not malha:
        return frozenset()
    ultima_linha = len(malha) - 1
    ultima_coluna = colunas - 1
    borda: set[int] = set()
    for i, linha in enumerate(malha):
        for j, valor in enumerate(linha):
            if valor is None:
                continue
            if i in (0, ultima_linha) or j in (0, ultima_coluna):
                borda.add(valor)
    return frozenset(borda)


def contar_moldura(
    dezenas: Sequence[int], universo: int, colunas: int, inicio: int = 1
) -> int:
    return len({int(d) for d in dezenas} & posicoes_moldura(universo, colunas, inicio))


def contar_miolo(
    dezenas: Sequence[int], universo: int, colunas: int, inicio: int = 1
) -> int:
    total = set(range(inicio, inicio + universo))
    miolo = total - posicoes_moldura(universo, colunas, inicio)
    return len({int(d) for d in dezenas} & miolo)


def quadrantes(universo: int, colunas: int, inicio: int = 1) -> list[frozenset[int]]:
    """Quatro blocos da malha, divididos por ``ceil(linhas/2)`` × ``ceil(colunas/2)``.

    Dezenas fora do universo nunca aparecem nos conjuntos.
    """
    malha = _celulas(universo, colunas, inicio)
    if not malha:
        return [frozenset(), frozenset(), frozenset(), frozenset()]
    linhas = len(malha)
    meio_linhas = math.ceil(linhas / 2)
    meio_colunas = math.ceil(colunas / 2)
    faixas_linhas = (range(0, meio_linhas), range(meio_linhas, linhas))
    faixas_colunas = (range(0, meio_colunas), range(meio_colunas, colunas))
    blocos: list[frozenset[int]] = []
    for faixa_linha in faixas_linhas:
        for faixa_coluna in faixas_colunas:
            bloco: set[int] = set()
            for i in faixa_linha:
                for j in faixa_coluna:
                    valor = malha[i][j]
                    if valor is not None:
                        bloco.add(valor)
            blocos.append(frozenset(bloco))
    return blocos


def contar_quadrantes(
    dezenas: Sequence[int], universo: int, colunas: int, inicio: int = 1
) -> list[int]:
    conjunto = {int(d) for d in dezenas}
    return [len(conjunto & bloco) for bloco in quadrantes(universo, colunas, inicio)]


def metricas(
    dezenas: Sequence[int], universo: int, colunas: int, inicio: int = 1
) -> dict:
    """Métricas de um jogo, com as chaves fixas do contrato."""
    valores = [int(d) for d in dezenas]
    total = len(valores)
    soma = sum(valores)
    m = {
        "pares": contar_pares(valores),
        "impares": contar_impares(valores),
        "primos": contar_primos(valores),
        "moldura": contar_moldura(valores, universo, colunas, inicio),
        "miolo": contar_miolo(valores, universo, colunas, inicio),
        "soma": soma,
        "quadrantes": contar_quadrantes(valores, universo, colunas, inicio),
        "total": total,
        "min": min(valores) if total else 0,
        "max": max(valores) if total else 0,
        "media": round(soma / total, 2) if total else 0.0,
    }
    return m


_FAIXAS = (
    ("pares", "pares"),
    ("impares", "impares"),
    ("primos", "primos"),
    ("moldura", "moldura"),
    ("miolo", "miolo"),
    ("soma", "soma"),
)


def _dentro(valor: int, faixa: tuple[int, int] | None) -> bool:
    if faixa is None:
        return True
    return int(faixa[0]) <= int(valor) <= int(faixa[1])


def atende(filtro: FiltroConfig, m: dict) -> bool:
    """True apenas se todos os filtros definidos forem satisfeitos."""
    if filtro is None:
        return True
    for chave, campo in _FAIXAS:
        if not _dentro(m[chave], getattr(filtro, campo)):
            return False
    quadros = list(m.get("quadrantes") or [])
    if filtro.quadrante_min is not None:
        if any(valor < filtro.quadrante_min for valor in quadros):
            return False
    if filtro.quadrante_max is not None:
        if any(valor > filtro.quadrante_max for valor in quadros):
            return False
    return True


def explicar_falha(filtro: FiltroConfig, m: dict) -> list[str]:
    """Motivos (pt-BR, curtos) pelos quais ``m`` não atende ``filtro``."""
    if filtro is None:
        return []
    motivos: list[str] = []
    for chave, campo in _FAIXAS:
        faixa = getattr(filtro, campo)
        if faixa is None:
            continue
        valor = m[chave]
        if not _dentro(valor, faixa):
            motivos.append(
                f"{chave}={valor} fora de ({faixa[0]}, {faixa[1]})"
            )
    quadros = list(m.get("quadrantes") or [])
    if filtro.quadrante_min is not None:
        for indice, valor in enumerate(quadros, start=1):
            if valor < filtro.quadrante_min:
                motivos.append(
                    f"quadrante {indice} com {valor} dezenas, mínimo "
                    f"{filtro.quadrante_min}"
                )
    if filtro.quadrante_max is not None:
        for indice, valor in enumerate(quadros, start=1):
            if valor > filtro.quadrante_max:
                motivos.append(
                    f"quadrante {indice} com {valor} dezenas, máximo "
                    f"{filtro.quadrante_max}"
                )
    return motivos
