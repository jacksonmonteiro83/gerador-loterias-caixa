"""Timemania.

Regra oficial: o apostador marca exatamente 10 dezenas distintas do intervalo
1..80 — a aposta é fixa em 10 dezenas — e escolhe também um Time do Coração.
A Caixa sorteia 10 dezenas por concurso.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.models import LotteryConfig, LotterySpec, ValidacaoError
from src.loterias import LoteriaConjunto

logger = logging.getLogger(__name__)

QTD_FIXA = 10


class Timemania(LoteriaConjunto):
    """Gerador de jogos da Timemania (1..80, 10 sorteadas, aposta fixa de 10)."""

    spec: ClassVar[LotterySpec] = LotterySpec(
        key="timemania",
        nome="Timemania",
        universo=80,
        sorteadas=10,
        aposta_min=10,
        aposta_max=10,
        colunas=10,
        tipo="conjunto",
        inicio=1,
    )

    DESCRICAO: ClassVar[str] = (
        "Aposta fixa de 10 dezenas de 1 a 80; sorteio de 10 dezenas por concurso."
    )

    def __init__(self, config: LotteryConfig | None = None, historico=None) -> None:
        if config is not None and config.dezenas_por_jogo not in (None, QTD_FIXA):
            raise ValidacaoError(
                "Timemania exige exatamente "
                f"{QTD_FIXA} dezenas por jogo (recebido {config.dezenas_por_jogo})."
            )
        super().__init__(config=config, historico=historico)
