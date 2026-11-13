"""Motor genérico de validação e geração de jogos.

Subclasses concretas (``src/loterias``) apenas definem ``spec`` e implementam
``_sortear``. Toda a validação oficial, filtros, histórico e orçamento de
tentativas vivem aqui.
"""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any, ClassVar, Sequence

import pandas as pd

from . import filters, scoring, stats
from .models import FiltroConfig, LotteryConfig, LotterySpec, ValidacaoError

__all__ = ["LotteryBase"]

logger = logging.getLogger(__name__)


class LotteryBase(ABC):
    """Base para as oito modalidades das Loterias Caixa."""

    spec: ClassVar[LotterySpec]

    def __init__(
        self,
        config: LotteryConfig | None = None,
        historico: pd.DataFrame | None = None,
    ) -> None:
        spec = getattr(self, "spec", None)
        if not isinstance(spec, LotterySpec):
            raise ValidacaoError(
                f"{type(self).__name__}: a classe deve definir 'spec' "
                "como uma instância de LotterySpec"
            )
        self.config = config if config is not None else LotteryConfig()
        if not isinstance(self.config, LotteryConfig):
            raise ValidacaoError("config deve ser uma instância de LotteryConfig")
        self.qtd_efetiva = self.config.validar_contra(spec)
        self.rng = random.Random(self.config.seed)
        self.historico = stats.normalizar(historico)
        self.ultimo = stats.dezenas_ultimo_concurso(self.historico)
        self._ultimo_lista: list[int] = []
        if not self.historico.empty:
            self._ultimo_lista = [
                int(d) for d in self.historico["dezenas"].iloc[-1]
            ]
        self._perfil_score: scoring.PerfilScore | None = None
        self._perfis_score: dict[int, scoring.PerfilScore] = {}
        self._padroes_linha = frozenset(self.config.padroes_linha or [])
        if (
            self.config.repetidas_concurso_anterior is not None
            and self.historico.empty
        ):
            raise ValidacaoError(
                f"{self.spec.nome}: histórico necessário para "
                "repetidas_concurso_anterior"
            )
        if not self.config.filtros.ativo():
            logger.debug("%s inicializada sem filtros ativos", self.spec.nome)

    # ------------------------------------------------------------------
    # regras oficiais
    # ------------------------------------------------------------------
    def intervalo(self) -> tuple[int, int]:
        """Intervalo fechado de valores aceitos para uma posição do jogo."""
        if self.spec.tipo == "posicional":
            # posicional: dígitos de 0 até universo - 1 (ex.: 0..9)
            return (0, self.spec.universo - 1)
        return (self.spec.inicio, self.spec.inicio + self.spec.universo - 1)

    def regras(self) -> dict:
        """Regras da modalidade em formato legível."""
        spec = self.spec
        return {
            "key": spec.key,
            "nome": spec.nome,
            "universo": spec.universo,
            "sorteadas": spec.sorteadas,
            "aposta_min": spec.aposta_min,
            "aposta_max": spec.aposta_max,
            "colunas": spec.colunas,
            "linhas": spec.linhas,
            "tipo": spec.tipo,
            "inicio": spec.inicio,
            "qtd_padrao": spec.qtd_padrao,
            "qtd_efetiva": self.qtd_efetiva,
            "intervalo": self.intervalo(),
        }

    def validar(self, jogo: Sequence[int]) -> None:
        """Valida as regras oficiais; levanta :class:`ValidacaoError`."""
        if jogo is None or isinstance(jogo, (str, bytes)):
            raise ValidacaoError(
                f"{self.spec.nome}: jogo deve ser uma sequência de inteiros"
            )
        try:
            itens = list(jogo)
        except TypeError as exc:
            raise ValidacaoError(
                f"{self.spec.nome}: jogo deve ser uma sequência de inteiros"
            ) from exc

        if self.spec.tipo == "posicional":
            self._validar_posicional(itens)
            return
        self._validar_conjunto(itens)

    def _validar_conjunto(self, itens: list[Any]) -> None:
        spec = self.spec
        esperado = self.qtd_efetiva
        if not (spec.aposta_min <= esperado <= spec.aposta_max):
            raise ValidacaoError(
                f"{spec.nome}: quantidade efetiva ({esperado}) fora do permitido "
                f"({spec.aposta_min} a {spec.aposta_max})"
            )
        if len(itens) != esperado:
            raise ValidacaoError(
                f"{spec.nome}: o jogo deve ter {esperado} dezenas "
                f"(recebido {len(itens)})"
            )
        inicio, fim = self.intervalo()
        vistos: set[int] = set()
        for item in itens:
            if isinstance(item, bool) or not self._eh_inteiro(item):
                raise ValidacaoError(
                    f"{spec.nome}: dezena inválida {item!r}; use inteiros"
                )
            dezena = int(item)
            if not inicio <= dezena <= fim:
                raise ValidacaoError(
                    f"{spec.nome}: dezena {dezena} fora do intervalo "
                    f"[{inicio}, {fim}]"
                )
            if dezena in vistos:
                raise ValidacaoError(
                    f"{spec.nome}: dezena {dezena} repetida no jogo"
                )
            vistos.add(dezena)

    def _validar_posicional(self, itens: list[Any]) -> None:
        spec = self.spec
        esperado = int(spec.sorteadas)
        if len(itens) != esperado:
            raise ValidacaoError(
                f"{spec.nome}: o jogo posicional deve ter {esperado} dígitos "
                f"(um por coluna), recebido {len(itens)}"
            )
        maximo = spec.universo - 1
        for indice, item in enumerate(itens, start=1):
            if isinstance(item, bool) or not self._eh_inteiro(item):
                raise ValidacaoError(
                    f"{spec.nome}: coluna {indice} com valor inválido {item!r}; "
                    "use um dígito inteiro"
                )
            digito = int(item)
            if not 0 <= digito <= maximo:
                raise ValidacaoError(
                    f"{spec.nome}: coluna {indice} deve ser um dígito entre "
                    f"0 e {maximo} (recebido {digito})"
                )

    @staticmethod
    def _eh_inteiro(valor: Any) -> bool:
        if isinstance(valor, bool):
            return False
        if isinstance(valor, int):
            return True
        try:
            import numbers

            return isinstance(valor, numbers.Integral)
        except Exception:  # pragma: no cover - defensivo
            return False

    def jogo_valido(self, jogo: Sequence[int]) -> bool:
        try:
            self.validar(jogo)
        except ValidacaoError:
            return False
        return True

    # ------------------------------------------------------------------
    # análise
    # ------------------------------------------------------------------
    def _metricas(self, jogo: Sequence[int]) -> dict:
        if self.spec.tipo == "posicional":
            return self._metricas_posicional(jogo)
        return filters.metricas(
            jogo, self.spec.universo, self.spec.colunas, self.spec.inicio
        )

    def _metricas_posicional(self, jogo: Sequence[int]) -> dict:
        valores = [int(d) for d in jogo]
        total = len(valores)
        soma = sum(valores)
        return {
            "pares": sum(1 for d in valores if d % 2 == 0),
            "impares": sum(1 for d in valores if d % 2 != 0),
            "primos": len(set(valores) & filters.PRIMOS),
            "moldura": 0,
            "miolo": 0,
            "soma": soma,
            "quadrantes": [],
            "total": total,
            "min": min(valores) if total else 0,
            "max": max(valores) if total else 0,
            "media": round(soma / total, 2) if total else 0.0,
            "digitos_repetidos": total - len(set(valores)),
        }

    def _repetidas(self, jogo: Sequence[int]) -> int:
        """Repetições em relação ao último concurso (ignora dezenas fixas)."""
        if not self.ultimo:
            return 0
        fixas = {int(d) for d in self.config.dezenas_fixas}
        if self.spec.tipo == "posicional" and len(self._ultimo_lista) == len(jogo):
            total = 0
            for atual, anterior in zip(jogo, self._ultimo_lista):
                atual = int(atual)
                if atual == anterior and atual not in fixas:
                    total += 1
            return total
        return len(({int(d) for d in jogo} & self.ultimo) - fixas)

    def _contaminacao(self, jogo: Sequence[int]) -> int:
        """Maior sobreposição com um concurso do histórico."""
        if self.historico.empty:
            return 0
        if (
            self.spec.tipo == "posicional"
            and len(self._ultimo_lista) == len(jogo)
        ):
            maior = 0
            for dezenas in self.historico["dezenas"].tolist():
                if len(dezenas) != len(jogo):
                    continue
                iguais = sum(
                    1 for a, b in zip(jogo, dezenas) if int(a) == int(b)
                )
                maior = max(maior, iguais)
            return maior
        return stats.contaminacao(jogo, self.historico)

    def analisar(self, jogo: Sequence[int]) -> dict:
        """Valida o jogo e devolve métricas + informações de histórico."""
        self.validar(jogo)
        metricas = self._metricas(jogo)
        if self.spec.tipo == "posicional":
            ordenado = [int(d) for d in jogo]
        else:
            ordenado = sorted(int(d) for d in jogo)
        metricas.update(
            {
                "jogo": ordenado,
                "repetidas_ultimo": int(self._repetidas(jogo)),
                "contaminacao": int(self._contaminacao(jogo)),
                "valido": True,
            }
        )
        return metricas

    # ------------------------------------------------------------------
    # padrões de linha
    # ------------------------------------------------------------------
    def padrao_linhas(self, jogo: Sequence[int]) -> str:
        """Assinatura de distribuição do jogo pelas linhas da malha."""
        return scoring.padrao_linhas(jogo, self.spec)

    @property
    def padroes_frequentes(self) -> list[dict]:
        """Padrões de linha mais frequentes no histórico (do mais comum)."""
        return scoring.frequencias_padroes(self.spec, self.historico)

    @property
    def padroes_cobertura(self) -> float:
        """Percentual de concursos cobertos pelos padrões configurados."""
        return scoring.cobertura_padroes(
            self.spec, self.historico, self.config.padroes_linha or []
        )

    # ------------------------------------------------------------------
    # score adaptativo
    # ------------------------------------------------------------------
    @property
    def perfil_score(self) -> scoring.PerfilScore:
        """Modelo de score calibrado para o tamanho do jogo configurado."""
        return self.perfil_score_para(self.qtd_efetiva)

    def perfil_score_para(self, qtd: int) -> scoring.PerfilScore:
        """Modelo calibrado para um tamanho de jogo (cache por tamanho)."""
        qtd = int(qtd)
        if self._perfis_score is None:
            self._perfis_score = {}
        if qtd not in self._perfis_score:
            self._perfis_score[qtd] = scoring.calibrar(
                self.spec, self.historico, qtd=qtd
            )
        return self._perfis_score[qtd]

    @property
    def score_minimo(self) -> int:
        """Limiar efetivo: o da configuração ou o calibrado para a modalidade."""
        if self.config.score_minimo is not None:
            return int(self.config.score_minimo)
        return int(self.perfil_score.limiar)

    def pontuar(self, jogo: Sequence[int], qtd: int | None = None) -> dict:
        """Devolve score, status e métricas do modelo para um jogo."""
        valores = [int(d) for d in jogo]
        perfil = self.perfil_score_para(qtd or len(valores))
        return perfil.avaliar(valores, self._ultimo_lista or None)

    def _filtro_efetivo(self) -> FiltroConfig:
        filtro = self.config.filtros
        if self._permite_repeticao_estrutural():
            return filtro
        return replace(
            filtro,
            moldura=None,
            miolo=None,
            quadrante_min=None,
            quadrante_max=None,
        )

    def atende_filtros(self, jogo: Sequence[int]) -> bool:
        return filters.atende(self._filtro_efetivo(), self._metricas(jogo))

    def _motivos_historico(self, jogo: Sequence[int]) -> list[str]:
        motivos: list[str] = []
        if self.historico.empty:
            return motivos
        repetidas = self._repetidas(jogo)
        if (
            self.config.repetidas_concurso_anterior is not None
            and repetidas != self.config.repetidas_concurso_anterior
        ):
            motivos.append(
                f"repetidas do último concurso = {repetidas}, esperado "
                f"{self.config.repetidas_concurso_anterior}"
            )
        if self.config.max_repetidas is not None and repetidas > self.config.max_repetidas:
            motivos.append(
                f"repetidas do último concurso = {repetidas}, máximo "
                f"{self.config.max_repetidas}"
            )
        if self.config.contaminacao_maxima is not None:
            contaminacao = self._contaminacao(jogo)
            if contaminacao > self.config.contaminacao_maxima:
                motivos.append(
                    f"contaminação = {contaminacao}, máximo "
                    f"{self.config.contaminacao_maxima}"
                )
        return motivos

    def explicar(self, jogo: Sequence[int]) -> list[str]:
        """Motivos de rejeição (vazio se o jogo passa em tudo)."""
        try:
            self.validar(jogo)
        except ValidacaoError as exc:
            return [str(exc)]
        motivos = filters.explicar_falha(
            self._filtro_efetivo(), self._metricas(jogo)
        )
        motivos.extend(self._motivos_historico(jogo))
        return motivos

    # ------------------------------------------------------------------
    # geração
    # ------------------------------------------------------------------
    def _permite_repeticao_estrutural(self) -> bool:
        """Hook para modalidades posicionais (padrão: ``True``)."""
        return True

    @abstractmethod
    def _sortear(self) -> list[int]:
        """Sorteio bruto de um jogo, sem validação de filtros/histórico."""

    def _pool(self) -> list[int]:
        fixas = {int(d) for d in self.config.dezenas_fixas}
        excluidas = {int(d) for d in self.config.dezenas_excluidas}
        inicio, fim = self.intervalo()
        return [
            d
            for d in range(inicio, fim + 1)
            if d not in fixas and d not in excluidas
        ]

    def _candidato(self) -> list[int]:
        """Monta um jogo respeitando ``dezenas_fixas``/``dezenas_excluidas``."""
        if self.spec.tipo == "posicional":
            return [int(d) for d in self._sortear()]
        fixas = sorted(int(d) for d in self.config.dezenas_fixas)
        faltam = self.qtd_efetiva - len(fixas)
        if faltam < 0:
            raise ValidacaoError(
                f"{self.spec.nome}: {len(fixas)} dezenas fixas para um jogo de "
                f"{self.qtd_efetiva} dezenas"
            )
        pool = self._pool()
        if faltam > len(pool):
            raise ValidacaoError(
                f"{self.spec.nome}: restrições deixam apenas {len(pool)} dezenas "
                f"livres para {faltam} posições"
            )
        resto = self.rng.sample(pool, faltam) if faltam else []
        return sorted(fixas + [int(d) for d in resto])

    def _respeita_restricoes(self, jogo: Sequence[int]) -> bool:
        conjunto = {int(d) for d in jogo}
        fixas = {int(d) for d in self.config.dezenas_fixas}
        excluidas = {int(d) for d in self.config.dezenas_excluidas}
        if not fixas <= conjunto:
            return False
        if conjunto & excluidas:
            return False
        return True

    def _checa_historico(self, jogo: Sequence[int]) -> bool:
        """Aplica os critérios de histórico (ignorados se não há histórico)."""
        if self.historico.empty:
            return True
        repetidas = self._repetidas(jogo)
        if (
            self.config.repetidas_concurso_anterior is not None
            and repetidas != self.config.repetidas_concurso_anterior
        ):
            return False
        if self.config.max_repetidas is not None and repetidas > self.config.max_repetidas:
            return False
        if self.config.contaminacao_maxima is not None:
            if self._contaminacao(jogo) > self.config.contaminacao_maxima:
                return False
        return True

    def _tentar(self) -> list[int] | None:
        """Um candidato completo: sorteio + regras + filtros + histórico."""
        jogo = self._candidato()
        try:
            self.validar(jogo)
        except ValidacaoError:
            logger.debug("%s: candidato inválido descartado", self.spec.nome)
            return None
        if not self._respeita_restricoes(jogo):
            return None
        if not self.atende_filtros(jogo):
            return None
        if not self._checa_historico(jogo):
            return None
        if self._padroes_linha and self.padrao_linhas(jogo) not in self._padroes_linha:
            return None
        if self.config.score_minimo is not None:
            if self.pontuar(jogo)["score"] < self.score_minimo:
                return None
        return [int(d) for d in jogo]

    def _resumo_restricoes(self) -> str:
        partes: list[str] = []
        if self.config.filtros.ativo():
            partes.append(f"filtros={self.config.filtros.como_dict()}")
        if self.config.dezenas_fixas:
            partes.append(f"fixas={sorted(self.config.dezenas_fixas)}")
        if self.config.dezenas_excluidas:
            partes.append(f"excluídas={sorted(self.config.dezenas_excluidas)}")
        if self.config.repetidas_concurso_anterior is not None:
            partes.append(
                f"repetidas={self.config.repetidas_concurso_anterior}"
            )
        if self.config.max_repetidas is not None:
            partes.append(f"max_repetidas={self.config.max_repetidas}")
        if self.config.contaminacao_maxima is not None:
            partes.append(f"contaminação_maxima={self.config.contaminacao_maxima}")
        if self.config.padroes_linha:
            partes.append(f"padrões={','.join(self.config.padroes_linha)}")
        if self.config.score_minimo is not None:
            partes.append(f"score_minimo={self.config.score_minimo}")
        return "; ".join(partes) if partes else "sem restrições adicionais"

    def gerar_jogo(self) -> list[int]:
        """Gera um jogo que passe em validação, filtros e histórico."""
        limite = self.config.max_tentativas
        for _ in range(limite):
            jogo = self._tentar()
            if jogo is not None:
                return jogo
        raise RuntimeError(
            f"{self.spec.nome}: não foi possível gerar um jogo válido em "
            f"{limite} tentativas; provável restrição impossível "
            f"({self._resumo_restricoes()})"
        )

    def gerar(self) -> list[list[int]]:
        """Gera ``config.qtd_jogos`` jogos distintos."""
        qtd = self.config.qtd_jogos
        orcamento = self.config.max_tentativas * qtd
        jogos: list[list[int]] = []
        vistos: set[tuple[int, ...]] = set()
        tentativas = 0
        sem_progresso = 0
        while len(jogos) < qtd:
            if tentativas >= orcamento:
                raise RuntimeError(
                    f"{self.spec.nome}: não foi possível gerar {qtd} jogos "
                    f"distintos em {orcamento} tentativas; provável restrição "
                    f"impossível ({self._resumo_restricoes()})"
                )
            if sem_progresso >= self.config.max_tentativas:
                raise RuntimeError(
                    f"{self.spec.nome}: {self.config.max_tentativas} tentativas "
                    f"sem progresso ao gerar o jogo {len(jogos) + 1}/{qtd}; "
                    f"provável filtro impossível ({self._resumo_restricoes()})"
                )
            tentativas += 1
            sem_progresso += 1
            jogo = self._tentar()
            if jogo is None:
                continue
            chave = tuple(int(d) for d in jogo)
            if chave in vistos:
                logger.debug("%s: jogo duplicado descartado", self.spec.nome)
                continue
            vistos.add(chave)
            jogos.append(jogo)
            sem_progresso = 0
        logger.debug("%s: %s jogos gerados em %s tentativas", self.spec.nome, qtd, tentativas)
        return jogos

    def probabilidade_filtro(self, n: int = 2000) -> float:
        """Estimativa por amostragem da taxa de aceitação dos critérios atuais."""
        n = int(n)
        if n <= 0:
            return 0.0
        aceitos = sum(1 for _ in range(n) if self._tentar() is not None)
        return round(aceitos / n, 4)

    def __repr__(self) -> str:  # pragma: no cover - conveniência
        return (
            f"{type(self).__name__}(key={self.spec.key!r}, "
            f"qtd={self.qtd_efetiva}, seed={self.config.seed!r})"
        )
