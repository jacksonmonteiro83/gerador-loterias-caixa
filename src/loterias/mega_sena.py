"""Mega-Sena.

Regra oficial: o apostador escolhe de 6 a 20 dezenas distintas do intervalo
1..60 e concorre com todas as combinações de 6 dezenas formadas a partir
delas. A Caixa sorteia 6 dezenas por concurso. O jogo padrão (menor aposta)
tem 6 dezenas.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.models import LotterySpec
from src.loterias import LoteriaConjunto

logger = logging.getLogger(__name__)


class MegaSena(LoteriaConjunto):
    """Gerador de jogos da Mega-Sena (1..60, 6 dezenas sorteadas)."""

    spec: ClassVar[LotterySpec] = LotterySpec(
        key="mega-sena",
        nome="Mega-Sena",
        universo=60,
        sorteadas=6,
        aposta_min=6,
        aposta_max=20,
        colunas=10,
        tipo="conjunto",
        inicio=1,
    )

    DESCRICAO: ClassVar[str] = (
        "Escolha de 6 a 20 dezenas de 1 a 60; sorteio de 6 dezenas por concurso."
    )
