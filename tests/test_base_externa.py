"""Sincronização com a base do repositório loterias-dashboard."""

from __future__ import annotations

import json

import pytest

from src.etl import historico
from src.etl.base_externa import converter, sincronizar


def _item(n, dezenas, data="2026-01-01", g=0):
    return {"numero": n, "data": data, "dezenas": [str(d).zfill(2) for d in dezenas],
            "faixas": [{"faixa": 1, "ganhadores": g, "premio": 0.0}]}


def _origem(tmp_path, slug, itens):
    (tmp_path / "raw").mkdir(exist_ok=True)
    (tmp_path / "raw" / f"{slug}.json").write_text(
        json.dumps({str(i["numero"]): i for i in itens}), encoding="utf-8")
    return tmp_path / "raw"


def test_converte_ordena_e_extrai_ganhadores():
    r = converter("mega-sena", {"2": _item(2, [9, 3, 1, 40, 22, 60], g=1), "1": _item(1, [1, 2, 3, 4, 5, 6])})
    assert [x["n"] for x in r] == [1, 2]
    assert r[1] == {"n": 2, "d": "2026-01-01", "z": [1, 3, 9, 22, 40, 60], "g": 1}


def test_lotomania_zero_vira_100_e_super_sete_mantem_posicao():
    lm = converter("lotomania", {"1": _item(1, [0] + list(range(1, 20)))})
    assert 100 in lm[0]["z"] and 0 not in lm[0]["z"]
    ss = converter("super-sete", {"1": {"numero": 1, "data": "2026-01-01", "dezenas": list("2998776"), "faixas": []}})
    assert ss[0]["z"] == [2, 9, 9, 8, 7, 7, 6] and "g" not in ss[0]


def test_sincroniza_mescla_e_preserva_g_local(tmp_path):
    destino = tmp_path / "hist"
    historico.gravar("mega-sena", [{"n": 1, "d": "2026-01-01", "z": [1, 2, 3, 4, 5, 6], "g": 7}], destino)
    itens = [{"numero": 1, "data": "2026-01-01", "dezenas": ["01", "02", "03", "04", "05", "06"], "faixas": []},
             _item(2, [7, 8, 9, 10, 11, 12], "2026-01-04", g=0)]
    r = sincronizar("mega-sena", _origem(tmp_path, "megasena", itens), destino)
    assert r["total"] == 2 and r["completo"]
    h = {x["n"]: x for x in historico.ler("mega-sena", destino)}
    assert h[1]["g"] == 7 and h[2]["g"] == 0


def test_tamanho_invalido_mantem_registro_local(tmp_path):
    destino = tmp_path / "hist"
    local = {"n": 1, "d": "2026-01-01", "z": [1, 2, 3, 4, 5, 6, 7], "g": 0}
    historico.gravar("timemania", [local, {"n": 2, "d": "2026-01-03", "z": [1, 2, 3, 4, 5, 6, 8], "g": 0}], destino)
    itens = [_item(1, [1, 2, 3, 4, 5, 6, 7, 70]), _item(2, [1, 2, 3, 4, 5, 6, 8], "2026-01-03")]
    r = sincronizar("timemania", _origem(tmp_path, "timemania", itens), destino)
    assert r["mantidos_locais"] == [1]
    assert historico.ler("timemania", destino)[0]["z"] == [1, 2, 3, 4, 5, 6, 7]


def test_tamanho_invalido_sem_registro_local_falha(tmp_path):
    itens = [_item(1, [1, 2, 3, 4, 5, 6, 7, 70])]
    with pytest.raises(ValueError, match="inválida"):
        sincronizar("timemania", _origem(tmp_path, "timemania", itens), tmp_path / "h")


def test_modalidade_desconhecida():
    with pytest.raises(ValueError):
        sincronizar("loteca", "/tmp")
