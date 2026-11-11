"""Testes das oito modalidades e do catálogo (``src.loterias``).

Cobrem o spec oficial, geração, determinismo por ``seed``, dezenas fixas e
excluídas, repetição em relação ao último concurso, filtros, metadados e o
registro de modalidades.
"""

from __future__ import annotations

import random

import pandas as pd
import pytest

from src.core.base_lottery import LotteryBase
from src.core.models import FiltroConfig, LotteryConfig, ValidacaoError
from src.loterias import (
    LOTERIAS,
    DiaDeSorte,
    DuplaSena,
    Lotofacil,
    Lotomania,
    MegaSena,
    Quina,
    SuperSete,
    Timemania,
    criar,
    get_loteria,
    listar_loterias,
)

# key -> (universo, sorteadas, aposta_min, aposta_max, colunas, tipo)
TABELA = {
    "mega-sena": (60, 6, 6, 20, 10, "conjunto"),
    "lotofacil": (25, 15, 15, 20, 5, "conjunto"),
    "quina": (80, 5, 5, 15, 10, "conjunto"),
    "lotomania": (100, 20, 50, 50, 10, "conjunto"),
    "timemania": (80, 10, 10, 10, 10, "conjunto"),
    "dupla-sena": (50, 6, 6, 15, 10, "conjunto"),
    "dia-de-sorte": (31, 7, 7, 15, 10, "conjunto"),
    "super-sete": (10, 7, 7, 7, 7, "posicional"),
}

ORDEM = [
    "mega-sena",
    "lotofacil",
    "quina",
    "lotomania",
    "timemania",
    "dupla-sena",
    "dia-de-sorte",
    "super-sete",
]

CLASSES = {
    "mega-sena": MegaSena,
    "lotofacil": Lotofacil,
    "quina": Quina,
    "lotomania": Lotomania,
    "timemania": Timemania,
    "dupla-sena": DuplaSena,
    "dia-de-sorte": DiaDeSorte,
    "super-sete": SuperSete,
}


def _config(**kwargs) -> LotteryConfig:
    base = {"seed": 1234, "qtd_jogos": 1}
    base.update(kwargs)
    return LotteryConfig(**base)


def _historico(key: str) -> pd.DataFrame:
    """5 concursos sintéticos; o último tem 3 dezenas para tornar viável
    exigir exatamente 2 repetições em todas as modalidades."""
    spec = get_loteria(key).spec
    rng = random.Random(2026)
    linhas = []
    for concurso in range(1, 5):
        dezenas = rng.sample(list(spec.dezenas_validas), spec.qtd_padrao)
        linhas.append({"concurso": concurso, "dezenas": sorted(dezenas)})
    linhas.append({"concurso": 5, "dezenas": [1, 2, 3]})
    return pd.DataFrame(linhas, columns=["concurso", "dezenas"])


# ---------------------------------------------------------------------------
# catálogo / specs
# ---------------------------------------------------------------------------
def test_registry_tem_as_oito_modalidades():
    catalogo = listar_loterias()
    assert len(catalogo) == 8
    assert [item["key"] for item in catalogo] == ORDEM
    assert len(LOTERIAS) == 8
    assert set(LOTERIAS) == set(TABELA)
    for item in catalogo:
        assert set(item) == {
            "key",
            "nome",
            "universo",
            "sorteadas",
            "aposta_min",
            "aposta_max",
        }


@pytest.mark.parametrize("key", ORDEM)
def test_spec_bate_com_a_tabela(key):
    universo, sorteadas, aposta_min, aposta_max, colunas, tipo = TABELA[key]
    classe = get_loteria(key)
    spec = classe.spec

    assert isinstance(classe, type) and issubclass(classe, LotteryBase)
    assert spec.key == key
    assert spec.universo == universo
    assert spec.sorteadas == sorteadas
    assert spec.aposta_min == aposta_min
    assert spec.aposta_max == aposta_max
    assert spec.colunas == colunas
    assert spec.tipo == tipo
    assert spec.qtd_padrao == aposta_min
    assert spec.inicio == (0 if tipo == "posicional" else 1)


