"""Distribuições de referência (hipótese nula) e testes de aderência.

Premissa de todo o módulo: cada sorteio é um subconjunto uniforme de ``k``
dezenas de um universo de ``N`` (ou, na Super Sete, ``k`` dígitos uniformes
independentes), e os concursos são independentes entre si. Sob essa hipótese
todas as métricas descritivas do dashboard (frequência, atraso, soma, repetição,
padrão de linha) têm distribuição conhecida, e este módulo calcula essas
distribuições de forma exata (ou com aproximações padrão e documentadas).

Só depende da biblioteca padrão e do NumPy; ``scipy`` é usado apenas nos testes
para conferir os resultados.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Sequence

import numpy as np

__all__ = [
    "repeticao_pmf",
    "binomial_pmf",
    "soma_pmf",
    "soma_posicional_pmf",
    "padroes_linhas_pmf",
    "banda_binomial",
    "wilson",
    "atraso_cauda",
    "atraso_quantil",
    "qui2_sf",
    "normal_sf",
    "uniformidade_dezenas",
    "aderencia_qui2",
    "autocorrelacao_lag1",
    "teste_de_runs",
    "benjamini_hochberg",
    "spearman",
    "acertos_media_var",
]


# --------------------------------------------------------------------------
# funções especiais (sem scipy)
# --------------------------------------------------------------------------
def normal_sf(z: float) -> float:
    """``P(Z > z)`` para ``Z ~ N(0, 1)``."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _gammaincc(a: float, x: float) -> float:
    """Função gama incompleta regularizada superior ``Q(a, x)``."""
    if x <= 0:
        return 1.0
    if a <= 0:
        raise ValueError("a deve ser positivo")
    log_prefixo = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1.0:
        # série para P(a, x); Q = 1 - P
        termo = 1.0 / a
        total = termo
        n = a
        for _ in range(10_000):
            n += 1.0
            termo *= x / n
            total += termo
            if abs(termo) < abs(total) * 1e-16:
                break
        return max(0.0, 1.0 - total * math.exp(log_prefixo))
    # fração contínua (Lentz) para Q(a, x)
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        atraso = d * c
        h *= atraso
        if abs(atraso - 1.0) < 1e-16:
            break
    return min(1.0, math.exp(log_prefixo) * h)


def qui2_sf(x: float, gl: float) -> float:
    """``P(X > x)`` para ``X ~ qui-quadrado(gl)``."""
    if gl <= 0:
        raise ValueError("graus de liberdade devem ser positivos")
    if x <= 0:
        return 1.0
    return _gammaincc(gl / 2.0, x / 2.0)


# --------------------------------------------------------------------------
# distribuições exatas
# --------------------------------------------------------------------------
def binomial_pmf(n: int, p: float) -> list[float]:
    """PMF de ``Binomial(n, p)`` para ``0..n``."""
    return [math.comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(n + 1)]


def repeticao_pmf(universo: int, k: int) -> list[float]:
    """PMF do nº de dezenas que um sorteio repete do anterior.

    Dois sorteios independentes de ``k`` entre ``N`` dezenas: a interseção é
    hipergeométrica ``H(N, k, k)``. Índice ``r`` = ``0..k``.
    """
    total = math.comb(universo, k)
    return [
        math.comb(k, r) * math.comb(universo - k, k - r) / total
        if k - r <= universo - k
        else 0.0
        for r in range(k + 1)
    ]


def soma_pmf(valores: Sequence[int], k: int) -> dict[int, float]:
    """Distribuição exata da soma de ``k`` dezenas sorteadas de ``valores``.

    Programação dinâmica sobre os subconjuntos; usa ``float64`` (probabilidades
    até ``C(100, 20) ~ 5e20`` cabem sem perda relevante de precisão relativa).
    """
    valores = [int(v) for v in valores]
    if not 0 < k <= len(valores):
        raise ValueError("k deve estar entre 1 e a quantidade de valores")
    maximo = sum(sorted(valores)[-k:])
    estados = np.zeros((k + 1, maximo + 1), dtype=np.float64)
    estados[0, 0] = 1.0
    for v in valores:
        for j in range(min(k, len(valores)), 0, -1):
            estados[j, v:] += estados[j - 1, : maximo + 1 - v]
    linha = estados[k] / math.comb(len(valores), k)
    return {int(s): float(p) for s, p in enumerate(linha) if p > 0.0}


