"""Dia de Sorte.

Regra oficial: o apostador escolhe de 7 a 15 dezenas distintas do intervalo
1..31 (uma para cada dia do mês) e também um Mês da Sorte. A Caixa sorteia 7
dezenas por concurso. O jogo padrão tem 7 dezenas.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.models import LotterySpec
from src.loterias import LoteriaConjunto

logger = logging.getLogger(__name__)


class DiaDeSorte(LoteriaConjunto):
    """Gerador de jogos do Dia de Sorte (1..31, 7 dezenas sorteadas)."""

    spec: ClassVar[LotterySpec] = LotterySpec(
        key="dia-de-sorte",
        nome="Dia de Sorte",
        universo=31,
        sorteadas=7,
        aposta_min=7,
        aposta_max=15,
        colunas=10,
        tipo="conjunto",
        inicio=1,
    )

    DESCRICAO: ClassVar[str] = (
        "Escolha de 7 a 15 dezenas de 1 a 31; sorteio de 7 dezenas por concurso."
    )
