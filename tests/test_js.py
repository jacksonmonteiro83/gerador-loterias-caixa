"""Testes do front-end puro (``dashboard/gerador.js``) e paridade com o Python."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core import scoring
from src.loterias.registry import get_loteria

RAIZ = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node não encontrado")


def test_suite_node_do_gerador():
    r = subprocess.run(
        [NODE, "--test", str(RAIZ / "tests" / "js" / "gerador.test.cjs")],
        capture_output=True, text=True, cwd=RAIZ, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def _jogos(spec, tamanho, quantidade, semente):
    rng = random.Random(semente)
    jogos = []
    for _ in range(quantidade):
        if spec.tipo == "posicional":
            atual = [rng.randrange(spec.universo) for _ in range(tamanho)]
            anterior = [rng.randrange(spec.universo) for _ in range(tamanho)]
        else:
            base = range(spec.inicio, spec.inicio + spec.universo)
            atual = sorted(rng.sample(base, tamanho))
            anterior = sorted(rng.sample(base, spec.sorteadas))
        jogos.append({"dezenas": atual, "anterior": anterior})
    return jogos


@pytest.mark.parametrize(
    "chave,tamanho",
    [
        ("mega-sena", 6), ("mega-sena", 9), ("lotofacil", 15), ("quina", 5),
        ("lotomania", 20), ("lotomania", 50), ("dia-de-sorte", 7),
        ("dupla-sena", 6), ("super-sete", 7),
    ],
)
def test_pontuacao_js_igual_python(chave, tamanho):
    spec = get_loteria(chave).spec
    perfil = scoring.calibrar(spec, None, qtd=tamanho)
    jogos = _jogos(spec, tamanho, 300, semente=sum(map(ord, chave)) * 100 + tamanho)
    r = subprocess.run(
        [NODE, str(RAIZ / "tests" / "js" / "paridade.cjs")],
        input=json.dumps({"perfil": perfil.como_dict(), "jogos": jogos}),
        capture_output=True, text=True, cwd=RAIZ, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    saida = json.loads(r.stdout)
    for jogo, js in zip(jogos, saida):
        py = perfil.avaliar(jogo["dezenas"], jogo["anterior"])
        assert js["score"] == py["score"], (jogo, js, py["status"])
        assert js["aprovado"] == py["aprovado"], (jogo, js, py["status"])
        assert js["status"] == py["status"], (jogo, js, py["status"])
