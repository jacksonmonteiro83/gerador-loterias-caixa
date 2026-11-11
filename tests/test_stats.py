"""Testes das estatísticas de histórico."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import stats  # noqa: E402

HISTORICO = [
    {"concurso": 3, "dezenas": [1, 2, 3]},
    {"concurso": 1, "dezenas": [2, 3, 4]},
    {"concurso": 2, "dezenas": [3, 4, 5]},
]


def test_normalizar_none_vira_frame_vazio():
    df = stats.normalizar(None)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["concurso", "dezenas"]
    assert df.empty
    assert df["concurso"].dtype == "int64"


def test_normalizar_lista_ordena_e_converte():
    df = stats.normalizar(HISTORICO)
    assert list(df.columns) == ["concurso", "dezenas"]
    assert df["concurso"].tolist() == [1, 2, 3]
    assert df["dezenas"].tolist() == [[2, 3, 4], [3, 4, 5], [1, 2, 3]]
    assert all(isinstance(d, int) for d in df["dezenas"].iloc[0])


def test_normalizar_dataframe_e_json():
    original = pd.DataFrame(
        {
            "concurso": [2, 1],
            "dezenas": ["[5, 3, 4]", [14, 12, 13]],
        }
    )
    df = stats.normalizar(original)
    assert df["concurso"].tolist() == [1, 2]
    assert df["dezenas"].tolist() == [[12, 13, 14], [3, 4, 5]]


def test_frequencia_e_atraso():
    df = stats.normalizar(HISTORICO)
    assert stats.frequencia(df, 5) == {1: 1, 2: 2, 3: 3, 4: 2, 5: 1}
    assert stats.frequencia(df, 5, inicio=0)[0] == 0
    assert stats.atraso(df, 5) == {1: 0, 2: 0, 3: 0, 4: 1, 5: 1}
    assert stats.atraso(df, 6)[6] == 3


def test_funcoes_toleram_historico_vazio():
    vazio = stats.normalizar(None)
    assert stats.frequencia(vazio, 3) == {1: 0, 2: 0, 3: 0}
    assert stats.frequencia(None, 3) == {1: 0, 2: 0, 3: 0}
    assert stats.atraso(vazio, 3) == {1: 0, 2: 0, 3: 0}
    assert stats.dezenas_ultimo_concurso(vazio) == set()
    assert stats.taxa_repeticao(vazio) == 0.0
    assert stats.contaminacao([1, 2, 3], vazio) == 0
    assert stats.filtrar_por_contaminacao([1, 2, 3], vazio, 0) is True
    resumo = stats.resumo(vazio, 3)
    assert resumo["concursos"] == 0
    assert resumo["ultimo_concurso"] is None


def test_dezenas_ultimo_concurso():
    df = stats.normalizar(HISTORICO)
    assert stats.dezenas_ultimo_concurso(df) == {1, 2, 3}


def test_taxa_repeticao():
    df = stats.normalizar(HISTORICO)
    # {2,3,4}->{3,4,5} = 2 repetidas; {3,4,5}->{1,2,3} = 1
    assert stats.taxa_repeticao(df) == pytest.approx(1.5)
    um_concurso = stats.normalizar([{"concurso": 1, "dezenas": [1, 2, 3]}])
    assert stats.taxa_repeticao(um_concurso) == 0.0


def test_contaminacao_e_filtro():
    df = stats.normalizar(HISTORICO)
    assert stats.contaminacao([1, 2, 3], df) == 3
    assert stats.contaminacao([2, 3, 9], df) == 2
    assert stats.contaminacao([9, 10], df) == 0
    assert stats.filtrar_por_contaminacao([2, 3, 9], df, 2) is True
    assert stats.filtrar_por_contaminacao([2, 3, 9], df, 1) is False
    assert stats.filtrar_por_contaminacao([2, 3, 9], df, None) is True


def test_resumo_chaves():
    df = stats.normalizar(HISTORICO)
    resumo = stats.resumo(df, 5)
    assert set(resumo) == {
        "concursos",
        "ultimo_concurso",
        "universo",
        "frequencia",
        "atraso",
        "taxa_repeticao",
        "ultimo",
        "mais_frequentes",
        "menos_frequentes",
    }
    assert resumo["concursos"] == 3
    assert resumo["ultimo_concurso"] == 3
    assert resumo["universo"] == 5
    assert resumo["ultimo"] == [1, 2, 3]
    assert resumo["mais_frequentes"][0] == (3, 3)
    assert isinstance(resumo["taxa_repeticao"], float)


def test_normalizar_tipo_invalido():
    with pytest.raises(TypeError):
        stats.normalizar(42)
