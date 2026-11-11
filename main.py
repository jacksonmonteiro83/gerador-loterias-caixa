"""CLI e teste de integração do Gerador de Jogos — Loterias Caixa.

Uso:
    python main.py                      # demo das 8 modalidades (offline-safe)
    python main.py --loteria mega-sena --jogos 5 --seed 42
    python main.py --atualizar          # baixa o histórico da Caixa para o SQLite
    python main.py --regras             # tabela de regras oficiais
    python main.py --json               # saída estruturada

Código de saída 0 quando todas as verificações passam, 1 caso contrário.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from src.core.models import FiltroConfig, LotteryConfig, ValidacaoError
from src.etl.loader import gerador_sintetico
from src.etl.loader import atualizar_todas as etl_atualizar_todas
from src.loterias.registry import criar, get_loteria, listar_loterias
from src.utils.db import DEFAULT_DB, carregar_df, contar_concursos

RAIZ = Path(__file__).resolve().parent
HISTORICO_SINTETICO = 100


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------
def _utf8() -> None:
    """Garante acentuação correta no console do Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - stream sem reconfigure
            pass


def _faixa(texto: str) -> tuple[int, int]:
    """Converte ``"3-5"`` (ou ``"3,5"``) em ``(3, 5)``."""
    partes = texto.replace(",", "-").split("-")
    if len(partes) != 2:
        raise argparse.ArgumentTypeError(f"faixa inválida: {texto!r} (use min-max)")
    try:
        minimo, maximo = int(partes[0]), int(partes[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"faixa inválida: {texto!r}") from exc
    if minimo > maximo:
        raise argparse.ArgumentTypeError(f"faixa invertida: {texto!r}")
    return (minimo, maximo)


def _lista(texto: str) -> list[int]:
    """Converte ``"4,7,23"`` em ``[4, 7, 23]``."""
    itens = [p for p in texto.replace(";", ",").split(",") if p.strip()]
    try:
        return [int(p) for p in itens]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"lista inválida: {texto!r}") from exc


def formatar(jogo: Sequence[int], posicional: bool = False) -> str:
    if posicional:
        return " ".join(str(int(d)) for d in jogo)
    return " ".join(f"{int(d):02d}" for d in jogo)


def historico_de(key: str, caminho: Path, offline: bool) -> tuple[pd.DataFrame | None, str]:
    """Histórico do SQLite quando existir; senão, histórico sintético em memória."""
    if not offline and Path(caminho).exists():
        try:
            df = carregar_df(key, caminho=caminho)
            if not df.empty:
                return df, "sqlite"
        except Exception as exc:  # banco corrompido/incompatível: degrada
            print(f"  ! banco ilegível ({exc}); usando histórico sintético",
                  file=sys.stderr)
    registros = gerador_sintetico(key, HISTORICO_SINTETICO)
    return pd.DataFrame(registros), "offline-sintetico"


# --------------------------------------------------------------------------
# verificação
# --------------------------------------------------------------------------
def verificar(loteria: Any, jogos: list[list[int]], config: LotteryConfig) -> list[str]:
    """Confere os critérios de aceite sobre os jogos gerados."""
    problemas: list[str] = []
    spec = loteria.spec
    posicional = spec.tipo == "posicional"

    if len(jogos) != config.qtd_jogos:
        problemas.append(f"esperados {config.qtd_jogos} jogos, obtidos {len(jogos)}")

    if not posicional and len({tuple(j) for j in jogos}) != len(jogos):
        problemas.append("jogos duplicados")

    for indice, jogo in enumerate(jogos, start=1):
        try:
            loteria.validar(jogo)
        except ValidacaoError as exc:
            problemas.append(f"jogo {indice} inválido: {exc}")
            continue
        if not loteria.atende_filtros(jogo):
            problemas.append(f"jogo {indice} viola os filtros")
        if config.dezenas_fixas:
            if not posicional and not set(config.dezenas_fixas) <= set(jogo):
                problemas.append(f"jogo {indice} sem todas as dezenas fixas")
        if config.dezenas_excluidas:
            if set(config.dezenas_excluidas) & set(jogo):
                problemas.append(f"jogo {indice} contém dezena excluída")
        if config.repetidas_concurso_anterior is not None:
            repetidas = loteria.analisar(jogo)["repetidas_ultimo"]
            if repetidas != config.repetidas_concurso_anterior:
                problemas.append(
                    f"jogo {indice} repete {repetidas}x o último concurso "
                    f"(esperado {config.repetidas_concurso_anterior})"
                )
    return problemas


