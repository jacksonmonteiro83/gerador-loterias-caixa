"""API pública do motor genérico de loterias."""

from __future__ import annotations

from . import stats
from .base_lottery import LotteryBase
from .filters import PRIMOS, atende, explicar_falha, metricas
from .models import FiltroConfig, LotteryConfig, LotterySpec, ValidacaoError

__all__ = [
    "LotteryBase",
    "LotterySpec",
    "LotteryConfig",
    "FiltroConfig",
    "ValidacaoError",
    "metricas",
    "atende",
    "explicar_falha",
    "PRIMOS",
    "stats",
]
