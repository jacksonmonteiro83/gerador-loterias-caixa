"""Modelos de configuração do motor de geração.

Define a exceção de validação e as dataclasses usadas por todo o `src.core`
(``LotterySpec``, ``FiltroConfig`` e ``LotteryConfig``). Todas as mensagens de
erro são em português.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = [
    "ValidacaoError",
    "LotterySpec",
    "FiltroConfig",
    "LotteryConfig",
]


class ValidacaoError(ValueError):
    """Erro de validação de regras oficiais ou de configuração."""


def _eh_int(valor: Any) -> bool:
    """True para inteiros "puros" (rejeita ``bool`` e aceita ``numpy.int64``)."""
    if isinstance(valor, bool):
        return False
    if isinstance(valor, int):
        return True
    # numpy.int64 / numpy.int32 expõem __index__
    try:
        import numbers

        return isinstance(valor, numbers.Integral)
    except Exception:  # pragma: no cover - defensivo
        return False


def _validar_faixa(nome: str, faixa: tuple[int, int] | None) -> tuple[int, int] | None:
    """Valida/normaliza uma faixa inclusiva ``(min, max)``."""
    if faixa is None:
        return None
    if isinstance(faixa, (list, tuple)):
        if len(faixa) != 2:
            raise ValidacaoError(f"filtro {nome} deve ser uma faixa (min, max)")
        itens = tuple(faixa)
    else:
        raise ValidacaoError(f"filtro {nome} deve ser uma faixa (min, max)")
    minimo, maximo = itens
    if not (_eh_int(minimo) and _eh_int(maximo)):
        raise ValidacaoError(f"filtro {nome} deve conter inteiros")
    minimo, maximo = int(minimo), int(maximo)
    if minimo < 0:
        raise ValidacaoError(f"filtro {nome}: o mínimo não pode ser negativo ({minimo})")
    if minimo > maximo:
        raise ValidacaoError(
            f"filtro {nome}: mínimo {minimo} maior que o máximo {maximo}"
        )
    return (minimo, maximo)


def _normalizar_padrao(valor: Any) -> str:
    """Normaliza ``"1-2-1"`` para ``"2-1-1"`` (contagens decrescentes)."""
    if not isinstance(valor, str):
        raise ValidacaoError(f"padrão de linha deve ser texto (recebido {valor!r})")
    partes = [parte.strip() for parte in valor.replace(" ", "").split("-")]
    if not partes or any(not parte for parte in partes):
        raise ValidacaoError(f"padrão de linha inválido: {valor!r}")
    try:
        numeros = [int(parte) for parte in partes]
    except ValueError as exc:
        raise ValidacaoError(f"padrão de linha inválido: {valor!r}") from exc
    if any(numero <= 0 for numero in numeros):
        raise ValidacaoError(
            f"padrão de linha deve conter contagens positivas: {valor!r}"
        )
    return "-".join(str(numero) for numero in sorted(numeros, reverse=True))


@dataclass(frozen=True)
class LotterySpec:
    """Regras oficiais de uma modalidade."""

    key: str
    nome: str
    universo: int
    sorteadas: int
    aposta_min: int
    aposta_max: int
    colunas: int
    tipo: str = "conjunto"  # "conjunto" | "posicional"
    inicio: int = 1  # 1 para conjunto, 0 para posicional

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValidacaoError("key da modalidade não pode ser vazia")
        if not isinstance(self.nome, str) or not self.nome.strip():
            raise ValidacaoError("nome da modalidade não pode ser vazio")
        if self.tipo not in ("conjunto", "posicional"):
            raise ValidacaoError(
                f"tipo inválido para {self.nome}: {self.tipo!r}; "
                "use 'conjunto' ou 'posicional'"
            )
        for campo in ("universo", "sorteadas", "aposta_min", "aposta_max", "colunas"):
            if not _eh_int(getattr(self, campo)):
                raise ValidacaoError(f"{self.nome}: {campo} deve ser inteiro")
        if self.universo <= 0:
            raise ValidacaoError(f"{self.nome}: universo deve ser maior que zero")
        if not (0 < self.sorteadas <= self.universo):
            raise ValidacaoError(
                f"{self.nome}: sorteadas ({self.sorteadas}) deve estar entre "
                f"1 e universo ({self.universo})"
            )
        if self.colunas <= 0:
            raise ValidacaoError(f"{self.nome}: colunas deve ser maior que zero")
        if self.aposta_min <= 0:
            raise ValidacaoError(f"{self.nome}: aposta_min deve ser maior que zero")
        if self.aposta_min > self.aposta_max:
            raise ValidacaoError(
                f"{self.nome}: aposta_min ({self.aposta_min}) não pode ser maior "
                f"que aposta_max ({self.aposta_max})"
            )
        if self.tipo == "conjunto" and self.aposta_min < self.sorteadas:
            raise ValidacaoError(
                f"{self.nome}: aposta_min ({self.aposta_min}) não pode ser menor "
                f"que sorteadas ({self.sorteadas})"
            )
        if self.tipo == "posicional" and self.sorteadas != self.aposta_min:
            raise ValidacaoError(
                f"{self.nome}: modalidade posicional exige aposta_min igual a "
                f"sorteadas ({self.sorteadas})"
            )
        if not _eh_int(self.inicio) or self.inicio < 0:
            raise ValidacaoError(f"{self.nome}: inicio deve ser inteiro não negativo")

    @property
    def qtd_padrao(self) -> int:
        """Quantidade padrão de dezenas por jogo (``aposta_min``)."""
        return int(self.aposta_min)

    @property
    def linhas(self) -> int:
        """Número de linhas da malha de moldura/miolo."""
        return math.ceil(self.universo / self.colunas)

    @property
    def dezenas_validas(self) -> range:
        """Intervalo das dezenas (conjunto) ou dígitos (posicional)."""
        if self.tipo == "posicional":
            return range(self.universo)
        return range(self.inicio, self.inicio + self.universo)


@dataclass
class FiltroConfig:
    """Faixas de aceitação aplicadas às métricas de um jogo."""

    pares: tuple[int, int] | None = None  # (min, max) inclusivo
    impares: tuple[int, int] | None = None
    primos: tuple[int, int] | None = None
    moldura: tuple[int, int] | None = None
    miolo: tuple[int, int] | None = None
    soma: tuple[int, int] | None = None
    quadrante_min: int | None = None  # aplicado a CADA quadrante
    quadrante_max: int | None = None

    def __post_init__(self) -> None:
        for nome in ("pares", "impares", "primos", "moldura", "miolo", "soma"):
            normalizada = _validar_faixa(nome, getattr(self, nome))
            if nome in ("pares", "impares", "primos", "moldura", "miolo", "soma"):
                setattr(self, nome, normalizada)
        for nome in ("quadrante_min", "quadrante_max"):
            valor = getattr(self, nome)
            if valor is None:
                continue
            if not _eh_int(valor):
                raise ValidacaoError(f"filtro {nome} deve ser inteiro")
            valor = int(valor)
            if valor < 0:
                raise ValidacaoError(f"filtro {nome} não pode ser negativo")
            setattr(self, nome, valor)
        if (
            self.quadrante_min is not None
            and self.quadrante_max is not None
            and self.quadrante_min > self.quadrante_max
        ):
            raise ValidacaoError(
                f"filtro de quadrante: mínimo {self.quadrante_min} maior que o "
                f"máximo {self.quadrante_max}"
            )

    def ativo(self) -> bool:
        """True se qualquer filtro estiver definido."""
        return any(
            getattr(self, nome) is not None
            for nome in (
                "pares",
                "impares",
                "primos",
                "moldura",
                "miolo",
                "soma",
                "quadrante_min",
                "quadrante_max",
            )
        )

    def como_dict(self) -> dict:
        """Representação serializável (inclui os campos inativos como ``None``)."""
        return asdict(self)


@dataclass
class LotteryConfig:
    """Configuração do gerador de uma modalidade."""

    qtd_jogos: int = 1
    dezenas_por_jogo: int | None = None  # None -> spec.qtd_padrao
    filtros: FiltroConfig = field(default_factory=FiltroConfig)
    dezenas_fixas: list[int] = field(default_factory=list)
    dezenas_excluidas: list[int] = field(default_factory=list)
    repetidas_concurso_anterior: int | None = None  # qtd EXATA a repetir
    max_repetidas: int | None = None  # teto de repetição
    contaminacao_maxima: int | None = None  # teto de sobreposição
    score_minimo: int | None = None  # None desliga o filtro de score
    padroes_linha: list[str] | None = None  # ex.: ["2-1-1-1", "2-2-1"]
    max_tentativas: int = 200_000
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.filtros is None:
            self.filtros = FiltroConfig()
        if not isinstance(self.filtros, FiltroConfig):
            raise ValidacaoError("filtros deve ser uma instância de FiltroConfig")
        if not _eh_int(self.qtd_jogos) or int(self.qtd_jogos) < 1:
            raise ValidacaoError("qtd_jogos deve ser maior ou igual a 1")
        if not _eh_int(self.max_tentativas) or int(self.max_tentativas) < 1:
            raise ValidacaoError("max_tentativas deve ser maior ou igual a 1")
        if self.dezenas_por_jogo is not None:
            if not _eh_int(self.dezenas_por_jogo) or int(self.dezenas_por_jogo) < 1:
                raise ValidacaoError("dezenas_por_jogo deve ser maior ou igual a 1")
        for nome in ("repetidas_concurso_anterior", "max_repetidas", "contaminacao_maxima"):
            valor = getattr(self, nome)
            if valor is None:
                continue
            if not _eh_int(valor) or int(valor) < 0:
                raise ValidacaoError(f"{nome} deve ser inteiro não negativo")
            setattr(self, nome, int(valor))
        if self.score_minimo is not None:
            if not _eh_int(self.score_minimo) or int(self.score_minimo) < 0:
                raise ValidacaoError("score_minimo deve ser inteiro não negativo")
            if int(self.score_minimo) > 200:
                raise ValidacaoError("score_minimo não pode passar de 200")
            self.score_minimo = int(self.score_minimo)
        if self.padroes_linha is not None:
            valor = self.padroes_linha
            if isinstance(valor, str):
                valor = [valor]
            if not isinstance(valor, (list, tuple)):
                raise ValidacaoError(
                    "padroes_linha deve ser uma lista de padrões (ex.: ['2-1-1-1'])"
                )
            normalizados: list[str] = []
            for item in valor:
                padrao = _normalizar_padrao(item)
                if padrao not in normalizados:
                    normalizados.append(padrao)
            self.padroes_linha = normalizados or None
        for nome in ("dezenas_fixas", "dezenas_excluidas"):
            valor = getattr(self, nome)
            if valor is None:
                setattr(self, nome, [])
            elif not isinstance(valor, (list, tuple)):
                raise ValidacaoError(f"{nome} deve ser uma lista de inteiros")
            else:
                itens: list[int] = []
                for item in valor:
                    if isinstance(item, bool) or not _eh_int(item):
                        raise ValidacaoError(
                            f"{nome} deve conter inteiros (recebido {item!r})"
                        )
                    itens.append(int(item))
                setattr(self, nome, itens)
        self.qtd_jogos = int(self.qtd_jogos)
        self.max_tentativas = int(self.max_tentativas)
        if self.dezenas_por_jogo is not None:
            self.dezenas_por_jogo = int(self.dezenas_por_jogo)
        if self.seed is not None and not _eh_int(self.seed):
            raise ValidacaoError("seed deve ser inteiro ou None")

    def resolver_qtd(self, spec: LotterySpec) -> int:
        """Quantidade efetiva de dezenas por jogo para o ``spec`` informado."""
        if spec.tipo == "posicional":
            qtd = int(spec.sorteadas)
            if self.dezenas_por_jogo is not None and int(self.dezenas_por_jogo) != qtd:
                raise ValidacaoError(
                    f"{spec.nome}: modalidade posicional exige exatamente {qtd} "
                    f"dezenas por jogo (recebido {self.dezenas_por_jogo})"
                )
            return qtd
        qtd = spec.qtd_padrao if self.dezenas_por_jogo is None else int(self.dezenas_por_jogo)
        if qtd < spec.aposta_min or qtd > spec.aposta_max:
            raise ValidacaoError(
                f"{spec.nome}: dezenas_por_jogo ({qtd}) fora do permitido "
                f"({spec.aposta_min} a {spec.aposta_max})"
            )
        return qtd

    def validar_contra(self, spec: LotterySpec) -> int:
        """Valida a configuração contra as regras do ``spec``.

        Retorna a quantidade efetiva de dezenas por jogo. Levanta
        :class:`ValidacaoError` em qualquer incoerência.
        """
        qtd = self.resolver_qtd(spec)
        validas = spec.dezenas_validas
        inicio = validas[0]
        fim = validas[-1]

        fixas = list(self.dezenas_fixas)
        excluidas = list(self.dezenas_excluidas)

        if len(set(fixas)) != len(fixas):
            repetidas = sorted({d for d in fixas if fixas.count(d) > 1})
            raise ValidacaoError(
                f"{spec.nome}: dezenas_fixas contém duplicatas: {repetidas}"
            )
        if len(set(excluidas)) != len(excluidas):
            repetidas = sorted({d for d in excluidas if excluidas.count(d) > 1})
            raise ValidacaoError(
                f"{spec.nome}: dezenas_excluidas contém duplicatas: {repetidas}"
            )

        for nome, lista in (("dezenas_fixas", fixas), ("dezenas_excluidas", excluidas)):
            for dezena in lista:
                if not _eh_int(dezena):
                    raise ValidacaoError(
                        f"{spec.nome}: {nome} deve conter inteiros "
                        f"(recebido {dezena!r})"
                    )
                if not inicio <= int(dezena) <= fim:
                    raise ValidacaoError(
                        f"{spec.nome}: {nome} contém {dezena} fora do intervalo "
                        f"[{inicio}, {fim}]"
                    )

        conflito = sorted(set(fixas) & set(excluidas))
        if conflito:
            raise ValidacaoError(
                f"{spec.nome}: dezenas fixas e excluídas se sobrepõem: {conflito}"
            )
        if len(fixas) > qtd:
            raise ValidacaoError(
                f"{spec.nome}: {len(fixas)} dezenas fixas para um jogo de {qtd} dezenas"
            )

        disponiveis = len(validas) - len(fixas) - len(excluidas)
        if spec.tipo == "conjunto" and disponiveis < qtd - len(fixas):
            raise ValidacaoError(
                f"{spec.nome}: restrições deixam {disponiveis} dezenas livres "
                f"para preencher {qtd - len(fixas)} posições"
            )

        if self.repetidas_concurso_anterior is not None:
            if self.repetidas_concurso_anterior > qtd:
                raise ValidacaoError(
                    f"{spec.nome}: repetidas_concurso_anterior "
                    f"({self.repetidas_concurso_anterior}) maior que o tamanho do "
                    f"jogo ({qtd})"
                )
        if self.max_repetidas is not None and self.max_repetidas > qtd:
            raise ValidacaoError(
                f"{spec.nome}: max_repetidas ({self.max_repetidas}) maior que o "
                f"tamanho do jogo ({qtd})"
            )
        if self.padroes_linha:
            if spec.tipo != "conjunto":
                raise ValidacaoError(
                    f"{spec.nome}: padrões de linha não se aplicam a modalidade "
                    "posicional (cada coluna sorteia um dígito)"
                )
            if qtd != int(spec.sorteadas):
                raise ValidacaoError(
                    f"{spec.nome}: padrões de linha usam o tamanho do sorteio "
                    f"({spec.sorteadas} dezenas); ajuste dezenas_por_jogo para "
                    f"{spec.sorteadas}"
                )
            for padrao in self.padroes_linha:
                partes = [int(parte) for parte in padrao.split("-")]
                if sum(partes) != qtd:
                    raise ValidacaoError(
                        f"{spec.nome}: padrão '{padrao}' soma {sum(partes)} "
                        f"dezenas, mas o jogo tem {qtd}"
                    )
                if len(partes) > spec.linhas:
                    raise ValidacaoError(
                        f"{spec.nome}: padrão '{padrao}' usa {len(partes)} linhas, "
                        f"mas a malha tem {spec.linhas}"
                    )
                if max(partes) > spec.colunas:
                    raise ValidacaoError(
                        f"{spec.nome}: padrão '{padrao}' concentra "
                        f"{max(partes)} dezenas numa linha de "
                        f"{spec.colunas} colunas"
                    )
        return qtd
