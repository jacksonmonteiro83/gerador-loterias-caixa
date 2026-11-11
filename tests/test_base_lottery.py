"""Testes do motor LotteryBase com subclasses locais (sem src.loterias)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import LotteryBase, LotteryConfig, LotterySpec, FiltroConfig  # noqa: E402
from src.core import stats  # noqa: E402
from src.core.models import ValidacaoError  # noqa: E402


class FakeSena(LotteryBase):
    """Loteria fictícia 60/6 no estilo Mega-Sena."""

    spec = LotterySpec(
        key="fake-sena",
        nome="Fake Sena",
        universo=60,
        sorteadas=6,
        aposta_min=6,
        aposta_max=20,
        colunas=10,
    )

    def _sortear(self) -> list[int]:
        return sorted(self.rng.sample(range(1, 61), self.qtd_efetiva))


class FakePosicional(LotteryBase):
    """Loteria fictícia posicional 7 colunas × 0-9 (estilo Super Sete)."""

    spec = LotterySpec(
        key="fake-sete",
        nome="Fake Sete",
        universo=10,
        sorteadas=7,
        aposta_min=7,
        aposta_max=7,
        colunas=7,
        tipo="posicional",
        inicio=0,
    )

    def _sortear(self) -> list[int]:
        return [self.rng.randrange(10) for _ in range(7)]

    def _permite_repeticao_estrutural(self) -> bool:
        return False


def historico_sintetico(ultimo: list[int] | None = None) -> list[dict]:
    return [
        {"concurso": 1, "dezenas": [7, 8, 9, 10, 11, 12]},
        {"concurso": 2, "dezenas": [13, 14, 15, 16, 17, 18]},
        {"concurso": 3, "dezenas": list(ultimo or [1, 2, 3, 4, 5, 6])},
    ]


def spec_valido(**overrides) -> LotterySpec:
    dados = dict(
        key="x",
        nome="X",
        universo=60,
        sorteadas=6,
        aposta_min=6,
        aposta_max=20,
        colunas=10,
    )
    dados.update(overrides)
    return LotterySpec(**dados)


# ---------------------------------------------------------------------------
# LotterySpec / FiltroConfig / LotteryConfig
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "overrides",
    [
        {"universo": 0},
        {"sorteadas": 0},
        {"sorteadas": 61},
        {"aposta_min": 21},
        {"aposta_min": 5},
        {"colunas": 0},
        {"tipo": "outro"},
        {"inicio": -1},
    ],
)
def test_spec_invalido(overrides):
    with pytest.raises(ValidacaoError):
        spec_valido(**overrides)


def test_spec_propriedades():
    spec = spec_valido()
    assert spec.qtd_padrao == 6
    assert spec.linhas == 6
    assert list(spec.dezenas_validas) == list(range(1, 61))
    posicional = FakePosicional.spec
    assert list(posicional.dezenas_validas) == list(range(10))
    assert posicional.linhas == 2


def test_filtro_config():
    filtro = FiltroConfig()
    assert filtro.ativo() is False
    assert filtro.como_dict()["pares"] is None
    assert FiltroConfig(pares=[2, 4]).pares == (2, 4)
    assert FiltroConfig(quadrante_min=1).ativo() is True
    for invalido in (
        dict(pares=(5, 2)),
        dict(soma=5),
        dict(primos=(1, 2, 3)),
        dict(quadrante_min=-1),
        dict(quadrante_min=3, quadrante_max=2),
        dict(moldura=(-1, 3)),
    ):
        with pytest.raises(ValidacaoError):
            FiltroConfig(**invalido)


def test_config_invalida():
    for invalido in (
        dict(qtd_jogos=0),
        dict(max_tentativas=0),
        dict(dezenas_por_jogo=0),
        dict(repetidas_concurso_anterior=-1),
        dict(max_repetidas=-1),
        dict(contaminacao_maxima=-1),
        dict(filtros="nada"),
        dict(seed="abc"),
    ):
        with pytest.raises(ValidacaoError):
            LotteryConfig(**invalido)


def test_validar_contra_restricoes():
    spec = FakeSena.spec
    casos = [
        dict(dezenas_fixas=[61]),
        dict(dezenas_fixas=[0]),
        dict(dezenas_fixas=[1, 1]),
        dict(dezenas_fixas=[1, 2, 3, 4, 5, 6, 7]),
        dict(dezenas_fixas=[1], dezenas_excluidas=[1]),
        dict(dezenas_excluidas=[10, 10]),
        dict(dezenas_por_jogo=5),
        dict(dezenas_por_jogo=21),
        dict(repetidas_concurso_anterior=7),
        dict(max_repetidas=7),
    ]
    for caso in casos:
        with pytest.raises(ValidacaoError):
            LotteryConfig(**caso).validar_contra(spec)


def test_posicional_exige_sete_dezenas():
    with pytest.raises(ValidacaoError):
        LotteryConfig(dezenas_por_jogo=6).validar_contra(FakePosicional.spec)


# ---------------------------------------------------------------------------
# validação de jogos
# ---------------------------------------------------------------------------
def test_validar_aceita_jogo_correto():
    loteria = FakeSena(LotteryConfig(seed=1))
    loteria.validar([1, 2, 3, 4, 5, 6])
    assert loteria.jogo_valido([60, 59, 58, 57, 56, 55]) is True


@pytest.mark.parametrize(
    "jogo",
    [
        [1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5, 6, 7],
        [1, 2, 3, 4, 5, 5],
        [0, 2, 3, 4, 5, 6],
        [1, 2, 3, 4, 5, 61],
        [1, 2, 3, 4, 5, True],
        [1, 2, 3, 4, 5, 6.5],
        [1, 2, 3, 4, 5, "6"],
        "123456",
    ],
)
def test_validar_rejeita_jogos_invalidos(jogo):
    loteria = FakeSena(LotteryConfig(seed=1))
    with pytest.raises(ValidacaoError):
        loteria.validar(jogo)
    assert loteria.jogo_valido(jogo) is False


def test_validar_posicional():
    loteria = FakePosicional(LotteryConfig(seed=1))
    loteria.validar([0, 0, 1, 2, 9, 9, 9])
    for invalido in (
        [1, 2, 3],
        [0, 1, 2, 3, 4, 5, 10],
        [0, 1, 2, 3, 4, 5, -1],
        [0, 1, 2, 3, 4, 5, True],
        [0, 1, 2, 3, 4, 5, "6"],
    ):
        with pytest.raises(ValidacaoError):
            loteria.validar(invalido)


def test_intervalo_e_regras():
    sena = FakeSena(LotteryConfig(seed=1))
    assert sena.intervalo() == (1, 60)
    regras = sena.regras()
    assert regras["key"] == "fake-sena"
    assert regras["nome"] == "Fake Sena"
    assert regras["qtd_efetiva"] == 6
    assert regras["intervalo"] == (1, 60)
    assert FakePosicional(LotteryConfig(seed=1)).intervalo() == (0, 9)


def test_classe_sem_spec_nao_instancia():
    class SemSpec(LotteryBase):
        def _sortear(self) -> list[int]:
            return []

    with pytest.raises(ValidacaoError):
        SemSpec()


# ---------------------------------------------------------------------------
# geração
# ---------------------------------------------------------------------------
def test_geracao_respeita_fixas_e_excluidas():
    config = LotteryConfig(
        qtd_jogos=100,
        dezenas_fixas=[10, 23],
        dezenas_excluidas=[4, 13],
        seed=7,
    )
    loteria = FakeSena(config)
    jogos = loteria.gerar()
    assert len(jogos) == 100
    assert len({tuple(j) for j in jogos}) == 100
    for jogo in jogos:
        assert 10 in jogo and 23 in jogo
        assert 4 not in jogo and 13 not in jogo
        assert len(jogo) == 6
        loteria.validar(jogo)


def test_geracao_posicional_respeita_fixas_e_excluidas():
    config = LotteryConfig(
        qtd_jogos=30, dezenas_fixas=[3], dezenas_excluidas=[4], seed=5
    )
    loteria = FakePosicional(config)
    jogos = loteria.gerar()
    assert len(jogos) == 30
    assert len({tuple(j) for j in jogos}) == 30
    for jogo in jogos:
        assert len(jogo) == 7
        assert 3 in jogo
        assert 4 not in jogo
        loteria.validar(jogo)


def test_posicional_com_varias_excluidas():
    config = LotteryConfig(
        qtd_jogos=5, dezenas_excluidas=[0, 1, 2, 3, 4], seed=9
    )
    loteria = FakePosicional(config)
    for jogo in loteria.gerar():
        assert not set(jogo) & {0, 1, 2, 3, 4}
        loteria.validar(jogo)


def test_repetidas_concurso_anterior_exato():
    config = LotteryConfig(
        qtd_jogos=20, repetidas_concurso_anterior=2, seed=11
    )
    loteria = FakeSena(config, historico=historico_sintetico())
    assert loteria.ultimo == {1, 2, 3, 4, 5, 6}
    for jogo in loteria.gerar():
        assert len(set(jogo) & {1, 2, 3, 4, 5, 6}) == 2
        assert loteria.analisar(jogo)["repetidas_ultimo"] == 2


def test_repetidas_exato_ignora_dezenas_fixas():
    config = LotteryConfig(
        qtd_jogos=10,
        dezenas_fixas=[1, 2],
        repetidas_concurso_anterior=2,
        seed=3,
    )
    loteria = FakeSena(config, historico=historico_sintetico())
    for jogo in loteria.gerar():
        assert set(jogo) & {1, 2} == {1, 2}
        # as fixas não entram na contagem: exatamente 2 de {3, 4, 5, 6}
        assert len(set(jogo) & {3, 4, 5, 6}) == 2
        assert loteria.analisar(jogo)["repetidas_ultimo"] == 2


def test_repetidas_sem_historico_levanta():
    with pytest.raises(ValidacaoError, match="repetidas_concurso_anterior"):
        FakeSena(LotteryConfig(repetidas_concurso_anterior=2))
    with pytest.raises(ValidacaoError, match="repetidas_concurso_anterior"):
        FakeSena(
            LotteryConfig(repetidas_concurso_anterior=2),
            historico=stats.normalizar(None),
        )


def test_max_repetidas():
    config = LotteryConfig(qtd_jogos=20, max_repetidas=1, seed=17)
    loteria = FakeSena(config, historico=historico_sintetico())
    for jogo in loteria.gerar():
        assert len(set(jogo) & {1, 2, 3, 4, 5, 6}) <= 1


def test_contaminacao_maxima():
    historico = historico_sintetico()
    config = LotteryConfig(qtd_jogos=15, contaminacao_maxima=2, seed=23)
    loteria = FakeSena(config, historico=historico)
    for jogo in loteria.gerar():
        assert stats.contaminacao(jogo, loteria.historico) <= 2
        assert loteria.analisar(jogo)["contaminacao"] <= 2


def test_filtro_impossivel_levanta_runtime_error():
    config = LotteryConfig(
        filtros=FiltroConfig(pares=(0, 0), impares=(0, 0)),
        max_tentativas=300,
        seed=1,
    )
    loteria = FakeSena(config)
    with pytest.raises(RuntimeError, match="tentativas"):
        loteria.gerar_jogo()
    with pytest.raises(RuntimeError, match="tentativas"):
        FakeSena(LotteryConfig(qtd_jogos=2, filtros=config.filtros, max_tentativas=300)).gerar()


def test_gerar_deduplica():
    loteria = FakeSena(LotteryConfig(qtd_jogos=10, seed=42))
    jogos = loteria.gerar()
    assert len(jogos) == 10
    assert len({tuple(j) for j in jogos}) == 10


def test_determinismo_com_seed():
    config = LotteryConfig(qtd_jogos=5, seed=99)
    primeiro = FakeSena(config).gerar()
    segundo = FakeSena(LotteryConfig(qtd_jogos=5, seed=99)).gerar()
    assert primeiro == segundo

    terceiro = FakeSena(LotteryConfig(qtd_jogos=5, seed=100)).gerar()
    assert terceiro != primeiro


def test_dezenas_por_jogo_configuravel():
    loteria = FakeSena(LotteryConfig(qtd_jogos=10, dezenas_por_jogo=8, seed=2))
    assert loteria.qtd_efetiva == 8
    for jogo in loteria.gerar():
        assert len(jogo) == 8
        loteria.validar(jogo)


# ---------------------------------------------------------------------------
# análise e filtros
# ---------------------------------------------------------------------------
def test_analisar_jogo_conjunto():
    loteria = FakeSena(
        LotteryConfig(seed=1),
        historico=stats.normalizar(historico_sintetico()),
    )
    resultado = loteria.analisar([6, 5, 4, 3, 2, 1])
    assert resultado["jogo"] == [1, 2, 3, 4, 5, 6]
    assert resultado["soma"] == 21
    assert resultado["valido"] is True
    assert resultado["repetidas_ultimo"] == 6
    assert resultado["contaminacao"] == 6
    assert set(resultado) >= {
        "pares",
        "impares",
        "primos",
        "moldura",
        "miolo",
        "soma",
        "quadrantes",
        "total",
        "min",
        "max",
        "media",
        "jogo",
        "repetidas_ultimo",
        "contaminacao",
        "valido",
    }


def test_analisar_jogo_posicional():
    loteria = FakePosicional(
        LotteryConfig(seed=1),
        historico=stats.normalizar(
            [{"concurso": 1, "dezenas": [1, 1, 2, 3, 4, 5, 6]}]
        ),
    )
    resultado = loteria.analisar([1, 1, 2, 3, 4, 5, 6])
    assert resultado["jogo"] == [1, 1, 2, 3, 4, 5, 6]
    assert resultado["soma"] == 22
    assert resultado["total"] == 7
    assert resultado["digitos_repetidos"] == 1
    assert resultado["moldura"] == 0
    assert resultado["quadrantes"] == []
    assert resultado["repetidas_ultimo"] == 7
    assert resultado["valido"] is True


def test_atende_filtros_e_explicar():
    config = LotteryConfig(filtros=FiltroConfig(pares=(3, 3), soma=(20, 30)))
    loteria = FakeSena(config)
    assert loteria.atende_filtros([1, 2, 3, 4, 5, 6]) is True
    assert loteria.explicar([1, 2, 3, 4, 5, 6]) == []

    assert loteria.atende_filtros([2, 4, 6, 8, 10, 12]) is False
    motivos = loteria.explicar([2, 4, 6, 8, 10, 12])
    assert any("pares=6" in motivo for motivo in motivos)
    assert any("soma=42" in motivo for motivo in motivos)

    invalido = loteria.explicar([1, 2, 3])
    assert len(invalido) == 1
    assert "6 dezenas" in invalido[0]


def test_moldura_ignorada_quando_sem_repeticao_estrutural():
    config = LotteryConfig(
        filtros=FiltroConfig(moldura=(5, 5), miolo=(0, 0)),
        max_tentativas=50,
        seed=4,
    )
    loteria = FakePosicional(config)
    assert loteria._permite_repeticao_estrutural() is False
    jogo = loteria.gerar_jogo()
    assert len(jogo) == 7
    assert loteria.explicar(jogo) == []


def test_probabilidade_filtro():
    sem_filtros = FakeSena(LotteryConfig(seed=1))
    assert sem_filtros.probabilidade_filtro(200) == 1.0

    impossivel = FakeSena(
        LotteryConfig(filtros=FiltroConfig(pares=(0, 0), impares=(0, 0)), seed=1)
    )
    assert impossivel.probabilidade_filtro(50) == 0.0

    com_filtro = FakeSena(
        LotteryConfig(filtros=FiltroConfig(pares=(3, 3)), seed=1)
    )
    taxa = com_filtro.probabilidade_filtro(500)
    assert 0.0 < taxa < 1.0


def test_historico_e_ultimo_normalizados():
    loteria = FakeSena(
        LotteryConfig(seed=1),
        historico=[
            {"concurso": 2, "dezenas": [7, 8, 9, 10, 11, 12]},
            {"concurso": 1, "dezenas": [1, 2, 3, 4, 5, 6]},
        ],
    )
    assert loteria.historico["concurso"].tolist() == [1, 2]
    assert loteria.ultimo == {7, 8, 9, 10, 11, 12}
    assert loteria.historico["dezenas"].tolist() == [
        [1, 2, 3, 4, 5, 6],
        [7, 8, 9, 10, 11, 12],
    ]