@pytest.mark.parametrize("entrada", ["Mega Sena", "mega sena", "MEGASENA", "Mega-Sena"])
def test_get_loteria_normaliza(entrada):
    assert get_loteria(entrada) is MegaSena


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        ("lotofácil", "lotofacil"),
        ("Lotofacil", "lotofacil"),
        ("Dupla Sena", "dupla-sena"),
        ("duplasena", "dupla-sena"),
        ("Dia-de-Sorte", "dia-de-sorte"),
        ("SUPER SETE", "super-sete"),
        ("super_sete", "super-sete"),
        ("Quiná", "quina"),
    ],
)
def test_get_loteria_aceita_variacoes(entrada, esperada):
    assert get_loteria(entrada).spec.key == esperada


def test_get_loteria_desconhecida_levanta_keyerror():
    with pytest.raises(KeyError) as excinfo:
        get_loteria("inexistente")
    mensagem = str(excinfo.value)
    assert "mega-sena" in mensagem
    assert "super-sete" in mensagem


def test_criar_devolve_instancia():
    loteria = criar("Mega-Sena")
    assert isinstance(loteria, MegaSena)
    assert loteria.spec.key == "mega-sena"


# ---------------------------------------------------------------------------
# geração básica
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", ORDEM)
def test_gera_20_jogos_validos(key):
    spec = get_loteria(key).spec
    loteria = criar(key, _config(qtd_jogos=20, seed=4242))
    jogos = loteria.gerar()

    assert len(jogos) == 20
    assert len({tuple(jogo) for jogo in jogos}) == 20
    inicio, fim = loteria.intervalo()
    for jogo in jogos:
        loteria.validar(jogo)  # não levanta
        assert len(jogo) == spec.qtd_padrao
        assert all(inicio <= int(d) <= fim for d in jogo)
        if spec.tipo == "conjunto":
            assert len(set(jogo)) == len(jogo)
            assert jogo == sorted(jogo)


@pytest.mark.parametrize("key", ORDEM)
def test_determinismo_com_seed(key):
    cfg_a = _config(qtd_jogos=8, seed=777)
    cfg_b = _config(qtd_jogos=8, seed=777)
    assert criar(key, cfg_a).gerar() == criar(key, cfg_b).gerar()


@pytest.mark.parametrize("key", ORDEM)
def test_dezenas_fixas_e_excluidas(key):
    spec = get_loteria(key).spec
    if spec.tipo == "posicional":
        fixas = [1, 2]
        excluidas = [9]
    else:
        fixas = [1, 2, 3]
        excluidas = [spec.universo - 1, spec.universo]

    cfg = _config(
        qtd_jogos=50,
        seed=99,
        dezenas_fixas=fixas,
        dezenas_excluidas=excluidas,
    )
    jogos = criar(key, cfg).gerar()

    assert len(jogos) == 50
    for jogo in jogos:
        assert set(fixas) <= set(jogo)
        assert not (set(jogo) & set(excluidas))


@pytest.mark.parametrize("key", ORDEM)
def test_repetidas_concurso_anterior_exatas(key):
    historico = _historico(key)
    cfg = _config(
        qtd_jogos=10,
        seed=31,
        repetidas_concurso_anterior=2,
        max_tentativas=100_000,
    )
    jogos = criar(key, cfg, historico=historico).gerar()

    assert len(jogos) == 10
    ultimo = {1, 2, 3}
    for jogo in jogos:
        assert len(set(jogo) & ultimo) == 2


@pytest.mark.parametrize("key", ORDEM)
def test_filtro_pares_amplo_aceita(key):
    spec = get_loteria(key).spec
    cfg = _config(
        qtd_jogos=5,
        seed=17,
        filtros=FiltroConfig(pares=(0, spec.universo)),
    )
    loteria = criar(key, cfg)
    jogos = loteria.gerar()
    assert len(jogos) == 5
    for jogo in jogos:
        assert loteria.atende_filtros(jogo)


