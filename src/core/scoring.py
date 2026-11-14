"""Sistema de score adaptativo por modalidade.

Porta o modelo da Timemania (blocos rígidos + pontuação ponderada) para um
motor genérico: as faixas ideais e os limites de corte são calibrados sobre o
histórico real de cada modalidade, em vez de valores fixos pensados só para
1..80 com 7 dezenas.

Cada jogo recebe de 0 a 140 pontos (7 critérios de 20) e é aprovado quando
alcança o limiar da modalidade. Modalidades posicionais (Super Sete) usam
critérios próprios de coluna e escala de 100 pontos.

Interpretação estatística: o score mede **tipicidade** (quão comum é o jogo
entre sorteios aleatórios), não qualidade nem chance de acerto, já que todo
jogo válido tem a mesma probabilidade. Por isso, a calibração padrão
(``fonte="nulo"``) usa uma amostra grande de sorteios *simulados sob a hipótese
nula* (uniforme), em vez de ajustar faixas a algumas dezenas de concursos
históricos (o que seria ajuste ao ruído). O histórico real entra só como
auditoria: a taxa de aprovação observada deve ser compatível com a taxa
nominal esperada ao acaso (``taxa_nominal``), com intervalo de Wilson.
"""

from __future__ import annotations

import copy
import random
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

import pandas as pd

from . import filters, nulo
from .models import LotterySpec

__all__ = [
    "PerfilScore",
    "calibrar",
    "avaliar",
    "padrao_linhas",
    "frequencias_padroes",
    "top_padroes",
    "cobertura_padroes",
    "CRITERIOS_CONJUNTO",
    "CRITERIOS_POSICIONAL",
]

CRITERIOS_CONJUNTO = (
    "soma",
    "pares",
    "primos",
    "linhas",
    "quadrantes",
    "repeticao",
    "consecutivos",
)
CRITERIOS_POSICIONAL = ("soma", "pares", "primos", "repeticao", "concentracao")

_METRICA = {"linhas": "max_linha", "concentracao": "max_digito"}
#: Tamanho da amostra simulada (hipótese nula) usada na calibração padrão.
AMOSTRA_NULO = 4000
SEMENTE_NULO = 20260101

_PONTOS_IDEAL = 20
_PONTOS_OK = 10
_PONTOS_FRACO = 5


# --------------------------------------------------------------------------
# percentis
# --------------------------------------------------------------------------
def _percentil(valores: Sequence[float], fracao: float) -> float:
    """Percentil simples por posição (sem interpolação), tolerante a vazio."""
    if not valores:
        return 0.0
    ordenados = sorted(float(v) for v in valores)
    indice = (len(ordenados) - 1) * float(fracao)
    inferior = int(indice)
    superior = min(inferior + 1, len(ordenados) - 1)
    peso = indice - inferior
    return ordenados[inferior] * (1 - peso) + ordenados[superior] * peso


def _faixa(valores: Sequence[float], de: float, ate: float, inteira: bool = True):
    minimo = _percentil(valores, de)
    maximo = _percentil(valores, ate)
    if inteira:
        minimo = int(round(minimo))
        maximo = int(round(maximo))
    if minimo > maximo:
        minimo, maximo = maximo, minimo
    return (minimo, maximo)


# --------------------------------------------------------------------------
# métricas
# --------------------------------------------------------------------------
def _consecutivos(ordenado: Sequence[int]) -> int:
    return sum(
        1 for esquerda, direita in zip(ordenado, ordenado[1:]) if direita == esquerda + 1
    )


def _padrao_linhas(contagem: Sequence[int]) -> str:
    return "-".join(str(v) for v in sorted(contagem, reverse=True))


def padrao_linhas(jogo: Sequence[int], spec: LotterySpec) -> str:
    """Assinatura de distribuição do jogo pelas linhas da malha.

    Ex.: na Quina (10 colunas), um jogo com 2 dezenas na primeira linha e 1 em
    três outras linhas vira ``2-1-1-1``.
    """
    if spec.tipo == "posicional":
        return ""
    linhas = [
        (int(d) - spec.inicio) // spec.colunas for d in sorted(int(d) for d in jogo)
    ]
    contagem: dict[int, int] = {}
    for linha in linhas:
        contagem[linha] = contagem.get(linha, 0) + 1
    return _padrao_linhas(contagem.values())


