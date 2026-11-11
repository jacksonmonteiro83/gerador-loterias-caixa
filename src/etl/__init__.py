"""ETL das Loterias Caixa: coleta, normalização e persistência."""

from .loader import atualizar_loteria, atualizar_todas

__all__ = ["atualizar_loteria", "atualizar_todas"]
