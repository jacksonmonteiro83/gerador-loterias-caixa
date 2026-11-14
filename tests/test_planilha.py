"""Importação da planilha de resultados (xlsx/csv) da Caixa."""

from __future__ import annotations

import pytest
from openpyxl import Workbook

from src.etl import historico
from src.etl.planilha import importar, ler_planilha


def _xlsx(caminho, linhas, preambulo=1):
    wb = Workbook()
    ws = wb.active
    for _ in range(preambulo):
        ws.append(["Resultados Mega-Sena"])
    ws.append(["Concurso", "Data do Sorteio", "Bola1", "Bola2", "Bola3", "Bola4", "Bola5", "Bola6",
               "Ganhadores 6 acertos", "Cidade / UF", "Ganhadores 5 acertos"])
    for linha in linhas:
        ws.append(linha)
    wb.save(caminho)


def test_le_xlsx_com_preambulo_linhas_de_rateio_e_ordem_embaralhada(tmp_path):
    arq = tmp_path / "m.xlsx"
    _xlsx(arq, [
        [2, "02/01/2026", 9, 3, 1, 40, 22, 60, 0, "", 50],
        [1, "01/01/2026", 5, 4, 3, 2, 1, 6, 2, "SP", 10],
        [1, None, None, None, None, None, None, None, None, "RJ", None],  # 2º ganhador do mesmo concurso
        [None, "Total", None, None, None, None, None, None, None, None, None],
    ])
    r = ler_planilha(arq, "mega-sena")
    assert [x["n"] for x in r] == [1, 2]
    assert r[0] == {"n": 1, "d": "2026-01-01", "z": [1, 2, 3, 4, 5, 6], "g": 2}
    assert r[1]["z"] == [1, 3, 9, 22, 40, 60] and r[1]["g"] == 0


def test_csv_e_erro_claro_quando_faltam_colunas(tmp_path):
    arq = tmp_path / "m.csv"
    arq.write_text("Concurso;Data;Bola1;Bola2\n1;01/01/2026;1;2\n", encoding="latin-1")
    with pytest.raises(ValueError, match="esperava 6 colunas"):
        ler_planilha(arq, "mega-sena")
    sem = tmp_path / "x.csv"
    sem.write_text("a;b\n1;2\n")
    with pytest.raises(ValueError, match="Concurso"):
        ler_planilha(sem, "mega-sena")


def test_importar_mescla_e_preserva_ganhadores_e_valida(tmp_path):
    historico.gravar("mega-sena", [{"n": 3, "d": "2026-01-03", "z": [1, 2, 3, 4, 5, 7], "g": 5}], tmp_path)
    arq = tmp_path / "m.xlsx"
    _xlsx(arq, [
        [1, "01/01/2026", 1, 2, 3, 4, 5, 6, 0, "", 1],
        [2, "02/01/2026", 1, 2, 3, 4, 5, 8, 1, "", 1],
        [3, "03/01/2026", 1, 2, 3, 4, 5, 7, None, "", 1],
    ])
    r = importar(arq, "mega-sena", tmp_path)
    assert r["total"] == 3 and r["completo"] and r["novos_ou_alterados"] == 2
    final = {x["n"]: x for x in historico.ler("mega-sena", tmp_path)}
    assert final[3]["g"] == 5  # a planilha não trouxe g: mantém o conhecido

    ruim = tmp_path / "r.xlsx"
    _xlsx(ruim, [[1, "01/01/2026", 1, 2, 3, 4, 5, 99, 0, "", 0]])
    with pytest.raises(ValueError, match="fora de"):
        importar(ruim, "mega-sena", tmp_path)


def test_lotomania_zero_vira_100(tmp_path):
    arq = tmp_path / "l.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["Concurso", "Data Sorteio"] + [f"Bola{i}" for i in range(1, 21)] + ["Ganhadores 20 acertos"])
    ws.append([1, "01/01/2026"] + [0] + list(range(1, 20)) + [0])
    wb.save(arq)
    assert ler_planilha(arq, "lotomania")[0]["z"][-1] == 100
