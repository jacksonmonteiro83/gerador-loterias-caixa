"""Paridade do motor da Timemania: JavaScript (dashboard/timemania.js) == Python de referência."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.ref_timemania import TimemaniaScoringSystem

RAIZ = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node não encontrado")


def _casos(qtd: int, semente: int) -> list[dict]:
    rng = random.Random(semente)
    casos = []
    for i in range(qtd):
        anterior = sorted(rng.sample(range(1, 81), 7))
        modo = i % 10
        if modo == 0:    # uniforme
            jogo = rng.sample(range(1, 81), 10)
        elif modo == 1:  # concentrado nas dezenas baixas (barra ultimo < 60 / amplitude)
            jogo = rng.sample(range(1, 45), 10)
        elif modo == 2:  # concentrado nas dezenas altas (barra primeiro >= 22)
            jogo = rng.sample(range(30, 81), 10)
        elif modo == 3:  # sequências (consecutivos)
            ini = rng.randrange(1, 60)
            jogo = list(range(ini, ini + rng.randint(3, 6))) + rng.sample(range(1, 81), 10)
            jogo = list(dict.fromkeys(jogo))[:10]
            if len(jogo) < 10:
                jogo = rng.sample(range(1, 81), 10)
        elif modo == 4:  # repetição forçada com o anterior
            k = rng.randint(0, 4)
            resto = [n for n in range(1, 81) if n not in anterior]
            jogo = rng.sample(anterior, k) + rng.sample(resto, 10 - k)
        elif modo == 5:  # poucos decis (max_linha alto)
            decis = rng.sample(range(8), rng.randint(2, 4))
            pool = [n for n in range(1, 81) if (n - 1) // 10 in decis]
            jogo = rng.sample(pool, min(10, len(pool)))
            if len(jogo) < 10:
                jogo = rng.sample(range(1, 81), 10)
        elif modo == 6:  # soma extrema
            pool = range(1, 31) if rng.random() < 0.5 else range(55, 81)
            jogo = rng.sample(pool, 10)
        elif modo == 7:  # apenas quadrantes 1 e 2 (metade superior) etc.
            pool = [n for n in range(1, 81) if (n - 1) // 10 < 4]
            jogo = rng.sample(pool, 10)
        elif modo == 8:  # poucos finais distintos (3 ou mais dezenas com o mesmo final)
            finais = rng.sample(range(10), rng.randint(4, 7))
            pool = [n for n in range(1, 81) if n % 10 in finais]
            jogo = rng.sample(pool, 10)
        else:            # finais bem distribuídos (8+ finais distintos) para exercitar o bônus de colunas
            finais = rng.sample(range(10), rng.randint(8, 10))
            jogo = [rng.choice([n for n in range(1, 81) if n % 10 == f]) for f in finais]
            jogo = list(dict.fromkeys(jogo))
            while len(jogo) < 10:
                n = rng.randint(1, 80)
                if n not in jogo:
                    jogo.append(n)
        casos.append({"jogo": jogo, "anterior": anterior})
    return casos


def _rodar_js(casos):
    r = subprocess.run(
        [NODE, str(RAIZ / "tests" / "js" / "paridade_timemania.cjs")],
        input=json.dumps({"casos": casos}), capture_output=True, text=True, cwd=RAIZ, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _casos7(qtd: int, semente: int) -> list[dict]:
    """Sorteios/jogos de 7 dezenas: uniformes, com repetição forçada e com sequências."""
    rng = random.Random(semente)
    casos = []
    for i in range(qtd):
        anterior = sorted(rng.sample(range(1, 81), 7))
        modo = i % 4
        if modo == 0:
            jogo = rng.sample(range(1, 81), 7)
        elif modo == 1:  # repetição forçada
            k = rng.randint(0, 3)
            resto = [n for n in range(1, 81) if n not in anterior]
            jogo = rng.sample(anterior, k) + rng.sample(resto, 7 - k)
        elif modo == 2:  # sequências
            ini = rng.randrange(1, 70)
            base = list(range(ini, ini + rng.randint(2, 4)))
            resto = [n for n in range(1, 81) if n not in base]
            jogo = base + rng.sample(resto, 7 - len(base))
        else:            # espalhados em dezenas diferentes (um por linha)
            decis = rng.sample(range(8), 7)
            jogo = [d * 10 + rng.randint(1, 10) for d in decis]
        casos.append({"jogo": jogo, "anterior": anterior})
    return casos


def test_validar_jogo_10_js_igual_python():
    py = TimemaniaScoringSystem()
    casos = _casos(8000, semente=20261121)
    saida = _rodar_js(casos)
    assert len(saida) == len(casos)
    aprovados = com_score = 0
    for caso, js in zip(casos, saida):
        esperado = py.validar_jogo_10(caso["jogo"], caso["anterior"])
        assert js == esperado, (caso, js, esperado)
        aprovados += esperado["all"]
        com_score += "score" in esperado
    # a bateria precisa exercitar todos os ramos: bloqueados, reprovados por score e aprovados
    assert aprovados > 300
    assert com_score - aprovados > 150
    assert len(casos) - com_score > 500
    # o critério de finais precisa aparecer nos degraus (6, 7, 8+ finais distintos) e no bloqueio (None)
    finais = {py.validar_jogo_10(c["jogo"], c["anterior"]).get("colunas_ativas") for c in casos}
    assert {None, 7, 8, 9, 10} <= finais, finais


def test_validar_jogo_7_js_igual_python():
    py = TimemaniaScoringSystem()
    casos = _casos7(20000, semente=20261122)
    saida = _rodar_js(casos)
    ramos = set()
    for caso, js in zip(casos, saida):
        esperado = py.validar_jogo_7(caso["jogo"], caso["anterior"])
        assert js == esperado, (caso, js, esperado)
        det = esperado["status_detalhado"]
        ramos.add(det.split("(0pts: ")[1].split("(")[0].split("[")[0].rstrip(")") if "(0pts:" in det
                  else ("APROV" if esperado["all"] else "REJ_SCORE"))
    assert ramos >= {
        "REP_ANT", "EXTREMOS", "SOMA", "ELIMINADO_LINHA", "ELIMINADO_ESPALHAMENTO_TOTAL",
        "QUADRANTES", "CONSECUTIVOS", "APROV", "REJ_SCORE",
    }, ramos


def test_dezenas_fora_de_ordem_e_tamanho_invalido():
    py = TimemaniaScoringSystem()
    jogo = [78, 5, 52, 12, 66, 19, 41, 60, 33, 71]
    anterior = [3, 4, 6, 22, 51, 71, 79]
    assert _rodar_js([{"jogo": jogo, "anterior": anterior}])[0] == py.validar_jogo_10(jogo, anterior)
    j7 = [71, 5, 52, 12, 66, 19, 41]
    assert _rodar_js([{"jogo": j7, "anterior": anterior}])[0] == py.validar_jogo_7(j7, anterior)
    for metodo in ("validarJogo10", "validarJogo7"):
        script = (
            "const T=require('./dashboard/timemania.js');"
            f"try{{new T().{metodo}([1,2,3],[1]);process.exit(1)}}catch(e){{process.exit(e instanceof RangeError?0:2)}}"
        )
        assert subprocess.run([NODE, "-e", script], cwd=RAIZ).returncode == 0
