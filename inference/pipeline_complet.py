#!/usr/bin/env python3
"""
SAMCAM V4.5.2 — Pipeline complet : collecte + prédiction V4 + dashboard

FIX V4.5.2 :
    - CORRECTION BUG scénarios J+3 (faux positif inondation en saison sèche / sécheresse) :
        Le code prenait valeurs_16[:13] pour alimenter FEATURES_13, mais l'ordre des
        colonnes de FEATURES_13 est différent de FEATURES_16 — les valeurs étaient donc
        mappées sur les mauvaises features, ce qui produisait un proba=0.75 d'inondation
        en pleine saison sèche. Fix : chaque scénario déclare maintenant un vecteur
        valeurs_13 dédié dont l'ordre respecte exactement FEATURES_13 :
            [mois, sin_mois, cos_mois,
             pluie_prev_7j, anomalie_pluie, pluie_30j,
             sm_surface, sm_rootzone, ndvi, ndwi,
             temp_max_3j, ratio_30j_7j, sm_deficit]
        Résultat : J+3 inondation saison sèche = 🟢 ok, J+3 sécheresse sévère = 🟢 ok.
    - make_dataframe() utilise maintenant le vecteur valeurs_13 pour n_feats==13
      (au lieu de valeurs_16[:13]).
    - Version bump V4.5.2.

FIX V4.5.1 :
    - Passe un pd.DataFrame avec les vrais noms de features au clf.predict_proba()
      → supprime le UserWarning sklearn "X does not have valid feature names"
    - Gère les .pkl corrompus / hérités d'une ancienne version (ex: HeuristiqueChaleur)
      avec un try/except propre : si le pkl ne peut pas être désérialisé correctement
      (attribut manquant, classe inconnue), il est ignoré avec un message clair
      au lieu de crasher avec une AttributeError cryptique.
    - Ajoute purge_stale_pkl() : supprime automatiquement les .pkl dont le chargement
      échoue au démarrage du test (évite les erreurs répétées à chaque scénario).

NOUVEAUTÉS V4.5 :
    - verifier_retrain_necessaire() appelle inference/train_model.py --all-horizons
      (remplace models/train_model.py qui n'existe plus)
    - test_prediction_v4() charge et teste tous les horizons disponibles
      (_j1, _j3, _j7) en plus des modèles J0
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
# UTILITAIRE — chargement sécurisé d'un .pkl
# ────────────────────────────────────────────────────────────────

def charger_pkl_securise(chemin: str):
    """
    Charge un fichier .pkl joblib de façon sécurisée.

    Retourne le dict {'clf', 'seuil', 'features', ...} si valide,
    ou None si le fichier est corrompu / hérité d'une ancienne version
    (ex: contient HeuristiqueChaleur ou une autre classe inconnue).

    Cause typique : un ancien model_chaleur.pkl généré avec une classe
    HeuristiqueChaleur définie dans train_model.py n'est plus désérialisable
    dans pipeline_complet.py qui ne connaît pas cette classe.
    Solution propre : ignorer le pkl invalide plutôt que crasher.
    """
    import joblib

    try:
        d = joblib.load(chemin)
        # Vérification minimale de structure
        if not isinstance(d, dict) or "clf" not in d or "seuil" not in d:
            print(f"  ⚠️  {os.path.basename(chemin)} : structure invalide (pas de clf/seuil) — ignoré")
            return None
        # Test rapide que le clf est bien appelable
        if not hasattr(d["clf"], "predict_proba"):
            print(f"  ⚠️  {os.path.basename(chemin)} : clf sans predict_proba — ignoré")
            return None
        return d
    except Exception as e:
        print(f"  ⚠️  {os.path.basename(chemin)} : impossible de charger ({e}) — ignoré")
        print(f"      → Supprimez ce fichier et relancez : python3 inference/train_model.py --force")
        return None


def purge_stale_pkl(models_dir: str, noms: list):
    """
    Détecte et supprime les .pkl qui ne peuvent pas être chargés
    (hérités d'une ancienne version avec classes custom).
    Appelé une seule fois au début du test pour éviter les erreurs répétées.
    """
    suffixes = ["", "_j1", "_j3", "_j7"]
    purges = []
    for nom in noms:
        for suf in suffixes:
            pkl = os.path.join(models_dir, f"model_{nom}{suf}.pkl")
            if not os.path.exists(pkl):
                continue
            d = charger_pkl_securise(pkl)
            if d is None:
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

# Noms de features par dimension — alignés sur train_model.py V4.4
FEATURES_16 = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi",
    "sin_mois", "cos_mois",
    "anomalie_pluie", "ratio_30j_7j", "trend_sm", "sm_deficit",
]
# FEATURES_13 : ordre exact issu de train_model.py FEATURES_J3
# [mois, sin_mois, cos_mois,
#  pluie_prev_7j, anomalie_pluie, pluie_30j,
#  sm_surface, sm_rootzone, ndvi, ndwi,
#  temp_max_3j, ratio_30j_7j, sm_deficit]
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
    """
    Construit un pd.DataFrame d'une ligne avec les bons noms de colonnes.
    Évite le UserWarning sklearn "X does not have valid feature names".
    Si la liste de features attendue ne correspond pas à la dimension du vecteur,
    tronque ou complète avec des zéros.
    """
    import pandas as pd
    n = len(features)
    v = list(valeurs[:n]) + [0.0] * max(0, n - len(valeurs))
    return pd.DataFrame([v], columns=features)


def test_prediction_v4():
    """
    V4.5.2 — Test rapide des modèles V4 avec des données simulées.

    Chaque scénario déclare trois vecteurs indépendants dont l'ordre
    correspond EXACTEMENT à FEATURES_16, FEATURES_13 et FEATURES_10.
    Ceci corrige le faux positif inondation J+3 introduit en V4.5.1
    où valeurs_16[:13] était passé à FEATURES_13 dont l'ordre diffère.

    FEATURES_13 : mois | sin_mois | cos_mois |
                  pluie_prev_7j | anomalie_pluie | pluie_30j |
                  sm_surface | sm_rootzone | ndvi | ndwi |
                  temp_max_3j | ratio_30j_7j | sm_deficit
    """
    import joblib  # noqa: F401 (utilisé dans charger_pkl_securise)

    MODELS_DIR = os.path.join(ROOT, "models")

    # ── Scénarios de test ──────────────────────────────────────────
    # Chaque vecteur suit EXACTEMENT l'ordre de sa liste de features :
    #   valeurs_16 → FEATURES_16  (J0 et J+1)
    #   valeurs_13 → FEATURES_13  (J+3)   ← FIX V4.5.2 : vecteur dédié
    #   valeurs_10 → FEATURES_10  (J+7)
    scenarios = [
        {
            "nom": "Saïson sèche normale (janvier)",
            # FEATURES_16 : mois | pluie_7j | pluie_30j | pluie_prev_7j |
            #   temp_max | temp_max_3j | sm_surface | sm_rootzone |
            #   ndvi | ndwi | sin_mois | cos_mois |
            #   anomalie_pluie | ratio_30j_7j | trend_sm | sm_deficit
            "valeurs_16": [
                1,      # mois
                5.0,    # pluie_7j
                30.0,   # pluie_30j
                8.0,    # pluie_prev_7j
                29.0,   # temp_max
                28.5,   # temp_max_3j
                0.20,   # sm_surface
                0.25,   # sm_rootzone
                0.55,   # ndvi
                0.05,   # ndwi
                -0.519, # sin_mois
                0.866,  # cos_mois
                -0.30,  # anomalie_pluie  (pluie 30 % sous la normale)
                0.17,   # ratio_30j_7j
                -0.02,  # trend_sm        (légère baisse humidité)
                0.10,   # sm_deficit
            ],
            # FEATURES_13 : mois | sin_mois | cos_mois |
            #   pluie_prev_7j | anomalie_pluie | pluie_30j |
            #   sm_surface | sm_rootzone | ndvi | ndwi |
            #   temp_max_3j | ratio_30j_7j | sm_deficit
            "valeurs_13": [
                1,      # mois
                -0.519, # sin_mois
                0.866,  # cos_mois
                8.0,    # pluie_prev_7j
                -0.30,  # anomalie_pluie
                30.0,   # pluie_30j
                0.20,   # sm_surface
                0.25,   # sm_rootzone
                0.55,   # ndvi
                0.05,   # ndwi
                28.5,   # temp_max_3j
                0.17,   # ratio_30j_7j
                0.10,   # sm_deficit
            ],
            # FEATURES_10 : mois | sin_mois | cos_mois |
            #   pluie_prev_7j | anomalie_pluie | pluie_30j |
            #   ndvi | sm_rootzone | sm_deficit | temp_max
            "valeurs_10": [
                1,      # mois
                -0.519, # sin_mois
                0.866,  # cos_mois
                8.0,    # pluie_prev_7j
                -0.30,  # anomalie_pluie
                30.0,   # pluie_30j
                0.55,   # ndvi
                0.25,   # sm_rootzone
                0.10,   # sm_deficit
                29.0,   # temp_max
            ],
        },
        {
            "nom": "Forte pluie octobre (risque inondation)",
            "valeurs_16": [
                10,     # mois
                120.0,  # pluie_7j
                280.0,  # pluie_30j
                90.0,   # pluie_prev_7j
                28.0,   # temp_max
                27.5,   # temp_max_3j
                0.45,   # sm_surface
                0.50,   # sm_rootzone
                0.72,   # ndvi
                0.35,   # ndwi
                0.866,  # sin_mois
                -0.5,   # cos_mois
                1.80,   # anomalie_pluie
                2.33,   # ratio_30j_7j
                0.05,   # trend_sm
                0.00,   # sm_deficit
            ],
            "valeurs_13": [
                10,     # mois
                0.866,  # sin_mois
                -0.5,   # cos_mois
                90.0,   # pluie_prev_7j
                1.80,   # anomalie_pluie
                280.0,  # pluie_30j
                0.45,   # sm_surface
                0.50,   # sm_rootzone
                0.72,   # ndvi
                0.35,   # ndwi
                27.5,   # temp_max_3j
                2.33,   # ratio_30j_7j
                0.00,   # sm_deficit
            ],
            "valeurs_10": [
                10,     # mois
                0.866,  # sin_mois
                -0.5,   # cos_mois
                90.0,   # pluie_prev_7j
                1.80,   # anomalie_pluie
                280.0,  # pluie_30j
                0.72,   # ndvi
                0.50,   # sm_rootzone
                0.00,   # sm_deficit
                28.0,   # temp_max
            ],
        },
        {
            "nom": "Sécheresse sévère (août)",
            "valeurs_16": [
                8,      # mois
                0.0,    # pluie_7j
                10.0,   # pluie_30j
                2.0,    # pluie_prev_7j
                32.0,   # temp_max
                31.5,   # temp_max_3j
                0.08,   # sm_surface
                0.12,   # sm_rootzone
                0.30,   # ndvi
                -0.05,  # ndwi
                -0.866, # sin_mois
                -0.5,   # cos_mois
                -1.50,  # anomalie_pluie  (pluie très en-dessous de la normale)
                0.083,  # ratio_30j_7j
                -0.08,  # trend_sm        (assèchement progressif)
                0.28,   # sm_deficit
            ],
            "valeurs_13": [
                8,      # mois
                -0.866, # sin_mois
                -0.5,   # cos_mois
                2.0,    # pluie_prev_7j
                -1.50,  # anomalie_pluie
                10.0,   # pluie_30j
                0.08,   # sm_surface
                0.12,   # sm_rootzone
                0.30,   # ndvi
                -0.05,  # ndwi
                31.5,   # temp_max_3j
                0.083,  # ratio_30j_7j
                0.28,   # sm_deficit
            ],
            "valeurs_10": [
                8,      # mois
                -0.866, # sin_mois
                -0.5,   # cos_mois
                2.0,    # pluie_prev_7j
                -1.50,  # anomalie_pluie
                10.0,   # pluie_30j
                0.30,   # ndvi
                0.12,   # sm_rootzone
                0.28,   # sm_deficit
                32.0,   # temp_max
            ],
        },
    ]

    # Horizons : (label_affichage, suffix_fichier, n_features_attendu)
    horizons_config = [
        ("J0",  None, 16),
        ("J+1", "j1", 16),
        ("J+3", "j3", 13),
        ("J+7", "j7", 10),
    ]
    modeles_risque = ["inondation", "secheresse", "chaleur"]

    print("\n" + "═" * 64)
    print("  SAMCAM V4.5.2 — Test de prédiction multi-horizon")
    print("═" * 64)

    # ── Purge des pkl obsolètes (hérités d'une version antérieure) ──
    purge_stale_pkl(MODELS_DIR, modeles_risque)

    # ── Vérification des modèles J0 obligatoires ──
    manquants = []
    for nom in modeles_risque:
        pkl = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
        if os.path.exists(pkl) and charger_pkl_securise(pkl) is None:
            pass  # déjà purgé ou inutilisable → ignoré
        elif not os.path.exists(pkl) and nom != "chaleur":
            manquants.append(pkl)

    if manquants:
        for m in manquants:
            print(f"  ❌ {m} introuvable → lance : python3 inference/train_model.py")
        return False
    print(f"  ✅ Modèles J0 présents\n")

    # ── Rapport de disponibilité ──
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

            # FIX V4.5.2 : vecteur dédié par dimension pour éviter le
            # mauvais mapping valeurs_16[:13] → FEATURES_13 (ordres différents)
            if n_feats == 13:
                valeurs_brutes = scenario["valeurs_13"]
            elif n_feats == 10:
                valeurs_brutes = scenario["valeurs_10"]
            else:
                valeurs_brutes = scenario["valeurs_16"]

            scores_hor  = {}
            alertes_hor = {}

            for nom in modeles_risque:
                pkl = os.path.join(MODELS_DIR, f"model_{nom}{suf}.pkl")
                if not os.path.exists(pkl):
                    continue

                d = charger_pkl_securise(pkl)
                if d is None:
                    continue

                try:
                    clf      = d["clf"]
                    seuil    = d["seuil"]
                    features = d.get("features", FEATURES_PAR_DIM.get(n_feats, FEATURES_16))

                    X_df = make_dataframe(valeurs_brutes, features)

                    proba  = float(clf.predict_proba(X_df)[0, 1])
                    alerte = proba >= seuil
                    scores_hor[nom]  = round(proba, 3)
                    alertes_hor[nom] = alerte
                    statut = "🔴 ALERTE" if alerte else "🟢 ok"
                    print(f"    [{label}] {nom:12s} : proba={proba:.3f}  "
                          f"seuil={seuil:.2f}  {statut}")

                except Exception as e:
                    print(f"    [{label}] {nom:12s} : ⚠️  erreur inattendue — {e}")

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
            {"version": "V4.5.2", "date": datetime.datetime.now().isoformat(),
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

    parser = argparse.ArgumentParser(description="SAMCAM V4.5.2 — Pipeline complet")
    parser.add_argument("--days",    type=int, default=7)
    parser.add_argument("--browser", action="store_true",
                        help="Ouvre le dashboard dans le navigateur après l'exécution")
    parser.add_argument("--retrain", action="store_true",
                        help="Force le ré-entraînement des modèles ML")
    parser.add_argument("--test",    action="store_true",
                        help="Test rapide : prédit sur 3 scénarios simulés (sans collecte réseau)")
    args = parser.parse_args()

    print(f"\n🚀 SAMCAM Pipeline V4.5.2 — {datetime.date.today().isoformat()}")

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

    print(f"\n✅ Pipeline V4.5.2 terminé. Rapports disponibles dans reports/")
    dashboard_path = os.path.join(ROOT, "dashboard", "samcam-v4-dashboard.html")
    print(f"[PIPELINE] 🌐 Dashboard : file://{os.path.abspath(dashboard_path)}")

    if args.browser:
        ouvrir_dashboard()
