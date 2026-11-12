"""Testes do cliente HTTP, do parser e do orquestrador do ETL."""

from __future__ import annotations

import requests
import pytest

from src.etl import atualizar_loteria, atualizar_todas
from src.etl import loader, scraper


PAYLOAD_MEGA = {
    "numero": 2631,
    "dataApuracao": "07/10/2023",
    "listaDezenas": ["10", "04", "33", "21", "60", "07"],
    "listaDezenasSegundoSorteio": ["01", "02", "03", "04", "05", "06"],
    "listaRateioPremio": [
        {"descricaoFaixa": "6 acertos", "numeroDeGanhadores": 0, "valorPremio": 0.0}
    ],
    "valorAcumuladoProximoConcurso": 12345678.9,
}

PAYLOAD_SUPER_SETE = {
    "numero": 700,
    "dataApuracao": "01/02/2024",
    "listaDezenas": ["5", "1", "9", "0", "3", "2", "7"],
    "valorAcumuladoProximoConcurso": "1.500.000,00",
}


class RespostaFalsa:
    """Resposta HTTP mínima para os testes (sem rede)."""

    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class SessaoFalsa:
    """Sessão injetável que devolve respostas pré-programadas."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.chamadas.append((url, kwargs))
        item = self.respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


def _registro(concurso: int, loteria: str = "mega-sena") -> dict:
    dezenas = (
        [1, 2, 3, 4, 5, 6, 7]
        if loteria == "super-sete"
        else [1, 2, 3, 4, 5, 6]
    )
    return {
        "loteria": loteria,
        "concurso": concurso,
        "data": None,
        "dezenas": dezenas,
        "premiacoes": None,
        "acumulado": None,
    }


def test_slugs_cobrem_as_oito_modalidades():
    assert scraper.SLUGS == {
        "mega-sena": "megasena",
        "lotofacil": "lotofacil",
        "quina": "quina",
        "lotomania": "lotomania",
        "timemania": "timemania",
        "dupla-sena": "duplasena",
        "dia-de-sorte": "diadesorte",
        "super-sete": "supersete",
    }
    assert set(loader.CATALOGO) == set(scraper.SLUGS)


def test_normalizar_resposta_formato_caixa():
    registro = scraper.normalizar_resposta(PAYLOAD_MEGA, "mega-sena")

    assert registro is not None
    assert registro["loteria"] == "mega-sena"
    assert registro["concurso"] == 2631
    assert registro["data"] == "2023-10-07"
    assert registro["dezenas"] == [4, 7, 10, 21, 33, 60]
    assert registro["premiacoes"] == PAYLOAD_MEGA["listaRateioPremio"]
    assert registro["acumulado"] == pytest.approx(12345678.9)


def test_normalizar_resposta_super_sete_preserva_posicoes():
    registro = scraper.normalizar_resposta(PAYLOAD_SUPER_SETE, "super-sete")

    assert registro is not None
    assert registro["loteria"] == "super-sete"
    assert registro["dezenas"] == [5, 1, 9, 0, 3, 2, 7]
    assert registro["data"] == "2024-02-01"
    assert registro["acumulado"] == pytest.approx(1_500_000.0)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"numero": 1},
        {"numero": 1, "listaDezenas": []},
        {"numero": 1, "listaDezenas": ["x"]},
    ],
)
def test_normalizar_resposta_tolerante_a_payloads_invalidos(payload):
    assert scraper.normalizar_resposta(payload, "mega-sena") is None


def test_buscar_concurso_usa_headers_e_timeout():
    sessao = SessaoFalsa([RespostaFalsa(200, PAYLOAD_MEGA)])
    registro = scraper.buscar_concurso("megasena", 2631, session=sessao)

    assert registro is not None
    assert registro["concurso"] == 2631
    url, kwargs = sessao.chamadas[0]
    assert url == (
        "https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena/2631"
    )
    assert kwargs["timeout"] == 15
    assert "Mozilla" in kwargs["headers"]["User-Agent"]
    assert kwargs["headers"]["Accept"] == "application/json"
    assert "verify" not in kwargs


def test_buscar_concurso_faz_retry_com_backoff(monkeypatch):
    monkeypatch.setattr(scraper.time, "sleep", lambda *_: None)
    sessao = SessaoFalsa(
        [requests.Timeout("timeout"), RespostaFalsa(200, PAYLOAD_MEGA)]
    )

    registro = scraper.buscar_concurso("megasena", 2631, session=sessao)

    assert registro is not None
    assert len(sessao.chamadas) == 2


def test_buscar_concurso_cai_para_endpoint_alternativo():
    sessao = SessaoFalsa(
        [RespostaFalsa(404), RespostaFalsa(200, PAYLOAD_MEGA)]
    )

    registro = scraper.buscar_concurso("mega-sena", 2631, session=sessao)

    assert registro is not None
    assert "herokuapp.com" in sessao.chamadas[1][0]


def test_buscar_concurso_sem_numero_usa_ultimo_da_lista():
    lista = [
        {"numero": 1, "listaDezenas": ["1", "2", "3", "4", "5", "6"]},
        {"numero": 2, "listaDezenas": ["6", "5", "4", "3", "2", "1"]},
    ]
    sessao = SessaoFalsa([RespostaFalsa(404), RespostaFalsa(200, lista)])

    registro = scraper.buscar_concurso("mega-sena", None, session=sessao)

    assert registro is not None
    assert registro["concurso"] == 2
    assert sessao.chamadas[1][0] == (
        "https://loteriascaixa-api.herokuapp.com/api/megasena"
    )


def test_buscar_concurso_sem_numero_escolhe_o_maior_da_lista_invertida():
    lista = [
        {"numero": 3084, "listaDezenas": ["6", "14", "22", "30", "31", "37"]},
        {"numero": 3083, "listaDezenas": ["1", "2", "3", "4", "5", "6"]},
        {"numero": 2985, "listaDezenas": ["7", "8", "9", "10", "11", "12"]},
    ]
    sessao = SessaoFalsa([RespostaFalsa(404), RespostaFalsa(200, lista)])

    registro = scraper.buscar_concurso("mega-sena", None, session=sessao)

    assert registro is not None
    assert registro["concurso"] == 3084


def test_super_sete_usa_endpoint_espelho_primeiro():
    sessao = SessaoFalsa([RespostaFalsa(200, PAYLOAD_SUPER_SETE)])

    registro = scraper.buscar_concurso("super-sete", 700, session=sessao)

    assert registro is not None
    assert sessao.chamadas[0][0] == (
        "https://loteriascaixa-api.herokuapp.com/api/supersete/700"
    )


def test_buscar_concurso_retorna_none_quando_tudo_falha():
    sessao = SessaoFalsa(
        [RespostaFalsa(404), RespostaFalsa(404), RespostaFalsa(404)]
    )
    assert scraper.buscar_concurso("mega-sena", 1, session=sessao) is None


def test_baixar_intervalo_para_no_primeiro_vazio(monkeypatch):
    chamadas: list[int] = []

    def buscar_falso(slug, numero=None, session=None):
        chamadas.append(numero)
        if numero in (1, 2):
            return _registro(numero)
        return None

    monkeypatch.setattr(scraper, "buscar_concurso", buscar_falso)

    registros = scraper.baixar_intervalo("mega-sena", 1, 5)

    assert [item["concurso"] for item in registros] == [1, 2]
    assert chamadas == [1, 2, 3]


def test_gerador_sintetico_e_deterministico():
    primeiro = loader.gerador_sintetico("mega-sena", 5)
    segundo = loader.gerador_sintetico("mega-sena", 5)

    assert primeiro == segundo
    assert [item["concurso"] for item in primeiro] == [1, 2, 3, 4, 5]
    assert [item["data"] for item in primeiro] == [
        "2020-01-01",
        "2020-01-02",
        "2020-01-03",
        "2020-01-04",
        "2020-01-05",
    ]
    for item in primeiro:
        assert item["loteria"] == "mega-sena"
        assert item["acumulado"] is None
        assert item["premiacoes"] is None
        assert len(item["dezenas"]) == 6
        assert item["dezenas"] == sorted(set(item["dezenas"]))
        assert all(1 <= dezena <= 60 for dezena in item["dezenas"])


def test_gerador_sintetico_super_sete_posicional():
    registros = loader.gerador_sintetico("super-sete", 3)

    for item in registros:
        assert len(item["dezenas"]) == 7
        assert all(0 <= dezena <= 9 for dezena in item["dezenas"])


def test_gerador_sintetico_valida_loteria():
    with pytest.raises(ValueError):
        loader.gerador_sintetico("inexistente", 3)


def test_atualizar_loteria_offline(tmp_path, monkeypatch):
    destino = tmp_path / "loterias.db"

    def sem_rede(*args, **kwargs):
        raise AssertionError("modo offline não deve acessar a rede")

    monkeypatch.setattr(requests.Session, "get", sem_rede)

    resultado = atualizar_loteria("mega-sena", caminho=destino, offline=True)

    assert resultado == {
        "loteria": "mega-sena",
        "novos": 100,
        "ultimo": 100,
        "fonte": "offline-sintetico",
        "erro": None,
    }
    assert loader.db.contar_concursos("mega-sena", destino) == 100

    de_novo = atualizar_loteria("mega-sena", caminho=destino, offline=True)
    assert de_novo["novos"] == 0
    assert de_novo["ultimo"] == 100
    assert de_novo["fonte"] == "offline-sintetico"

    limitado = atualizar_loteria(
        "quina", caminho=tmp_path / "outro.db", offline=True, maximo=7
    )
    assert limitado["novos"] == 7
    assert limitado["ultimo"] == 7


def test_atualizar_loteria_offline_aceita_slug(tmp_path):
    resultado = atualizar_loteria("megasena", caminho=tmp_path / "db.db", offline=True)
    assert resultado["loteria"] == "mega-sena"
    assert resultado["novos"] > 0


def test_atualizar_loteria_fallback_quando_rede_falha(tmp_path, monkeypatch):
    destino = tmp_path / "loterias.db"

    def explodir(*args, **kwargs):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(requests.Session, "get", explodir)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_: None)

    resultado = atualizar_loteria(
        "mega-sena", caminho=destino, maximo=5
    )

    assert resultado["fonte"] == "fallback"
    assert resultado["novos"] == 5
    assert resultado["ultimo"] == 5
    assert resultado["erro"] is not None
    assert loader.db.contar_concursos("mega-sena", destino) == 5


def test_atualizar_loteria_baixa_somente_concursos_novos(tmp_path, monkeypatch):
    destino = tmp_path / "loterias.db"
    capturado: dict[str, tuple[int, int]] = {}
    remoto = {"valor": 5}

    monkeypatch.setattr(
        loader.scraper, "obter_ultimo", lambda slug: remoto["valor"]
    )

    def baixar_falso(slug, de, ate):
        capturado["intervalo"] = (de, ate)
        return [_registro(numero) for numero in range(de, ate + 1)]

    monkeypatch.setattr(loader.scraper, "baixar_intervalo", baixar_falso)

    inicial = atualizar_loteria("mega-sena", caminho=destino, maximo=5)
    assert inicial["fonte"] == "caixa"
    assert inicial["erro"] is None
    assert inicial["novos"] == 5
    assert inicial["ultimo"] == 5
    assert capturado["intervalo"] == (1, 5)

    remoto["valor"] = 7
    incremental = atualizar_loteria("mega-sena", caminho=destino)
    assert capturado["intervalo"] == (6, 7)
    assert incremental["fonte"] == "caixa"
    assert incremental["novos"] == 2
    assert incremental["ultimo"] == 7


def test_atualizar_loteria_banco_vazio_baixa_no_maximo_100(
    tmp_path, monkeypatch
):
    destino = tmp_path / "loterias.db"
    capturado: dict[str, tuple[int, int]] = {}

    monkeypatch.setattr(loader.scraper, "obter_ultimo", lambda slug: 250)

    def baixar_falso(slug, de, ate):
        capturado["intervalo"] = (de, ate)
        return [_registro(numero) for numero in range(de, ate + 1)]

    monkeypatch.setattr(loader.scraper, "baixar_intervalo", baixar_falso)

    resultado = atualizar_loteria("mega-sena", caminho=destino)

    assert capturado["intervalo"] == (151, 250)
    assert resultado["novos"] == 100
    assert resultado["ultimo"] == 250
    assert resultado["fonte"] == "caixa"


def test_atualizar_loteria_fallback_nao_sobrescreve_historico(
    tmp_path, monkeypatch
):
    destino = tmp_path / "loterias.db"
    atualizar_loteria("mega-sena", caminho=destino, offline=True)

    def explodir(*args, **kwargs):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(requests.Session, "get", explodir)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_: None)

    resultado = atualizar_loteria("mega-sena", caminho=destino)

    assert resultado["fonte"] == "fallback"
    assert resultado["novos"] == 0
    assert resultado["erro"] is not None
    assert resultado["ultimo"] == 100


def test_atualizar_todas_offline(tmp_path):
    destino = tmp_path / "loterias.db"

    resultados = atualizar_todas(caminho=destino, offline=True)

    assert set(resultados) == set(scraper.SLUGS)
    for chave, resultado in resultados.items():
        assert resultado["loteria"] == chave
        assert resultado["novos"] > 0
        assert resultado["fonte"] == "offline-sintetico"
        assert resultado["erro"] is None

    df_super = loader.db.carregar_df("super-sete", destino)
    assert len(df_super) == 100
    assert all(len(dezenas) == 7 for dezenas in df_super["dezenas"])
