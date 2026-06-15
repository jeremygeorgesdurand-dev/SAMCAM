#!/usr/bin/env python3
"""
SAMCAM — Pipeline complet : collecte + analyse en une seule commande

Usage :
    python3 inference/pipeline_complet.py
    python3 inference/pipeline_complet.py --days 14

Exécute dans l'ordre :
    1. collect_kribi.py (collecte données)
    2. analyser_kribi.py (analyse Phi-3)
"""

import subprocess
import sys
import os
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(BASE, "..")


def run(cmd: list, label: str):
    print(f"\n{'='*60}")
    print(f"🔄 {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"❌ {label} a échoué (code {result.returncode})")
        sys.exit(result.returncode)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SAMCAM — Pipeline complet")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    print(f"\n🚀 SAMCAM Pipeline — {datetime.date.today().isoformat()}")

    run(
        [sys.executable, "data_collection/collect_kribi.py", "--days", str(args.days)],
        "[1/2] Collecte des données"
    )
    run(
        [sys.executable, "inference/analyser_kribi.py"],
        "[2/2] Analyse Phi-3 mini"
    )

    print(f"\n✅ Pipeline terminé. Rapports disponibles dans reports/")
