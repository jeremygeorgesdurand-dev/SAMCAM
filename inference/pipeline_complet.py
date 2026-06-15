#!/usr/bin/env python3
"""
SAMCAM — Pipeline complet : collecte + analyse + dashboard

Usage :
    python3 inference/pipeline_complet.py
    python3 inference/pipeline_complet.py --days 14
    python3 inference/pipeline_complet.py --no-browser

Exécute dans l'ordre :
    1. collect_kribi.py     (collecte données)
    2. analyser_kribi.py    (analyse Phi-3)
    3. Copie le JSON dans   dashboard/latest_report.json
    4. Ouvre le dashboard   dans le navigateur par défaut
"""

import subprocess
import sys
import os
import shutil
import glob
import datetime
import webbrowser
import time

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


def copier_rapport_json():
    """Copie le dernier rapport JSON dans dashboard/latest_report.json
    pour que le dashboard (et à terme l'app Android) puisse le lire facilement."""
    reports_dir  = os.path.join(ROOT, "reports")
    dashboard_dir = os.path.join(ROOT, "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)

    fichiers = sorted(glob.glob(os.path.join(reports_dir, "rapport_kribi_*.json")))
    if not fichiers:
        print("⚠️  Aucun rapport JSON trouvé dans reports/ — dashboard non mis à jour.")
        return None

    source = fichiers[-1]
    dest   = os.path.join(dashboard_dir, "latest_report.json")
    shutil.copy2(source, dest)
    print(f"\n[SAMCAM] 📋 Rapport JSON copié :")
    print(f"         Source  : {source}")
    print(f"         Dest    : {dest}")
    return dest


def ouvrir_dashboard():
    """Ouvre le dashboard v4 dans le navigateur par défaut."""
    dashboard_path = os.path.join(ROOT, "dashboard", "samcam-v4-dashboard.html")
    if not os.path.exists(dashboard_path):
        # Fallback v3
        dashboard_path = os.path.join(ROOT, "dashboard", "samcam-v3-dashboard.html")
    if not os.path.exists(dashboard_path):
        print("⚠️  Aucun dashboard HTML trouvé dans dashboard/")
        return

    url = "file://" + os.path.abspath(dashboard_path)
    print(f"\n[SAMCAM] 🌐 Ouverture du dashboard :")
    print(f"         {url}")
    # Petit délai pour laisser le JSON se stabiliser sur disque
    time.sleep(0.5)
    webbrowser.open(url)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SAMCAM — Pipeline complet")
    parser.add_argument("--days",       type=int,            default=7)
    parser.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir le navigateur")
    args = parser.parse_args()

    print(f"\n🚀 SAMCAM Pipeline — {datetime.date.today().isoformat()}")

    # Étape 1 — Collecte
    run(
        [sys.executable, "data_collection/collect_kribi.py", "--days", str(args.days)],
        "[1/2] Collecte des données"
    )

    # Étape 2 — Analyse Phi-3
    run(
        [sys.executable, "inference/analyser_kribi.py"],
        "[2/2] Analyse Phi-3 mini"
    )

    # Étape 3 — Copie JSON → dashboard/
    print(f"\n{'='*60}")
    print(f"📋 [3/3] Export JSON pour le dashboard")
    print(f"{'='*60}")
    copier_rapport_json()

    print(f"\n✅ Pipeline terminé. Rapports disponibles dans reports/")

    # Étape 4 — Ouvrir le dashboard
    if not args.no_browser:
        ouvrir_dashboard()