def soma_posicional_pmf(universo: int, colunas: int) -> dict[int, float]:
    """Distribuição da soma de ``colunas`` dígitos uniformes independentes."""
    dist = np.array([1.0])
    um = np.full(universo, 1.0 / universo)
    for _ in range(colunas):
        dist = np.convolve(dist, um)
    return {int(s): float(p) for s, p in enumerate(dist) if p > 0.0}


def padroes_linhas_pmf(universo: int, colunas: int, k: int) -> dict[str, float]:
    """Probabilidade de cada padrão de linha para um sorteio uniforme.

    O padrão é a assinatura usada no projeto: contagem de dezenas por linha da
    malha, em ordem decrescente e ignorando linhas vazias (ex.: ``2-2-1-1``).
    Cada linha tem capacidade ``colunas`` (a última pode ser menor). A
    probabilidade soma ``prod C(cap_i, c_i) / C(N, k)`` sobre todas as formas de
    distribuir as ``k`` dezenas pelas linhas.
    """
    capacidades = [colunas] * (universo // colunas)
    if universo % colunas:
        capacidades.append(universo % colunas)
    estados: dict[tuple[int, ...], int] = {(): 1}
    for cap in capacidades:
        novos: dict[tuple[int, ...], int] = defaultdict(int)
        for contagens, peso in estados.items():
            usado = sum(contagens)
            for c in range(0, min(cap, k - usado) + 1):
                chave = (
                    contagens
                    if c == 0
                    else tuple(sorted(contagens + (c,), reverse=True))
                )
                novos[chave] += peso * math.comb(cap, c)
        estados = novos
    total = math.comb(universo, k)
    return {
        "-".join(str(c) for c in contagens): peso / total
        for contagens, peso in estados.items()
        if sum(contagens) == k
    }


def acertos_media_var(universo: int, sorteadas: int, aposta: int) -> tuple[float, float]:
    """Média e variância do nº de acertos de um jogo de ``aposta`` dezenas.

    Hipergeométrica ``H(N, k, m)``: independe de como o jogo foi escolhido.
    """
    p = sorteadas / universo
    media = aposta * p
    if universo <= 1:
        return media, 0.0
    var = aposta * p * (1 - p) * (universo - aposta) / (universo - 1)
    return media, var


# --------------------------------------------------------------------------
# intervalos e caudas
# --------------------------------------------------------------------------
def banda_binomial(n: int, p: float, z: float = 1.96) -> tuple[float, float]:
    """Faixa central aproximada (normal) da contagem ``Binomial(n, p)``."""
    media = n * p
    dp = math.sqrt(n * p * (1.0 - p))
    return max(0.0, media - z * dp), media + z * dp


def wilson(sucessos: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson para uma proporção observada (em 0..1)."""
    if n <= 0:
        return 0.0, 1.0
    p = sucessos / n
    z2 = z * z
    centro = (p + z2 / (2 * n)) / (1 + z2 / n)
    meia = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centro - meia), min(1.0, centro + meia)


def atraso_cauda(p: float, atraso: int) -> float:
    """``P(atraso >= a)`` com ``atraso ~ Geométrica(p)`` (nº de concursos sem sair)."""
    if not 0.0 < p < 1.0:
        return 0.0 if p >= 1.0 else 1.0
    return (1.0 - p) ** atraso


def atraso_quantil(p: float, nivel: float = 0.95) -> int:
    """Menor atraso ``a`` tal que ``P(atraso >= a) <= 1 - nivel``."""
    if not 0.0 < p < 1.0:
        return 0
    return int(math.ceil(math.log(1.0 - nivel) / math.log(1.0 - p)))


# --------------------------------------------------------------------------
# testes de aderência
# --------------------------------------------------------------------------
def uniformidade_dezenas(
    frequencias: Sequence[int], concursos: int, sorteadas: int
) -> dict[str, float]:
    """Qui-quadrado de uniformidade das frequências das dezenas.

    Como as ``k`` dezenas de um sorteio são tiradas sem reposição, cada contagem
    tem variância ``n p (1-p)`` e as contagens são negativamente correlacionadas.
    A estatística correta é ``(N-1)/N * sum (O-E)^2 / (n p (1-p))`` com ``N-1``
    graus de liberdade. O Pearson ingênuo (denominador ``E = n p``) subestima a
    dispersão por um fator ``1 - p`` e quase nunca rejeita (p grande, p. ex. na
    Lotofácil).
    """
    N = len(frequencias)
    p = sorteadas / N
    esperado = concursos * p
    estat = (
        (N - 1)
        / N
        * sum((o - esperado) ** 2 for o in frequencias)
        / (concursos * p * (1 - p))
    )
    gl = N - 1
    return {"estat": estat, "gl": gl, "p": qui2_sf(estat, gl)}


def aderencia_qui2(
    observado: dict[str, int],
    prob: dict[str, float],
    minimo_esperado: float = 5.0,
) -> dict[str, float] | None:
    """Qui-quadrado de aderência com agrupamento de categorias raras.

    Categorias com contagem esperada abaixo de ``minimo_esperado`` são unidas
    (das menos prováveis para as mais prováveis) até atingir o mínimo. Devolve
    ``None`` quando restam menos de duas categorias.
    """
    n = sum(observado.values())
    if n <= 0:
        return None
    categorias = sorted(prob, key=lambda c: prob[c])
    grupos: list[tuple[float, float]] = []  # (esperado, observado)
    atual_e = atual_o = 0.0
    for cat in categorias:
        atual_e += n * prob[cat]
        atual_o += observado.get(cat, 0)
        if atual_e >= minimo_esperado:
            grupos.append((atual_e, atual_o))
            atual_e = atual_o = 0.0
    if atual_e > 0:
        if grupos:
            e, o = grupos[-1]
            grupos[-1] = (e + atual_e, o + atual_o)
        else:
            grupos.append((atual_e, atual_o))
    if len(grupos) < 2:
        return None
    estat = sum((o - e) ** 2 / e for e, o in grupos)
    gl = len(grupos) - 1
    return {"estat": estat, "gl": gl, "p": qui2_sf(estat, gl)}


def autocorrelacao_lag1(serie: Sequence[float]) -> dict[str, float] | None:
    """Autocorrelação de lag 1 com teste normal (``r * sqrt(n) ~ N(0,1)``)."""
    n = len(serie)
    if n < 10:
        return None
    media = sum(serie) / n
    den = sum((x - media) ** 2 for x in serie)
    if den == 0:
        return None
    num = sum((serie[i] - media) * (serie[i + 1] - media) for i in range(n - 1))
    r = num / den
    z = r * math.sqrt(n)
    return {"r": r, "z": z, "p": 2.0 * normal_sf(abs(z))}


def teste_de_runs(serie: Sequence[float]) -> dict[str, float] | None:
    """Teste de Wald-Wolfowitz (sequências acima/abaixo da mediana)."""
    n = len(serie)
    if n < 20:
        return None
    ordenada = sorted(serie)
    mediana = (ordenada[(n - 1) // 2] + ordenada[n // 2]) / 2.0
    sinais = [x > mediana for x in serie if x != mediana]
    n1 = sum(sinais)
    n2 = len(sinais) - n1
    if n1 == 0 or n2 == 0:
        return None
    runs = 1 + sum(1 for a, b in zip(sinais, sinais[1:]) if a != b)
    total = n1 + n2
    media = 2.0 * n1 * n2 / total + 1.0
    var = (media - 1.0) * (media - 2.0) / (total - 1.0)
    if var <= 0:
        return None
    z = (runs - media) / math.sqrt(var)
    return {"runs": runs, "z": z, "p": 2.0 * normal_sf(abs(z))}


def benjamini_hochberg(pvalores: Iterable[float]) -> list[float]:
    """Valores-q de Benjamini-Hochberg (controle da taxa de falsas descobertas)."""
    p = list(pvalores)
    m = len(p)
    if m == 0:
        return []
    ordem = sorted(range(m), key=lambda i: p[i])
    q = [0.0] * m
    menor = 1.0
    for posicao in range(m - 1, -1, -1):
        i = ordem[posicao]
        menor = min(menor, p[i] * m / (posicao + 1))
        q[i] = menor
    return q


def _ranks(valores: Sequence[float]) -> list[float]:
    ordem = sorted(range(len(valores)), key=lambda i: valores[i])
    ranks = [0.0] * len(valores)
    i = 0
    while i < len(ordem):
        j = i
        while j + 1 < len(ordem) and valores[ordem[j + 1]] == valores[ordem[i]]:
            j += 1
        media = (i + j) / 2.0 + 1.0
        for pos in range(i, j + 1):
            ranks[ordem[pos]] = media
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> dict[str, float] | None:
    """Correlação de Spearman com p-valor normal aproximado (n >= 30)."""
    n = len(x)
    if n != len(y) or n < 30:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    rho = sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / math.sqrt(sxx * syy)
    z = rho * math.sqrt(n - 1)
    return {"rho": rho, "n": n, "p": 2.0 * normal_sf(abs(z))}
