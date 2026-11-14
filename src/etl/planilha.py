"""Importa a planilha de resultados históricos (xlsx/csv) baixada do site da Caixa.

Alternativa ao ``--atualizar --completo`` quando a API falha: o arquivo é lido,
validado e mesclado em ``data/historico/<modalidade>.jsonl``.

O leitor é tolerante: acha a linha de cabeçalho pela coluna "Concurso", as
dezenas pelas colunas "Bola1..BolaN" (ou "Coluna 1..N" na Super Sete) e o nº de
ganhadores da 1ª faixa pela primeira coluna "Ganhadores ...". Colunas extras
(Mês de Sorte, Time de Coração, rateios, 2º sorteio da Dupla Sena etc.) são
ignoradas; só as primeiras ``sorteadas`` dezenas de cada linha entram.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from . import historico
from .scraper import normalizar_dezenas
from .validacao import validar_historico
from ..loterias.registry import get_loteria

__all__ = ["SORTEADAS", "ler_planilha", "importar"]

#: tamanho real de cada sorteio (≠ aposta na Timemania e na Lotomania)
SORTEADAS = {
    "mega-sena": 6, "lotofacil": 15, "quina": 5, "lotomania": 20,
    "timemania": 7, "dupla-sena": 6, "dia-de-sorte": 7, "super-sete": 7,
}

_BOLA = re.compile(r"^(bola|coluna|dezena)\s*\d+$|^\d+\s*[ªa]?\s*dezena$")


def _norm(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto).strip().lower()


def _abrir(caminho: Path) -> pd.DataFrame:
    if caminho.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(caminho, header=None, dtype=object)
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(caminho, header=None, sep=None, engine="python",
                               encoding=codificacao, dtype=object)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"não consegui decodificar {caminho.name}")


def ler_planilha(caminho: str | Path, chave: str) -> list[dict]:
    """Converte a planilha em registros ``{"n", "d", "z", "g"?}``."""
    if chave not in SORTEADAS:
        raise ValueError(f"modalidade desconhecida: {chave}")
    caminho = Path(caminho)
    bruto = _abrir(caminho)

    cabecalho = None
    for i in range(min(25, len(bruto))):
        if any(_norm(c) == "concurso" for c in bruto.iloc[i].tolist()):
            cabecalho = i
            break
    if cabecalho is None:
        raise ValueError("não achei a coluna 'Concurso' nas primeiras linhas da planilha")

    nomes = [_norm(c) for c in bruto.iloc[cabecalho].tolist()]
    corpo = bruto.iloc[cabecalho + 1:].reset_index(drop=True)
    idx_concurso = nomes.index("concurso")
    idx_data = next((i for i, n in enumerate(nomes) if n.startswith("data")), None)
    idx_bolas = [i for i, n in enumerate(nomes) if _BOLA.match(n)]
    idx_g = next((i for i, n in enumerate(nomes) if n.startswith("ganhadores")), None)
    esperado = SORTEADAS[chave]
    if len(idx_bolas) < esperado:
        raise ValueError(
            f"esperava {esperado} colunas de dezenas (Bola1..), achei {len(idx_bolas)}; "
            f"colunas lidas: {[n for n in nomes if n][:15]}"
        )
    idx_bolas = idx_bolas[:esperado]

    registros: dict[int, dict] = {}
    for _, linha in corpo.iterrows():
        try:
            numero = int(float(str(linha.iloc[idx_concurso]).replace(",", ".")))
            dezenas = [int(float(str(linha.iloc[i]))) for i in idx_bolas]
        except (ValueError, TypeError):
            continue  # linhas de rateio, rodapé ou células vazias
        item: dict[str, Any] = {"n": numero, "z": normalizar_dezenas(chave, dezenas)}
        if idx_data is not None:
            data = pd.to_datetime(linha.iloc[idx_data], dayfirst=True, errors="coerce")
            item["d"] = None if pd.isna(data) else data.date().isoformat()
        else:
            item["d"] = None
        if idx_g is not None:
            try:
                g = int(float(str(linha.iloc[idx_g]).replace(".", "").replace(",", ".")))
                if g >= 0:
                    item["g"] = g
            except (ValueError, TypeError):
                pass
        if chave != "super-sete":
            item["z"] = sorted(item["z"])
        registros[numero] = item
    if not registros:
        raise ValueError("nenhum concurso válido encontrado na planilha")
    return [registros[n] for n in sorted(registros)]


def importar(
    caminho: str | Path, chave: str, diretorio: str | Path | None = None, gravar: bool = True
) -> dict[str, Any]:
    """Lê, valida e mescla a planilha no histórico versionado."""
    novos = ler_planilha(caminho, chave)
    spec = get_loteria(chave).spec
    validacao = validar_historico(spec, novos, sorteadas=SORTEADAS[chave])
    if validacao["erros"]:
        raise ValueError("planilha inválida:\n  " + "\n  ".join(validacao["erros"]))
    existentes = {r["n"]: r for r in historico.ler(chave, diretorio)}
    atualizados = 0
    for item in novos:
        anterior = existentes.get(item["n"])
        if anterior is not None and "g" not in item and "g" in anterior:
            item["g"] = anterior["g"]
        if anterior is None or anterior["z"] != item["z"]:
            atualizados += 1
        existentes[item["n"]] = item
    mesclado = [existentes[n] for n in sorted(existentes)]
    total = validar_historico(spec, mesclado, sorteadas=SORTEADAS[chave])
    if gravar:
        historico.gravar(chave, mesclado, diretorio)
    return {
        "lidos": len(novos), "novos_ou_alterados": atualizados,
        "total": total["n"], "completo": total["completo"],
        "faltantes": total["faltantes"], "avisos": total["avisos"],
    }
