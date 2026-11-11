"""Testes das métricas puras de filtros."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.filters import (  # noqa: E402
    PRIMOS,
    atende,
    contar_impares,
    contar_miolo,
    contar_moldura,
    contar_pares,
    contar_primos,
    contar_quadrantes,
    eh_primo,
    explicar_falha,
    metricas,
    posicoes_moldura,
    quadrantes,
    somar,
)
from src.core.models import FiltroConfig  # noqa: E402

COMBOS = [(60, 10), (25, 5), (100, 10), (80, 10), (50, 10), (31, 10), (10, 7), (6, 3)]


def test_primos_ate_100():
    assert eh_primo(2) and eh_primo(3) and eh_primo(97)
    assert not eh_primo(0) and not eh_primo(1) and not eh_primo(4)
    assert not eh_primo(100) and not eh_primo(-7)
    assert PRIMOS == frozenset(
        [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97]
    )
    assert len(PRIMOS) == 25


def test_contadores_basicos():
    jogo = [1, 2, 3, 4, 5, 6]
    assert contar_pares(jogo) == 3
    assert contar_impares(jogo) == 3
    assert contar_primos(jogo) == 3  # 2, 3, 5
    assert somar(jogo) == 21
    assert contar_pares([]) == 0
    assert somar([]) == 0


def test_moldura_valores_de_referencia():
    assert len(posicoes_moldura(60, 10)) == 28
    assert len(posicoes_moldura(25, 5)) == 16
    assert len(posicoes_moldura(100, 10)) == 36
    # Dia de Sorte: 4 linhas (última incompleta, só a dezena 31)
    assert len(posicoes_moldura(31, 10)) == 15

    mega = set(range(1, 61))
    moldura = posicoes_moldura(60, 10)
    assert contar_moldura([1, 60, 10, 51], 60, 10) == 4
    assert contar_miolo([1, 60, 12], 60, 10) == 1
    assert moldura | (mega - moldura) == mega
    assert moldura & (mega - moldura) == set()


@pytest.mark.parametrize("universo,colunas", COMBOS)
def test_moldura_e_miolo_particionam_o_universo(universo, colunas):
    universo_dezenas = set(range(1, universo + 1))
    moldura = set(posicoes_moldura(universo, colunas))
    miolo = universo_dezenas - moldura
    assert moldura | miolo == universo_dezenas
    assert moldura & miolo == set()
    jogo = sorted(universo_dezenas)
    assert contar_moldura(jogo, universo, colunas) == len(moldura)
    assert contar_miolo(jogo, universo, colunas) == len(miolo)


def test_quadrantes_valores_e_particao():
    blocos = quadrantes(60, 10)
    assert len(blocos) == 4
    assert [len(b) for b in blocos] == [15, 15, 15, 15]
    assert blocos[0] == frozenset({1, 2, 3, 4, 5, 11, 12, 13, 14, 15, 21, 22, 23, 24, 25})
    assert blocos[1] == frozenset({6, 7, 8, 9, 10, 16, 17, 18, 19, 20, 26, 27, 28, 29, 30})

    # 31 dezenas em 10 colunas: última linha incompleta e último bloco vazio
    blocos_ds = quadrantes(31, 10)
    assert len(blocos_ds) == 4
    assert blocos_ds[3] == frozenset(range(26, 31))
    assert blocos_ds[2] == frozenset({21, 22, 23, 24, 25, 31})
    assert blocos_ds[0] | blocos_ds[1] | blocos_ds[2] | blocos_ds[3] == frozenset(range(1, 32))
    assert sum(len(b) for b in blocos_ds) == 31


@pytest.mark.parametrize("universo,colunas", COMBOS)
def test_quadrantes_particionam_sem_vazar_universo(universo, colunas):
    universo_dezenas = set(range(1, universo + 1))
    blocos = quadrantes(universo, colunas)
    assert len(blocos) == 4
    uniao = set().union(*blocos)
    assert uniao == universo_dezenas
    assert sum(len(b) for b in blocos) == len(universo_dezenas)
    for bloco in blocos:
        assert bloco <= universo_dezenas


def test_contar_quadrantes():
    jogo = [1, 6, 31, 36]
    assert contar_quadrantes(jogo, 60, 10) == [1, 1, 1, 1]
    assert contar_quadrantes([], 60, 10) == [0, 0, 0, 0]


def test_metricas_chaves_e_valores():
    m = metricas([1, 2, 3, 4, 5, 6], 60, 10)
    assert set(m) == {
        "pares",
        "impares",
        "primos",
        "moldura",
        "miolo",
        "soma",
        "quadrantes",
        "total",
        "min",
        "max",
        "media",
    }
    assert m["pares"] == 3 and m["impares"] == 3 and m["primos"] == 3
    assert m["moldura"] == 6 and m["miolo"] == 0
    assert m["soma"] == 21
    assert m["quadrantes"] == [5, 1, 0, 0]
    assert m["total"] == 6
    assert m["min"] == 1 and m["max"] == 6
    assert m["media"] == pytest.approx(3.5)

    vazio = metricas([], 60, 10)
    assert vazio["total"] == 0
    assert vazio["min"] == 0 and vazio["max"] == 0
    assert vazio["media"] == 0.0
    assert vazio["quadrantes"] == [0, 0, 0, 0]


def test_atende_todas_as_faixas():
    m = metricas([1, 2, 3, 4, 5, 6], 60, 10)
    assert atende(FiltroConfig(), m)
    assert atende(FiltroConfig(pares=(3, 3), impares=(3, 3)), m)
    assert not atende(FiltroConfig(pares=(4, 6)), m)
    assert atende(FiltroConfig(primos=(1, 4)), m)
    assert not atende(FiltroConfig(primos=(4, 4)), m)
    assert atende(FiltroConfig(moldura=(0, 10), miolo=(0, 0)), m)
    assert not atende(FiltroConfig(miolo=(1, 5)), m)
    assert atende(FiltroConfig(soma=(21, 21)), m)
    assert not atende(FiltroConfig(soma=(22, 30)), m)
    assert atende(FiltroConfig(quadrante_min=0, quadrante_max=5), m)
    assert not atende(FiltroConfig(quadrante_min=2), m)
    assert not atende(FiltroConfig(quadrante_max=0), m)


def test_explicar_falha_mensagens():
    m = metricas([1, 2, 3, 4, 5, 6], 60, 10)
    assert explicar_falha(FiltroConfig(), m) == []

    motivos = explicar_falha(
        FiltroConfig(pares=(2, 2), soma=(100, 200), quadrante_min=3), m
    )
    assert "pares=3 fora de (2, 2)" in motivos
    assert "soma=21 fora de (100, 200)" in motivos
    assert any("quadrante 2" in motivo and "mínimo 3" in motivo for motivo in motivos)
    assert all(isinstance(motivo, str) for motivo in motivos)

    motivos_max = explicar_falha(FiltroConfig(quadrante_max=4), m)
    assert any("quadrante 1" in motivo and "máximo 4" in motivo for motivo in motivos_max)
