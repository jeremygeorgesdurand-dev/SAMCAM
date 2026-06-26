#!/usr/bin/env python3
"""
SAMCAM V4.4 — Entraînement des modèles de classification de risques climatiques

NOUVEAUTÉS V4.4 :
    - GridSearchCV sur GradientBoostingClassifier (hyperparamètres optimaux)
    - TimeSeriesSplit (5 folds) : validation temporelle stricte
      (pas de fuite de données futures dans le training)
    - CalibratedClassifierCV : calibration des probabilités de sortie
    - Seuil de décision optimal calculé par maximisation du F1
    - Rapport de métriques complet : F1, recall, precision, AUC-ROC
    - Sauvegarde format dict {clf, seuil, features} pour risk_model.py

Usage :
    python3 models/train_model.py
    python3 models/train_model.py --dataset data/dataset_kribi_historical.csv
    python3 models/train_model.py --no-grid   # rapide, sans GridSearchCV
    python3 models/train_model.py --verbose

Sortie :
    models/model_inondation.pkl
    models/model_secheresse.pkl
    models/model_chaleur.pkl
    models/training_report.json
"""

import os
import json
import argparse
import datetime
import warnings
warnings.filterwarnings("ignore")

MODELS_DIR = os.path.join(os.path.dirname(__file__))
DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
DEFAULT_DATASET = os.path.join(DATA_DIR, "dataset_kribi_historical.csv")

# ─────────────────────────────────────────────────────────────────────────────
# FEATURES (doit être identique à risk_model.py V4.3)
# ─────────────────────────────────────────────────────────────────────────────

FEATURES_BASE = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi", "et0_semaine",
]

FEATURES_DERIVEES = [
    "sin_mois", "cos_mois",
    "anomalie_pluie", "ratio_30j_7j",
    "trend_sm", "sm_deficit",
    "ratio_et0_pluie",
]

FEATURES_ALL = FEATURES_BASE + FEATURES_DERIVEES  # 18 features

TARGETS = {
    "inondation": "label_inondation",
    "secheresse": "label_secheresse",
    "chaleur":    "label_chaleur",
}

# ─────────────────────────────────────────────────────────────────────────────
# GRILLE D'HYPERPARAMÈTRES
# Couvre les axes les plus impactants pour GradientBoosting :
#   n_estimators  : nb d'arbres (capacité du modèle)
#   max_depth     : profondeur max (complexité)
#   learning_rate : pas de gradient (vitesse vs précision)
#   subsample     : fraction d'exemples par arbre (régularisation)
#   min_samples_leaf : taille min des feuilles (évite overfitting)
# ─────────────────────────────────────────────────────────────────────────────

PARAM_GRID_FULL = {
    "base_estimator__n_estimators":    [100, 200, 300],
    "base_estimator__max_depth":       [3, 4, 5],
    "base_estimator__learning_rate":   [0.05, 0.10, 0.15],
    "base_estimator__subsample":       [0.75, 0.85, 1.0],
    "base_estimator__min_samples_leaf": [5, 10, 20],
}

# Grille réduite pour --no-grid (baseline rapide)
PARAM_GRID_FAST = {
    "base_estimator__n_estimators":  [200],
    "base_estimator__max_depth":     [4],
    "base_estimator__learning_rate": [0.10],
    "base_estimator__subsample":     [0.85],
    "base_estimator__min_samples_leaf": [10],
}


# ─────────────────────────────────────────────────────────────────────────────
# CHARGEMENT DU DATASET
# ─────────────────────────────────────────────────────────────────────────────

