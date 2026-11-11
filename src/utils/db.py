"""Persistência do histórico das loterias em SQLite.

Este módulo concentra o schema, o upsert idempotente e a leitura do
histórico como :class:`pandas.DataFrame`, conforme a seção 8 do contrato.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

logger = logging.getLogger(__name__)

#: Caminho padrão do banco, resolvido a partir da raiz do repositório.
RAIZ_PROJETO: Path = Path(__file__).resolve().parents[2]
DEFAULT_DB: Path = RAIZ_PROJETO / "data" / "loterias.db"

COLUNAS_DF: tuple[str, ...] = (
    "concurso",
    "data",
    "dezenas",
    "acumulado",
    "premiacoes",
)

_LOTERIAS_POSICIONAIS = frozenset({"super-sete", "supersete", "super sete"})

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS concursos (
    loteria   TEXT    NOT NULL,
    concurso  INTEGER NOT NULL,
    data      TEXT,
    dezenas   TEXT    NOT NULL,   -- JSON array de int
    premiacoes TEXT,              -- JSON
    acumulado REAL,
    PRIMARY KEY (loteria, concurso)
);

CREATE TABLE IF NOT EXISTS meta (
    loteria        TEXT PRIMARY KEY,
    ultimo_concurso INTEGER,
    atualizado_em  TEXT
);

CREATE INDEX IF NOT EXISTS idx_concursos_loteria_concurso
    ON concursos (loteria, concurso);
CREATE INDEX IF NOT EXISTS idx_concursos_loteria_data
    ON concursos (loteria, data);
"""

_SQL_UPSERT = """
INSERT INTO concursos (loteria, concurso, data, dezenas, premiacoes, acumulado)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(loteria, concurso) DO UPDATE SET
    data       = excluded.data,
    dezenas    = excluded.dezenas,
    premiacoes = excluded.premiacoes,
    acumulado  = excluded.acumulado
"""

_SQL_META = """
INSERT INTO meta (loteria, ultimo_concurso, atualizado_em)
VALUES (?, ?, ?)
ON CONFLICT(loteria) DO UPDATE SET
    ultimo_concurso = excluded.ultimo_concurso,
    atualizado_em   = excluded.atualizado_em
"""


def _resolver_caminho(caminho: str | Path | None) -> Path:
    """Devolve o caminho absoluto do banco (padrão: ``data/loterias.db``)."""
    if caminho is None:
        return DEFAULT_DB
    return Path(caminho).expanduser().resolve()


def _eh_posicional(loteria: str) -> bool:
    """Indica se a modalidade usa dezenas posicionais (Super Sete)."""
    return str(loteria).strip().lower() in _LOTERIAS_POSICIONAIS


def conectar(caminho: str | Path | None = None) -> sqlite3.Connection:
    """Abre uma conexão SQLite configurada para o banco de loterias.

    Cria o diretório pai quando necessário, ativa chaves estrangeiras e o
    modo WAL e devolve linhas acessíveis por nome (``sqlite3.Row``).
    """
    destino = _resolver_caminho(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(destino), timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db(caminho: str | Path | None = None) -> None:
    """Cria as tabelas e índices do banco de forma idempotente."""
    con = conectar(caminho)
    try:
        con.executescript(_SCHEMA_SQL)
        con.commit()
        logger.debug("Schema inicializado em %s", _resolver_caminho(caminho))
    finally:
        con.close()


def _parse_concurso(valor: Any, contexto: str) -> int:
    """Converte o número do concurso para ``int`` positivo."""
    if isinstance(valor, bool):
        raise ValueError(f"{contexto}: número de concurso inválido: {valor!r}")
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, float) and valor.is_integer():
        numero = int(valor)
    elif isinstance(valor, str) and valor.strip().lstrip("-").isdigit():
        numero = int(valor.strip())
    else:
        raise ValueError(f"{contexto}: número de concurso inválido: {valor!r}")
    if numero <= 0:
        raise ValueError(f"{contexto}: número de concurso deve ser positivo: {numero}")
    return numero


