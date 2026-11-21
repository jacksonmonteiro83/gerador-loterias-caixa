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
        modo = i % 8
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
        else:            # apenas quadrantes 1 e 2 (metade superior) etc.
            pool = [n for n in range(1, 81) if (n - 1) // 10 < 4]
            jogo = rng.sample(pool, 10)
        casos.append({"jogo": jogo, "anterior": anterior})
    return casos


def _rodar_js(casos):
    r = subprocess.run(
        [NODE, str(RAIZ / "tests" / "js" / "paridade_timemania.cjs")],
        input=json.dumps({"casos": casos}), capture_output=True, text=True, cwd=RAIZ, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


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
    assert aprovados > 500
    assert com_score - aprovados > 200
    assert len(casos) - com_score > 500


def test_dezenas_fora_de_ordem_e_tamanho_invalido():
    py = TimemaniaScoringSystem()
    jogo = [78, 5, 52, 12, 66, 19, 41, 60, 33, 71]
    anterior = [3, 4, 6, 22, 51, 71, 79]
    assert _rodar_js([{"jogo": jogo, "anterior": anterior}])[0] == py.validar_jogo_10(jogo, anterior)
    script = (
        "const T=require('./dashboard/timemania.js');"
        "try{new T().validarJogo10([1,2,3],[1]);process.exit(1)}catch(e){process.exit(e instanceof RangeError?0:2)}"
    )
    assert subprocess.run([NODE, "-e", script], cwd=RAIZ).returncode == 0
