"""Testes do motor de score adaptativo (``src/core/scoring.py``)."""

from __future__ import annotations

import random

import pandas as pd
import pytest

from src.core import scoring
from src.core.models import LotteryConfig, LotterySpec, ValidacaoError
from src.loterias.mega_sena import MegaSena
from src.loterias.super_sete import SuperSete


def _historico(spec: LotterySpec, quantidade: int = 120, seed: int = 7) -> pd.DataFrame:
    """Histórico sintético com a mesma forma do histórico real."""
    rng = random.Random(seed)
    if spec.tipo == "posicional":
        dezenas = [
            [rng.randrange(spec.universo) for _ in range(spec.sorteadas)]
            for _ in range(quantidade)
        ]
    else:
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
# métricas
# --------------------------------------------------------------------------
def test_metricas_conjunto_basicas():
    spec = MegaSena.spec
    m = scoring.metricas_conjunto([1, 2, 3, 4, 5, 6], spec)
    assert m["soma"] == 21
    assert m["pares"] == 3
    assert m["primos"] == 3  # 2, 3 e 5
    assert m["primeiro"] == 1
    assert m["ultimo"] == 6
    assert m["amplitude"] == 5
    assert m["consecutivos"] == 5


def test_metricas_conjunto_repeticao_contra_anterior():
    spec = MegaSena.spec
    m = scoring.metricas_conjunto(
        [1, 2, 3, 4, 5, 6], spec, anterior=[1, 2, 30, 40, 50, 60]
    )
    assert m["repeticao"] == 2


def test_metricas_posicional_super_sete():
    spec = SuperSete.spec
    m = scoring.metricas_posicional([1, 1, 2, 2, 3, 4, 5], spec)
    assert m["soma"] == 18
    assert m["pares"] == 3  # 2, 2 e 4
    assert m["primos"] == 3  # 2, 3 e 5 (1 não é primo)
    assert m["max_digito"] == 2


# --------------------------------------------------------------------------
# perfil e faixas
# --------------------------------------------------------------------------
def test_calibrar_conjunto_produz_faixas_e_limiar():
    perfil = scoring.calibrar(MegaSena.spec, _historico(MegaSena.spec))
    assert perfil.posicional is False
    assert perfil.maximo == 140
    assert 70 <= perfil.limiar <= 125
    assert set(perfil.criterios) == set(scoring.CRITERIOS_CONJUNTO)
    for criterio in scoring.CRITERIOS_CONJUNTO:
        assert criterio in perfil.ideal
        assert criterio in perfil.ok
        assert perfil.ideal[criterio][0] <= perfil.ideal[criterio][1]
    assert 0.0 <= perfil.aderencia <= 100.0


def test_calibrar_sem_historico_usa_amostra_teorica():
    perfil = scoring.calibrar(MegaSena.spec, None)
    assert perfil.amostra > 0
    assert perfil.limiar >= 70


def test_calibrar_posicional_usa_cinco_criterios():
    perfil = scoring.calibrar(SuperSete.spec, _historico(SuperSete.spec))
    assert perfil.posicional is True
    assert perfil.maximo == 100
    assert set(perfil.criterios) == set(scoring.CRITERIOS_POSICIONAL)
    assert 45 <= perfil.limiar <= 90


def test_calibrar_para_tamanho_de_jogo_diferente():
    perfil_sorteio = scoring.calibrar(MegaSena.spec, _historico(MegaSena.spec, 60))
    perfil_aposta = scoring.calibrar(
        MegaSena.spec, _historico(MegaSena.spec, 60), qtd=10
    )
    assert perfil_sorteio.sorteadas == 6
    assert perfil_aposta.sorteadas == 10
    # um jogo de 10 dezenas é aceito pelo perfil de 10
    resultado = perfil_aposta.avaliar(list(range(1, 11)))
    assert 0 <= resultado["score"] <= 140


# --------------------------------------------------------------------------
# avaliação
# --------------------------------------------------------------------------
def test_avaliar_respeita_limites_do_score():
    perfil = scoring.calibrar(MegaSena.spec, _historico(MegaSena.spec))
    for jogo in (
        [1, 2, 3, 4, 5, 6],
        [10, 20, 30, 40, 50, 60],
        [4, 11, 23, 35, 47, 58],
    ):
        resultado = perfil.avaliar(jogo)
        assert 0 <= resultado["score"] <= perfil.maximo
        assert isinstance(resultado["aprovado"], bool)
        assert "status" in resultado
        assert "metricas" in resultado


def test_bloqueio_rigido_zera_o_score():
    perfil = scoring.calibrar(MegaSena.spec, _historico(MegaSena.spec))
    # força um corte impossível de soma para garantir a rejeição imediata
    perfil.corte["soma"] = (0, 0)
    resultado = perfil.avaliar([1, 2, 3, 4, 5, 6])
    assert resultado["score"] == 0
    assert resultado["aprovado"] is False
    assert "SOMA" in resultado["status"]


def test_avaliar_posicional_respeita_limites():
    perfil = scoring.calibrar(SuperSete.spec, _historico(SuperSete.spec))
    resultado = perfil.avaliar([0, 1, 2, 3, 4, 5, 6])
    assert 0 <= resultado["score"] <= 100
    assert isinstance(resultado["aprovado"], bool)


def test_perfil_serializavel_para_dashboard():
    perfil = scoring.calibrar(MegaSena.spec, _historico(MegaSena.spec))
    dados = perfil.como_dict()
    assert dados["modalidade"] == MegaSena.spec.nome
    assert isinstance(dados["ideal"]["soma"], list)
    assert isinstance(dados["criterios"], list)
    assert dados["colunas"] == MegaSena.spec.colunas
    assert dados["inicio"] == MegaSena.spec.inicio


# --------------------------------------------------------------------------
# integração com a engine de geração
# --------------------------------------------------------------------------
def test_geracao_com_score_minimo():
    historico = _historico(MegaSena.spec, 150)
    loteria = MegaSena(
        config=LotteryConfig(qtd_jogos=3, seed=11, score_minimo=120),
        historico=historico,
    )
    jogos = loteria.gerar()
    assert len(jogos) == 3
    for jogo in jogos:
        resultado = loteria.pontuar(jogo)
        assert resultado["score"] >= 120
        assert resultado["aprovado"] is True


def test_score_minimo_da_config_sobrepoe_o_limiar():
    historico = _historico(MegaSena.spec, 80)
    loteria = MegaSena(
        config=LotteryConfig(score_minimo=135), historico=historico
    )
    assert loteria.score_minimo == 135
    assert loteria.perfil_score.limiar <= 125


def test_perfil_score_por_tamanho_de_jogo():
    historico = _historico(MegaSena.spec, 80)
    loteria = MegaSena(config=LotteryConfig(seed=1), historico=historico)
    perfil6 = loteria.perfil_score_para(6)
    perfil10 = loteria.perfil_score_para(10)
    assert perfil6 is loteria.perfil_score_para(6)  # cache
    assert perfil6.sorteadas == 6
    assert perfil10.sorteadas == 10


def test_config_rejeita_score_minimo_invalido():
    for valor in (-1, 201):
        with pytest.raises(ValidacaoError):
            LotteryConfig(score_minimo=valor)