def _parse_dezenas(valor: Any, loteria: str, contexto: str) -> list[int]:
    """Valida e serializa as dezenas como lista de inteiros.

    Para modalidades de conjunto a lista é ordenada e não pode ter
    repetições. Na Super Sete a ordem das colunas é preservada, pois cada
    posição representa uma coluna do volante.
    """
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{contexto}: dezenas devem ser uma lista de inteiros ou JSON válido"
            ) from exc
    if isinstance(valor, (tuple, set, frozenset)):
        valor = list(valor)
    if not isinstance(valor, list) or not valor:
        raise ValueError(f"{contexto}: campo 'dezenas' deve ser uma lista não vazia")

    dezenas: list[int] = []
    for item in valor:
        if isinstance(item, bool):
            raise ValueError(f"{contexto}: dezena inválida: {item!r}")
        if isinstance(item, int):
            dezena = item
        elif isinstance(item, float) and item.is_integer():
            dezena = int(item)
        elif isinstance(item, str) and item.strip().lstrip("-").isdigit():
            dezena = int(item.strip())
        else:
            raise ValueError(f"{contexto}: dezena inválida: {item!r}")
        dezenas.append(dezena)

    if not _eh_posicional(loteria):
        if len(set(dezenas)) != len(dezenas):
            raise ValueError(f"{contexto}: dezenas duplicadas na modalidade de conjunto")
        return sorted(dezenas)
    return dezenas


def _parse_data(valor: Any, contexto: str) -> str | None:
    """Normaliza datas para o formato ISO ``aaaa-mm-dd``."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip()
    if not texto:
        return None
    texto = texto.split(" ")[0].split("T")[0]
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    raise ValueError(
        f"{contexto}: data inválida {valor!r} (esperado dd/mm/aaaa ou aaaa-mm-dd)"
    )


def _parse_acumulado(valor: Any, contexto: str) -> float | None:
    """Converte o valor acumulado para ``float`` (aceita formato brasileiro)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{contexto}: acumulado inválido: {valor!r}")
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError as exc:
        raise ValueError(f"{contexto}: acumulado inválido: {valor!r}") from exc


