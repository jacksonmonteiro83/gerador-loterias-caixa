"""Lotofácil.

Regra oficial: o apostador marca de 15 a 20 dezenas distintas do intervalo
1..25. A Caixa sorteia 20 dezenas e ganha quem acertar 15 ou mais. O jogo
padrão tem 15 dezenas.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.models import LotterySpec
from src.loterias import LoteriaConjunto

logger = logging.getLogger(__name__)


class Lotofacil(LoteriaConjunto):
    """Gerador de jogos da Lotofácil (1..25, 15 dezenas sorteadas)."""

    spec: ClassVar[LotterySpec] = LotterySpec(
        key="lotofacil",
        nome="Lotofácil",
        universo=25,
        sorteadas=15,
        aposta_min=15,
        aposta_max=20,
        colunas=5,
        tipo="conjunto",
        inicio=1,
    )

    DESCRICAO: ClassVar[str] = (
        "Marque de 15 a 20 dezenas de 1 a 25; sorteio de 15 dezenas por concurso."
    )