def filtros_do_cli(args: argparse.Namespace) -> FiltroConfig:
    return FiltroConfig(
        pares=args.pares,
        impares=args.impares,
        primos=args.primos,
        moldura=args.moldura,
        miolo=args.miolo,
        soma=args.soma,
        quadrante_min=args.quadrante_min,
        quadrante_max=args.quadrante_max,
    )


def config_restricoes(
    spec: Any, seed: int | None, historico: pd.DataFrame | None
) -> LotteryConfig:
    """Cenário com fixas, excluídas, repetição e contaminação controladas.

    Os valores são derivados do histórico e da própria regra, para que o
    cenário seja sempre matematicamente possível (ex.: na Lotofácil um jogo de
    15 dezenas com apenas 21 dezenas livres não poderia repetir só 2).
    """
    posicional = spec.tipo == "posicional"
    inicio = 0 if posicional else 1
    fim = (spec.universo - 1) if posicional else spec.universo
    qtd = int(spec.qtd_padrao)

    ultimo: set[int] = set()
    if historico is not None and not historico.empty:
        ultimo = {int(d) for d in historico["dezenas"].iloc[-1]}

    if posicional:
        excluidas = [fim]
        fixas = [inicio] if inicio not in excluidas else []
        repetidas = 1
        contaminacao = spec.sorteadas
    else:
        # Excluir/fixar dezenas fora do último concurso mantém o cálculo previsível.
        excluidas = [d for d in range(fim, inicio - 1, -1) if d not in ultimo][:2]
        fixas = [
            d for d in range(inicio, fim + 1)
            if d not in ultimo and d not in excluidas
        ][:2]

        livres = spec.universo - len(excluidas) - len(fixas)
        repetiveis = len(ultimo - set(excluidas) - set(fixas))
        fora_do_ultimo = livres - repetiveis
        soltas = qtd - len(fixas)

        esperadas = round(qtd * spec.sorteadas / spec.universo)
        repetidas = max(esperadas, soltas - fora_do_ultimo, 1)
        repetidas = min(repetidas, repetiveis, soltas - 1)
        contaminacao = max(spec.sorteadas - 2, 1)

    return LotteryConfig(
        qtd_jogos=2,
        dezenas_fixas=fixas,
        dezenas_excluidas=excluidas,
        repetidas_concurso_anterior=repetidas,
        contaminacao_maxima=contaminacao,
        max_tentativas=200_000,
        seed=seed,
    )


# --------------------------------------------------------------------------
# ações
# --------------------------------------------------------------------------
def acao_regras() -> int:
    print(f"{'Modalidade':<13} {'Universo':>10} {'Sort.':>6} {'Aposta':>8} {'Grade':>7}  Tipo")
    print("-" * 68)
    for item in listar_loterias():
        classe = get_loteria(item["key"])
        spec = classe.spec
        universo = (
            f"0-{spec.universo - 1}"
            if spec.tipo == "posicional"
            else f"{spec.inicio}-{spec.universo}"
        )
        aposta = (
            str(spec.aposta_min)
            if spec.aposta_min == spec.aposta_max
            else f"{spec.aposta_min}-{spec.aposta_max}"
        )
        grade = f"{spec.colunas}x{spec.linhas}"
        print(
            f"{spec.nome:<13} {universo:>10} {spec.sorteadas:>6} {aposta:>8} "
            f"{grade:>7}  {spec.tipo}"
        )
    return 0


def acao_atualizar(caminho: Path, offline: bool) -> int:
    print(f"Atualizando histórico em {caminho} ...")
    resultados = etl_atualizar_todas(caminho=caminho, offline=offline)
    print(f"\n{'Modalidade':<13} {'Novos':>6} {'Último':>7} {'Total':>6}  Fonte")
    print("-" * 62)
    for key, res in resultados.items():
        total = contar_concursos(key, caminho=caminho)
        print(
            f"{key:<13} {res.get('novos', 0):>6} {res.get('ultimo') or 0:>7} "
            f"{total:>6}  {res.get('fonte', '?')}"
            + (f" ({res['erro']})" if res.get("erro") else "")
        )
    return 0


