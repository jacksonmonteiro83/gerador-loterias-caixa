"""Modalidades das Loterias Caixa.

Cada módulo deste pacote expõe uma classe concreta que herda de
:class:`src.core.base_lottery.LotteryBase` e declara o respectivo
:class:`~src.core.models.LotterySpec` com as regras oficiais da modalidade.

Este ``__init__`` também concentra a base comum das modalidades de
**conjunto** (dezenas únicas, intervalo ``1..universo``), definida antes dos
imports dos módulos concretos justamente para que eles possam reutilizá-la sem
dependência circular.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.base_lottery import LotteryBase
from src.core.models import LotterySpec

logger = logging.getLogger(__name__)


class LoteriaConjunto(LotteryBase):
    """Comportamento comum às modalidades em que um jogo é um conjunto.

    Um jogo é uma lista de ``qtd`` dezenas distintas de ``1..universo``
    (ou ``0..universo-1`` se o spec for posicional, caso não usado aqui).
    Subclasses só precisam declarar ``spec`` e ``DESCRICAO``; o sorteio, as
    faixas de soma e a ficha ``info()`` são genéricos.
    """

    spec: ClassVar[LotterySpec]
    DESCRICAO: ClassVar[str] = ""

    # ------------------------------------------------------------------ sorteio
    def _qtd_do_jogo(self) -> int:
        """Quantidade efetiva de dezenas do jogo (config ou padrão do spec)."""
        config = getattr(self, "config", None)
        if config is not None:
            qtd = getattr(config, "dezenas_por_jogo", None)
            if qtd:
                return int(qtd)
        for nome in ("dezenas_por_jogo", "qtd_efetiva", "qtd_dezenas"):
            valor = getattr(self, nome, None)
            if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0:
                return valor
        return int(self.spec.qtd_padrao)

    def _sortear(self) -> list[int]:
        """Sorteia ``qtd`` dezenas distintas no intervalo oficial."""
        inicio, universo = self.intervalo()
        qtd = self._qtd_do_jogo()
        return sorted(self.rng.sample(range(inicio, universo + 1), qtd))

    # ------------------------------------------------------------- metadados
    @classmethod
    def faixas_soma(cls) -> tuple[int, int]:
        """Soma mínima e máxima teoricamente possível para o jogo padrão."""
        qtd = int(cls.spec.qtd_padrao)
        inicio = int(cls.spec.inicio)
        universo = int(cls.spec.universo)
        minima = sum(range(inicio, inicio + qtd))
        maxima = sum(range(universo - qtd + 1, universo + 1))
        return (minima, maxima)

    @classmethod
    def info(cls) -> dict:
        """Ficha resumida da modalidade (spec + faixas + descrição)."""
        spec = cls.spec
        return {
            "key": spec.key,
            "nome": spec.nome,
            "universo": spec.universo,
            "sorteadas": spec.sorteadas,
            "aposta_min": spec.aposta_min,
            "aposta_max": spec.aposta_max,
            "colunas": spec.colunas,
            "tipo": spec.tipo,
            "inicio": spec.inicio,
            "qtd_padrao": spec.qtd_padrao,
            "faixas_soma": cls.faixas_soma(),
            "descricao": cls.DESCRICAO,
        }


from .mega_sena import MegaSena  # noqa: E402
from .lotofacil import Lotofacil  # noqa: E402
from .quina import Quina  # noqa: E402
from .lotomania import Lotomania  # noqa: E402
from .timemania import Timemania  # noqa: E402
from .dupla_sena import DuplaSena  # noqa: E402
from .dia_de_sorte import DiaDeSorte  # noqa: E402
from .super_sete import SuperSete  # noqa: E402
from .registry import LOTERIAS, criar, get_loteria, listar_loterias  # noqa: E402

__all__ = [
    "LOTERIAS",
    "LoteriaConjunto",
    "MegaSena",
    "Lotofacil",
    "Quina",
    "Lotomania",
    "Timemania",
    "DuplaSena",
    "DiaDeSorte",
    "SuperSete",
    "criar",
    "get_loteria",
    "listar_loterias",
]
