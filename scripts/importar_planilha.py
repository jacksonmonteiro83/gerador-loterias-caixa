"""Importa a planilha de resultados da Caixa (xlsx/csv) para data/historico/.

Uso:
    python scripts/importar_planilha.py mega-sena Mega-Sena.xlsx
    python scripts/importar_planilha.py quina Quina.xlsx --historico-dir data/historico
Depois rode: python scripts/export_dashboard.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.etl.planilha import SORTEADAS, importar  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("modalidade", choices=sorted(SORTEADAS))
    p.add_argument("arquivo", type=Path)
    p.add_argument("--historico-dir", default=None)
    p.add_argument("--simular", action="store_true", help="valida sem gravar")
    a = p.parse_args(argv)
    try:
        r = importar(a.arquivo, a.modalidade, a.historico_dir, gravar=not a.simular)
    except (ValueError, OSError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 3
    print(f"{a.modalidade}: {r['lidos']} concursos lidos, {r['novos_ou_alterados']} novos/alterados, "
          f"{r['total']} no histórico ({'completo' if r['completo'] else 'faltam ' + str(r['faltantes'])})")
    for aviso in r["avisos"]:
        print(f"  aviso: {aviso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