def acao_demo(args: argparse.Namespace) -> int:
    chaves = [args.loteria] if args.loteria else [i["key"] for i in listar_loterias()]
    filtros = filtros_do_cli(args)
    saida: dict[str, Any] = {"modalidades": {}, "falhas": []}
    falar = (lambda *a, **k: None) if args.json else print

    falar("=" * 78)
    falar("GERADOR DE JOGOS — LOTERIAS CAIXA · DEMONSTRAÇÃO DE INTEGRAÇÃO")
    falar("=" * 78)

    for key in chaves:
        classe = get_loteria(key)
        spec = classe.spec
        posicional = spec.tipo == "posicional"
        historico, fonte = historico_de(key, args.db, args.offline)
        concursos = 0 if historico is None else len(historico)

        titulo_qtd = (
            f"{spec.sorteadas} dígitos (1 por coluna)"
            if posicional
            else f"{spec.sorteadas} dezenas"
        )
        falar(f"\n{spec.nome.upper()}  ·  {titulo_qtd}  ·  "
              f"universo {'0-9' if posicional else f'1-{spec.universo}'}  ·  "
              f"histórico: {concursos} concursos ({fonte})")

        config = LotteryConfig(
            qtd_jogos=args.jogos,
            dezenas_por_jogo=args.dezenas,
            filtros=filtros,
            dezenas_fixas=list(args.fixas or []),
            dezenas_excluidas=list(args.excluidas or []),
            repetidas_concurso_anterior=args.repetidas,
            contaminacao_maxima=args.contaminacao,
            max_tentativas=200_000,
            seed=args.seed,
        )
        registro: dict[str, Any] = {"fonte": fonte, "concursos": concursos}

        try:
            loteria = criar(key, config=config, historico=historico)
            jogos = loteria.gerar()
        except (ValidacaoError, RuntimeError) as exc:
            falar(f"  FALHA: {exc}")
            saida["falhas"].append(f"{spec.nome}: {exc}")
            saida["modalidades"][key] = registro | {"erro": str(exc)}
            continue

        problemas = verificar(loteria, jogos, config)
        largura = min(74, max((len(formatar(j, posicional)) for j in jogos), default=10))
        for jogo in jogos:
            analise = loteria.analisar(jogo)
            texto = formatar(jogo, posicional)
            if len(texto) > largura:
                partes = texto.split(" ")
                linhas, atual = [], ""
                for parte in partes:
                    if len(atual) + len(parte) + 1 > largura:
                        linhas.append(atual)
                        atual = parte
                    else:
                        atual = f"{atual} {parte}".strip()
                linhas.append(atual)
                texto = ("\n" + " " * 4).join(linhas)
            falar(
                f"  {texto:<{largura}}  soma={analise['soma']:>4} "
                f"pares={analise['pares']:>2} primos={analise['primos']:>2} "
                f"rep={analise['repetidas_ultimo']:>2}"
            )
        falar(f"  → {len(jogos)}/{config.qtd_jogos} jogos válidos · "
              f"{'OK' if not problemas else 'PROBLEMAS'}")
        for problema in problemas:
            falar(f"    - {problema}")
        if problemas:
            saida["falhas"].extend(f"{spec.nome}: {p}" for p in problemas)

        # cenário 2: dezenas fixas/excluídas + repetição + contaminação
        restricoes: dict[str, Any] | None = None
        if not args.sem_restricoes and not filtros.ativo():
            cfg2 = config_restricoes(spec, args.seed, historico)
            try:
                loteria2 = criar(key, config=cfg2, historico=historico)
                jogos2 = loteria2.gerar()
                problemas2 = verificar(loteria2, jogos2, cfg2)
                detalhe = (
                    f"fixas={cfg2.dezenas_fixas} excluídas={cfg2.dezenas_excluidas} "
                    f"repetidas={cfg2.repetidas_concurso_anterior} "
                    f"contaminação≤{cfg2.contaminacao_maxima}"
                )
                falar(f"  → restrições ({detalhe}): "
                      f"{'OK' if not problemas2 else 'PROBLEMAS'}  "
                      f"[{formatar(jogos2[0], posicional)}]")
                for problema in problemas2:
                    falar(f"    - {problema}")
                if problemas2:
                    saida["falhas"].extend(
                        f"{spec.nome} (restrições): {p}" for p in problemas2
                    )
                restricoes = {
                    "fixas": cfg2.dezenas_fixas,
                    "excluidas": cfg2.dezenas_excluidas,
                    "repetidas": cfg2.repetidas_concurso_anterior,
                    "contaminacao_maxima": cfg2.contaminacao_maxima,
                    "jogos": jogos2,
                    "problemas": problemas2,
                }
            except (ValidacaoError, RuntimeError) as exc:
                falar(f"  → restrições: FALHA: {exc}")
                saida["falhas"].append(f"{spec.nome} (restrições): {exc}")
                restricoes = {"erro": str(exc)}

        registro.update(
            {
                "jogos": jogos,
                "problemas": problemas,
                "soma": [loteria.analisar(j)["soma"] for j in jogos],
            }
        )
        if restricoes is not None:
            registro["restricoes"] = restricoes
        saida["modalidades"][key] = registro

    total = len(chaves)
    falhas = saida["falhas"]
    falar("\n" + "=" * 78)
    if falhas:
        falar(f"RESULTADO: {total - len({f.split(':')[0] for f in falhas})}/{total} "
              f"modalidades OK · {len(falhas)} falha(s)")
        for falha in falhas:
            falar(f"  - {falha}")
    else:
        falar(f"RESULTADO: {total}/{total} modalidades OK · "
              f"{sum(len(m.get('jogos', [])) for m in saida['modalidades'].values())} "
              f"jogos validados")
    falar("=" * 78)

    if args.json:
        print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 0 if not falhas else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Gerador de jogos das Loterias Caixa (validação + filtros).",
    )
    p.add_argument("--loteria", help="chave da modalidade (padrão: todas)")
    p.add_argument("--jogos", type=int, default=3, help="jogos por modalidade (padrão: 3)")
    p.add_argument("--dezenas", type=int, default=None,
                   help="dezenas por jogo (respeita a faixa oficial)")
    p.add_argument("--seed", type=int, default=42, help="semente do sorteio")
    p.add_argument("--offline", action="store_true",
                   help="não usa o SQLite; histórico sintético")
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="caminho do SQLite")
    p.add_argument("--atualizar", action="store_true", help="atualiza o histórico (ETL)")
    p.add_argument("--regras", action="store_true", help="mostra as regras oficiais")
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")
    p.add_argument("--sem-restricoes", action="store_true",
                   help="pula o cenário 2 (fixas/excluídas/repetição)")

    f = p.add_argument_group("filtros quantitativos (faixa min-max)")
    f.add_argument("--pares", type=_faixa)
    f.add_argument("--impares", type=_faixa)
    f.add_argument("--primos", type=_faixa)
    f.add_argument("--moldura", type=_faixa)
    f.add_argument("--miolo", type=_faixa)
    f.add_argument("--soma", type=_faixa)
    f.add_argument("--quadrante-min", type=int, dest="quadrante_min")
    f.add_argument("--quadrante-max", type=int, dest="quadrante_max")

    g = p.add_argument_group("restrições de histórico")
    g.add_argument("--fixas", type=_lista, help="dezenas obrigatórias, ex. 4,7,23")
    g.add_argument("--excluidas", type=_lista, help="dezenas proibidas, ex. 1,60")
    g.add_argument("--repetidas", type=int,
                   help="quantidade exata de dezenas repetidas do último concurso")
    g.add_argument("--contaminacao", type=int,
                   help="sobreposição máxima com qualquer concurso do histórico")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    _utf8()
    args = montar_parser().parse_args(argv)
    if args.jogos < 1:
        print("erro: --jogos deve ser >= 1")
        return 2
    try:
        if args.regras:
            return acao_regras()
        if args.atualizar:
            return acao_atualizar(args.db, args.offline)
        return acao_demo(args)
    except KeyError as exc:
        print(f"erro: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
