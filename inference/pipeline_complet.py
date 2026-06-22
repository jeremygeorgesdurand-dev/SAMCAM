#!/usr/bin/env python3
"""
SAMCAM V4.2 — Pipeline complet : collecte + analyse + dashboard

NOUVEAUTÉS V4.2 :
    - Option --retrain : ré-entraîne les modèles ML après la collecte
      si suffisamment de nouvelles données réelles ont été accumulées
    - Affichage du nombre de fichiers de données collectées

Usage :
    python3 inference/pipeline_complet.py
    python3 inference/pipeline_complet.py --days 14
    python3 inference/pipeline_complet.py --retrain
    python3 inference/pipeline_complet.py --no-browser
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

# Seuil : nombre minimal de fichiers de données réelles avant de proposer un retrain
SEUIL_RETRAIN = 12  # ~12 semaines de données réelles accumulées


def run(cmd: list, label: str):
    print(f"\n{'='*60}")
    print(f"🔄 {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"❌ {label} a échoué (code {result.returncode})")
        sys.exit(result.returncode)


def copier_rapport_json():
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


def compter_donnees_reelles() -> int:
    """Compte les fichiers de données collectées dans data/."""
    data_dir = os.path.join(ROOT, "data")
    fichiers = glob.glob(os.path.join(data_dir, "kribi_*.json"))
    return len(fichiers)


def verifier_retrain_necessaire(force: bool = False) -> bool:
    """
    V4.2 — Vérifie si un ré-entraînement est opportun.
    Conditions :
    - --retrain passé explicitement (force=True), OU
    - Plus de SEUIL_RETRAIN fichiers de données collectées
      ET le dataset historique existe déjà (base à enrichir)
    """
    if force:
        return True
    n = compter_donnees_reelles()
    dataset_existe = os.path.exists(os.path.join(ROOT, "data", "dataset_kribi_historical.csv"))
    if n >= SEUIL_RETRAIN and dataset_existe:
        print(f"\n[PIPELINE] 📊 {n} fichiers de données réelles détectés.")
        print(f"           Ré-entraînement recommandé (seuil={SEUIL_RETRAIN}).")
        return True
    return False


def ouvrir_dashboard():
    dashboard_path = os.path.join(ROOT, "dashboard", "samcam-v4-dashboard.html")
    if not os.path.exists(dashboard_path):
        dashboard_path = os.path.join(ROOT, "dashboard", "samcam-v3-dashboard.html")
    if not os.path.exists(dashboard_path):
        print("⚠️  Aucun dashboard HTML trouvé dans dashboard/")
        return

    url = "file://" + os.path.abspath(dashboard_path)
    print(f"\n[SAMCAM] 🌐 Ouverture du dashboard :")
    print(f"         {url}")
    time.sleep(0.5)
    webbrowser.open(url)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SAMCAM V4.2 — Pipeline complet")
    parser.add_argument("--days",       type=int,            default=7)
    parser.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir le navigateur")
    parser.add_argument("--retrain",    action="store_true",
                        help="Ré-entraîne les modèles ML après la collecte")
    args = parser.parse_args()

    print(f"\n🚀 SAMCAM Pipeline V4.2 — {datetime.date.today().isoformat()}")
    n_data = compter_donnees_reelles()
    print(f"   Données collectées disponibles : {n_data} fichiers")

    # Étape 1 — Collecte
    run(
        [sys.executable, "data_collection/collect_kribi.py", "--days", str(args.days)],
        "[1/3] Collecte des données météo + satellite"
    )

    # Étape 2 — Ré-entraînement conditionnel (V4.2)
    if verifier_retrain_necessaire(force=args.retrain):
        print(f"\n{'='*60}")
        print(f"🤖 [2/3] Ré-entraînement des modèles ML")
        print(f"{'='*60}")
        run(
            [sys.executable, "inference/train_model.py", "--force"],
            "[2/3] Ré-entraînement modèles"
        )
    else:
        print(f"\n[PIPELINE] ⏭️  Ré-entraînement ignoré "
              f"(données {n_data}/{SEUIL_RETRAIN} — utilisez --retrain pour forcer)")

    # Étape 3 — Analyse Phi-3
    run(
        [sys.executable, "inference/analyser_kribi.py"],
        "[3/3] Analyse Phi-3 mini + génération rapport"
    )

    # Export JSON → dashboard/
    print(f"\n{'='*60}")
    print(f"📋 Export JSON pour le dashboard")
    print(f"{'='*60}")
    copier_rapport_json()

    print(f"\n✅ Pipeline V4.2 terminé. Rapports disponibles dans reports/")

    if not args.no_browser:
        ouvrir_dashboard()
