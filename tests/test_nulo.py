"""Testes das distribuições de referência e testes de aderência (``nulo.py``)."""

from __future__ import annotations

import itertools
import math
import random

import pytest

from src.core import nulo

scipy_stats = pytest.importorskip("scipy.stats", reason="scipy só é usado para conferência")


# --------------------------------------------------------------------------
# funções especiais
# --------------------------------------------------------------------------
@pytest.mark.parametrize("gl", [1, 2, 5, 9, 24, 59, 99])
@pytest.mark.parametrize("x", [0.3, 1.0, 4.0, 12.5, 40.0, 150.0])
def test_qui2_sf_confere_com_scipy(x, gl):
    assert nulo.qui2_sf(x, gl) == pytest.approx(scipy_stats.chi2.sf(x, gl), rel=1e-9, abs=1e-15)


def test_normal_sf_confere_com_scipy():
    for z in (-2.0, 0.0, 1.0, 1.96, 3.5):
        assert nulo.normal_sf(z) == pytest.approx(scipy_stats.norm.sf(z), rel=1e-12)


# --------------------------------------------------------------------------
# distribuições exatas
# --------------------------------------------------------------------------
@pytest.mark.parametrize("N,k", [(60, 6), (25, 15), (80, 5), (100, 20), (31, 7)])
def test_repeticao_pmf_e_hipergeometrica(N, k):
    pmf = nulo.repeticao_pmf(N, k)
    assert sum(pmf) == pytest.approx(1.0, abs=1e-12)
    ref = scipy_stats.hypergeom(N, k, k).pmf(range(k + 1))
    for obtido, esperado in zip(pmf, ref):
        assert obtido == pytest.approx(esperado, rel=1e-9, abs=1e-15)


def test_soma_pmf_enumeracao_exata_em_universo_pequeno():
    valores = list(range(1, 11))
    pmf = nulo.soma_pmf(valores, 3)
    contagem: dict[int, int] = {}
    for combo in itertools.combinations(valores, 3):
        contagem[sum(combo)] = contagem.get(sum(combo), 0) + 1
    total = math.comb(10, 3)
    assert set(pmf) == set(contagem)
    for soma, qtd in contagem.items():
        assert pmf[soma] == pytest.approx(qtd / total, rel=1e-12)


def test_soma_pmf_mega_sena_media_e_variancia():
    pmf = nulo.soma_pmf(range(1, 61), 6)
    assert sum(pmf.values()) == pytest.approx(1.0, abs=1e-12)
    media = sum(s * p for s, p in pmf.items())
    var = sum((s - media) ** 2 * p for s, p in pmf.items())
    # amostragem sem reposição: E = k (N+1)/2; Var = k (N+1)(N-k)/12
    assert media == pytest.approx(6 * 61 / 2)
    assert var == pytest.approx(6 * 61 * 54 / 12)


def test_soma_posicional_media_e_variancia():
    pmf = nulo.soma_posicional_pmf(10, 7)
    assert sum(pmf.values()) == pytest.approx(1.0, abs=1e-12)
    media = sum(s * p for s, p in pmf.items())
    var = sum((s - media) ** 2 * p for s, p in pmf.items())
    assert media == pytest.approx(7 * 4.5)
    assert var == pytest.approx(7 * 99 / 12)