def frequencias_padroes(
    spec: LotterySpec,
    historico: pd.DataFrame | None,
    limite: int = 8,
) -> list[dict[str, Any]]:
    """Padrões de linha mais frequentes no histórico, do mais comum ao menos."""
    draws = _draws(historico)
    if spec.tipo == "posicional" or not draws:
        return []
    contagem: dict[str, int] = {}
    for dezenas in draws:
        padrao = padrao_linhas(dezenas, spec)
        contagem[padrao] = contagem.get(padrao, 0) + 1
    total = sum(contagem.values())
    ordenado = sorted(contagem.items(), key=lambda item: (-item[1], item[0]))
    return [
        {
            "padrao": padrao,
            "quantidade": quantidade,
            "percentual": round(100 * quantidade / total, 1) if total else 0.0,
        }
        for padrao, quantidade in ordenado[: max(1, int(limite))]
    ]


def top_padroes(
    spec: LotterySpec,
    historico: pd.DataFrame | None,
    n: int = 3,
) -> list[str]:
    """Os ``n`` padrões de linha mais frequentes no histórico."""
    return [item["padrao"] for item in frequencias_padroes(spec, historico, limite=n)]


def cobertura_padroes(
    spec: LotterySpec,
    historico: pd.DataFrame | None,
    padroes: Sequence[str],
) -> float:
    """Percentual de concursos cobertos por um conjunto de padrões."""
    alvo = set(padroes)
    itens = [
        item
        for item in frequencias_padroes(spec, historico, limite=10_000)
        if item["padrao"] in alvo
    ]
    return round(sum(item["percentual"] for item in itens), 1)


