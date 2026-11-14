"""Sincroniza o histórico com a base diária do repositório ``loterias-dashboard``.

Aquele repositório já baixa todos os concursos da Caixa todo dia e guarda um
JSON bruto por loteria (``data/raw/<slug>.json``, chave = nº do concurso, com
dezenas e ganhadores por faixa). Em vez de refazer a coleta na API (que falha
com HTTP 403 em partes do histórico), este módulo lê esses arquivos e mescla em
``data/historico/<modalidade>.jsonl``.

A origem pode ser uma URL base (``https://raw.githubusercontent.com/...``) ou
uma pasta local com os mesmos arquivos.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from . import historico
from .planilha import SORTEADAS
from .scraper import normalizar_dezenas
from .validacao import validar_historico
from ..loterias import get_loteria

URL_PADRAO = "https://raw.githubusercontent.com/jacksonmonteiro83/loterias-dashboard/main/data/raw"

# modalidade deste projeto -> nome do arquivo no loterias-dashboard
SLUGS = {
    "mega-sena": "megasena",
    "lotofacil": "lotofacil",
    "quina": "quina",
    "lotomania": "lotomania",
    "timemania": "timemania",
    "dupla-sena": "duplasena",
    "dia-de-sorte": "diadesorte",
    "super-sete": "supersete",
}


def _ler_bruto(origem: str | Path, slug: str, timeout: int = 120) -> dict[str, Any]:
    texto = str(origem)
    if texto.startswith(("http://", "https://")):
        url = f"{texto.rstrip('/')}/{slug}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "gerador-loterias-caixa"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    with (Path(origem) / f"{slug}.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def converter(chave: str, bruto: dict[str, Any]) -> list[dict]:
    """Converte o JSON bruto no formato do histórico (n, d, z, g)."""
    posicional = chave == "super-sete"
    registros: list[dict] = []
    for item in bruto.values():
        if not isinstance(item, dict) or not item.get("dezenas"):
            continue
        z = [int(v) for v in item["dezenas"]]
        z = normalizar_dezenas(chave, z)
        if not posicional:
            z = sorted(z)
        reg: dict = {"n": int(item["numero"]), "d": item.get("data"), "z": z}
        g = historico.ganhadores_faixa1(
            [{"faixa": f.get("faixa"), "ganhadores": f.get("ganhadores")}
             for f in item.get("faixas") or []]
        )
        if g is not None:
            reg["g"] = g
        registros.append(reg)
    return sorted(registros, key=lambda r: r["n"])


def sincronizar(
    chave: str,
    origem: str | Path = URL_PADRAO,
    diretorio: str | Path | None = None,
    gravar: bool = True,
) -> dict[str, Any]:
    """Mescla a base externa no histórico local, validando antes de gravar."""
    if chave not in SLUGS:
        raise ValueError(f"modalidade sem correspondência na base externa: {chave}")
    novos = converter(chave, _ler_bruto(origem, SLUGS[chave]))
    if not novos:
        raise ValueError(f"{chave}: a base externa veio vazia")
    spec = get_loteria(chave).spec
    existentes = {r["n"]: r for r in historico.ler(chave, diretorio)}
    # registro externo com nº de dezenas errado (ex.: a API da Caixa às vezes
    # anexa o "Time do Coração" na Timemania): mantém o local, se for válido
    mantidos: list[int] = []
    validos: list[dict] = []
    for item in novos:
        if len(item["z"]) != SORTEADAS[chave]:
            local = existentes.get(item["n"])
            if local is not None and len(local["z"]) == SORTEADAS[chave]:
                mantidos.append(item["n"])
                continue
        validos.append(item)
    novos = validos
    val = validar_historico(spec, novos, sorteadas=SORTEADAS[chave])
    erros = [e for e in val["erros"]]
    if erros:
        raise ValueError(f"{chave}: base externa inválida:\n  " + "\n  ".join(erros[:10]))
    por_n = {x["n"]: x for x in novos}
    divergentes = [n for n, r in existentes.items() if n in por_n and r["z"] != por_n[n]["z"]]
    alterados = 0
    for item in novos:
        antigo = existentes.get(item["n"])
        if antigo is not None and "g" not in item and "g" in antigo:
            item["g"] = antigo["g"]
        if antigo != item:
            alterados += 1
        existentes[item["n"]] = item
    mesclado = [existentes[n] for n in sorted(existentes)]
    total = validar_historico(spec, mesclado, sorteadas=SORTEADAS[chave])
    if gravar:
        historico.gravar(chave, mesclado, diretorio)
    return {
        "lidos": len(novos), "novos_ou_alterados": alterados, "total": total["n"],
        "completo": total["completo"], "faltantes": total["faltantes"],
        "mantidos_locais": mantidos, "divergentes": divergentes[:20], "n_divergentes": len(divergentes),
        "avisos": total["avisos"],
    }


__all__ = ["URL_PADRAO", "SLUGS", "converter", "sincronizar"]
