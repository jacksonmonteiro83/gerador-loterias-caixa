"""Score por simulação nula, auditoria, histórico versionado, backfill e validação."""

from __future__ import annotations

import json
import random

import pandas as pd
import pytest

from src.core import auditoria, scoring
from src.etl import historico, loader, scraper
from src.etl.validacao import validar_historico
from src.loterias.registry import get_loteria
from src.utils import db


def _draws(spec, n, semente=1):
    rng = random.Random(semente)
    if spec.tipo == "posicional":
        return [[rng.randrange(spec.universo) for _ in range(spec.sorteadas)] for _ in range(n)]
    base = range(spec.inicio, spec.inicio + spec.universo)
    return [sorted(rng.sample(base, spec.sorteadas)) for _ in range(n)]


# ---------------- score ----------------
def test_calibracao_nula_independe_do_historico():
    spec = get_loteria("mega-sena").spec
    a = scoring.calibrar(spec, pd.DataFrame({"dezenas": _draws(spec, 80, 1)}))
    b = scoring.calibrar(spec, pd.DataFrame({"dezenas": _draws(spec, 80, 2)}))
    assert a.fonte == "nulo"
    assert (a.limiar, a.ideal, a.ok, a.corte) == (b.limiar, b.ideal, b.ok, b.corte)
    assert a.taxa_nominal == b.taxa_nominal > 0
    assert a.amostra_nulo == scoring.AMOSTRA_NULO - 1  # pares (anterior, atual)


def test_aderencia_historica_tem_ic_de_wilson_e_cobre_a_taxa_nominal():
    spec = get_loteria("lotofacil").spec
    perfil = scoring.calibrar(spec, pd.DataFrame({"dezenas": _draws(spec, 600, 3)}))
    lo, hi = perfil.aderencia_ic
    assert lo <= perfil.aderencia_hist <= hi
    assert perfil.amostra_hist == 599
    # dados gerados sob H0: a taxa nominal deve cair dentro do IC (folga de 1 pt)
    assert lo - 1 <= perfil.taxa_nominal <= hi + 1


def test_perfil_em_cache_nao_vaza_mutacao():
    spec = get_loteria("quina").spec
    p1 = scoring.calibrar(spec, None)
    p1.corte["soma"] = [0, 0]
    p2 = scoring.calibrar(spec, None)
    assert p2.corte["soma"] != [0, 0]


def test_fonte_historico_preserva_comportamento_anterior():
    spec = get_loteria("mega-sena").spec
    p = scoring.calibrar(spec, pd.DataFrame({"dezenas": _draws(spec, 200)}), fonte="historico")
    assert p.fonte == "historico" and p.amostra_nulo == 0
    with pytest.raises(ValueError):
        scoring.calibrar(spec, None, fonte="outra")


# ---------------- auditoria ----------------
@pytest.mark.parametrize("chave", ["mega-sena", "lotofacil", "lotomania", "super-sete"])
def test_resumo_e_auditoria_sob_h0_nao_acusam_desvio(chave):
    spec = get_loteria(chave).spec
    resumo = auditoria.resumir(spec, _draws(spec, 800, 7))
    audit = auditoria.auditar(spec, resumo)
    assert audit["n_testes"] >= 6
    assert audit["n_q05"] == 0
    assert all(0 <= t["p"] <= 1 and t["q"] >= t["p"] for t in audit["testes"])
    json.dumps(auditoria.sem_internos(resumo))  # serializável


def test_auditoria_detecta_dado_adulterado():
    spec = get_loteria("mega-sena").spec
    draws = _draws(spec, 800, 9)
    for jogo in draws:  # dezena 1 em todos os sorteios
        if 1 not in jogo:
            jogo[0] = 1
            jogo.sort()
    audit = auditoria.auditar(spec, auditoria.resumir(spec, draws))
    assert audit["n_q05"] >= 1


