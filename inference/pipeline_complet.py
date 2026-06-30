#!/usr/bin/env python3
"""
SAMCAM V4.5 — Pipeline complet : collecte + prédiction V4 + dashboard

NOUVEAUTÉS V4.5 :
    - verifier_retrain_necessaire() appelle inference/train_model.py --all-horizons
      (remplace models/train_model.py qui n'existe plus)
    - test_prediction_v4() charge et teste tous les horizons disponibles
      (_j1, _j3, _j7) en plus des modèles J0
    - Supprime l'import HeuristiqueChaleur (plus nécessaire)
    - Version bump V4.5

FIX V4.4.6 :
    - Supprime l'ouverture automatique du dashboard dans le navigateur
    - Ajouter --browser pour forcer l'ouverture si souhaité

FIX V4.4.5 :
    - copier_rapport_json() trie par date de modification réelle (getmtime)
    - Priorité explicite au rapport du jour

Ce pipeline orchestre les 3 étapes dans l'ordre :
  1. Collecte des données météo/satellite (data_collection/collect_kribi.py)
  2. Prédiction de risque via les modèles V4 (inference/risk_model.py)
  3. Copie du rapport dans dashboard/latest_report.json

Mode test rapide (sans collecte réseau) :
  python3 inference/pipeline_complet.py --test

Usage complet :
  python3 inference/pipeline_complet.py
  python3 inference/pipeline_complet.py --days 14
  python3 inference/pipeline_complet.py --retrain
  python3 inference/pipeline_complet.py --browser
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

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

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
    Priorité 1 : rapport du jour.
    Priorité 2 : rapport le plus récent par date de modification (getmtime).
    """
    reports_dir   = os.path.join(ROOT, "reports")
    dashboard_dir = os.path.join(ROOT, "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)

    fichiers = glob.glob(os.path.join(reports_dir, "rapport_kribi_*.json"))
    if not fichiers:
        print("⚠️  Aucun rapport JSON trouvé dans reports/ — dashboard non mis à jour.")
        return None

    today = datetime.date.today().isoformat()
    rapport_du_jour = os.path.join(reports_dir, f"rapport_kribi_{today}.json")
    if os.path.exists(rapport_du_jour):
        source = rapport_du_jour
    else:
        source = max(fichiers, key=os.path.getmtime)

    dest = os.path.join(dashboard_dir, "latest_report.json")
    shutil.copy2(source, dest)

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
            print(f"\n[PIPELINE] 🌐 Ouverture du dashboard : {url}")
            time.sleep(0.5)
            webbrowser.open(url)
            return
    print("⚠️  Aucun dashboard HTML trouvé dans dashboard/")


# ────────────────────────────────────────────────────────────────
# MODE TEST — prédiction directe sans collecte réseau
# ────────────────────────────────────────────────────────────────

def test_prediction_v4():
    """
    V4.5 — Test rapide des modèles V4 avec des données simulées.
    Teste les modèles J0 et, si présents, les horizons _j1/_j3/_j7.
    Vérifie que les .pkl se chargent et retournent des prédictions cohérentes.
    """
    import numpy as np
    import joblib

    MODELS_DIR = os.path.join(ROOT, "models")

    # Scénarios de test (16 features — J0/J1/J3 partagent ce vecteur)
    scenarios = [
        {
            "nom": "Saïson sèche normale (janvier)",
            "valeurs_16": [1, 5.0, 30.0, 8.0, 29.0, 28.5, 0.20, 0.25, 0.55, 0.05,
                           -0.519, 0.866, -0.30, 0.17, -0.02, 0.10],
            # J7 = 10 features : mois sin cos pluie_prev_7j anomalie pluie_30j ndvi sm_rootzone sm_deficit temp_max
            "valeurs_10": [1, -0.519, 0.866, 8.0, -0.30, 30.0, 0.55, 0.25, 0.10, 29.0],
        },
        {
            "nom": "Forte pluie octobre (risque inondation)",
            "valeurs_16": [10, 120.0, 280.0, 90.0, 28.0, 27.5, 0.45, 0.50, 0.72, 0.35,
                           0.866, -0.5, 1.80, 2.33, 0.05, 0.00],
            "valeurs_10": [10, 0.866, -0.5, 90.0, 1.80, 280.0, 0.72, 0.50, 0.00, 28.0],
        },
        {
            "nom": "Sécheresse sévère (août)",
            "valeurs_16": [8, 0.0, 10.0, 2.0, 32.0, 31.5, 0.08, 0.12, 0.30, -0.05,
                           -0.866, -0.5, -1.50, 0.083, -0.08, 0.28],
            "valeurs_10": [8, -0.866, -0.5, 2.0, -1.50, 10.0, 0.30, 0.12, 0.28, 32.0],
        },
    ]

    # Définition des horizons à tester avec leur dimension de features attendue
    horizons_config = [
        ("J0",  None, 16),
        ("J+1", "j1", 16),
        ("J+3", "j3", 13),
        ("J+7", "j7", 10),
    ]
    modeles_risque = ["inondation", "secheresse", "chaleur"]

    print("\n" + "═" * 64)
    print("  SAMCAM V4.5 — Test de prédiction multi-horizon")
    print("═" * 64)

    # Vérification des modèles J0 (obligatoires)
    manquants = []
    for nom in modeles_risque:
        pkl = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
        if not os.path.exists(pkl):
            manquants.append(pkl)
    if manquants:
        for m in manquants:
            print(f"  ❌ {m} introuvable → lance : python3 inference/train_model.py")
        return False
    print(f"  ✅ Modèles J0 présents\n")

    # Rapport de disponibilité des horizons
    print("  Modèles disponibles par horizon :")
    for label, suffix, _ in horizons_config:
        for nom in modeles_risque:
            suf = f"_{suffix}" if suffix else ""
            pkl = os.path.join(MODELS_DIR, f"model_{nom}{suf}.pkl")
            statut = "✅" if os.path.exists(pkl) else "⏭️ absent"
            print(f"    model_{nom}{suf:5s}.pkl  {statut}")
    print()

    resultats = []

    for scenario in scenarios:
        print(f"  ─── Scénario : {scenario['nom']} ───")

        for label, suffix, n_feats in horizons_config:
            suf = f"_{suffix}" if suffix else ""
            # Choisir le bon vecteur selon la dimension attendue
            if n_feats == 10:
                X = np.array([scenario["valeurs_10"]])
            else:
                X = np.array([scenario["valeurs_16"][:n_feats]])

            scores_hor  = {}
            alertes_hor = {}
            for nom in modeles_risque:
                pkl = os.path.join(MODELS_DIR, f"model_{nom}{suf}.pkl")
                if not os.path.exists(pkl):
                    continue
                try:
                    d     = joblib.load(pkl)
                    clf   = d["clf"]
                    seuil = d["seuil"]
                    # Adapter la dimension si le modèle a été entraîné avec moins de features
                    n_model = len(d.get("features", []))
                    X_in = X[:, :n_model] if X.shape[1] >= n_model else X
                    proba = float(clf.predict_proba(X_in)[0, 1])
                    alerte = proba >= seuil
                    scores_hor[nom]  = round(proba, 3)
                    alertes_hor[nom] = alerte
                    statut = "🔴 ALERTE" if alerte else "🟢 ok"
                    print(f"    [{label}] {nom:12s} : proba={proba:.3f}  "
                          f"seuil={seuil:.2f}  {statut}")
                except Exception as e:
                    print(f"    [{label}] {nom:12s} : ⚠️  erreur — {e}")

            if scores_hor:
                n_alertes = sum(alertes_hor.values())
                if n_alertes >= 2:
                    niveau, icone = "ELEVÉ",  "🔴"
                elif n_alertes == 1:
                    niveau, icone = "MODÉRÉ", "🟡"
                else:
                    niveau, icone = "FAIBLE", "🟢"
                print(f"    [{label}] Niveau global : {icone} {niveau}")

            resultats.append({
                "scenario": scenario["nom"],
                "horizon":  label,
                "scores":   scores_hor,
            })
        print()

    reports_dir = os.path.join(ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = os.path.join(reports_dir, f"test_prediction_{ts}.json")
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(
            {"version": "V4.5", "date": datetime.datetime.now().isoformat(),
             "resultats": resultats},
            f, ensure_ascii=False, indent=2
        )
    print(f"  💾 Résultats sauvegardés : {outpath}")
    print("═" * 64 + "\n")
    return True


# ────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SAMCAM V4.5 — Pipeline complet")
    parser.add_argument("--days",    type=int, default=7)
    parser.add_argument("--browser", action="store_true",
                        help="Ouvre le dashboard dans le navigateur après l'exécution")
    parser.add_argument("--retrain", action="store_true",
                        help="Force le ré-entraînement des modèles ML")
    parser.add_argument("--test",    action="store_true",
                        help="Test rapide : prédit sur 3 scénarios simulés (sans collecte réseau)")
    args = parser.parse_args()

    print(f"\n🚀 SAMCAM Pipeline V4.5 — {datetime.date.today().isoformat()}")

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
        # V4.5 : inference/train_model.py --all-horizons (pas models/train_model.py)
        run(
            [sys.executable, "inference/train_model.py", "--all-horizons"],
            "[2/3] Ré-entraînement modèles V4.4 (tous horizons)"
        )
    else:
        print(f"\n[PIPELINE] ⏭️  Ré-entraînement ignoré "
              f"({n_data}/{SEUIL_RETRAIN} — --retrain pour forcer)")

    run(
        [sys.executable, "inference/risk_model.py"],
        "[3/3] Prédiction de risque V4"
    )

    copier_rapport_json()

    print(f"\n✅ Pipeline V4.5 terminé. Rapports disponibles dans reports/")
    dashboard_path = os.path.join(ROOT, "dashboard", "samcam-v4-dashboard.html")
    print(f"[PIPELINE] 🌐 Dashboard : file://{os.path.abspath(dashboard_path)}")

    if args.browser:
        ouvrir_dashboard()
