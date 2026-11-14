"""Validação de integridade do histórico antes de publicar.

Separa o que **quebra** a publicação (erros: dado estruturalmente impossível)
do que apenas **informa** (avisos: histórico incompleto, backfill pendente).
"""

from __future__ import annotations

from typing import Any, Sequence

from ..core.models import LotterySpec

__all__ = ["validar_historico"]


def validar_historico(
    spec: LotterySpec, registros: Sequence[dict], sorteadas: int | None = None
) -> dict[str, Any]:
    """Confere continuidade, duplicatas, tamanho e faixa das dezenas.

    ``sorteadas`` é o tamanho real do sorteio quando difere de
    ``spec.sorteadas`` (ex.: Timemania, aposta de 10 e sorteio de 7).
    ``registros`` são dicionários ``{"n", "d", "z"}``. Devolve
    ``{"erros", "avisos", "n", "primeiro", "ultimo", "faltantes", "completo"}``.
    """
    erros: list[str] = []
    avisos: list[str] = []
    numeros = [int(r["n"]) for r in registros]

    if len(numeros) != len(set(numeros)):
        duplicados = sorted({n for n in numeros if numeros.count(n) > 1})
        erros.append(f"concursos duplicados: {duplicados[:5]}")

    posicional = spec.tipo == "posicional"
    esperado = int(sorteadas) if sorteadas else spec.sorteadas
    inferior = spec.inicio
    superior = spec.inicio + spec.universo - 1
    for r in registros:
        z = [int(v) for v in r["z"]]
        n = r["n"]
        if len(z) != esperado:
            erros.append(f"concurso {n}: {len(z)} dezenas (esperado {esperado})")
        if any(v < inferior or v > superior for v in z):
            erros.append(f"concurso {n}: dezena fora de {inferior}..{superior}")
        if not posicional and len(set(z)) != len(z):
            erros.append(f"concurso {n}: dezenas repetidas")
        if len(erros) >= 20:
            erros.append("... (demais erros omitidos)")
            break

    datas = [r.get("d") for r in sorted(registros, key=lambda r: r["n"])]
    validas = [d for d in datas if d]
    if any(a > b for a, b in zip(validas, validas[1:])):
        avisos.append("datas fora de ordem em relação ao número do concurso")

    primeiro = min(numeros) if numeros else None
    ultimo = max(numeros) if numeros else None
    faltantes = 0
    if numeros:
        # conta desde o concurso 1: o histórico só é "completo" se começar nele
        faltantes = ultimo - len(set(numeros))
        if primeiro and primeiro > 1:
            avisos.append(
                f"histórico começa no concurso {primeiro}: faltam {faltantes} "
                "concursos (rode o backfill: --atualizar --completo)"
            )
        elif faltantes:
            avisos.append(f"{faltantes} concurso(s) ausente(s) no meio do histórico")

    return {
        "erros": erros,
        "avisos": avisos,
        "n": len(set(numeros)),
        "primeiro": primeiro,
        "ultimo": ultimo,
        "faltantes": faltantes,
        "completo": bool(numeros) and primeiro == 1 and faltantes == 0,
    }
