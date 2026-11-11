"""Catálogo e fábrica das modalidades.

``LOTERIAS`` mantém a ordem oficial do catálogo da Caixa; ``get_loteria``
normaliza a chave recebida (acentos, caixa, espaços, hífen, sublinhado e
pontuação) para que ``"Mega Sena"``, ``"mega-sena"``, ``"MEGASENA"`` e
``"lotofácil"`` funcionem igualmente.
"""

from __future__ import annotations

import logging
import unicodedata

import pandas as pd

from src.core.base_lottery import LotteryBase
from src.core.models import LotteryConfig
from src.loterias.dia_de_sorte import DiaDeSorte
from src.loterias.dupla_sena import DuplaSena
from src.loterias.lotofacil import Lotofacil
from src.loterias.lotomania import Lotomania
from src.loterias.mega_sena import MegaSena
from src.loterias.quina import Quina
from src.loterias.super_sete import SuperSete
from src.loterias.timemania import Timemania

logger = logging.getLogger(__name__)

#: Ordem oficial do catálogo (usada por ``listar_loterias``).
LOTERIAS: dict[str, type[LotteryBase]] = {
    MegaSena.spec.key: MegaSena,
    Lotofacil.spec.key: Lotofacil,
    Quina.spec.key: Quina,
    Lotomania.spec.key: Lotomania,
    Timemania.spec.key: Timemania,
    DuplaSena.spec.key: DuplaSena,
    DiaDeSorte.spec.key: DiaDeSorte,
    SuperSete.spec.key: SuperSete,
}


def _normalizar(chave: object) -> str:
    """Reduz a chave a letras/dígitos minúsculos e sem acento."""
    if not isinstance(chave, str):
        raise KeyError(
            f"Loteria inválida: {chave!r} (esperado texto). "
            f"Chaves válidas: {', '.join(LOTERIAS)}."
        )
    decomposto = unicodedata.normalize("NFKD", chave)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return "".join(c for c in sem_acento.casefold() if c.isalnum())


# Mapa normalizado -> chave canônica.
_INDICE: dict[str, str] = {_normalizar(key): key for key in LOTERIAS}

# Sinônimos informais aceitos além do nome oficial.
_ALIASES: dict[str, str] = {
    _normalizar("mega"): "mega-sena",
    _normalizar("sena"): "mega-sena",
    _normalizar("lotofacil"): "lotofacil",
    _normalizar("duplasena"): "dupla-sena",
    _normalizar("diadesorte"): "dia-de-sorte",
    _normalizar("supersete"): "super-sete",
}


def get_loteria(key: str) -> type[LotteryBase]:
    """Devolve a classe da modalidade, aceitando grafias informais.

    Levanta ``KeyError`` com a lista de chaves válidas quando não reconhece.
    """
    normalizada = _normalizar(key)
    canonica = _INDICE.get(normalizada) or _ALIASES.get(normalizada)
    if canonica is None:
        validas = ", ".join(LOTERIAS)
        raise KeyError(
            f"Loteria desconhecida: {key!r}. Chaves válidas: {validas}."
        )
    return LOTERIAS[canonica]


def listar_loterias() -> list[dict]:
    """Catálogo resumido, na ordem oficial."""
    catalogo: list[dict] = []
    for classe in LOTERIAS.values():
        spec = classe.spec
        catalogo.append(
            {
                "key": spec.key,
                "nome": spec.nome,
                "universo": spec.universo,
                "sorteadas": spec.sorteadas,
                "aposta_min": spec.aposta_min,
                "aposta_max": spec.aposta_max,
            }
        )
    return catalogo


def criar(
    key: str,
    config: LotteryConfig | None = None,
    historico: pd.DataFrame | None = None,
) -> LotteryBase:
    """Instancia a modalidade ``key`` já com ``config`` e ``historico``."""
    classe = get_loteria(key)
    logger.debug("Criando loteria %s", classe.spec.key)
    return classe(config=config, historico=historico)