def test_resumo_referencias_batem_com_teoria():
    spec = get_loteria("mega-sena").spec
    r = auditoria.resumir(spec, _draws(spec, 500, 4))
    assert r["freq_ref"]["esperado"] == pytest.approx(500 * 0.1)
    assert r["repeticao"]["media_esp"] == pytest.approx(36 / 60)
    assert sum(b["esp"] for b in r["soma"]["bins"]) == pytest.approx(500, rel=1e-3)
    assert r["padroes_top3"] == ["2-2-1-1", "2-1-1-1-1", "3-1-1-1"]


def test_backtest_estrategias_igualam_o_acaso():
    spec = get_loteria("mega-sena").spec
    draws = _draws(spec, 400, 5)
    perfil = scoring.calibrar(spec, None)
    top3 = auditoria.resumir(spec, draws)["padroes_top3"]
    bt = auditoria.backtest(spec, perfil, draws, top3=top3, jogos_por_concurso=8)
    assert bt["media_teorica"] == pytest.approx(0.6)
    assert set(bt["estrategias"]) == {"aleatorio", "aprovado", "padroes_top3"}
    for e in bt["estrategias"].values():
        assert abs(e["z_vs_teorico"]) < 4
    assert auditoria.backtest(spec, perfil, draws[:20]) is None


def test_geradores_respeitam_filtros():
    spec = get_loteria("mega-sena").spec
    rng = random.Random(1)
    top3 = ["2-2-1-1", "2-1-1-1-1", "3-1-1-1"]
    for _ in range(50):
        assert scoring.padrao_linhas(auditoria.gerar_padroes(spec, rng, 6, top3), spec) in top3


def test_rateio_exige_minimo_e_calcula_spearman():
    spec = get_loteria("mega-sena").spec
    draws = _draws(spec, 400, 6)
    sem = auditoria.analise_rateio(spec, [{"n": i, "z": z} for i, z in enumerate(draws)])
    assert sem["disponivel"] is False
    rng = random.Random(2)
    regs = [{"n": i, "z": z, "g": rng.randint(0, 3) + auditoria.indice_popularidade(z)} for i, z in enumerate(draws)]
    r = auditoria.analise_rateio(spec, regs)
    assert r["disponivel"] and r["spearman"]["rho"] > 0.3
    assert auditoria.analise_rateio(get_loteria("lotofacil").spec, regs)["disponivel"] is False


# ---------------- histórico versionado ----------------
def test_historico_roundtrip_ordena_e_normaliza_lotomania(tmp_path):
    historico.gravar("lotomania", [
        {"n": 2, "d": "2026-01-02", "z": [0, 5, 7]},
        {"n": 1, "d": "2026-01-01", "z": [1, 2, 3], "g": 4},
    ], tmp_path)
    lidos = historico.ler("lotomania", tmp_path)
    assert [r["n"] for r in lidos] == [1, 2]
    assert lidos[1]["z"] == [5, 7, 100]  # "00" é a 100ª dezena
    assert lidos[0]["g"] == 4
    assert historico.ler("mega-sena", tmp_path) == []


def test_hidratar_e_exportar_preservam_dados(tmp_path):
    caminho = tmp_path / "t.db"
    historico.gravar("mega-sena", [
        {"n": n, "d": f"2026-01-{n:02d}", "z": [1, 2, 3, 4, 5, n + 5], "g": n % 2} for n in range(1, 6)
    ], tmp_path)
    assert historico.hidratar(["mega-sena"], caminho, tmp_path) == {"mega-sena": 5}
    assert historico.hidratar(["mega-sena"], caminho, tmp_path) == {"mega-sena": 0}  # idempotente
    db.upsert_concursos([{"loteria": "mega-sena", "concurso": 6, "data": "2026-01-06",
                          "dezenas": [1, 2, 3, 4, 5, 11], "premiacoes": [{"faixa": 1, "numeroDeGanhadores": 2}]}], caminho)
    assert historico.exportar(["mega-sena"], caminho, tmp_path) == {"mega-sena": 6}
    final = historico.ler("mega-sena", tmp_path)
    assert [r["n"] for r in final] == [1, 2, 3, 4, 5, 6]
    assert final[0]["g"] == 1 and final[5]["g"] == 2