def charger_dataset(chemin: str):
    import pandas as pd

    if not os.path.exists(chemin):
        raise FileNotFoundError(
            f"Dataset introuvable : {chemin}\n"
            "  Générez-le d'abord avec :\n"
            "  python3 inference/build_dataset.py --openmeteo"
        )

    df = pd.read_csv(chemin, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)  # ordre chronologique !

    print(f"[TRAIN] Dataset chargé : {len(df)} lignes")
    print(f"[TRAIN] Période : {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"[TRAIN] Source  : {df['source'].value_counts().to_dict()}")

    # Vérification features
    features_manquantes = [f for f in FEATURES_ALL if f not in df.columns]
    if features_manquantes:
        print(f"[TRAIN] ⚠️  Features absentes du dataset : {features_manquantes}")
        print(f"[TRAIN]    → Imputation à 0 pour ces colonnes")
        for f in features_manquantes:
            df[f] = 0.0

    # Imputation des NaN par médiane de la colonne
    for col in FEATURES_ALL:
        if df[col].isna().any():
            med = df[col].median()
            df[col] = df[col].fillna(med)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# SEUIL OPTIMAL — maximise F1 sur les probabilités de validation
# ─────────────────────────────────────────────────────────────────────────────

def seuil_optimal_f1(y_true, y_proba) -> float:
    from sklearn.metrics import f1_score
    import numpy as np

    seuils = [i / 100 for i in range(20, 81)]
    meilleur_seuil = 0.5
    meilleur_f1    = 0.0

    for s in seuils:
        preds = (y_proba >= s).astype(int)
        f1 = f1_score(y_true, preds, zero_division=0)
        if f1 > meilleur_f1:
            meilleur_f1    = f1
            meilleur_seuil = s

    return round(meilleur_seuil, 2)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRAÎNEMENT D'UN MODÈLE
# ─────────────────────────────────────────────────────────────────────────────

def entrainer_modele(nom: str, df, param_grid: dict, verbose: bool = False) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
    from sklearn.metrics import (
        f1_score, recall_score, precision_score,
        roc_auc_score, classification_report
    )
    import numpy as np

    label_col = TARGETS[nom]
    X = df[FEATURES_ALL].values
    y = df[label_col].values

    n_positifs = int(y.sum())
    n_total    = len(y)
    print(f"\n[{nom.upper()}] Positifs : {n_positifs}/{n_total} ({100*n_positifs//n_total}%)")

    # ── Split temporel : 80% train / 20% test (dernières semaines = test)
    split_idx = int(len(X) * 0.80)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    print(f"[{nom.upper()}] Train : {len(X_train)} | Test : {len(X_test)}")

    # ── Poids de classe pour compenser le déséquilibre
    ratio = max(1, (y_train == 0).sum() / max(1, (y_train == 1).sum()))
    class_weight = {0: 1.0, 1: min(ratio, 10.0)}
    print(f"[{nom.upper()}] Ratio déséquilibre : {ratio:.1f}x → class_weight[1]={class_weight[1]:.1f}")

    # ── Base estimator GradientBoosting
    base_clf = GradientBoostingClassifier(
        random_state=42,
        # Note : GradientBoosting natif ne supporte pas class_weight,
        # on compense via sample_weight dans le fit
    )

    # ── CalibratedClassifierCV : wraps le base estimator
    # → calibre les probabilités sorties (Platt scaling)
    calibrated = CalibratedClassifierCV(base_clf, cv=3, method="isotonic")

    # ── TimeSeriesSplit : validation croisée temporelle stricte
    # Chaque fold : train sur passé, validation sur futur immédiat
    tscv = TimeSeriesSplit(n_splits=5)

    # ── GridSearchCV
    print(f"[{nom.upper()}] GridSearchCV en cours ({len(list(TimeSeriesSplit(n_splits=5).split(X_train)))} folds × {_count_combinations(param_grid)} combinaisons)...")

    grid = GridSearchCV(
        calibrated,
        param_grid,
        cv=tscv,
        scoring="f1",
        n_jobs=-1,
        verbose=1 if verbose else 0,
        refit=True,
    )

    # Sample weights pour compenser le déséquilibre de classes
    sample_weights = np.array([class_weight[int(yi)] for yi in y_train])

    # GridSearchCV avec sample_weight via fit_params
    grid.fit(X_train, y_train, **{"sample_weight": sample_weights})

    meilleur_clf    = grid.best_estimator_
    meilleurs_params = grid.best_params_
    meilleur_score_cv = round(grid.best_score_, 4)

    print(f"[{nom.upper()}] Meilleurs params : {meilleurs_params}")
    print(f"[{nom.upper()}] Meilleur F1 CV   : {meilleur_score_cv}")

    # ── Calcul du seuil optimal sur les données de validation
    # On utilise le dernier fold du TimeSeriesSplit pour le seuil
    folds = list(tscv.split(X_train))
    idx_train_last, idx_val_last = folds[-1]
    X_val = X_train[idx_val_last]
    y_val = y_train[idx_val_last]

    y_proba_val = meilleur_clf.predict_proba(X_val)[:, 1]
    seuil = seuil_optimal_f1(y_val, y_proba_val)
    print(f"[{nom.upper()}] Seuil optimal F1 : {seuil}")

    # ── Évaluation finale sur le test set (données les plus récentes)
    y_proba_test = meilleur_clf.predict_proba(X_test)[:, 1]
    y_pred_test  = (y_proba_test >= seuil).astype(int)

    f1        = round(f1_score(y_test,        y_pred_test, zero_division=0), 4)
    recall    = round(recall_score(y_test,    y_pred_test, zero_division=0), 4)
    precision = round(precision_score(y_test, y_pred_test, zero_division=0), 4)
    try:
        auc = round(roc_auc_score(y_test, y_proba_test), 4)
    except Exception:
        auc = None

    print(f"[{nom.upper()}] ── Métriques test ──")
    print(f"[{nom.upper()}]   F1        : {f1}")
    print(f"[{nom.upper()}]   Recall    : {recall}")
    print(f"[{nom.upper()}]   Precision : {precision}")
    print(f"[{nom.upper()}]   AUC-ROC   : {auc}")

    if verbose:
        print(classification_report(y_test, y_pred_test,
                                    target_names=["négatif", "positif"],
                                    zero_division=0))

    return {
        "clf":      meilleur_clf,
        "seuil":    seuil,
        "features": FEATURES_ALL,
        "metriques": {
            "f1":        f1,
            "recall":    recall,
            "precision": precision,
            "auc_roc":   auc,
            "f1_cv":     meilleur_score_cv,
        },
        "params_optimaux": meilleurs_params,
        "n_train":   len(X_train),
        "n_test":    len(X_test),
        "n_positifs": n_positifs,
    }


def _count_combinations(param_grid: dict) -> int:
    total = 1
    for v in param_grid.values():
        total *= len(v)
    return total


# ─────────────────────────────────────────────────────────────────────────────
# SAUVEGARDE
# ─────────────────────────────────────────────────────────────────────────────

def sauvegarder_modele(nom: str, result: dict):
    import joblib

    chemin = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
    payload = {
        "clf":      result["clf"],
        "seuil":    result["seuil"],
        "features": result["features"],
    }
    joblib.dump(payload, chemin)
    print(f"[SAVE] ✅ {chemin} sauvegardé")


def sauvegarder_rapport(resultats: dict):
    chemin = os.path.join(MODELS_DIR, "training_report.json")
    rapport = {
        "version":    "V4.4",
        "date":       datetime.datetime.now().isoformat(),
        "features":   FEATURES_ALL,
        "n_features": len(FEATURES_ALL),
        "modeles":    {},
    }
    for nom, r in resultats.items():
        rapport["modeles"][nom] = {
            "metriques":       r["metriques"],
            "seuil":           r["seuil"],
            "params_optimaux": r["params_optimaux"],
            "n_train":         r["n_train"],
            "n_test":          r["n_test"],
            "n_positifs":      r["n_positifs"],
        }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] ✅ Rapport : {chemin}")
    return rapport