@pytest.mark.parametrize("key", ORDEM)
def test_filtro_impossivel_levanta_runtimeerror(key):
    _, soma_maxima = get_loteria(key).faixas_soma()
    cfg = _config(
        qtd_jogos=1,
        seed=5,
        max_tentativas=300,
        filtros=FiltroConfig(soma=(soma_maxima + 1, soma_maxima + 2)),
    )
    loteria = criar(key, cfg)
    with pytest.raises(RuntimeError):
        loteria.gerar()


# ---------------------------------------------------------------------------
# metadados
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", ORDEM)
def test_info_e_faixas_soma_coerentes(key):
    spec = get_loteria(key).spec
    classe = get_loteria(key)
    info = classe.info()
    minima, maxima = classe.faixas_soma()

    assert info["key"] == key
    assert info["qtd_padrao"] == spec.qtd_padrao
    assert info["faixas_soma"] == (minima, maxima)
    assert isinstance(info["descricao"], str) and info["descricao"].strip()

    assert 0 <= minima <= maxima
    assert maxima > 0
    assert minima < maxima
    if spec.tipo == "conjunto":
        # soma do menor jogo possível: 1 + 2 + ... + qtd
        assert minima == sum(range(spec.inicio, spec.inicio + spec.qtd_padrao))
        assert maxima == sum(
            range(spec.universo - spec.qtd_padrao + 1, spec.universo + 1)
        )
    else:
        assert maxima == 7 * 9


# ---------------------------------------------------------------------------
# regras específicas
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", ["timemania", "lotomania"])
def test_quantidade_fixa_rejeita_outros_valores(key):
    spec = get_loteria(key).spec
    assert spec.aposta_min == spec.aposta_max
    with pytest.raises(ValidacaoError):
        criar(key, _config(dezenas_por_jogo=spec.aposta_min + 1))
    # o valor permitido funciona
    assert len(criar(key, _config(qtd_jogos=2)).gerar()) == 2


def test_super_sete_fixas_por_coluna():
    fixas = [0, 1, 2, 3, 4, 5, 6]
    cfg = _config(
        qtd_jogos=1,
        seed=3,
        dezenas_fixas=fixas,
        dezenas_excluidas=[9],
    )
    jogo = criar("super-sete", cfg).gerar()[0]
    assert jogo == fixas

    # dígitos podem repetir entre colunas
    repetidas = [1, 1, 2, 2, 3, 3, 4]
    jogo = criar(
        "super-sete",
        _config(qtd_jogos=1, seed=4, dezenas_fixas=repetidas),
    ).gerar()[0]
    assert jogo == repetidas


@pytest.mark.parametrize(
    "fixas",
    [[10, 1, 2, 3, 4, 5, 6], [0, 1, 2, 3, 4, 5, -1], [1, 2, "x"]],
)
def test_super_sete_fixas_invalidas_levantam_validacao(fixas):
    with pytest.raises((ValidacaoError, ValueError)):
        criar("super-sete", _config(dezenas_fixas=fixas))


def test_super_sete_quantidade_dezenas_invalida():
    with pytest.raises(ValidacaoError):
        criar("super-sete", _config(dezenas_por_jogo=8))


def test_super_sete_ignora_filtros_estruturais():
    cfg = _config(
        qtd_jogos=5,
        seed=88,
        filtros=FiltroConfig(
            moldura=(99, 99),
            miolo=(99, 99),
            quadrante_min=99,
            quadrante_max=99,
        ),
    )
    jogos = criar("super-sete", cfg).gerar()
    assert len(jogos) == 5
    for jogo in jogos:
        assert len(jogo) == 7
        assert all(0 <= d <= 9 for d in jogo)


def test_super_sete_dezenas_excluidas_ausentes():
    cfg = _config(qtd_jogos=20, seed=6, dezenas_excluidas=[0, 9])
    for jogo in criar("super-sete", cfg).gerar():
        assert 0 not in jogo and 9 not in jogo


def test_super_sete_permite_digitos_repetidos_entre_colunas():
    jogo = criar("super-sete", _config(seed=1)).gerar()[0]
    assert len(jogo) == 7
    # a validação oficial aceita repetição entre colunas
    SuperSete().validar([0, 0, 0, 0, 0, 0, 0])