def test_ganhadores_faixa1_formatos():
    assert historico.ganhadores_faixa1([{"faixa": 2, "numeroDeGanhadores": 9}, {"faixa": 1, "numeroDeGanhadores": 3}]) == 3
    assert historico.ganhadores_faixa1([{"ganhadores": "7"}]) == 7
    assert historico.ganhadores_faixa1(None) is None
    assert historico.ganhadores_faixa1([{"faixa": 1}]) is None


def test_scraper_normaliza_zero_da_lotomania():
    assert scraper.normalizar_dezenas("lotomania", [0, 3, 99]) == [3, 99, 100]
    assert scraper.normalizar_dezenas("mega-sena", [3, 1]) == [3, 1]


# ---------------- backfill ----------------
def test_atualizar_completo_preenche_lacunas(tmp_path, monkeypatch):
    caminho = tmp_path / "t.db"
    db.upsert_concursos([
        {"loteria": "mega-sena", "concurso": n, "data": "2026-01-01", "dezenas": [1, 2, 3, 4, 5, 6]}
        for n in (3, 4)
    ], caminho)
    pedidos = []

    def falso(slug, numeros, limite=None):
        pedidos.append(list(numeros))
        regs = [{"loteria": "mega-sena", "concurso": n, "data": "2026-01-01", "dezenas": [1, 2, 3, 4, 5, 7],
                 "premiacoes": None, "acumulado": None} for n in numeros if n != 2]
        return regs, [2]

    monkeypatch.setattr(scraper, "obter_ultimo", lambda slug: 5)
    monkeypatch.setattr(scraper, "baixar_numeros", falso)
    r = loader.atualizar_loteria("mega-sena", caminho=caminho, completo=True)
    assert pedidos == [[1, 2, 5]]
    assert r["novos"] == 2
    assert db.numeros_concursos("mega-sena", caminho) == {1, 3, 4, 5}


def test_baixar_numeros_segue_apos_falha(monkeypatch):
    def falso(slug, numero, session=None):
        return None if numero == 2 else {"concurso": numero}

    monkeypatch.setattr(scraper, "buscar_concurso", falso)
    ok, falhas = scraper.baixar_numeros("megasena", [3, 1, 2, 4], limite=3)
    assert [r["concurso"] for r in ok] == [1, 3] and falhas == [2]


# ---------------- validação ----------------
def _regs(ns, z=(1, 2, 3, 4, 5, 6)):
    return [{"n": n, "d": f"2026-01-{n:02d}", "z": list(z)} for n in ns]


def test_validacao_completo_incompleto_e_erros():
    spec = get_loteria("mega-sena").spec
    ok = validar_historico(spec, _regs(range(1, 11)))
    assert ok["completo"] and not ok["erros"] and not ok["avisos"]
    parcial = validar_historico(spec, _regs(range(5, 11)))
    assert not parcial["completo"] and parcial["faltantes"] == 4 and parcial["avisos"]
    buraco = validar_historico(spec, _regs([1, 2, 4, 5]))
    assert buraco["faltantes"] == 1 and not buraco["completo"]
    ruim = validar_historico(spec, _regs([1, 1]) + [{"n": 3, "d": None, "z": [1, 2, 3, 4, 5, 99]},
                                                   {"n": 4, "d": None, "z": [1, 1, 2, 3, 4, 5]},
                                                   {"n": 5, "d": None, "z": [1, 2, 3]}])
    assert len(ruim["erros"]) >= 4
    assert not validar_historico(get_loteria("timemania").spec, _regs([1], z=range(1, 8)), sorteadas=7)["erros"]
