"""Exporta o histórico para os JSON consumidos pelo dashboard estático.

Uso:
    python scripts/export_dashboard.py [--db data/loterias.db]
        [--historico-dir data/historico] [--saida dashboard/data]

Fonte de verdade: ``data/historico/<modalidade>.jsonl`` (versionado). Se o
arquivo de uma modalidade não existir, usa o SQLite como alternativa.

Saída (em ``dashboard/data``):
    index.json          manifesto leve (metadados e tamanho de cada modalidade)
    <modalidade>.json   estatísticas pré-calculadas (frequência, atraso, soma,
                        repetição, padrões, auditoria, backtest, perfil de score)

Todo o cálculo pesado roda aqui (Python, testado contra scipy); o navegador só
desenha e gera jogos, e baixa apenas a modalidade selecionada.
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

from src.core import auditoria, scoring  # noqa: E402
from src.etl import historico as historico_repo  # noqa: E402
from src.etl.validacao import validar_historico  # noqa: E402
from src.loterias.registry import get_loteria  # noqa: E402
from src.utils import db  # noqa: E402

VERSAO_SCHEMA = 3

MODALIDADES: dict[str, dict] = {
    "mega-sena": {"nome": "Mega-Sena", "posicional": False, "sorteadas": 6},
    "lotofacil": {"nome": "Lotofácil", "posicional": False, "sorteadas": 15},
    "quina": {"nome": "Quina", "posicional": False, "sorteadas": 5},
    "lotomania": {"nome": "Lotomania", "posicional": False, "sorteadas": 20},
    "timemania": {
        "nome": "Timemania",
        "posicional": False,
        "sorteadas": 7,
        "nota": "Sete dezenas por sorteio, mais o Time do Coração (não incluído no histórico de dezenas).",
    },
    "dupla-sena": {
        "nome": "Dupla Sena",
        "posicional": False,
        "sorteadas": 6,
        "nota": "Cada concurso tem dois sorteios; o histórico usa apenas o primeiro.",
    },
    "dia-de-sorte": {
        "nome": "Dia de Sorte",
        "posicional": False,
        "sorteadas": 7,
        "nota": "Sete dezenas por sorteio, mais o Mês da Sorte (não incluído no histórico de dezenas).",
    },
    "super-sete": {"nome": "Super Sete", "posicional": True, "sorteadas": 7},
}


def _carregar_registros(chave: str, caminho_db, diretorio) -> list[dict]:
    registros = historico_repo.ler(chave, diretorio)
    if registros:
        return registros
    if caminho_db is None or not Path(caminho_db).exists():
        return []
    df = db.carregar_df(chave, caminho=caminho_db)
    if df is None or df.empty:
        return []
    saida = []
    for _, linha in df.iterrows():
        item = {
            "n": int(linha["concurso"]),
            "d": linha["data"] if linha["data"] is not None else None,
            "z": [int(v) for v in linha["dezenas"]],
        }
        g = historico_repo.ganhadores_faixa1(linha["premiacoes"])
        if g is not None:
            item["g"] = g
        saida.append(item)
    return saida


def _modalidade(chave: str, info: dict, registros: list[dict], validacao: dict, backtest: bool) -> dict:
    spec = get_loteria(chave).spec
    k = info["sorteadas"]  # tamanho real do sorteio (≠ aposta na Timemania/Lotomania)
    draws = [r["z"] for r in registros]
    base = {
        "chave": chave,
        "nome": info["nome"],
        "min": spec.inicio,
        "max": spec.inicio + spec.universo - 1,
        "sorteadas": k,
        "aposta_min": spec.aposta_min,
        "posicional": info["posicional"],
        "nota": info.get("nota"),
        "linhas": spec.linhas,
        "colunas_malha": spec.colunas,
    }
    if not draws:
        return {**base, "n": 0, "completo": False, "faltantes": 0, "vazio": True}

    resumo = auditoria.resumir(spec, draws)
    # faixas vindas de simulação sob H0; o histórico só audita a taxa de aprovação
    perfil = scoring.calibrar(spec, _df(draws), qtd=k)
    perfil_aposta = None
    if spec.aposta_min != k:
        perfil_aposta = scoring.calibrar(spec, None, qtd=spec.aposta_min)

    recentes = []
    for i in range(max(0, len(registros) - 10), len(registros)):
        anterior = draws[i - 1] if i > 0 else None
        r = perfil.avaliar(draws[i], anterior)
        recentes.append(
            {
                "n": registros[i]["n"],
                "d": registros[i].get("d"),
                "z": draws[i],
                "s": r["score"],
                "a": 1 if r["aprovado"] else 0,
                "p": scoring.padrao_linhas(draws[i], spec),
            }
        )

    teste = auditoria.auditar(spec, resumo)
    perfil_bt = perfil_aposta or perfil
    bt = (
        auditoria.backtest(spec, perfil_bt, draws, top3=resumo.get("padroes_top3"))
        if backtest
        else None
    )
    rateio = auditoria.analise_rateio(spec, registros)

    saida = {
        **base,
        "n": validacao["n"],
        "completo": validacao["completo"],
        "faltantes": validacao["faltantes"],
        "avisos": validacao["avisos"],
        "primeiro": {"n": registros[0]["n"], "d": registros[0].get("d")},
        "ultimo": {"n": registros[-1]["n"], "d": registros[-1].get("d"), "z": draws[-1]},
        "recentes": recentes,
        **auditoria.sem_internos(resumo),
        "perfil": perfil.como_dict(),
        "perfil_aposta": perfil_aposta.como_dict() if perfil_aposta else None,
        "auditoria": teste,
        "backtest": bt,
        "rateio": rateio,
    }
    return saida


def _df(draws: list[list[int]]):
    import pandas as pd

    return pd.DataFrame({"dezenas": draws})


def exportar(
    caminho_db,
    diretorio_historico,
    destino: str | Path,
    backtest: bool = True,
) -> dict:
    """Lê as modalidades e grava ``index.json`` + um JSON por modalidade."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now().date().isoformat()
    indice: dict = {
        "versao": VERSAO_SCHEMA,
        "gerado_em": hoje,
        "fonte": "Loterias Caixa (dados públicos de sorteio)",
        "loterias": {},
    }
    erros_fatais: list[str] = []
    for chave, info in MODALIDADES.items():
        registros = _carregar_registros(chave, caminho_db, diretorio_historico)
        registros.sort(key=lambda r: r["n"])
        spec = get_loteria(chave).spec
        validacao = validar_historico(spec, registros, sorteadas=info["sorteadas"])
        for erro in validacao["erros"]:
            erros_fatais.append(f"{chave}: {erro}")
        dados = _modalidade(chave, info, registros, validacao, backtest)
        dados["gerado_em"] = hoje
        arquivo = destino / f"{chave}.json"
        with arquivo.open("w", encoding="utf-8") as fh:
            json.dump(dados, fh, ensure_ascii=False, separators=(",", ":"))
        indice["loterias"][chave] = {
            "nome": info["nome"],
            "posicional": info["posicional"],
            "n": dados["n"],
            "completo": dados["completo"],
            "faltantes": dados["faltantes"],
            "ultimo": {
                "n": dados.get("ultimo", {}).get("n"),
                "d": dados.get("ultimo", {}).get("d"),
            },
            "arquivo": f"data/{chave}.json",
            "avisos": dados.get("avisos", []),
        }
    with (destino / "index.json").open("w", encoding="utf-8") as fh:
        json.dump(indice, fh, ensure_ascii=False, separators=(",", ":"))
    if erros_fatais:
        raise ValueError("Histórico inválido:\n  " + "\n  ".join(erros_fatais))
    return indice


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite de apoio (padrão: data/loterias.db)")
    parser.add_argument("--historico-dir", default=None, help="pasta dos .jsonl (padrão: data/historico)")
    parser.add_argument("--saida", default=str(RAIZ / "dashboard" / "data"), help="pasta de saída")
    parser.add_argument("--sem-backtest", action="store_true", help="pula o backtest (mais rápido)")
    args = parser.parse_args(argv)

    caminho_db = args.db or db.DEFAULT_DB
    try:
        indice = exportar(caminho_db, args.historico_dir, args.saida, backtest=not args.sem_backtest)
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 3
    total = sum(item["n"] for item in indice["loterias"].values())
    print(f"Exportados {total} concursos de {len(indice['loterias'])} modalidades -> {args.saida}")
    for chave, item in indice["loterias"].items():
        marca = "completo" if item["completo"] else f"INCOMPLETO (faltam {item['faltantes']})"
        print(f"  {item['nome']:<12} {item['n']:>5} concursos  {marca}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
