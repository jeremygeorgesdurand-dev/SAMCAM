#!/usr/bin/env python3
"""
SAMCAM V4.4.5 — Pipeline complet : collecte + prédiction V4 + dashboard

FIX V4.4.5 :
    - copier_rapport_json() trie par date de modification réelle (getmtime)
      au lieu du tri alphabétique qui sélectionnait l'ancien rapport
    - Priorité explicite au rapport du jour (rapport_kribi_{today}.json)
    - Affichage de la date du rapport copié dans les logs

FIX V4.4.4 :
    - Importe HeuristiqueChaleur depuis models.train_model avant joblib.load
      pour éviter AttributeError lors de la désérialisation du .pkl chaleur

Ce pipeline orchestre les 3 étapes dans l'ordre :
  1. Collecte des données météo/satellite (data_collection/collect_kribi.py)
  2. Prédiction de risque via les modèles V4 (inference/risk_model.py)
  3. Ouverture du dashboard HTML

Mode test rapide (sans collecte réseau) :
  python3 inference/pipeline_complet.py --test

Usage complet :
  python3 inference/pipeline_complet.py
  python3 inference/pipeline_complet.py --days 14
  python3 inference/pipeline_complet.py --retrain
  python3 inference/pipeline_complet.py --no-browser
  python3 inference/pipeline_complet.py --test
"""

import subprocess
import sys
import os
import shutil
import glob
import json
import datetime
import webbrowser
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(BASE, "..")

# Rendre models/ importable
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Import CRITIQUE : nécessaire pour que joblib puisse désérialiser
#    model_chaleur.pkl qui contient une instance de HeuristiqueChaleur
from models.train_model import HeuristiqueChaleur  # noqa: F401

SEUIL_RETRAIN = 12