def test_padroes_linhas_pmf_soma_um_e_confere_com_enumeracao():
    # universo pequeno: 12 dezenas em 3 linhas de 4, sorteio de 3
    pmf = nulo.padroes_linhas_pmf(12, 4, 3)
    assert sum(pmf.values()) == pytest.approx(1.0, abs=1e-12)
    contagem: dict[str, int] = {}
    for combo in itertools.combinations(range(1, 13), 3):
        linhas = [(d - 1) // 4 for d in combo]
        assinatura = "-".join(
            str(c) for c in sorted((linhas.count(i) for i in set(linhas)), reverse=True)
        )
        contagem[assinatura] = contagem.get(assinatura, 0) + 1
    total = math.comb(12, 3)
    assert set(pmf) == set(contagem)
    for padrao, qtd in contagem.items():
        assert pmf[padrao] == pytest.approx(qtd / total, rel=1e-12)


@pytest.mark.parametrize("N,colunas,k", [(60, 10, 6), (80, 10, 5), (25, 5, 15), (100, 10, 20), (50, 10, 6)])
def test_padroes_linhas_pmf_modalidades_reais_somam_um(N, colunas, k):
    pmf = nulo.padroes_linhas_pmf(N, colunas, k)
    assert sum(pmf.values()) == pytest.approx(1.0, abs=1e-9)


def test_padroes_linhas_pmf_confere_com_monte_carlo_mega_sena():
    pmf = nulo.padroes_linhas_pmf(60, 10, 6)
    rng = random.Random(11)
    n = 60_000
    contagem: dict[str, int] = {}
    for _ in range(n):
        jogo = rng.sample(range(1, 61), 6)
        linhas = [(d - 1) // 10 for d in jogo]
        assinatura = "-".join(
            str(c) for c in sorted((linhas.count(i) for i in set(linhas)), reverse=True)
        )
        contagem[assinatura] = contagem.get(assinatura, 0) + 1
    for padrao, prob in pmf.items():
        if prob > 0.02:
            erro_padrao = math.sqrt(prob * (1 - prob) / n)
            assert abs(contagem.get(padrao, 0) / n - prob) < 5 * erro_padrao


def test_acertos_media_var_confere_com_scipy():
    media, var = nulo.acertos_media_var(60, 6, 6)
    dist = scipy_stats.hypergeom(60, 6, 6)
    assert media == pytest.approx(dist.mean())
    assert var == pytest.approx(dist.var())
    media, var = nulo.acertos_media_var(60, 6, 10)
    dist = scipy_stats.hypergeom(60, 6, 10)
    assert media == pytest.approx(dist.mean())
    assert var == pytest.approx(dist.var())


# --------------------------------------------------------------------------
# bandas, atraso
# --------------------------------------------------------------------------
def test_wilson_confere_com_scipy():
    ic = scipy_stats.binomtest(35, 100).proportion_ci(method="wilson")
    lo, hi = nulo.wilson(35, 100, z=float(scipy_stats.norm.ppf(0.975)))
    assert lo == pytest.approx(ic.low, rel=1e-6)
    assert hi == pytest.approx(ic.high, rel=1e-6)


def test_banda_binomial_cobre_cerca_de_95_por_cento():
    rng = random.Random(3)
    n, p = 400, 0.1
    lo, hi = nulo.banda_binomial(n, p)
    dentro = 0
    ensaios = 4000
    for _ in range(ensaios):
        x = sum(rng.random() < p for _ in range(n))
        dentro += lo <= x <= hi
    assert 0.92 < dentro / ensaios < 0.98


def test_atraso_geometrico():
    p = 6 / 60
    assert nulo.atraso_cauda(p, 0) == 1.0
    assert nulo.atraso_cauda(p, 10) == pytest.approx(0.9**10)
    a95 = nulo.atraso_quantil(p, 0.95)
    assert nulo.atraso_cauda(p, a95) <= 0.05 < nulo.atraso_cauda(p, a95 - 1)


# --------------------------------------------------------------------------
# testes de aderência
# --------------------------------------------------------------------------
def _frequencias(N, k, n, seed):
    rng = random.Random(seed)
    freq = [0] * N
    for _ in range(n):
        for d in rng.sample(range(N), k):
            freq[d] += 1
    return freq


def test_uniformidade_p_valores_sob_h0_sao_aproximadamente_uniformes():
    # Lotofácil (p = 0.6): o Pearson ingênuo falharia; o corrigido deve calibrar.
    pvals = []
    for seed in range(300):
        freq = _frequencias(25, 15, 400, seed)
        pvals.append(nulo.uniformidade_dezenas(freq, 400, 15)["p"])
    rejeita_5 = sum(p < 0.05 for p in pvals) / len(pvals)
    rejeita_50 = sum(p < 0.50 for p in pvals) / len(pvals)
    assert 0.02 < rejeita_5 < 0.09
    assert 0.42 < rejeita_50 < 0.58


def test_uniformidade_detecta_vies_forte():
    freq = _frequencias(25, 15, 400, 1)
    freq[0] += 120
    freq[1] -= 120
    assert nulo.uniformidade_dezenas(freq, 400, 15)["p"] < 1e-6


def test_aderencia_qui2_agrupa_categorias_raras_e_calibra():
    pmf = nulo.repeticao_pmf(60, 6)
    prob = {str(r): p for r, p in enumerate(pmf)}
    rng = random.Random(5)
    pvals = []
    for _ in range(300):
        obs: dict[str, int] = {}
        anterior = set(rng.sample(range(60), 6))
        for _ in range(500):
            atual = set(rng.sample(range(60), 6))
            r = str(len(atual & anterior))
            obs[r] = obs.get(r, 0) + 1
            anterior = atual
        resultado = nulo.aderencia_qui2(obs, prob)
        pvals.append(resultado["p"])
    assert 0.02 < sum(p < 0.05 for p in pvals) / len(pvals) < 0.09


def test_aderencia_qui2_confere_com_scipy_sem_agrupamento():
    prob = {"a": 0.5, "b": 0.3, "c": 0.2}
    obs = {"a": 540, "b": 280, "c": 180}
    r = nulo.aderencia_qui2(obs, prob)
    ref = scipy_stats.chisquare([540, 280, 180], [500, 300, 200])
    assert r["estat"] == pytest.approx(ref.statistic)
    assert r["p"] == pytest.approx(ref.pvalue, rel=1e-9)
    assert r["gl"] == 2


def test_autocorrelacao_e_runs_em_serie_iid_e_serie_dependente():
    rng = random.Random(9)
    iid = [rng.random() for _ in range(800)]
    assert nulo.autocorrelacao_lag1(iid)["p"] > 0.01
    assert nulo.teste_de_runs(iid)["p"] > 0.01
    dep = [0.0]
    for _ in range(799):
        dep.append(0.7 * dep[-1] + rng.random())
    assert nulo.autocorrelacao_lag1(dep)["p"] < 1e-6
    assert nulo.teste_de_runs(dep)["p"] < 1e-6
    assert nulo.autocorrelacao_lag1([1.0] * 5) is None
    assert nulo.teste_de_runs([1.0] * 10) is None


def test_benjamini_hochberg_confere_com_scipy():
    pvals = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    q = nulo.benjamini_hochberg(pvals)
    ref = scipy_stats.false_discovery_control(pvals, method="bh")
    for a, b in zip(q, ref):
        assert a == pytest.approx(b, rel=1e-12)
    assert nulo.benjamini_hochberg([]) == []


def test_spearman_confere_com_scipy_no_rho():
    rng = random.Random(2)
    x = [rng.randint(0, 6) for _ in range(300)]  # com empates
    y = [xi * 0.3 + rng.random() for xi in x]
    r = nulo.spearman(x, y)
    ref = scipy_stats.spearmanr(x, y)
    assert r["rho"] == pytest.approx(ref.statistic, abs=1e-12)
    assert r["p"] == pytest.approx(ref.pvalue, abs=1e-6)
    assert nulo.spearman([1, 2, 3], [1, 2, 3]) is None
