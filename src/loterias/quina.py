"""Quina.

Regra oficial: o apostador escolhe de 5 a 15 dezenas distintas do intervalo
1..80. A Caixa sorteia 5 dezenas por concurso. O jogo padrão tem 5 dezenas.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.models import LotterySpec
from src.loterias import LoteriaConjunto

logger = logging.getLogger(__name__)


class Quina(LoteriaConjunto):
    """Gerador de jogos da Quina (1..80, 5 dezenas sorteadas)."""

    spec: ClassVar[LotterySpec] = LotterySpec(
        key="quina",
        nome="Quina",
        universo=80,
        sorteadas=5,
        aposta_min=5,
        aposta_max=15,
        colunas=10,
        tipo="conjunto",
        inicio=1,
    )

    DESCRICAO: ClassVar[str] = (
        "Escolha de 5 a 15 dezenas de 1 a 80; sorteio de 5 dezenas por concurso."
    )