# ─────────────────────────────────────────────────────────────────────────────
# RÉSUMÉ FINAL
# ─────────────────────────────────────────────────────────────────────────────

def afficher_resume(rapport: dict):
    print("\n" + "═" * 60)
    print("  SAMCAM V4.4 — Résumé de l'entraînement")
    print("═" * 60)
    print(f"  Features utilisées : {rapport['n_features']}")
    print(f"  Date               : {rapport['date'][:19]}")
    print()
    print(f"  {'Modèle':<15} {'F1':>6} {'Recall':>8} {'Précision':>10} {'AUC':>7} {'Seuil':>7}")
    print(f"  {'-'*15} {'-'*6} {'-'*8} {'-'*10} {'-'*7} {'-'*7}")
    for nom, m in rapport["modeles"].items():
        mt = m["metriques"]
        auc = f"{mt['auc_roc']:.4f}" if mt["auc_roc"] else "  N/A "
        print(f"  {nom:<15} {mt['f1']:>6.4f} {mt['recall']:>8.4f} {mt['precision']:>10.4f} {auc:>7} {m['seuil']:>7.2f}")
    print("═" * 60)
    print()
    print("  Prochaines étapes :")
    print("  1. Vérifier les métriques ci-dessus")
    print("  2. Redémarrer le serveur : bash server/start.sh")
    print("  3. Tester : curl http://localhost:8000/api/risk")
    print("═" * 60 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM V4.4 — Entraînement modèles")
    parser.add_argument("--dataset",  default=DEFAULT_DATASET,
                        help="Chemin vers le CSV dataset")
    parser.add_argument("--no-grid",  action="store_true",
                        help="Désactive GridSearchCV (rapide, baseline)")
    parser.add_argument("--verbose",  action="store_true",
                        help="Affiche le rapport de classification complet")
    parser.add_argument("--modeles",  nargs="+",
                        default=["inondation", "secheresse", "chaleur"],
                        help="Modèles à entraîner (défaut : tous)")
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  SAMCAM V4.4 — Entraînement avec GridSearchCV")
    if args.no_grid:
        print("  Mode : RAPIDE (sans GridSearchCV)")
    else:
        print("  Mode : COMPLET (GridSearchCV + TimeSeriesSplit)")
    print("═" * 60)

    df = charger_dataset(args.dataset)
    param_grid = PARAM_GRID_FAST if args.no_grid else PARAM_GRID_FULL

    resultats = {}
    for nom in args.modeles:
        if nom not in TARGETS:
            print(f"[TRAIN] ⚠️  Modèle inconnu ignoré : {nom}")
            continue
        result = entrainer_modele(nom, df, param_grid, verbose=args.verbose)
        sauvegarder_modele(nom, result)
        resultats[nom] = result

    rapport = sauvegarder_rapport(resultats)
    afficher_resume(rapport)


if __name__ == "__main__":
    main()