def _serializar_premiacoes(valor: Any, contexto: str) -> str | None:
    """Serializa as premiações como JSON (lista, dicionário ou ``None``)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{contexto}: premiações devem ser JSON válido ou lista/dict"
            ) from exc
    if not isinstance(valor, (list, dict)):
        raise ValueError(
            f"{contexto}: premiações devem ser lista, dicionário ou None"
        )
    return json.dumps(valor, ensure_ascii=False)


def _validar_registro(registro: Any, indice: int) -> tuple[str, int, str | None, str, str | None, float | None]:
    """Valida um registro de entrada e devolve a linha pronta para o SQL."""
    contexto = f"registro #{indice + 1}"
    if not isinstance(registro, dict):
        raise ValueError(
            f"{contexto}: esperado dicionário, recebido {type(registro).__name__}"
        )
    for campo in ("loteria", "concurso", "dezenas"):
        if campo not in registro or registro[campo] is None or registro[campo] == "":
            raise ValueError(f"{contexto}: campo obrigatório ausente: {campo!r}")

    loteria = str(registro["loteria"]).strip()
    if not loteria:
        raise ValueError(f"{contexto}: campo obrigatório ausente: 'loteria'")
    concurso = _parse_concurso(registro["concurso"], contexto)
    data_iso = _parse_data(registro.get("data"), contexto)
    dezenas = _parse_dezenas(registro["dezenas"], loteria, contexto)
    premiacoes = _serializar_premiacoes(registro.get("premiacoes"), contexto)
    acumulado = _parse_acumulado(registro.get("acumulado"), contexto)

    dezenas_json = json.dumps(dezenas, ensure_ascii=False)
    return loteria, concurso, data_iso, dezenas_json, premiacoes, acumulado


def upsert_concursos(
    registros: Iterable[dict], caminho: str | Path | None = None
) -> int:
    """Grava ou atualiza concursos e atualiza a tabela ``meta``.

    Aceita dicionários com ``loteria``, ``concurso``, ``data``, ``dezenas``,
    ``premiacoes`` e ``acumulado``. Levanta :class:`ValueError` (mensagem em
    português) quando um campo obrigatório está ausente ou inválido.

    Retorna a quantidade de registros processados (inseridos ou atualizados).
    """
    linhas = [
        _validar_registro(registro, indice)
        for indice, registro in enumerate(list(registros))
    ]
    if not linhas:
        return 0

    init_db(caminho)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con = conectar(caminho)
    try:
        with con:
            con.executemany(_SQL_UPSERT, linhas)
            for loteria in sorted({linha[0] for linha in linhas}):
                row = con.execute(
                    "SELECT MAX(concurso) FROM concursos WHERE loteria = ?",
                    (loteria,),
                ).fetchone()
                ultimo = int(row[0]) if row and row[0] is not None else None
                con.execute(_SQL_META, (loteria, ultimo, agora))
        logger.debug("%d registro(s) gravado(s)", len(linhas))
        return len(linhas)
    finally:
        con.close()


def _df_vazio() -> pd.DataFrame:
    """DataFrame vazio com as colunas e dtypes esperados."""
    return pd.DataFrame(
        {
            "concurso": pd.Series([], dtype="int64"),
            "data": pd.Series([], dtype="object"),
            "dezenas": pd.Series([], dtype="object"),
            "acumulado": pd.Series([], dtype="float64"),
            "premiacoes": pd.Series([], dtype="object"),
        },
        columns=list(COLUNAS_DF),
    )


def carregar_df(
    loteria: str, caminho: str | Path | None = None, limite: int | None = None
) -> pd.DataFrame:
    """Carrega o histórico de uma modalidade como ``DataFrame``.

    As colunas são ``concurso`` (int), ``data`` (str ISO ou ``None``),
    ``dezenas`` (``list[int]``), ``acumulado`` (float) e ``premiacoes``
    (lista/dict ou ``None``), em ordem crescente de concurso. Com ``limite``,
    devolve apenas os últimos concursos, ainda em ordem crescente.
    """
    chave = str(loteria).strip()
    if limite is not None:
        limite = int(limite)
        if limite <= 0:
            return _df_vazio()

    init_db(caminho)
    con = conectar(caminho)
    try:
        if limite is None:
            sql = (
                "SELECT concurso, data, dezenas, acumulado, premiacoes "
                "FROM concursos WHERE loteria = ? ORDER BY concurso ASC"
            )
            rows = con.execute(sql, (chave,)).fetchall()
        else:
            sql = (
                "SELECT concurso, data, dezenas, acumulado, premiacoes FROM ("
                "  SELECT concurso, data, dezenas, acumulado, premiacoes "
                "  FROM concursos WHERE loteria = ? "
                "  ORDER BY concurso DESC LIMIT ?"
                ") ORDER BY concurso ASC"
            )
            rows = con.execute(sql, (chave, limite)).fetchall()
    finally:
        con.close()

    if not rows:
        return _df_vazio()

    posicional = _eh_posicional(chave)
    concursos: list[int] = []
    datas: list[str | None] = []
    dezenas_col: list[list[int]] = []
    acumulados: list[float] = []
    premiacoes_col: list[Any] = []

    for row in rows:
        concursos.append(int(row["concurso"]))
        datas.append(row["data"])
        dezenas = [int(item) for item in json.loads(row["dezenas"])]
        dezenas_col.append(dezenas if posicional else sorted(dezenas))
        acumulados.append(
            float(row["acumulado"]) if row["acumulado"] is not None else float("nan")
        )
        premiacoes_col.append(
            json.loads(row["premiacoes"]) if row["premiacoes"] else None
        )

    return pd.DataFrame(
        {
            "concurso": pd.Series(concursos, dtype="int64"),
            "data": pd.Series(datas, dtype="object"),
            "dezenas": pd.Series(dezenas_col, dtype="object"),
            "acumulado": pd.Series(acumulados, dtype="float64"),
            "premiacoes": pd.Series(premiacoes_col, dtype="object"),
        },
        columns=list(COLUNAS_DF),
    )


def ultimo_concurso(
    loteria: str, caminho: str | Path | None = None
) -> int | None:
    """Devolve o maior número de concurso gravado ou ``None`` se vazio."""
    init_db(caminho)
    con = conectar(caminho)
    try:
        row = con.execute(
            "SELECT MAX(concurso) FROM concursos WHERE loteria = ?",
            (str(loteria).strip(),),
        ).fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def contar_concursos(loteria: str, caminho: str | Path | None = None) -> int:
    """Conta quantos concursos existem para a modalidade informada."""
    init_db(caminho)
    con = conectar(caminho)
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM concursos WHERE loteria = ?",
            (str(loteria).strip(),),
        ).fetchone()
    finally:
        con.close()
    return int(row[0]) if row else 0


__all__ = [
    "DEFAULT_DB",
    "COLUNAS_DF",
    "conectar",
    "init_db",
    "upsert_concursos",
    "carregar_df",
    "ultimo_concurso",
    "contar_concursos",
]
