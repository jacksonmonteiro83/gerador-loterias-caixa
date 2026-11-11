"""Super Sete.

Regra oficial: a aposta é **posicional**. São 7 colunas e, em cada uma, o
apostador escolhe 1 dígito de 0 a 9 — sempre 7 dígitos, um por coluna (a aposta
é fixa). A Caixa sorteia um dígito por coluna. O mesmo dígito pode aparecer em
colunas diferentes; não existe a noção de "dezena repetida" do jogo de
conjunto.

Por ser posicional, esta modalidade:

* ignora filtros estruturais de malha (``moldura``, ``miolo`` e ``quadrante_*``);
* interpreta ``dezenas_fixas`` **por coluna** quando a lista tem exatamente 7
  itens (posição ``i`` é o dígito obrigatório da coluna ``i + 1``); com outro
  tamanho, os valores são tratados como dígitos que devem aparecer ao menos uma
  vez no jogo.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import ClassVar, Sequence

from src.core.models import (
    FiltroConfig,
    LotteryConfig,
    LotterySpec,
    ValidacaoError,
)
from src.core.base_lottery import LotteryBase

logger = logging.getLogger(__name__)

COLUNAS = 7
DIGITOS = range(10)  # 0..9


class SuperSete(LotteryBase):
    """Gerador de jogos da Super Sete (7 colunas, 1 dígito de 0 a 9 por coluna)."""

    spec: ClassVar[LotterySpec] = LotterySpec(
        key="super-sete",
        nome="Super Sete",
        universo=10,
        sorteadas=7,
        aposta_min=7,
        aposta_max=7,
        colunas=7,
        tipo="posicional",
        inicio=0,
    )

    DESCRICAO: ClassVar[str] = (
        "Sete colunas, um dígito de 0 a 9 em cada; aposta fixa de 7 dígitos."
    )

    def __init__(self, config: LotteryConfig | None = None, historico=None) -> None:
        self._fixas_por_coluna: tuple[int, ...] | None = None
        self._digitos_obrigatorios: tuple[int, ...] = ()
        self._excluidas: frozenset[int] = frozenset()

        if config is not None:
            if config.dezenas_por_jogo not in (None, COLUNAS):
                raise ValidacaoError(
                    "Super Sete exige exatamente 7 dígitos por jogo "
                    f"(recebido {config.dezenas_por_jogo})."
                )
            fixas = list(config.dezenas_fixas or [])
            self._validar_digitos(fixas, "dezenas_fixas")
            excluidas = list(config.dezenas_excluidas or [])
            self._validar_digitos(excluidas, "dezenas_excluidas")

            conflito = sorted(set(fixas) & set(excluidas))
            if conflito:
                raise ValidacaoError(
                    "Super Sete: dígitos não podem ser fixos e excluídos ao mesmo "
                    f"tempo: {conflito}."
                )

            if len(fixas) == COLUNAS:
                self._fixas_por_coluna = tuple(fixas)
            else:
                obrigatorios = tuple(sorted(set(fixas)))
                if len(obrigatorios) > COLUNAS:
                    raise ValidacaoError(
                        "Super Sete: há mais dígitos fixos distintos "
                        f"({len(obrigatorios)}) do que colunas ({COLUNAS})."
                    )
                self._digitos_obrigatorios = obrigatorios
            self._excluidas = frozenset(excluidas)

            # O core não injeta fixas em jogos posicionais (cada coluna tem seu
            # próprio dígito), então elas são resolvidas aqui. Filtros
            # estruturais de malha também são removidos: não se aplicam.
            config = replace(
                config,
                dezenas_fixas=[],
                filtros=self._sem_filtros_estruturais(config.filtros),
            )

        super().__init__(config=config, historico=historico)

    # ------------------------------------------------------------- validação
    @staticmethod
    def _validar_digitos(valores: Sequence[int], campo: str) -> None:
        for valor in valores:
            if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= 9:
                raise ValidacaoError(
                    f"Super Sete: {campo} aceita apenas inteiros de 0 a 9 "
                    f"(recebido {valor!r})."
                )

    @staticmethod
    def _sem_filtros_estruturais(filtros: FiltroConfig | None) -> FiltroConfig:
        if filtros is None:
            return FiltroConfig()
        return replace(
            filtros, moldura=None, miolo=None, quadrante_min=None, quadrante_max=None
        )

    # ------------------------------------------------------------------ sorteio
    def _permite_repeticao_estrutural(self) -> bool:
        """Super Sete não tem malha de dezenas; filtros de moldura não se aplicam."""
        return False

    def _sortear(self) -> list[int]:
        """Um dígito por coluna, sorteados de forma independente."""
        permitidos = [d for d in DIGITOS if d not in self._excluidas]
        if not permitidos:
            raise ValidacaoError(
                "Super Sete: todos os dígitos (0 a 9) foram excluídos; "
                "não há jogo possível."
            )

        if self._fixas_por_coluna is not None:
            return [int(d) for d in self._fixas_por_coluna]

        jogo = [self.rng.choice(permitidos) for _ in range(COLUNAS)]
        if self._digitos_obrigatorios:
            # Reserva colunas distintas para os dígitos obrigatórios, sem
            # deslocar um pelo outro.
            posicoes = self.rng.sample(range(COLUNAS), len(self._digitos_obrigatorios))
            for posicao, digito in zip(posicoes, self._digitos_obrigatorios):
                jogo[posicao] = digito
        return jogo

    # --------------------------------------------------------------- metadados
    @classmethod
    def faixas_soma(cls) -> tuple[int, int]:
        """Soma mínima (0) e máxima (7 x 9 = 63) dos 7 dígitos."""
        return (0, (COLUNAS) * 9)

    @classmethod
    def info(cls) -> dict:
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
