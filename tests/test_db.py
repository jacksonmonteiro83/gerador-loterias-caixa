"""Testes da camada de persistência SQLite."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from src.utils import db


@pytest.fixture
def caminho(tmp_path):
    return tmp_path / "loterias.db"


def _registro(concurso: int, dezenas=None, **extra) -> dict:
    registro = {
        "loteria": "mega-sena",
        "concurso": concurso,
        "data": "2024-01-01",
        "dezenas": dezenas if dezenas is not None else [1, 2, 3, 4, 5, 6],
        "premiacoes": None,
        "acumulado": None,
    }
    registro.update(extra)
    return registro


def test_default_db_aponta_para_raiz_do_repo():
    assert db.DEFAULT_DB.is_absolute()
    assert db.DEFAULT_DB.parts[-2:] == ("data", "loterias.db")


def test_conectar_cria_diretorio_e_configura_sqlite(tmp_path):
    destino = tmp_path / "sub" / "dir" / "loterias.db"
    con = db.conectar(destino)
    try:
        assert destino.exists()
        assert con.row_factory is sqlite3.Row
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        row = con.execute("SELECT 1 AS valor").fetchone()
        assert row["valor"] == 1
    finally:
        con.close()


def test_init_db_idempotente(caminho):
    db.init_db(caminho)
    db.init_db(caminho)

    con = sqlite3.connect(caminho)
    try:
        tabelas = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indices = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    finally:
        con.close()

    assert {"concursos", "meta"} <= tabelas
    assert "idx_concursos_loteria_concurso" in indices


def test_upsert_conta_ultimo_e_atualiza_meta(caminho):
    db.init_db(caminho)

    assert db.contar_concursos("mega-sena", caminho) == 0
    assert db.ultimo_concurso("mega-sena", caminho) is None

    gravados = db.upsert_concursos(
        [_registro(2), _registro(1, data="07/10/2023")], caminho
    )
    assert gravados == 2
    assert db.contar_concursos("mega-sena", caminho) == 2
    assert db.ultimo_concurso("mega-sena", caminho) == 2

    df = db.carregar_df("mega-sena", caminho)
    assert df["concurso"].tolist() == [1, 2]
    assert df["data"].tolist() == ["2023-10-07", "2024-01-01"]

    con = sqlite3.connect(caminho)
    try:
        linha = con.execute(
            "SELECT ultimo_concurso, atualizado_em FROM meta WHERE loteria = ?",
            ("mega-sena",),
        ).fetchone()
    finally:
        con.close()
    assert linha is not None
    assert linha[0] == 2
    momento = datetime.fromisoformat(linha[1])
    assert momento.utcoffset() is not None
    assert momento.utcoffset().total_seconds() == 0


def test_upsert_atualiza_registro_existente(caminho):
    db.init_db(caminho)
    db.upsert_concursos([_registro(1)], caminho)

    gravados = db.upsert_concursos(
        [
            _registro(
                1,
                dezenas=["15", "10", "11", "12", "13", "14"],
                acumulado="1.234,56",
                premiacoes=[{"faixa": 1, "premio": 1000.0}],
            )
        ],
        caminho,
    )
    assert gravados == 1
    assert db.contar_concursos("mega-sena", caminho) == 1

    df = db.carregar_df("mega-sena", caminho)
    assert df.loc[0, "dezenas"] == [10, 11, 12, 13, 14, 15]
    assert df.loc[0, "acumulado"] == pytest.approx(1234.56)
    assert df.loc[0, "premiacoes"] == [{"faixa": 1, "premio": 1000.0}]


@pytest.mark.parametrize(
    "registro",
    [
        {"concurso": 1, "dezenas": [1, 2]},
        {"loteria": "mega-sena", "dezenas": [1, 2]},
        {"loteria": "mega-sena", "concurso": 1},
        {"loteria": "mega-sena", "concurso": 1, "dezenas": []},
        {"loteria": "mega-sena", "concurso": 1, "dezenas": [1, "x"]},
        {"loteria": "mega-sena", "concurso": 1, "dezenas": [1, 1, 2]},
        {"loteria": "mega-sena", "concurso": 0, "dezenas": [1, 2]},
    ],
)
def test_upsert_valida_registros(caminho, registro):
    db.init_db(caminho)
    with pytest.raises(ValueError):
        db.upsert_concursos([registro], caminho)


def test_upsert_mensagem_de_campo_obrigatorio_em_portugues(caminho):
    with pytest.raises(ValueError, match="obrigatório"):
        db.upsert_concursos([{"loteria": "mega-sena", "concurso": 1}], caminho)


def test_carregar_df_ordem_tipos_e_limite(caminho):
    db.init_db(caminho)
    db.upsert_concursos(
        [
            _registro(3, dezenas=[30, 31, 32, 33, 34, 35], acumulado=3.0),
            _registro(1, dezenas=[10, 11, 12, 13, 14, 15], acumulado=None),
            _registro(2, dezenas=[20, 21, 22, 23, 24, 25], acumulado=None),
        ],
        caminho,
    )

    df = db.carregar_df("mega-sena", caminho)
    assert list(df.columns) == [
        "concurso",
        "data",
        "dezenas",
        "acumulado",
        "premiacoes",
    ]
    assert df["concurso"].tolist() == [1, 2, 3]
    assert str(df["concurso"].dtype) == "int64"
    assert str(df["acumulado"].dtype) == "float64"
    assert str(df["dezenas"].dtype) == "object"
    assert all(isinstance(item, list) for item in df["dezenas"])
    assert all(
        all(isinstance(dezena, int) for dezena in item) for item in df["dezenas"]
    )
    assert df.loc[0, "data"] == "2024-01-01"
    assert df.loc[2, "acumulado"] == pytest.approx(3.0)

    ultimos = db.carregar_df("mega-sena", caminho, limite=2)
    assert ultimos["concurso"].tolist() == [2, 3]

    nenhum = db.carregar_df("mega-sena", caminho, limite=0)
    assert nenhum.empty


def test_carregar_df_vazio_tem_colunas_e_dtypes(caminho):
    db.init_db(caminho)
    df = db.carregar_df("quina", caminho)

    assert df.empty
    assert list(df.columns) == [
        "concurso",
        "data",
        "dezenas",
        "acumulado",
        "premiacoes",
    ]
    assert str(df["concurso"].dtype) == "int64"
    assert str(df["acumulado"].dtype) == "float64"
    assert str(df["dezenas"].dtype) == "object"
    assert str(df["premiacoes"].dtype) == "object"
    assert db.ultimo_concurso("quina", caminho) is None
    assert db.contar_concursos("quina", caminho) == 0


def test_super_sete_preserva_ordem_posicional(caminho):
    db.init_db(caminho)
    dezenas = [5, 1, 9, 0, 3, 2, 7]
    db.upsert_concursos(
        [
            {
                "loteria": "super-sete",
                "concurso": 1,
                "data": None,
                "dezenas": dezenas,
                "premiacoes": None,
                "acumulado": None,
            }
        ],
        caminho,
    )

    df = db.carregar_df("super-sete", caminho)
    assert df.loc[0, "dezenas"] == dezenas
    assert df.loc[0, "data"] is None


def test_api_funciona_sem_init_explicito(caminho):
    assert db.contar_concursos("quina", caminho) == 0
    assert db.ultimo_concurso("quina", caminho) is None
    assert db.carregar_df("quina", caminho).empty

    db.upsert_concursos(
        [
            {
                "loteria": "quina",
                "concurso": 1,
                "data": "2024-02-29",
                "dezenas": [80, 1, 2, 3, 4],
                "premiacoes": None,
                "acumulado": None,
            }
        ],
        caminho,
    )
    assert db.contar_concursos("quina", caminho) == 1
    assert db.carregar_df("quina", caminho).loc[0, "dezenas"] == [1, 2, 3, 4, 80]
