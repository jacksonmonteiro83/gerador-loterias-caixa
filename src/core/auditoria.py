"""Resumo descritivo com referência teórica, auditoria de aleatoriedade e backtest.

Tudo aqui parte da hipótese nula (sorteios uniformes e independentes) e a usa
como régua: para cada métrica do dashboard calcula-se o valor *esperado ao
acaso* e compara-se com o observado. O objetivo é descritivo e educacional;
nenhum resultado daqui prevê sorteios futuros.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Sequence

from . import nulo, scoring
from .models import LotterySpec

__all__ = [
    "resumir",
    "auditar",
    "backtest",
    "analise_rateio",
    "gerar_aleatorio",
    "gerar_padroes",
    "gerar_aprovado",
    "indice_popularidade",
]

NIVEL_Z = 1.96
BINS_SOMA = 14


def _r(x: float, casas: int = 6) -> float:
    return round(float(x), casas)


# --------------------------------------------------------------------------
# resumo descritivo com referência esperada
# --------------------------------------------------------------------------
def _atrasos(draws: Sequence[Sequence[int]], valores: Sequence[int]) -> list[int]:
    n = len(draws)
    ultimo: dict[int, int] = {}
    for i, jogo in enumerate(draws):
        for d in jogo:
            ultimo[d] = i
    return [n - 1 - ultimo[v] if v in ultimo else n for v in valores]


def _bins_soma(
    pmf: dict[int, float], somas: Sequence[int], n: int
) -> tuple[list[dict[str, Any]], int, int]:
    """Histograma observado vs esperado (exato) da soma, em ``BINS_SOMA`` faixas."""
    acumulado = 0.0
    lo = hi = None
    for s in sorted(pmf):
        acumulado += pmf[s]
        if lo is None and acumulado >= 0.0005:
            lo = s
        if hi is None and acumulado >= 0.9995:
            hi = s
    lo = lo if lo is not None else min(pmf)
    hi = hi if hi is not None else max(pmf)
    largura = max(1, math.ceil((hi - lo + 1) / BINS_SOMA))
    nbins = math.ceil((hi - lo + 1) / largura)
    esperado = [0.0] * nbins
    observado = [0] * nbins

    def indice(valor: int) -> int:
        return min(nbins - 1, max(0, (valor - lo) // largura))

    for s, p in pmf.items():
        esperado[indice(s)] += n * p
    for s in somas:
        observado[indice(s)] += 1
    bins = [
        {
            "ini": lo + i * largura,
            "fim": lo + (i + 1) * largura - 1,
            "obs": observado[i],
            "esp": _r(esperado[i], 3),
        }
        for i in range(nbins)
    ]
    return bins, lo, hi


def _estatisticas(valores: Sequence[float]) -> tuple[float, float]:
    n = len(valores)
    media = sum(valores) / n
    var = sum((v - media) ** 2 for v in valores) / max(1, n - 1)
    return media, math.sqrt(var)


def _resumir_conjunto(spec: LotterySpec, draws: list[list[int]]) -> dict[str, Any]:
    n = len(draws)
    N = spec.universo
    k = len(draws[0])
    p = k / N
    valores = list(range(spec.inicio, spec.inicio + N))

    freq = [0] * N
    for jogo in draws:
        for d in jogo:
            freq[d - spec.inicio] += 1
    atrasos = _atrasos(draws, valores)
    lo, hi = nulo.banda_binomial(n, p, NIVEL_Z)
    a95 = nulo.atraso_quantil(p, 0.95)
    freq_info = {
        "esperado": _r(n * p, 3),
        "banda": [_r(lo, 3), _r(hi, 3)],
        "fora_banda": sum(1 for f in freq if f < lo or f > hi),
        "fora_banda_esperado": _r(N * 0.05, 2),
    }
    atraso_info = {
        "media_esperada": _r((1 - p) / p, 3),
        "p95": a95,
        "acima_p95": sum(1 for a in atrasos if a >= a95),
        "acima_p95_esperado": _r(N * 0.05, 2),
        "cauda": [_r(nulo.atraso_cauda(p, a), 6) for a in atrasos],
    }

    pmf = nulo.soma_pmf(valores, k)
    somas = [sum(j) for j in draws]
    bins, s_lo, s_hi = _bins_soma(pmf, somas, n)
    media_esp = sum(s * q for s, q in pmf.items())
    sd_esp = math.sqrt(sum((s - media_esp) ** 2 * q for s, q in pmf.items()))
    media_obs, sd_obs = _estatisticas(somas)
    soma_info = {
        "bins": bins,
        "media_obs": _r(media_obs, 2),
        "media_esp": _r(media_esp, 2),
        "dp_obs": _r(sd_obs, 2),
        "dp_esp": _r(sd_esp, 2),
    }

    pares_universo = sum(1 for v in valores if v % 2 == 0)
    pares_obs = sum(sum(1 for d in j if d % 2 == 0) for j in draws) / n

    rep_pmf = nulo.repeticao_pmf(N, k)
    rep_obs = [0] * (k + 1)
    reps = []
    for anterior, atual in zip(draws, draws[1:]):
        r = len(set(anterior) & set(atual))
        rep_obs[r] += 1
        reps.append(r)
    pares_n = max(1, n - 1)
    repeticao_info = {
        "obs": rep_obs,
        "esp": [_r(pares_n * q, 3) for q in rep_pmf],
        "media_obs": _r(sum(reps) / len(reps), 3) if reps else None,
        "media_esp": _r(k * k / N, 3),
        "pares": len(reps),
    }

    pad_pmf = nulo.padroes_linhas_pmf(N, spec.colunas, k)
    pad_obs: dict[str, int] = {}
    for jogo in draws:
        chave = scoring.padrao_linhas(jogo, spec)
        pad_obs[chave] = pad_obs.get(chave, 0) + 1
    ordenados = sorted(pad_pmf, key=lambda c: (-pad_pmf[c], c))
    padroes = []
    for chave in ordenados[:8]:
        q = pad_pmf[chave]
        obs = pad_obs.get(chave, 0)
        dp = math.sqrt(n * q * (1 - q))
        padroes.append(
            {
                "padrao": chave,
                "quantidade": obs,
                "percentual": _r(100 * obs / n, 2),
                "esperado_pct": _r(100 * q, 2),
                "z": _r((obs - n * q) / dp, 2) if dp > 0 else 0.0,
            }
        )
    top3 = ordenados[:3]

    return {
        "n": n,
        "sorteadas": k,
        "freq": freq,
        "atraso": atrasos,
        "freq_ref": freq_info,
        "atraso_ref": atraso_info,
        "soma": soma_info,
        "pares": {"media_obs": _r(pares_obs, 3), "media_esp": _r(k * pares_universo / N, 3)},
        "repeticao": repeticao_info,
        "padroes": padroes,
        "padroes_top3": top3,
        "padroes_top3_esperado_pct": _r(100 * sum(pad_pmf[c] for c in top3), 2),
        "padroes_top3_observado_pct": _r(100 * sum(pad_obs.get(c, 0) for c in top3) / n, 2),
        "padroes_distintos": len(pad_pmf),
        "_pmf_soma": pmf,
        "_pmf_padroes": pad_pmf,
        "_pad_obs": pad_obs,
        "_somas": somas,
        "_reps": reps,
        "_rep_obs": rep_obs,
        "_rep_pmf": rep_pmf,
    }


def _resumir_posicional(spec: LotterySpec, draws: list[list[int]]) -> dict[str, Any]:
    n = len(draws)
    cols = len(draws[0])
    base = spec.universo
    p = 1.0 / base
    colunas = [[0] * base for _ in range(cols)]
    for jogo in draws:
        for i, v in enumerate(jogo):
            colunas[i][v] += 1
    lo, hi = nulo.banda_binomial(n, p, NIVEL_Z)
    celulas = cols * base
    fora = sum(1 for linha in colunas for c in linha if c < lo or c > hi)

    pmf = nulo.soma_posicional_pmf(base, cols)
    somas = [sum(j) for j in draws]
    bins, _, _ = _bins_soma(pmf, somas, n)
    media_esp = sum(s * q for s, q in pmf.items())
    sd_esp = math.sqrt(sum((s - media_esp) ** 2 * q for s, q in pmf.items()))
    media_obs, sd_obs = _estatisticas(somas)

    rep_obs = [0] * (cols + 1)
    reps = []
    for anterior, atual in zip(draws, draws[1:]):
        r = sum(1 for a, b in zip(anterior, atual) if a == b)
        rep_obs[r] += 1
        reps.append(r)
    rep_pmf = nulo.binomial_pmf(cols, p)
    pares_n = max(1, n - 1)
    pares_digitos = sum(1 for v in range(base) if v % 2 == 0)

    return {
        "n": n,
        "sorteadas": cols,
        "colunas": colunas,
        "freq_ref": {
            "esperado": _r(n * p, 3),
            "banda": [_r(lo, 3), _r(hi, 3)],
            "fora_banda": fora,
            "fora_banda_esperado": _r(celulas * 0.05, 2),
        },
        "soma": {
            "bins": bins,
            "media_obs": _r(media_obs, 2),
            "media_esp": _r(media_esp, 2),
            "dp_obs": _r(sd_obs, 2),
            "dp_esp": _r(sd_esp, 2),
        },
        "pares": {
            "media_obs": _r(sum(sum(1 for d in j if d % 2 == 0) for j in draws) / n, 3),
            "media_esp": _r(cols * pares_digitos / base, 3),
        },
        "repeticao": {
            "obs": rep_obs,
            "esp": [_r(pares_n * q, 3) for q in rep_pmf],
            "media_obs": _r(sum(reps) / len(reps), 3) if reps else None,
            "media_esp": _r(cols * p, 3),
            "pares": len(reps),
        },
        "padroes": [],
        "padroes_top3": [],
        "_pmf_soma": pmf,
        "_somas": somas,
        "_reps": reps,
        "_rep_obs": rep_obs,
        "_rep_pmf": rep_pmf,
        "_colunas": colunas,
    }


def resumir(spec: LotterySpec, draws: list[list[int]]) -> dict[str, Any]:
    """Métricas observadas + referência teórica, prontas para o dashboard.

    As chaves iniciadas por ``_`` são insumos internos (usados por
    :func:`auditar`) e devem ser removidas antes de serializar.
    """
    if not draws:
        raise ValueError("histórico vazio")
    if spec.tipo == "posicional":
        return _resumir_posicional(spec, draws)
    return _resumir_conjunto(spec, draws)


def sem_internos(resumo: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in resumo.items() if not k.startswith("_")}


# --------------------------------------------------------------------------
# auditoria de aleatoriedade
# --------------------------------------------------------------------------
def auditar(spec: LotterySpec, resumo: dict[str, Any]) -> dict[str, Any]:
    """Bateria de testes sob H0 com correção de Benjamini-Hochberg."""
    testes: list[dict[str, Any]] = []

    def adicionar(identificador: str, rotulo: str, resultado: dict | None, **extra):
        if resultado is None:
            return
        item = {"id": identificador, "rotulo": rotulo, **extra}
        for chave in ("estat", "gl", "r", "z", "runs"):
            if chave in resultado:
                item[chave] = _r(resultado[chave], 4)
        item["p"] = _r(resultado["p"], 6)
        testes.append(item)

    n = resumo["n"]
    if spec.tipo == "posicional":
        uniforme = {str(d): 1.0 / spec.universo for d in range(spec.universo)}
        for i, contagem in enumerate(resumo["_colunas"], start=1):
            obs = {str(d): c for d, c in enumerate(contagem)}
            adicionar(
                f"uniformidade_c{i}",
                f"Uniformidade dos dígitos da coluna {i}",
                nulo.aderencia_qui2(obs, uniforme),
            )
    else:
        adicionar(
            "uniformidade",
            "Uniformidade da frequência das dezenas",
            nulo.uniformidade_dezenas(resumo["freq"], n, resumo["sorteadas"]),
        )
        pad_prob = resumo["_pmf_padroes"]
        adicionar(
            "padroes",
            "Padrões de linha vs. distribuição teórica",
            nulo.aderencia_qui2(resumo["_pad_obs"], pad_prob),
        )

    soma_prob = {str(s): q for s, q in resumo["_pmf_soma"].items()}
    soma_obs: dict[str, int] = {}
    for s in resumo["_somas"]:
        soma_obs[str(s)] = soma_obs.get(str(s), 0) + 1
    adicionar("soma", "Distribuição da soma vs. exata", nulo.aderencia_qui2(soma_obs, soma_prob))

    rep_prob = {str(r): q for r, q in enumerate(resumo["_rep_pmf"])}
    rep_obs = {str(r): c for r, c in enumerate(resumo["_rep_obs"])}
    adicionar("repeticao", "Repetição do concurso anterior vs. teórica", nulo.aderencia_qui2(rep_obs, rep_prob))

    adicionar(
        "autocorrelacao_soma", "Autocorrelação (lag 1) da soma",
        nulo.autocorrelacao_lag1(resumo["_somas"]),
    )
    adicionar("runs_soma", "Teste de sequências (runs) da soma", nulo.teste_de_runs(resumo["_somas"]))

    qs = nulo.benjamini_hochberg([t["p"] for t in testes])
    for teste, q in zip(testes, qs):
        teste["q"] = _r(q, 6)
    return {
        "n": n,
        "testes": testes,
        "n_testes": len(testes),
        "n_p05": sum(1 for t in testes if t["p"] < 0.05),
        "n_q05": sum(1 for t in testes if t["q"] < 0.05),
        "esperado_p05": _r(0.05 * len(testes), 2),
    }


# --------------------------------------------------------------------------
# geradores de referência (espelham o dashboard)
# --------------------------------------------------------------------------
def gerar_aleatorio(spec: LotterySpec, rng: random.Random, tamanho: int) -> list[int]:
    if spec.tipo == "posicional":
        return [rng.randrange(spec.universo) for _ in range(tamanho)]
    return sorted(rng.sample(range(spec.inicio, spec.inicio + spec.universo), tamanho))


def _rejeicao(
    spec: LotterySpec,
    rng: random.Random,
    tamanho: int,
    aceita: Callable[[list[int]], bool],
    tentativas: int,
) -> list[int]:
    """Amostragem por rejeição: uniforme dentro do conjunto aceito."""
    jogo = gerar_aleatorio(spec, rng, tamanho)
    for _ in range(tentativas):
        if aceita(jogo):
            return jogo
        jogo = gerar_aleatorio(spec, rng, tamanho)
    return jogo


def gerar_padroes(
    spec: LotterySpec, rng: random.Random, tamanho: int, top3: Sequence[str],
    tentativas: int = 5000,
) -> list[int]:
    alvo = set(top3)
    return _rejeicao(
        spec, rng, tamanho,
        lambda j: scoring.padrao_linhas(j, spec) in alvo, tentativas,
    )


def gerar_aprovado(
    spec: LotterySpec, rng: random.Random, tamanho: int,
    perfil: scoring.PerfilScore, anterior: Sequence[int] | None,
    tentativas: int = 5000,
) -> list[int]:
    return _rejeicao(
        spec, rng, tamanho,
        lambda j: perfil.avaliar(j, anterior)["aprovado"], tentativas,
    )


# --------------------------------------------------------------------------
# backtest walk-forward
# --------------------------------------------------------------------------
def _acertos(spec: LotterySpec, jogo: Sequence[int], sorteio: Sequence[int]) -> int:
    if spec.tipo == "posicional":
        return sum(1 for a, b in zip(jogo, sorteio) if a == b)
    return len(set(jogo) & set(sorteio))


def backtest(
    spec: LotterySpec,
    perfil: scoring.PerfilScore,
    draws: list[list[int]],
    top3: Sequence[str] | None = None,
    jogos_por_concurso: int = 10,
    max_concursos: int = 300,
    semente: int = 20261113,
) -> dict[str, Any] | None:
    """Compara estratégias de geração contra os sorteios reais, sem look-ahead.

    Para cada concurso ``t`` o gerador só conhece os concursos anteriores
    (``anterior = draws[t-1]``); o perfil de score vem da simulação sob H0, não
    do histórico, então não há vazamento. Em todas as estratégias o nº de
    acertos de um jogo é hipergeométrico com a **mesma** média ``m*k/N``; o
    teste verifica isso empiricamente (z da diferença pareada contra o acaso).
    """
    if len(draws) < 31:
        return None
    k = len(draws[0])
    m = perfil.sorteadas
    N = spec.universo
    if spec.tipo == "posicional":
        media_teorica, var_teorica = m / N, m * (1 / N) * (1 - 1 / N)
    else:
        media_teorica, var_teorica = nulo.acertos_media_var(N, k, m)

    estrategias: dict[str, Callable[[random.Random, Sequence[int]], list[int]]] = {
        "aleatorio": lambda rng, ant: gerar_aleatorio(spec, rng, m),
        "aprovado": lambda rng, ant: gerar_aprovado(spec, rng, m, perfil, ant),
    }
    if top3 and spec.tipo != "posicional" and m == k:
        estrategias["padroes_top3"] = lambda rng, ant: gerar_padroes(spec, rng, m, top3)

    inicio = max(1, len(draws) - max_concursos)
    alvo_idx = list(range(inicio, len(draws)))
    medias: dict[str, list[float]] = {nome: [] for nome in estrategias}
    for t in alvo_idx:
        anterior, sorteio = draws[t - 1], draws[t]
        for nome, fabrica in estrategias.items():
            rng = random.Random(f"{semente}-{nome}-{t}")
            total = sum(
                _acertos(spec, fabrica(rng, anterior), sorteio)
                for _ in range(jogos_por_concurso)
            )
            medias[nome].append(total / jogos_por_concurso)

    n = len(alvo_idx)

    def resumo_estrategia(nome: str) -> dict[str, Any]:
        media, dp = _estatisticas(medias[nome])
        ep = dp / math.sqrt(n)
        z = (media - media_teorica) / ep if ep > 0 else 0.0
        item = {
            "media": _r(media, 4),
            "erro_padrao": _r(ep, 4),
            "z_vs_teorico": _r(z, 3),
        }
        if nome != "aleatorio":
            difs = [a - b for a, b in zip(medias[nome], medias["aleatorio"])]
            md, dpd = _estatisticas(difs)
            epd = dpd / math.sqrt(n)
            zd = md / epd if epd > 0 else 0.0
            item.update(
                {
                    "dif_vs_aleatorio": _r(md, 4),
                    "dif_erro_padrao": _r(epd, 4),
                    "dif_z": _r(zd, 3),
                    "dif_p": _r(2 * nulo.normal_sf(abs(zd)), 4),
                }
            )
        return item

    return {
        "concursos": n,
        "jogos_por_concurso": jogos_por_concurso,
        "tamanho_jogo": m,
        "media_teorica": _r(media_teorica, 4),
        "dp_teorico_por_jogo": _r(math.sqrt(var_teorica), 4),
        "estrategias": {nome: resumo_estrategia(nome) for nome in estrategias},
    }


# --------------------------------------------------------------------------
# rateio: popularidade das combinações vs ganhadores
# --------------------------------------------------------------------------
def indice_popularidade(jogo: Sequence[int], limite_data: int = 31) -> int:
    """Nº de dezenas ≤ 31 (datas de aniversário): proxy de combinação popular."""
    return sum(1 for d in jogo if d <= limite_data)


def analise_rateio(
    spec: LotterySpec, registros: Sequence[dict], minimo: int = 200
) -> dict[str, Any]:
    """Relaciona o índice de popularidade do resultado ao nº de ganhadores.

    O valor esperado do prêmio de quem acerta depende de com quantos ele divide.
    Se resultados "populares" (muitas dezenas ≤ 31) tiverem mais ganhadores na
    1ª faixa, evitar combinações populares aumenta E[prêmio | acerto] sem mudar
    a chance de acerto. Limitação: o nº de ganhadores também cresce com o volume
    de apostas (concursos acumulados), que não é controlado aqui.
    """
    if spec.tipo == "posicional" or spec.universo <= 31:
        return {"disponivel": False, "motivo": "índice de datas só faz sentido com universo > 31"}
    com_g = [r for r in registros if r.get("g") is not None]
    if len(com_g) < minimo:
        return {
            "disponivel": False,
            "motivo": "ganhadores por concurso ainda não coletados (rode o backfill completo)",
            "com_ganhadores": len(com_g),
            "minimo": minimo,
        }
    pop = [indice_popularidade(r["z"]) for r in com_g]
    ganhadores = [r["g"] for r in com_g]
    esp_pop = len(com_g[0]["z"]) * 31 / spec.universo
    correlacao = nulo.spearman(pop, ganhadores)
    grupos: dict[int, list[int]] = {}
    for q, g in zip(pop, ganhadores):
        grupos.setdefault(q, []).append(g)
    return {
        "disponivel": True,
        "n": len(com_g),
        "dezenas_ate_31_esperado": _r(esp_pop, 2),
        "spearman": (
            {k: _r(v, 6) for k, v in correlacao.items()} if correlacao else None
        ),
        "grupos": [
            {"dezenas_ate_31": q, "concursos": len(v), "media_ganhadores": _r(sum(v) / len(v), 3)}
            for q, v in sorted(grupos.items())
        ],
    }
