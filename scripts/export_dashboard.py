"""Exporta o histórico do SQLite para o JSON consumido pelo dashboard estático.

Uso:
    python scripts/export_dashboard.py [--db data/loterias.db] [--saida dashboard/data.json]

O JSON é ordenado por concurso crescente e inclui apenas dados públicos de
sorteio (número, data e dezenas), sem prêmios ou dados pessoais.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.utils import db  # noqa: E402

MODALIDADES: dict[str, dict] = {
    "mega-sena": {"nome": "Mega-Sena", "min": 1, "max": 60, "sorteadas": 6, "posicional": False},
    "lotofacil": {"nome": "Lotofácil", "min": 1, "max": 25, "sorteadas": 15, "posicional": False},
    "quina": {"nome": "Quina", "min": 1, "max": 80, "sorteadas": 5, "posicional": False},
    "lotomania": {"nome": "Lotomania", "min": 1, "max": 100, "sorteadas": 20, "posicional": False},
    "timemania": {
        "nome": "Timemania",
        "min": 1,
        "max": 80,
        "sorteadas": 7,
        "posicional": False,
        "nota": "Sete dezenas por sorteio, mais o Time do Coração (não incluído no histórico de dezenas).",
    },
    "dupla-sena": {"nome": "Dupla Sena", "min": 1, "max": 50, "sorteadas": 6, "posicional": False},
    "dia-de-sorte": {
        "nome": "Dia de Sorte",
        "min": 1,
        "max": 31,
        "sorteadas": 7,
        "posicional": False,
        "nota": "Sete dezenas por sorteio, mais o Mês da Sorte (não incluído no histórico de dezenas).",
    },
    "super-sete": {"nome": "Super Sete", "min": 0, "max": 9, "sorteadas": 7, "posicional": True},
}


def _dezenas(valor) -> list[int]:
    """Normaliza o campo ``dezenas`` (JSON em texto) para lista de inteiros."""
    if isinstance(valor, str):
        valor = json.loads(valor)
    return [int(item) for item in valor]


def exportar(caminho_db: str | Path | None, destino: str | Path) -> dict:
    """Lê as oito modalidades e grava o JSON do dashboard."""
    dados: dict = {
        "gerado_em": datetime.now().date().isoformat(),
        "fonte": "Loterias Caixa (dados públicos de sorteio)",
        "loterias": {},
    }
    for chave, info in MODALIDADES.items():
        df = db.carregar_df(chave, caminho=caminho_db)
        registros = []
        if df is not None and not df.empty:
            df = df.sort_values("concurso")
            for _, linha in df.iterrows():
                registros.append(
                    {
                        "n": int(linha["concurso"]),
                        "d": str(linha["data"]) if linha.get("data") is not None else None,
                        "z": _dezenas(linha["dezenas"]),
                    }
                )
        dados["loterias"][chave] = {
            "nome": info["nome"],
            "min": info["min"],
            "max": info["max"],
            "sorteadas": info["sorteadas"],
            "posicional": info["posicional"],
            "nota": info.get("nota"),
            "concursos": registros,
        }

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, separators=(",", ":"))
    return dados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="caminho do SQLite (padrão: data/loterias.db)")
    parser.add_argument(
        "--saida", default=str(RAIZ / "dashboard" / "data.json"), help="arquivo JSON de saída"
    )
    args = parser.parse_args(argv)

    dados = exportar(args.db, args.saida)
    total = sum(len(item["concursos"]) for item in dados["loterias"].values())
    print(f"Exportados {total} concursos de {len(dados['loterias'])} modalidades -> {args.saida}")
    for chave, item in dados["loterias"].items():
        print(f"  {item['nome']:<12} {len(item['concursos']):>4} concursos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
