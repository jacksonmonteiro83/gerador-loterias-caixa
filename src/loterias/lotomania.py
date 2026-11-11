"""Lotomania.

Regra oficial: o apostador marca exatamente 50 dezenas distintas entre as 100
disponíveis (1..100) — a aposta é fixa em 50 dezenas. A Caixa sorteia 20
dezenas por concurso.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.models import LotteryConfig, LotterySpec, ValidacaoError
from src.loterias import LoteriaConjunto

logger = logging.getLogger(__name__)

QTD_FIXA = 50


class Lotomania(LoteriaConjunto):
    """Gerador de jogos da Lotomania (1..100, 20 sorteadas, aposta fixa de 50)."""

    spec: ClassVar[LotterySpec] = LotterySpec(
        key="lotomania",
        nome="Lotomania",
        universo=100,
        sorteadas=20,
        aposta_min=50,
        aposta_max=50,
        colunas=10,
        tipo="conjunto",
        inicio=1,
    )

    DESCRICAO: ClassVar[str] = (
        "Aposta fixa de 50 dezenas de 1 a 100; sorteio de 20 dezenas por concurso."
    )

    def __init__(self, config: LotteryConfig | None = None, historico=None) -> None:
        if config is not None and config.dezenas_por_jogo not in (None, QTD_FIXA):
            raise ValidacaoError(
                "Lotomania exige exatamente "
                f"{QTD_FIXA} dezenas por jogo (recebido {config.dezenas_por_jogo})."
            )
        super().__init__(config=config, historico=historico)
