"""Testes de integração da CLI (``main.py``).

Rodam 100% offline: nenhuma chamada de rede e nenhum acesso ao banco padrão.
"""

from __future__ import annotations

import json

import pytest

import main as cli


def test_demo_offline_gera_todas_as_modalidades(tmp_path, capsys):
    rc = cli.main(
        ["--offline", "--jogos", "2", "--seed", "7", "--db", str(tmp_path / "x.db")]
    )
    saida = capsys.readouterr().out
    assert rc == 0
    assert "8/8 modalidades OK" in saida
    assert "16 jogos validados" in saida
    assert "PROBLEMAS" not in saida


def test_demo_com_filtros(tmp_path, capsys):
    rc = cli.main(
        [
            "--offline",
            "--loteria", "mega-sena",
            "--jogos", "4",
            "--seed", "1",
            "--pares", "3-3",
            "--soma", "150-250",
            "--db", str(tmp_path / "x.db"),
        ]
    )
    saida = capsys.readouterr().out
    assert rc == 0
    assert "4/4 jogos válidos" in saida
    # toda linha de jogo deve ter exatamente 3 pares
    for linha in saida.splitlines():
        if "pares=" in linha:
            assert "pares= 3" in linha


def test_demo_restricoes_de_historico(tmp_path, capsys):
    rc = cli.main(
        [
            "--offline",
            "--loteria", "quina",
            "--jogos", "3",
            "--fixas", "1,2",
            "--excluidas", "79,80",
            "--repetidas", "1",
            "--db", str(tmp_path / "x.db"),
        ]
    )
    saida = capsys.readouterr().out
    assert rc == 0
    jogos = [l for l in saida.splitlines() if "rep=" in l and "restrições" not in l]
    assert len(jogos) == 3
    for linha in jogos:
        assert "01 02" in linha
        assert "79" not in linha and "80" not in linha
        assert "rep= 1" in linha


def test_json_emite_apenas_json(tmp_path, capsys):
    rc = cli.main(
        ["--offline", "--loteria", "lotofacil", "--jogos", "2",
         "--db", str(tmp_path / "x.db"), "--json"]
    )
    dados = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert dados["falhas"] == []
    assert set(dados["modalidades"]) == {"lotofacil"}
    assert len(dados["modalidades"]["lotofacil"]["jogos"]) == 2


def test_regras_lista_as_oito_modalidades(capsys):
    assert cli.main(["--regras"]) == 0
    saida = capsys.readouterr().out
    for nome in ("Mega-Sena", "Lotofácil", "Quina", "Lotomania",
                 "Timemania", "Dupla Sena", "Dia de Sorte", "Super Sete"):
        assert nome in saida


def test_loteria_inexistente_retorna_erro(capsys):
    assert cli.main(["--offline", "--loteria", "inexistente"]) == 2
    assert "erro" in capsys.readouterr().out.lower()


def test_jogos_zero_retorna_codigo_de_erro(capsys):
    assert cli.main(["--offline", "--jogos", "0"]) == 2
    assert "--jogos" in capsys.readouterr().out


def test_faixa_invertida_falha_no_argparse():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--offline", "--pares", "5-3"])
    assert exc.value.code != 0
