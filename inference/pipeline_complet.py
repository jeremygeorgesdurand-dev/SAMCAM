#!/usr/bin/env python3
"""
SAMCAM V4.4.3 — Pipeline complet : collecte + prédiction V4 + dashboard

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
    reports_dir   = os.path.join(ROOT, "reports")
    dashboard_dir = os.path.join(ROOT, "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)

    fichiers = sorted(glob.glob(os.path.join(reports_dir, "rapport_kribi_*.json")))
    if not fichiers:
        print("⚠️  Aucun rapport JSON trouvé dans reports/ — dashboard non mis à jour.")
        return None

    source = fichiers[-1]
    dest   = os.path.join(dashboard_dir, "latest_report.json")
    shutil.copy2(source, dest)
    print(f"\n[PIPELINE] 📋 Rapport JSON copié :")
    print(f"           Source : {source}")
    print(f"           Dest   : {dest}")
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
# Simule des données météo réalistes pour Kribi en saison sèche
# ─────────────────────────────────────────────────────────────

def test_prediction_v4():
    """
    Test rapide des 3 modèles V4.4.3 avec des données simulées.
    Vérifie que les .pkl se chargent et retournent des prédictions cohérentes.
    """
    import numpy as np
    import joblib

    MODELS_DIR = os.path.join(ROOT, "models")
    FEATURES = [
        "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
        "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
        "ndvi", "ndwi", "et0_semaine",
        "sin_mois", "cos_mois",
        "anomalie_pluie", "ratio_30j_7j",
        "trend_sm", "sm_deficit",
        "ratio_et0_pluie",
    ]

    # ── Scénarios de test ────────────────────────────────────
    scenarios = [
        {
            "nom": "Saison sèche normale (janvier)",
            "valeurs": [
                1,      # mois
                5.0,    # pluie_7j  (mm)
                30.0,   # pluie_30j
                8.0,    # pluie_prev_7j
                29.0,   # temp_max
                28.5,   # temp_max_3j
                0.20,   # sm_surface
                0.25,   # sm_rootzone
                0.55,   # ndvi
                0.05,   # ndwi
                4.5,    # et0_semaine
                # dérivées
                round(__import__('math').sin(2 * __import__('math').pi * 1 / 12), 4),
                round(__import__('math').cos(2 * __import__('math').pi * 1 / 12), 4),
                -0.3,   # anomalie_pluie
                0.17,   # ratio_30j_7j
                -0.02,  # trend_sm
                0.10,   # sm_deficit
                0.15,   # ratio_et0_pluie
            ],
        },
        {
            "nom": "Forte pluie octobre (risque inondation)",
            "valeurs": [
                10,     # mois
                120.0,  # pluie_7j  (mm élevé)
                280.0,  # pluie_30j
                90.0,   # pluie_prev_7j
                28.0,   # temp_max
                27.5,   # temp_max_3j
                0.45,   # sm_surface (saturé)
                0.50,   # sm_rootzone
                0.72,   # ndvi
                0.35,   # ndwi (élevé)
                3.0,    # et0_semaine
                round(__import__('math').sin(2 * __import__('math').pi * 10 / 12), 4),
                round(__import__('math').cos(2 * __import__('math').pi * 10 / 12), 4),
                1.8,    # anomalie_pluie
                2.33,   # ratio_30j_7j
                0.05,   # trend_sm
                0.0,    # sm_deficit
                0.025,  # ratio_et0_pluie
            ],
        },
        {
            "nom": "Sécheresse sévère (août)",
            "valeurs": [
                8,      # mois
                0.0,    # pluie_7j
                10.0,   # pluie_30j
                2.0,    # pluie_prev_7j
                32.0,   # temp_max
                31.5,   # temp_max_3j
                0.08,   # sm_surface (très bas)
                0.12,   # sm_rootzone
                0.30,   # ndvi (dégradé)
                -0.05,  # ndwi
                6.5,    # et0_semaine (fort)
                round(__import__('math').sin(2 * __import__('math').pi * 8 / 12), 4),
                round(__import__('math').cos(2 * __import__('math').pi * 8 / 12), 4),
                -1.5,   # anomalie_pluie
                0.083,  # ratio_30j_7j
                -0.08,  # trend_sm
                0.28,   # sm_deficit
                0.65,   # ratio_et0_pluie
            ],
        },
    ]

    modeles = ["inondation", "secheresse", "chaleur"]

    print("\n" + "═" * 64)
    print("  SAMCAM V4.4.3 — Test de prédiction des 3 modèles")
    print("═" * 64)

    # Vérifier que les modèles existent
    for nom in modeles:
        pkl = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
        if not os.path.exists(pkl):
            print(f"  ❌ {pkl} introuvable → lance d'abord : python3 models/train_model.py")
            return False

    print(f"  ✅ Les 3 fichiers .pkl sont présents\n")

    # Charger les modèles
    modeles_charges = {}
    for nom in modeles:
        pkl  = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
        data = joblib.load(pkl)
        modeles_charges[nom] = data
        print(f"  📦 {nom:12s} chargé — seuil={data['seuil']:.2f}")

    print()

    # Lancer les 3 scénarios
    resultats = []
    for scenario in scenarios:
        print(f"  ─── Scénario : {scenario['nom']} ───")
        X = np.array([scenario["valeurs"]])

        scores = {}
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

        # Niveau d'alerte global
        n_alertes = sum(alertes.values())
        if n_alertes >= 2:
            niveau = "ÉLEVÉ"
            icone  = "🔴"
        elif n_alertes == 1:
            niveau = "MODÉRÉ"
            icone  = "🟡"
        else:
            niveau = "FAIBLE"
            icone  = "🟢"

        print(f"    → Niveau global : {icone} {niveau}")
        print()

        resultats.append({
            "scenario": scenario["nom"],
            "scores":   scores,
            "alertes":  alertes,
            "niveau":   niveau,
        })

    # Sauvegarder le résultat dans reports/
    reports_dir = os.path.join(ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = os.path.join(reports_dir, f"test_prediction_{ts}.json")
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(
            {"version": "V4.4.3", "date": datetime.datetime.now().isoformat(),
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

    parser = argparse.ArgumentParser(description="SAMCAM V4.4.3 — Pipeline complet")
    parser.add_argument("--days",       type=int, default=7)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--retrain",    action="store_true",
                        help="Force le ré-entraînement des modèles ML")
    parser.add_argument("--test",       action="store_true",
                        help="Test rapide : prédit sur 3 scénarios simulés (sans collecte réseau)")
    args = parser.parse_args()

    print(f"\n🚀 SAMCAM Pipeline V4.4.3 — {datetime.date.today().isoformat()}")

    # ── Mode test uniquement ──────────────────────────────────
    if args.test:
        ok = test_prediction_v4()
        sys.exit(0 if ok else 1)

    # ── Mode pipeline complet ────────────────────────────────
    n_data = compter_donnees_reelles()
    print(f"   Données collectées disponibles : {n_data} fichiers")

    # Étape 1 — Collecte
    run(
        [sys.executable, "data_collection/collect_kribi.py", "--days", str(args.days)],
        "[1/3] Collecte météo + satellite"
    )

    # Étape 2 — Ré-entraînement conditionnel
    if verifier_retrain_necessaire(force=args.retrain):
        run(
            [sys.executable, "models/train_model.py"],
            "[2/3] Ré-entraînement modèles V4"
        )
    else:
        print(f"\n[PIPELINE] ⏭️  Ré-entraînement ignoré "
              f"({n_data}/{SEUIL_RETRAIN} — --retrain pour forcer)")

    # Étape 3 — Prédiction V4
    run(
        [sys.executable, "inference/risk_model.py"],
        "[3/3] Prédiction de risque V4"
    )

    # Export JSON → dashboard/
    copier_rapport_json()

    print(f"\n✅ Pipeline V4.4.3 terminé. Rapports disponibles dans reports/")

    if not args.no_browser:
        ouvrir_dashboard()