def metricas_conjunto(
    jogo: Sequence[int],
    spec: LotterySpec,
    anterior: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Métricas do modelo para um jogo de conjunto (dezenas distintas)."""
    ordenado = sorted(int(d) for d in jogo)
    linhas = [(d - 1) // spec.colunas for d in ordenado]
    contagem = list({linha: linhas.count(linha) for linha in set(linhas)}.values())
    quadrantes = filters.contar_quadrantes(
        ordenado, spec.universo, spec.colunas, spec.inicio
    )
    return {
        "soma": sum(ordenado),
        "pares": filters.contar_pares(ordenado),
        "primos": filters.contar_primos(ordenado),
        "max_linha": max(contagem) if contagem else 0,
        "quadrantes": sum(1 for q in quadrantes if q > 0),
        "consecutivos": _consecutivos(ordenado),
        "repeticao": len(set(ordenado) & {int(d) for d in anterior})
        if anterior
        else 0,
        "primeiro": ordenado[0] if ordenado else 0,
        "ultimo": ordenado[-1] if ordenado else 0,
        "amplitude": (ordenado[-1] - ordenado[0]) if ordenado else 0,
        "padrao_linhas": _padrao_linhas(contagem),
    }


def metricas_posicional(
    jogo: Sequence[int],
    spec: LotterySpec,
    anterior: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Métricas do modelo para a Super Sete (dígitos por coluna)."""
    valores = [int(d) for d in jogo]
    contagem = {}
    for digito in valores:
        contagem[digito] = contagem.get(digito, 0) + 1
    repeticao = (
        sum(1 for atual, antes in zip(valores, anterior) if atual == antes)
        if anterior
        else 0
    )
    return {
        "soma": sum(valores),
        "pares": sum(1 for d in valores if d % 2 == 0),
        "primos": len(set(valores) & filters.PRIMOS),
        "max_digito": max(contagem.values()) if contagem else 0,
        "repeticao": repeticao,
        "padrao_linhas": "-".join(str(v) for v in sorted(contagem.values(), reverse=True)),
    }


# --------------------------------------------------------------------------
# perfil
# --------------------------------------------------------------------------
@dataclass
class PerfilScore:
    """Faixas e cortes calibrados para uma modalidade."""

    modalidade: str
    posicional: bool
    universo: int
    sorteadas: int
    colunas: int
    inicio: int
    limiar: int
    maximo: int
    amostra: int
    aderencia: float
    ideal: dict[str, tuple[float, float]] = field(default_factory=dict)
    ok: dict[str, tuple[float, float]] = field(default_factory=dict)
    corte: dict[str, Any] = field(default_factory=dict)
    criterios: tuple[str, ...] = CRITERIOS_CONJUNTO
    #: "nulo" (simulação sob H0, padrão) ou "historico" (faixas ajustadas ao histórico)
    fonte: str = "historico"
    #: taxa de aprovação esperada ao acaso (%), medida na amostra simulada
    taxa_nominal: float = 0.0
    #: tamanho da amostra simulada usada na calibração (0 quando fonte="historico")
    amostra_nulo: int = 0
    #: aprovação observada no histórico real (%), com IC de Wilson de 95%
    aderencia_hist: float | None = None
    aderencia_ic: tuple[float, float] | None = None
    amostra_hist: int = 0

    def como_dict(self) -> dict:
        """Versão serializável (usada pelo dashboard)."""
        dados = asdict(self)
        dados["ideal"] = {k: list(v) for k, v in self.ideal.items()}
        dados["ok"] = {k: list(v) for k, v in self.ok.items()}
        dados["criterios"] = list(self.criterios)
        dados["aderencia_ic"] = (
            list(self.aderencia_ic) if self.aderencia_ic is not None else None
        )
        return dados

    # ------------------------------------------------------------------ score
    def avaliar(
        self, jogo: Sequence[int], anterior: Sequence[int] | None = None
    ) -> dict[str, Any]:
        if self.posicional:
            return self._avaliar_posicional(jogo, anterior)
        return self._avaliar_conjunto(jogo, anterior)

    def _fora_dos_cortes(self, m: dict[str, Any]) -> str | None:
        corte = self.corte
        if m["soma"] < corte["soma"][0] or m["soma"] > corte["soma"][1]:
            return f"SOMA({m['soma']})"
        if m["primeiro"] > corte["primeiro"]:
            return f"EXTREMOS[{m['primeiro']}-{m['ultimo']}]"
        if m["ultimo"] < corte["ultimo"]:
            return f"EXTREMOS[{m['primeiro']}-{m['ultimo']}]"
        if m["amplitude"] < corte["amplitude"]:
            return f"AMPLITUDE({m['amplitude']})"
        if m["max_linha"] > corte["max_linha"]:
            return f"CONCENTRACAO_LINHA({m['max_linha']})"
        if m["quadrantes"] < corte["quadrantes"]:
            return f"QUADRANTES({m['quadrantes']})"
        if m["consecutivos"] > corte["consecutivos"]:
            return f"CONSECUTIVOS({m['consecutivos']})"
        if m["repeticao"] > corte["repeticao"]:
            return f"REP_ANTERIOR({m['repeticao']})"
        return None

    def _avaliar_conjunto(
        self, jogo: Sequence[int], anterior: Sequence[int] | None
    ) -> dict[str, Any]:
        m = metricas_conjunto(jogo, _spec_ficticio(self), anterior)
        bloqueio = self._fora_dos_cortes(m)
        if bloqueio:
            return {
                "score": 0,
                "aprovado": False,
                "status": f"REJ (0pts: {bloqueio})",
                "metricas": m,
                "limiar": self.limiar,
            }
        score = 0
        falhas: list[str] = []
        for criterio in self.criterios:
            valor = m[_METRICA.get(criterio, criterio)]
            ideal = self.ideal.get(criterio)
            ok = self.ok.get(criterio)
            if ideal and ideal[0] <= valor <= ideal[1]:
                score += _PONTOS_IDEAL
            elif ok and ok[0] <= valor <= ok[1]:
                score += _PONTOS_OK
            elif criterio in ("pares", "primos"):
                falhas.append(f"{criterio.upper()}({valor})")
            else:
                score += _PONTOS_FRACO
        aprovado = score >= self.limiar
        status = (
            f"APROV ({score}pts)"
            if aprovado
            else f"REJ ({score}pts: {'/'.join(falhas) or 'FORA_DAS_FAIXAS'})"
        )
        return {
            "score": score,
            "aprovado": aprovado,
            "status": status,
            "metricas": m,
            "limiar": self.limiar,
        }

    def _avaliar_posicional(
        self, jogo: Sequence[int], anterior: Sequence[int] | None
    ) -> dict[str, Any]:
        m = metricas_posicional(jogo, _spec_ficticio(self), anterior)
        corte = self.corte
        if m["soma"] < corte["soma"][0] or m["soma"] > corte["soma"][1]:
            return {
                "score": 0,
                "aprovado": False,
                "status": f"REJ (0pts: SOMA({m['soma']}))",
                "metricas": m,
                "limiar": self.limiar,
            }
        if m["repeticao"] > corte["repeticao"]:
            return {
                "score": 0,
                "aprovado": False,
                "status": f"REJ (0pts: REP_ANTERIOR({m['repeticao']}))",
                "metricas": m,
                "limiar": self.limiar,
            }
        score = 0
        falhas: list[str] = []
        for criterio in self.criterios:
            valor = m[_METRICA.get(criterio, criterio)]
            ideal = self.ideal.get(criterio)
            ok = self.ok.get(criterio)
            if ideal and ideal[0] <= valor <= ideal[1]:
                score += _PONTOS_IDEAL
            elif ok and ok[0] <= valor <= ok[1]:
                score += _PONTOS_OK
            else:
                falhas.append(f"{criterio.upper()}({valor})")
        aprovado = score >= self.limiar
        return {
            "score": score,
            "aprovado": aprovado,
            "status": (
                f"APROV ({score}pts)"
                if aprovado
                else f"REJ ({score}pts: {'/'.join(falhas) or 'FORA_DAS_FAIXAS'})"
            ),
            "metricas": m,
            "limiar": self.limiar,
        }


def _spec_ficticio(perfil: PerfilScore) -> LotterySpec:
    """Spec mínimo para reutilizar as métricas de malha (sem regras oficiais)."""
    if perfil.posicional:
        return LotterySpec(
            key="posicional",
            nome="posicional",
            universo=perfil.universo,
            sorteadas=perfil.sorteadas,
            aposta_min=perfil.sorteadas,
            aposta_max=perfil.sorteadas,
            colunas=perfil.sorteadas,
            tipo="posicional",
            inicio=0,
        )
    return LotterySpec(
        key="conjunto",
        nome="conjunto",
        universo=perfil.universo,
        sorteadas=perfil.sorteadas,
        aposta_min=perfil.sorteadas,
        aposta_max=perfil.sorteadas,
        colunas=perfil.colunas,
        inicio=perfil.inicio,
    )


# --------------------------------------------------------------------------
# calibração
# --------------------------------------------------------------------------
def _draws(historico: pd.DataFrame | None) -> list[list[int]]:
    if historico is None or getattr(historico, "empty", True):
        return []
    return [
        [int(d) for d in linha]
        for linha in historico["dezenas"].tolist()
        if linha is not None
    ]


def _calibrar_conjunto(
    spec: LotterySpec, draws: list[list[int]]
) -> PerfilScore:
    metricas = [
        metricas_conjunto(atual, spec, anterior)
        for anterior, atual in zip(draws, draws[1:])
    ]
    if not metricas:
        metricas = [metricas_conjunto(d, spec) for d in draws]
    somas = [m["soma"] for m in metricas]
    pares = [m["pares"] for m in metricas]
    primos = [m["primos"] for m in metricas]
    max_linha = [m["max_linha"] for m in metricas]
    quadrantes = [m["quadrantes"] for m in metricas]
    repeticao = [m["repeticao"] for m in metricas]
    consecutivos = [m["consecutivos"] for m in metricas]
    amplitude = [m["amplitude"] for m in metricas]
    primeiro = [m["primeiro"] for m in metricas]
    ultimo = [m["ultimo"] for m in metricas]

    ideal = {
        "soma": _faixa(somas, 0.25, 0.75),
        "pares": _faixa(pares, 0.35, 0.65),
        "primos": _faixa(primos, 0.35, 0.65),
        "linhas": (min(max_linha), max(1, _percentil(max_linha, 0.55))),
        "quadrantes": (
            max(1, int(_percentil(quadrantes, 0.5))),
            max(1, int(_percentil(quadrantes, 1.0))),
        ),
        "repeticao": (min(repeticao), max(0, _percentil(repeticao, 0.5))),
        "consecutivos": (0, max(0, _percentil(consecutivos, 0.5))),
    }
    ideal["linhas"] = (min(ideal["linhas"]), max(ideal["linhas"]))
    ok = {
        "soma": _faixa(somas, 0.1, 0.9),
        "pares": _faixa(pares, 0.1, 0.9),
        "primos": _faixa(primos, 0.1, 0.9),
        "linhas": (min(max_linha), max(1, _percentil(max_linha, 0.9))),
        "quadrantes": (1, max(1, int(_percentil(quadrantes, 1.0)))),
        "repeticao": (0, max(0, _percentil(repeticao, 0.9))),
        "consecutivos": (0, max(0, _percentil(consecutivos, 0.9))),
    }
    corte = {
        "soma": _faixa(somas, 0.02, 0.98),
        "primeiro": max(1, int(_percentil(primeiro, 0.98))),
        "ultimo": int(_percentil(ultimo, 0.02)),
        "amplitude": int(_percentil(amplitude, 0.02)),
        "max_linha": max(1, int(_percentil(max_linha, 0.98))),
        "quadrantes": max(1, int(_percentil(quadrantes, 0.02))),
        "consecutivos": max(0, int(_percentil(consecutivos, 0.98))),
        "repeticao": max(0, int(_percentil(repeticao, 0.9))),
    }

    perfil = PerfilScore(
        modalidade=spec.nome,
        posicional=False,
        universo=spec.universo,
        sorteadas=len(draws[0]) if draws else spec.sorteadas,
        colunas=spec.colunas,
        inicio=spec.inicio,
        limiar=85,
        maximo=140,
        amostra=len(metricas),
        aderencia=0.0,
        ideal=ideal,
        ok=ok,
        corte=corte,
        criterios=CRITERIOS_CONJUNTO,
    )
    # Limiar = percentil 65 dos scores históricos (aprox. 35% aprovados),
    # limitado à faixa 70..125 para não degenerar com histórico curto.
    provisorio = [perfil.avaliar(atual, anterior)["score"] for anterior, atual in zip(draws, draws[1:])]
    if not provisorio:
        provisorio = [perfil.avaliar(d)["score"] for d in draws]
    limiar = int(round(_percentil(provisorio, 0.65)))
    perfil.limiar = max(70, min(125, limiar))
    resultados = [perfil.avaliar(atual, anterior) for anterior, atual in zip(draws, draws[1:])]
    if resultados:
        perfil.aderencia = round(
            100 * sum(1 for r in resultados if r["aprovado"]) / len(resultados), 1
        )
    return perfil


def _calibrar_posicional(
    spec: LotterySpec, draws: list[list[int]]
) -> PerfilScore:
    metricas = [
        metricas_posicional(atual, spec, anterior)
        for anterior, atual in zip(draws, draws[1:])
    ]
    if not metricas:
        metricas = [metricas_posicional(d, spec) for d in draws]
    somas = [m["soma"] for m in metricas]
    pares = [m["pares"] for m in metricas]
    primos = [m["primos"] for m in metricas]
    repeticao = [m["repeticao"] for m in metricas]
    max_digito = [m["max_digito"] for m in metricas]

    ideal = {
        "soma": _faixa(somas, 0.25, 0.75),
        "pares": _faixa(pares, 0.35, 0.65),
        "primos": _faixa(primos, 0.3, 0.7),
        "repeticao": (0, max(0, int(_percentil(repeticao, 0.5)))),
        "concentracao": (1, max(1, int(_percentil(max_digito, 0.5)))),
    }
    ok = {
        "soma": _faixa(somas, 0.1, 0.9),
        "pares": _faixa(pares, 0.1, 0.9),
        "primos": _faixa(primos, 0.1, 0.95),
        "repeticao": (0, max(0, int(_percentil(repeticao, 0.9)))),
        "concentracao": (1, max(1, int(_percentil(max_digito, 0.95)))),
    }
    corte = {
        "soma": _faixa(somas, 0.02, 0.98),
        "repeticao": max(0, int(_percentil(repeticao, 0.95))),
    }
    perfil = PerfilScore(
        modalidade=spec.nome,
        posicional=True,
        universo=spec.universo,
        sorteadas=len(draws[0]) if draws else spec.sorteadas,
        colunas=spec.colunas,
        inicio=spec.inicio,
        limiar=65,
        maximo=100,
        amostra=len(metricas),
        aderencia=0.0,
        ideal=ideal,
        ok=ok,
        corte=corte,
        criterios=CRITERIOS_POSICIONAL,
    )
    provisorio = [perfil.avaliar(atual, anterior)["score"] for anterior, atual in zip(draws, draws[1:])]
    if not provisorio:
        provisorio = [perfil.avaliar(d)["score"] for d in draws]
    perfil.limiar = max(45, min(90, int(round(_percentil(provisorio, 0.65)))))
    resultados = [perfil.avaliar(atual, anterior) for anterior, atual in zip(draws, draws[1:])]
    if resultados:
        perfil.aderencia = round(
            100 * sum(1 for r in resultados if r["aprovado"]) / len(resultados), 1
        )
    return perfil


def _sorteios_nulos(spec: LotterySpec, alvo: int, quantidade: int, semente: int):
    """Sorteios uniformes simulados (hipótese nula), reprodutíveis."""
    rng = random.Random(semente)
    if spec.tipo == "posicional":
        return [
            [rng.randrange(spec.universo) for _ in range(alvo)]
            for _ in range(quantidade)
        ]
    base = range(spec.inicio, spec.inicio + spec.universo)
    return [sorted(rng.sample(base, alvo)) for _ in range(quantidade)]


_CACHE_NULO: dict[tuple, PerfilScore] = {}


def _perfil_nulo(spec: LotterySpec, alvo: int) -> PerfilScore:
    """Perfil calibrado só com sorteios simulados (independe do histórico)."""
    chave = (
        spec.key, spec.tipo, spec.universo, spec.sorteadas,
        spec.colunas, spec.inicio, alvo, AMOSTRA_NULO, SEMENTE_NULO,
    )
    if chave not in _CACHE_NULO:
        draws = _sorteios_nulos(spec, alvo, AMOSTRA_NULO, SEMENTE_NULO)
        if spec.tipo == "posicional":
            perfil = _calibrar_posicional(spec, draws)
        else:
            perfil = _calibrar_conjunto(spec, draws)
        perfil.fonte = "nulo"
        perfil.taxa_nominal = perfil.aderencia
        perfil.amostra_nulo = perfil.amostra
        _CACHE_NULO[chave] = perfil
    # cópia: o perfil é mutável e quem chama pode alterar faixas/cortes
    return copy.deepcopy(_CACHE_NULO[chave])


def _auditar_historico(perfil: PerfilScore, draws: list[list[int]]) -> None:
    """Anexa ao perfil a taxa de aprovação observada no histórico real."""
    pares = list(zip(draws, draws[1:]))
    if not pares:
        return
    aprovados = sum(
        1 for anterior, atual in pares if perfil.avaliar(atual, anterior)["aprovado"]
    )
    n = len(pares)
    baixo, alto = nulo.wilson(aprovados, n)
    perfil.amostra_hist = n
    perfil.aderencia_hist = round(100 * aprovados / n, 1)
    perfil.aderencia_ic = (round(100 * baixo, 1), round(100 * alto, 1))
    perfil.aderencia = perfil.aderencia_hist
    perfil.amostra = n


def calibrar(
    spec: LotterySpec,
    historico: pd.DataFrame | None,
    qtd: int | None = None,
    fonte: str = "nulo",
) -> PerfilScore:
    """Calibra o modelo de score para um tamanho de jogo.

    ``fonte="nulo"`` (padrão): faixas e limiar vêm de sorteios simulados sob a
    hipótese nula; o histórico só alimenta a auditoria (``aderencia_hist``).
    ``fonte="historico"``: comportamento anterior, faixas ajustadas ao histórico
    (sem histórico, cai numa amostra sintética de 300 sorteios).

    ``qtd`` é o tamanho do jogo que será pontuado (na Lotomania a aposta tem 50
    dezenas, mas o sorteio tem 20; os dois usam faixas próprias).
    """
    if fonte not in ("nulo", "historico"):
        raise ValueError("fonte deve ser 'nulo' ou 'historico'")
    draws = _draws(historico)
    alvo = int(qtd) if qtd else (len(draws[0]) if draws else int(spec.sorteadas))

    if fonte == "nulo":
        perfil = _perfil_nulo(spec, alvo)
        if draws and len(draws[0]) == alvo:
            _auditar_historico(perfil, draws)
        return perfil

    if not draws or len(draws[0]) != alvo:
        draws = _sorteios_nulos(spec, alvo, 300, 0)
    if spec.tipo == "posicional":
        return _calibrar_posicional(spec, draws)
    return _calibrar_conjunto(spec, draws)


def avaliar(
    spec: LotterySpec,
    jogo: Sequence[int],
    historico: pd.DataFrame | None = None,
    anterior: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Atalho: calibra (sem cache) e avalia um jogo do tamanho informado."""
    perfil = calibrar(spec, historico, qtd=len(list(jogo)))
    return perfil.avaliar(jogo, anterior)
