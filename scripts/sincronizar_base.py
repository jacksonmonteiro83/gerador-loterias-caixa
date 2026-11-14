"""Sincroniza data/historico/ com a base diária do repositório loterias-dashboard.

Uso:
    python scripts/sincronizar_base.py                       # baixa do GitHub (todas)
    python scripts/sincronizar_base.py quina mega-sena       # só algumas
    python scripts/sincronizar_base.py --origem /caminho/loterias-dashboard/data/raw
Depois rode: python scripts/export_dashboard.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.etl.base_externa import SLUGS, URL_PADRAO, sincronizar  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("modalidades", nargs="*", choices=sorted(SLUGS))
    p.add_argument("--origem", default=URL_PADRAO, help="URL base ou pasta com <slug>.json")
    p.add_argument("--historico-dir", default=None)
    p.add_argument("--simular", action="store_true", help="valida sem gravar")
    a = p.parse_args(argv)
    falhas = 0
    for chave in a.modalidades or sorted(SLUGS):
        try:
            r = sincronizar(chave, a.origem, a.historico_dir, gravar=not a.simular)
        except (ValueError, OSError) as exc:
            print(f"ERRO {chave}: {exc}", file=sys.stderr)
            falhas += 1
            continue
        estado = "completo" if r["completo"] else f"faltam {len(r['faltantes'])}"
        print(f"{chave}: {r['lidos']} lidos, {r['novos_ou_alterados']} novos/alterados, "
              f"{r['total']} no histórico ({estado})")
        if r["n_divergentes"]:
            print(f"  aviso: {r['n_divergentes']} concursos com dezenas diferentes do histórico local "
                  f"(a base externa prevaleceu): {r['divergentes'][:5]}")
        if r["mantidos_locais"]:
            print(f"  aviso: concursos {r['mantidos_locais']} vieram com nº de dezenas inválido na "
                  "base externa; mantido o registro local")
        for aviso in r["avisos"]:
            print(f"  aviso: {aviso}")
    return 3 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