def run(cmd: list, label: str):
    print(f"\n{'='*60}")
    print(f"🔄 {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"❌ {label} a échoué (code {result.returncode})")
        sys.exit(result.returncode)


def copier_rapport_json():
    """
    Copie le rapport JSON le plus récent dans dashboard/latest_report.json.

    Priorité 1 : rapport du jour (rapport_kribi_{today}.json)
    Priorité 2 : rapport le plus récent par date de modification (getmtime)

    FIX V4.4.5 : remplace le tri alphabétique (fichiers[-1]) qui
    sélectionnait un ancien rapport quand le rapport du jour n'avait
    pas encore été créé au moment de l'appel.
    """
    reports_dir   = os.path.join(ROOT, "reports")
    dashboard_dir = os.path.join(ROOT, "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)

    fichiers = glob.glob(os.path.join(reports_dir, "rapport_kribi_*.json"))
    if not fichiers:
        print("⚠️  Aucun rapport JSON trouvé dans reports/ — dashboard non mis à jour.")
        return None

    # Priorité 1 : rapport du jour
    today   = datetime.date.today().isoformat()  # ex. "2026-06-30"
    rapport_du_jour = os.path.join(reports_dir, f"rapport_kribi_{today}.json")
    if os.path.exists(rapport_du_jour):
        source = rapport_du_jour
    else:
        # Priorité 2 : fichier le plus récent par date de modification
        source = max(fichiers, key=os.path.getmtime)

    dest = os.path.join(dashboard_dir, "latest_report.json")
    shutil.copy2(source, dest)

    # Lire la date depuis le contenu du rapport pour l'afficher
    try:
        with open(source, encoding="utf-8") as f:
            contenu = json.load(f)
        date_rapport = contenu.get("date") or contenu.get("metadata", {}).get("date") or "?"
    except Exception:
        date_rapport = os.path.basename(source)

    print(f"\n[PIPELINE] 📋 Rapport JSON copié :")
    print(f"           Source  : {os.path.basename(source)}")
    print(f"           Date    : {date_rapport}")
    print(f"           Dest    : {dest}")
    return dest


def compter_donnees_reelles() -> int:
    data_dir = os.path.join(ROOT, "data")
    return len(glob.glob(os.path.join(data_dir, "kribi_*.json")))


def verifier_retrain_necessaire(force: bool = False) -> bool:
    if force:
        return True
    n = compter_donnees_reelles()
    dataset_existe = os.path.exists(
        os.path.join(ROOT, "data", "dataset_kribi_historical.csv")
    )
    if n >= SEUIL_RETRAIN and dataset_existe:
        print(f"\n[PIPELINE] 📊 {n} fichiers réels détectés → ré-entraînement recommandé.")
        return True
    return False


def ouvrir_dashboard():
    for name in ["samcam-v4-dashboard.html", "samcam-v3-dashboard.html"]:
        path = os.path.join(ROOT, "dashboard", name)
        if os.path.exists(path):
            url = "file://" + os.path.abspath(path)
            print(f"\n[PIPELINE] 🌐 Dashboard : {url}")
            time.sleep(0.5)
            webbrowser.open(url)
            return
    print("⚠️  Aucun dashboard HTML trouvé dans dashboard/")


# ─────────────────────────────────────────────────────────────
# MODE TEST — prédiction directe sans collecte réseau
# ─────────────────────────────────────────────────────────────

def test_prediction_v4():
    """
    Test rapide des 3 modèles V4.4.5 avec des données simulées.
    Vérifie que les .pkl se chargent et retournent des prédictions cohérentes.
    """
    import math
    import numpy as np
    import joblib

    MODELS_DIR = os.path.join(ROOT, "models")

    scenarios = [
        {
            "nom": "Saison sèche normale (janvier)",
            "valeurs": [
                1, 5.0, 30.0, 8.0, 29.0, 28.5, 0.20, 0.25, 0.55, 0.05, 4.5,
                round(math.sin(2 * math.pi * 1 / 12), 4),
                round(math.cos(2 * math.pi * 1 / 12), 4),
                -0.3, 0.17, -0.02, 0.10, 0.15,
            ],
        },
        {
            "nom": "Forte pluie octobre (risque inondation)",
            "valeurs": [
                10, 120.0, 280.0, 90.0, 28.0, 27.5, 0.45, 0.50, 0.72, 0.35, 3.0,
                round(math.sin(2 * math.pi * 10 / 12), 4),
                round(math.cos(2 * math.pi * 10 / 12), 4),
                1.8, 2.33, 0.05, 0.0, 0.025,
            ],
        },
        {
            "nom": "Sécheresse sévère (août)",
            "valeurs": [
                8, 0.0, 10.0, 2.0, 32.0, 31.5, 0.08, 0.12, 0.30, -0.05, 6.5,
                round(math.sin(2 * math.pi * 8 / 12), 4),
                round(math.cos(2 * math.pi * 8 / 12), 4),
                -1.5, 0.083, -0.08, 0.28, 0.65,
            ],
        },
    ]

    modeles = ["inondation", "secheresse", "chaleur"]

    print("\n" + "═" * 64)
    print("  SAMCAM V4.4.5 — Test de prédiction des 3 modèles")
    print("═" * 64)

    for nom in modeles:
        pkl = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
        if not os.path.exists(pkl):
            print(f"  ❌ {pkl} introuvable → lance d'abord : python3 models/train_model.py")
            return False

    print(f"  ✅ Les 3 fichiers .pkl sont présents\n")

    modeles_charges = {}
    for nom in modeles:
        pkl  = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
        data = joblib.load(pkl)
        modeles_charges[nom] = data
        print(f"  📦 {nom:12s} chargé — seuil={data['seuil']:.2f}")

    print()

    resultats = []
    for scenario in scenarios:
        print(f"  ─── Scénario : {scenario['nom']} ───")
        X = np.array([scenario["valeurs"]])

        scores  = {}
        alertes = {}
        for nom in modeles:
            d      = modeles_charges[nom]
            clf    = d["clf"]
            seuil  = d["seuil"]
            proba  = float(clf.predict_proba(X)[0, 1])
            alerte = proba >= seuil
            scores[nom]  = round(proba, 3)
            alertes[nom] = alerte
            statut = "🔴 ALERTE" if alerte else "🟢 ok"
            print(f"    {nom:12s} : proba={proba:.3f}  seuil={seuil:.2f}  {statut}")

        n_alertes = sum(alertes.values())
        if n_alertes >= 2:
            niveau, icone = "ÉLEVÉ",  "🔴"
        elif n_alertes == 1:
            niveau, icone = "MODÉRÉ", "🟡"
        else:
            niveau, icone = "FAIBLE", "🟢"

        print(f"    → Niveau global : {icone} {niveau}\n")

        resultats.append({
            "scenario": scenario["nom"],
            "scores":   scores,
            "alertes":  alertes,
            "niveau":   niveau,
        })

    reports_dir = os.path.join(ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = os.path.join(reports_dir, f"test_prediction_{ts}.json")
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(
            {"version": "V4.4.5", "date": datetime.datetime.now().isoformat(),
             "resultats": resultats},
            f, ensure_ascii=False, indent=2
        )
    print(f"  💾 Résultats sauvegardés : {outpath}")
    print("═" * 64 + "\n")
    return True


# ─────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SAMCAM V4.4.5 — Pipeline complet")
    parser.add_argument("--days",       type=int, default=7)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--retrain",    action="store_true",
                        help="Force le ré-entraînement des modèles ML")
    parser.add_argument("--test",       action="store_true",
                        help="Test rapide : prédit sur 3 scénarios simulés (sans collecte réseau)")
    args = parser.parse_args()

    print(f"\n🚀 SAMCAM Pipeline V4.4.5 — {datetime.date.today().isoformat()}")

    if args.test:
        ok = test_prediction_v4()
        sys.exit(0 if ok else 1)

    n_data = compter_donnees_reelles()
    print(f"   Données collectées disponibles : {n_data} fichiers")

    run(
        [sys.executable, "data_collection/collect_kribi.py", "--days", str(args.days)],
        "[1/3] Collecte météo + satellite"
    )

    if verifier_retrain_necessaire(force=args.retrain):
        run(
            [sys.executable, "models/train_model.py"],
            "[2/3] Ré-entraînement modèles V4"
        )
    else:
        print(f"\n[PIPELINE] ⏭️  Ré-entraînement ignoré "
              f"({n_data}/{SEUIL_RETRAIN} — --retrain pour forcer)")

    run(
        [sys.executable, "inference/risk_model.py"],
        "[3/3] Prédiction de risque V4"
    )

    copier_rapport_json()

    print(f"\n✅ Pipeline V4.4.5 terminé. Rapports disponibles dans reports/")

    if not args.no_browser:
        ouvrir_dashboard()
