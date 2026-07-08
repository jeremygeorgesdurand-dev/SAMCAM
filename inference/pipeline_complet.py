#!/usr/bin/env python3
"""
SAMCAM V5.0.2 — Pipeline complet multi-zones : collecte + analyse + dashboard

FIX V5.0.2 :
    - Étape [2/4] : utilise training/train_zonal_models.py (modèles zonaux V5)
      à la place de inference/train_model.py (modèles V4 génériques).
      Produit 24 .pkl (8 zones × 3 risques) dans models/zonal/.

FIX V5.0.1 :
    - Correction appel collect_zone.py : suppression de --all (argument inexistant).
      collect_zone.py collecte toutes les zones quand --zone est absent.

NOUVEAUTÉS V5.0 :
    - Étape 1 : collect_zone.py  (collecte toutes les zones, sans --zone)
      remplace collect_kribi.py (zone unique Kribi seulement)
    - Étape 3 : analyse_zone.py --all  (analyse toutes les zones)
      remplace risk_model.py (zone unique Kribi seulement)
    - copier_rapport_multi() : copie les 8 rapports zones dans dashboard/
      ET maintient dashboard/latest_report.json pointant sur Kribi (compat)
    - Banner mis à jour V5.0
    - Compat descendante : --test et --browser conservés

FIX V4.5.2 :
    - CORRECTION BUG scénarios J+3 (faux positif inondation en saison sèche)
    - make_dataframe() utilise le vecteur valeurs_13 pour n_feats==13

FIX V4.5.1 :
    - Passe un pd.DataFrame avec les vrais noms de features au clf.predict_proba()
    - Gère les .pkl corrompus avec try/except propre
    - Ajoute purge_stale_pkl()

NOUVEAUTÉS V4.5 :
    - verifier_retrain_necessaire() appelle inference/train_model.py --all-horizons
    - test_prediction_v4() charge tous les horizons (_j1, _j3, _j7)

Usage :
    python3 inference/pipeline_complet.py               # toutes les zones
    python3 inference/pipeline_complet.py --days 14
    python3 inference/pipeline_complet.py --retrain
    python3 inference/pipeline_complet.py --browser
    python3 inference/pipeline_complet.py --test        # test rapide sans réseau
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

# Zones gérées par le pipeline multi-zones
ZONES_SLUGS = [
    "kribi", "ebolowa", "kumba", "bafoussam",
    "yaounde_peri", "ngaoundere", "garoua", "maroua",
]


def run(cmd: list, label: str):
    print(f"\n{'='*60}")
    print(f"🔄 {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"❌ {label} a échoué (code {result.returncode})")
        sys.exit(result.returncode)


def copier_rapport_multi():
    """
    V5.0 — Copie tous les rapports zones du jour dans dashboard/.
    Maintient aussi dashboard/latest_report.json → rapport Kribi (compat V4).
    """
    reports_dir   = os.path.join(ROOT, "reports")
    dashboard_dir = os.path.join(ROOT, "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)

    today = datetime.date.today().isoformat()
    copies = []

    for slug in ZONES_SLUGS:
        exact = os.path.join(reports_dir, f"rapport_{slug}_{today}.json")
        candidats = sorted(glob.glob(os.path.join(reports_dir, f"rapport_{slug}_*.json")))
        if os.path.exists(exact):
            source = exact
        elif candidats:
            source = max(candidats, key=os.path.getmtime)
        else:
            print(f"  ⚠️  Pas de rapport pour {slug} — ignoré")
            continue

        dest = os.path.join(dashboard_dir, f"rapport_{slug}.json")
        shutil.copy2(source, dest)
        copies.append((slug, os.path.basename(source), dest))

    # latest_report.json → Kribi (compat dashboard V4)
    kribi_dash = os.path.join(dashboard_dir, "rapport_kribi.json")
    if os.path.exists(kribi_dash):
        shutil.copy2(kribi_dash, os.path.join(dashboard_dir, "latest_report.json"))

    print(f"\n[PIPELINE] 📋 Rapports copiés dans dashboard/ :")
    for slug, src, dst in copies:
        print(f"           {slug:<20} ← {src}")
    return copies


def compter_donnees_reelles() -> int:
    data_dir = os.path.join(ROOT, "data")
    return len(glob.glob(os.path.join(data_dir, "*.json")))


def verifier_retrain_necessaire(force: bool = False) -> bool:
    if force:
        print("\n[PIPELINE] 🔁 --retrain forcé.")
        return True
    n = compter_donnees_reelles()
    if n >= SEUIL_RETRAIN:
        print(f"\n[PIPELINE] 🔁 {n} fichiers data ≥ seuil {SEUIL_RETRAIN} → ré-entraînement.")
        return True
    return False


def ouvrir_dashboard():
    for name in ["samcam-v4-dashboard.html", "index.html", "dashboard.html"]:
        path = os.path.join(ROOT, "dashboard", name)
        if os.path.exists(path):
            url = "file://" + os.path.abspath(path)
            print(f"\n[PIPELINE] 🌐 Ouverture du dashboard : {url}")
            time.sleep(0.5)
            webbrowser.open(url)
            return
    print("⚠️  Aucun dashboard HTML trouvé dans dashboard/")


# ────────────────────────────────────────────────────────────────
# UTILITAIRE — chargement sécurisé d'un .pkl
# ────────────────────────────────────────────────────────────────

def charger_pkl_securise(chemin: str):
    import joblib
    try:
        d = joblib.load(chemin)
        if not isinstance(d, dict) or "clf" not in d or "seuil" not in d:
            print(f"  ⚠️  {os.path.basename(chemin)} : structure invalide — ignoré")
            return None
        if not hasattr(d["clf"], "predict_proba"):
            print(f"  ⚠️  {os.path.basename(chemin)} : clf sans predict_proba — ignoré")
            return None
        return d
    except Exception as e:
        print(f"  ⚠️  {os.path.basename(chemin)} : impossible de charger ({e}) — ignoré")
        return None


def purge_stale_pkl(models_dir: str, noms: list):
    suffixes = ["", "_j1", "_j3", "_j7"]
    purges = []
    for nom in noms:
        for suf in suffixes:
            pkl = os.path.join(models_dir, f"model_{nom}{suf}.pkl")
            if not os.path.exists(pkl):
                continue
            if charger_pkl_securise(pkl) is None:
                try:
                    os.remove(pkl)
                    purges.append(os.path.basename(pkl))
                except OSError:
                    pass
    if purges:
        print(f"\n  🧹 PKL obsolètes supprimés : {purges}")
        print(f"     Relancez train_model.py --force pour les régénérer.\n")


# ────────────────────────────────────────────────────────────────
# MODE TEST — prédiction directe sans collecte réseau
# ────────────────────────────────────────────────────────────────

FEATURES_16 = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi",
    "sin_mois", "cos_mois",
    "anomalie_pluie", "ratio_30j_7j", "trend_sm", "sm_deficit",
]
FEATURES_13 = [
    "mois", "sin_mois", "cos_mois",
    "pluie_prev_7j", "anomalie_pluie", "pluie_30j",
    "sm_surface", "sm_rootzone", "ndvi", "ndwi",
    "temp_max_3j", "ratio_30j_7j", "sm_deficit",
]
FEATURES_10 = [
    "mois", "sin_mois", "cos_mois",
    "pluie_prev_7j", "anomalie_pluie", "pluie_30j",
    "ndvi", "sm_rootzone", "sm_deficit", "temp_max",
]
FEATURES_PAR_DIM = {16: FEATURES_16, 13: FEATURES_13, 10: FEATURES_10}


def make_dataframe(valeurs: list, features: list):
    import pandas as pd
    n = len(features)
    v = list(valeurs[:n]) + [0.0] * max(0, n - len(valeurs))
    return pd.DataFrame([v], columns=features)


def test_prediction_v4():
    """
    V4.5.2 — Test rapide des modèles V4 avec des données simulées.
    Scénarios : saison des pluies, saison sèche, sécheresse sévère.
    """
    import numpy as np

    models_dir = os.path.join(ROOT, "models")
    noms = ["inondation", "secheresse", "chaleur"]

    print("\n" + "="*60)
    print("🧪 MODE TEST — prédiction V4.5.2 (données simulées)")
    print("="*60)

    purge_stale_pkl(models_dir, noms)

    val16_pluies = [7, 185, 420, 210, 29.5, 31.2, 0.42, 0.51, 0.68, 0.12,
                    0.866, -0.5, 1.8, 2.27, 0.02, 0.05]
    val13_pluies = [7, 0.866, -0.5, 210, 1.8, 420, 0.42, 0.51, 0.68, 0.12, 31.2, 2.27, 0.05]
    val10_pluies = [7, 0.866, -0.5, 210, 1.8, 420, 0.68, 0.51, 0.05, 29.5]

    val16_seche  = [2, 5, 12, 3, 36.8, 38.1, 0.08, 0.12, 0.22, -0.15,
                    0.309, 0.951, -0.9, 0.42, -0.01, 0.72]
    val13_seche  = [2, 0.309, 0.951, 3, -0.9, 12, 0.08, 0.12, 0.22, -0.15, 38.1, 0.42, 0.72]
    val10_seche  = [2, 0.309, 0.951, 3, -0.9, 12, 0.22, 0.12, 0.72, 36.8]

    val16_sev    = [4, 2, 8, 1, 38.5, 39.2, 0.05, 0.08, 0.15, -0.20,
                    0.0, 1.0, -1.2, 0.25, -0.02, 0.88]
    val13_sev    = [4, 0.0, 1.0, 1, -1.2, 8, 0.05, 0.08, 0.15, -0.20, 39.2, 0.25, 0.88]
    val10_sev    = [4, 0.0, 1.0, 1, -1.2, 8, 0.15, 0.08, 0.88, 38.5]

    scenarios = [
        ("🌧️  Saison des pluies (juil)", val16_pluies, val13_pluies, val10_pluies),
        ("☀️  Saison sèche (fév)",       val16_seche,  val13_seche,  val10_seche),
        ("🏜️  Sécheresse sévère (avr)",  val16_sev,    val13_sev,    val10_sev),
    ]

    horizons = [("J0", ""), ("J+1", "_j1"), ("J+3", "_j3"), ("J+7", "_j7")]
    resultats_ok = True

    for titre, v16, v13, v10 in scenarios:
        print(f"\n  {titre}")
        for nom in noms:
            for label_h, suf in horizons:
                pkl = os.path.join(models_dir, f"model_{nom}{suf}.pkl")
                if not os.path.exists(pkl):
                    continue
                d = charger_pkl_securise(pkl)
                if d is None:
                    resultats_ok = False
                    continue
                clf     = d["clf"]
                seuil   = d["seuil"]
                n_feats = len(d.get("features", FEATURES_16))
                if n_feats == 13:
                    vecteur = v13
                elif n_feats == 10:
                    vecteur = v10
                else:
                    vecteur = v16
                features_noms = FEATURES_PAR_DIM.get(n_feats, FEATURES_16)
                df    = make_dataframe(vecteur, features_noms)
                proba = clf.predict_proba(df)[0][1]
                pred  = "⚠️ OUI" if proba >= seuil else "✅ non"
                print(f"      {nom:<12} {label_h}  proba={proba:.3f} seuil={seuil:.2f} → {pred}")

    print("\n" + "="*60)
    if resultats_ok:
        print("✅ Test V4.5.2 terminé — tous les modèles chargés correctement.")
    else:
        print("⚠️  Test terminé avec des avertissements (certains modèles ignorés).")
    return resultats_ok


# ────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="SAMCAM Pipeline V5.0.2 — collecte + analyse multi-zones"
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="Nombre de jours d'historique à collecter (défaut: 7)"
    )
    parser.add_argument(
        "--retrain", action="store_true",
        help="Forcer le ré-entraînement des modèles"
    )
    parser.add_argument(
        "--browser", action="store_true",
        help="Ouvrir le dashboard dans le navigateur après le pipeline"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test rapide : prédit sur 3 scénarios simulés (sans collecte réseau)"
    )
    args = parser.parse_args()

    print(f"\n🚀 SAMCAM Pipeline V5.0.2 — {datetime.date.today().isoformat()}")
    print(f"   Zones : {len(ZONES_SLUGS)} zones ({', '.join(ZONES_SLUGS)})")

    if args.test:
        ok = test_prediction_v4()
        sys.exit(0 if ok else 1)

    n_data = compter_donnees_reelles()
    print(f"   Données collectées disponibles : {n_data} fichiers")

    # ── Étape 1 : Collecte toutes les zones (sans --zone = toutes)
    run(
        [sys.executable, "data_collection/collect_zone.py", "--days", str(args.days)],
        "[1/4] Collecte météo + satellite — toutes les zones"
    )

    # ── Étape 2 : Ré-entraînement conditionnel (modèles zonaux V5)
    if verifier_retrain_necessaire(force=args.retrain):
        run(
            [sys.executable, "training/train_zonal_models.py", "--all-horizons"],
            "[2/4] Ré-entraînement modèles zonaux V5 (tous horizons)"
        )
    else:
        print(f"\n[PIPELINE] ⏭️  Ré-entraînement ignoré "
              f"({n_data}/{SEUIL_RETRAIN} — --retrain pour forcer)")

    # ── Étape 3 : Analyse risque toutes les zones
    run(
        [sys.executable, "inference/analyse_zone.py", "--all"],
        "[3/4] Analyse des risques — toutes les zones"
    )

    # ── Étape 4 : Copie des rapports dans dashboard/
    copier_rapport_multi()

    print(f"\n✅ Pipeline V5.0.2 terminé — {len(ZONES_SLUGS)} zones analysées.")
    print(f"   Rapports : reports/rapport_<zone>_{datetime.date.today().isoformat()}.json")
    dashboard_path = os.path.join(ROOT, "dashboard", "samcam-v4-dashboard.html")
    print(f"[PIPELINE] 🌐 Dashboard : file://{os.path.abspath(dashboard_path)}")

    if args.browser:
        ouvrir_dashboard()


if __name__ == "__main__":
    main()
