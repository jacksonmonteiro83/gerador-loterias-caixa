"""Dupla Sena.

Regra oficial: o apostador escolhe de 6 a 15 dezenas distintas do intervalo
1..50. A Caixa realiza dois sorteios de 6 dezenas por concurso. O jogo padrão
tem 6 dezenas.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.models import LotterySpec
from src.loterias import LoteriaConjunto

logger = logging.getLogger(__name__)


class DuplaSena(LoteriaConjunto):
    """Gerador de jogos da Dupla Sena (1..50, 6 dezenas sorteadas)."""

    spec: ClassVar[LotterySpec] = LotterySpec(
        key="dupla-sena",
        nome="Dupla Sena",
        universo=50,
        sorteadas=6,
        aposta_min=6,
        aposta_max=15,
        colunas=10,
        tipo="conjunto",
        inicio=1,
    )

    DESCRICAO: ClassVar[str] = (
        "Escolha de 6 a 15 dezenas de 1 a 50; dois sorteios de 6 dezenas por concurso."
    )
