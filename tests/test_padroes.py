"""Testes do filtro por padrões de linha (top 3 do histórico)."""

from __future__ import annotations

import random

import pandas as pd
import pytest

from src.core import scoring
from src.core.models import LotteryConfig, ValidacaoError
from src.loterias.mega_sena import MegaSena
from src.loterias.quina import Quina
from src.loterias.super_sete import SuperSete


def _historico(spec, quantidade: int = 120, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    dezenas = [
        sorted(rng.sample(spec.dezenas_validas, spec.sorteadas))
        for _ in range(quantidade)
    ]
    return pd.DataFrame(
        {
            "concurso": list(range(1, quantidade + 1)),
            "data": ["2026-01-01"] * quantidade,
            "dezenas": dezenas,
        }
    )


# --------------------------------------------------------------------------
# assinatura e frequências
# --------------------------------------------------------------------------
def test_padrao_linhas_assinatura():
    spec = Quina.spec
    # 1..10 é a primeira linha (10 colunas): duas dezenas ali, uma em cada outra
    assert scoring.padrao_linhas([1, 2, 11, 21, 31], spec) == "2-1-1-1"
    assert scoring.padrao_linhas([1, 11, 21, 31, 41], spec) == "1-1-1-1-1"
    assert scoring.padrao_linhas([1, 2, 3, 11, 21], spec) == "3-1-1"


def test_frequencias_padroes_ordenadas():
    spec = Quina.spec
    tabela = scoring.frequencias_padroes(spec, _historico(spec), limite=4)
    assert len(tabela) == 4
    quantidades = [item["quantidade"] for item in tabela]
    assert quantidades == sorted(quantidades, reverse=True)
    soma_percentual = sum(item["percentual"] for item in tabela)
    assert 0.0 < soma_percentual <= 100.0


def test_padroes_em_posicional_ficam_vazios():
    assert scoring.padrao_linhas([1, 2, 3, 4, 5, 6, 7], SuperSete.spec) == ""
    assert scoring.frequencias_padroes(SuperSete.spec, None) == []


def test_top_padroes_e_cobertura():
    spec = Quina.spec
    historico = _historico(spec)
    top = scoring.top_padroes(spec, historico, n=3)
    assert len(top) == 3
    cobertura = scoring.cobertura_padroes(spec, historico, top)
    assert 0.0 < cobertura <= 100.0
    # cobertura de tudo é 100%
    todos = [item["padrao"] for item in scoring.frequencias_padroes(spec, historico, 99)]
    assert scoring.cobertura_padroes(spec, historico, todos) == pytest.approx(100.0)


# --------------------------------------------------------------------------
# configuração
# --------------------------------------------------------------------------
def test_config_normaliza_padrao():
    cfg = LotteryConfig(padroes_linha="1-2-1")
    assert cfg.padroes_linha == ["2-1-1"]


def test_config_aceita_lista_e_remove_duplicados():
    cfg = LotteryConfig(padroes_linha=["2-1-1-1", "2-1-1-1", "1-1-1-1-1"])
    assert cfg.padroes_linha == ["2-1-1-1", "1-1-1-1-1"]


@pytest.mark.parametrize("valor", ["0-1-1", "2-x-1", "2-", "", 42, ["2-0-1"]])
def test_config_rejeita_padrao_invalido(valor):
    with pytest.raises(ValidacaoError):
        LotteryConfig(padroes_linha=valor)


def test_validar_contra_exige_soma_do_padrao_igual_ao_jogo():
    cfg = LotteryConfig(padroes_linha=["2-1-1"])  # soma 4, jogo da Quina tem 5
    with pytest.raises(ValidacaoError, match="soma 4"):
        Quina(config=cfg)


def test_validar_contra_exige_tamanho_do_sorteio():
    from src.loterias.lotomania import Lotomania

    cfg = LotteryConfig(padroes_linha=["4-3-3-3-2-2-1-1-1"])  # soma 20 = sorteio
    with pytest.raises(ValidacaoError, match="tamanho do sorteio"):
        Lotomania(config=cfg)  # aposta fixa de 50 dezenas


def test_validar_contra_rejeita_posicional():
    cfg = LotteryConfig(padroes_linha=["2-1-1-1-1-1"])
    with pytest.raises(ValidacaoError, match="posicional"):
        SuperSete(config=cfg)


def test_validar_contra_rejeita_concentracao_impossivel():
    from src.loterias.lotofacil import Lotofacil

    # Lotofácil: 15 dezenas, malha de 5 colunas — 6 numa linha é impossível
    cfg = LotteryConfig(padroes_linha=["6-5-4"])
    with pytest.raises(ValidacaoError, match="colunas"):
        cfg.validar_contra(Lotofacil.spec)


# --------------------------------------------------------------------------
# geração
# --------------------------------------------------------------------------
def test_geracao_respeita_padroes_top3():
    historico = _historico(Quina.spec, 150)
    top = scoring.top_padroes(Quina.spec, historico, n=3)
    loteria = Quina(
        config=LotteryConfig(qtd_jogos=5, seed=11, padroes_linha=top),
        historico=historico,
    )
    jogos = loteria.gerar()
    assert len(jogos) == 5
    for jogo in jogos:
        assert loteria.padrao_linhas(jogo) in set(top)
    assert 0.0 < loteria.padroes_cobertura <= 100.0
    assert loteria.padroes_frequentes[0]["quantidade"] >= 1


def test_padrao_unico_forca_a_assinatura():
    historico = _historico(Quina.spec, 150)
    loteria = Quina(
        config=LotteryConfig(qtd_jogos=3, seed=3, padroes_linha=["2-1-1-1"]),
        historico=historico,
    )
    for jogo in loteria.gerar():
        assert loteria.padrao_linhas(jogo) == "2-1-1-1"


def test_padroes_convivem_com_score_e_filtros():
    historico = _historico(MegaSena.spec, 150)
    top = scoring.top_padroes(MegaSena.spec, historico, n=3)
    cfg = LotteryConfig(qtd_jogos=2, seed=9, padroes_linha=top, score_minimo=110)
    cfg.filtros.pares = (2, 4)
    loteria = MegaSena(config=cfg, historico=historico)
    for jogo in loteria.gerar():
        assert loteria.padrao_linhas(jogo) in set(top)
        assert 2 <= loteria.analisar(jogo)["pares"] <= 4
        assert loteria.pontuar(jogo)["score"] >= 110
