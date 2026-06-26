#!/usr/bin/env python3
"""
SAMCAM V4.4.4 — Entraînement des modèles de classification de risques climatiques

FIX V4.4.4 :
    - HeuristiqueChaleur recalibrée pour Kribi :
        • Ancienne formule : linéaire sur percentile 95 (~30.2°C) → faux positifs
          constants en saison sèche normale
        • Nouvelle formule : sigmoïde centrée sur 34°C (vraie anomalie thermique)
          avec pente douce, 3 niveaux : normal / stress modéré / anomalie
          • 32°C → proba ≈26% (stress léger, jamais ALERTE seul)
          • 34°C → proba ≈50% (seuil alerte)
          • 36°C → proba ≈82% (anomalie confirmée)

FIX V4.4.3 :
    - HeuristiqueChaleur déplacée au niveau module pour être sérialisable
      par joblib (corrige PicklingError)

FIX V4.4.2 :
    - Chaleur (0 positifs) : skip + modèle heuristique basé sur temp_max
    - Inondation (<30 positifs) : RandomForest sans calibration
    - Protection générale : vérifie le nb de positifs avant tout entraînement

FIX V4.4.1 :
    - PARAM_GRID : détection automatique préfixe 'estimator__' vs 'base_estimator__'
"""

import os
import json
import argparse
import datetime
import warnings
warnings.filterwarnings("ignore")

MODELS_DIR      = os.path.join(os.path.dirname(__file__))
DATA_DIR        = os.path.join(os.path.dirname(__file__), "..", "data")
DEFAULT_DATASET = os.path.join(DATA_DIR, "dataset_kribi_historical.csv")

MIN_POSITIFS_ML    = 10
MIN_POSITIFS_CALIB = 30

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

FEATURES_ALL = FEATURES_BASE + FEATURES_DERIVEES

TARGETS = {
    "inondation": "label_inondation",
    "secheresse": "label_secheresse",
    "chaleur":    "label_chaleur",
}

# ── Seuils thermiques Kribi ──────────────────────────────────────
# T_REF  : température de référence climatique de Kribi (~30.2°C, p95)
# T_ALERTE : centre de la sigmoïde — vraie anomalie thermique Kribi
#            32°C est la normale saison sèche, 34°C = véritable anomalie
# T_PENTE  : largeur de la transition (1°C = montee rapide, 3°C = douce)
T_ALERTE = 34.0   # °C — centre de la sigmoïde
T_PENTE  = 1.5    # °C — pente de la transition
# ─────────────────────────────────────────────────────────────


class HeuristiqueChaleur:
    """
    Pseudo-estimateur sklearn-compatible sérialisable par joblib.

    Score basé sur une sigmoïde centrée sur T_ALERTE (34°C pour Kribi) :

        score = 1 / (1 + exp(-(temp - T_ALERTE) / T_PENTE))

    Valeurs représentatives :
        30°C  → proba ~0.07  (🟢 normal)
        32°C  → proba ~0.27  (🟢 stress léger — saison sèche habituelle)
        33°C  → proba ~0.40  (🟡 stress modéré)
        34°C  → proba ~0.50  (🟡 seuil alerte)
        35°C  → proba ~0.65  (🔴 anomalie probable)
        36°C  → proba ~0.82  (🔴 anomalie confirmée)
    """

    def __init__(self, t_alerte: float = T_ALERTE, t_pente: float = T_PENTE, idx: int = 0):
        self.t_alerte = t_alerte
        self.t_pente  = t_pente
        self.idx      = idx
        # Compat ascendante : expose aussi self.seuil utilisé dans certains logs
        self.seuil    = t_alerte

    def predict_proba(self, X):
        import numpy as np
        temp   = X[:, self.idx]
        scores = 1.0 / (1.0 + np.exp(-(temp - self.t_alerte) / self.t_pente))
        return np.column_stack([1 - scores, scores])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def _get_param_prefix() -> str:
    try:
        import sklearn
        parts = sklearn.__version__.split(".")
        if (int(parts[0]), int(parts[1])) >= (1, 2):
            return "estimator__"
    except Exception:
        pass
    return "base_estimator__"


def _build_param_grid_gb(prefix: str, fast: bool) -> dict:
    if fast:
        return {
            f"{prefix}n_estimators": [200],
            f"{prefix}max_depth": [4],
            f"{prefix}learning_rate": [0.10],
            f"{prefix}subsample": [0.85],
            f"{prefix}min_samples_leaf": [10],
        }
    return {
        f"{prefix}n_estimators": [100, 200, 300],
        f"{prefix}max_depth": [3, 4, 5],
        f"{prefix}learning_rate": [0.05, 0.10, 0.15],
        f"{prefix}subsample": [0.75, 0.85, 1.0],
        f"{prefix}min_samples_leaf": [5, 10, 20],
    }


def _build_param_grid_rf(fast: bool) -> dict:
    if fast:
        return {
            "n_estimators": [200],
            "max_depth": [None],
            "min_samples_leaf": [1],
        }
    return {
        "n_estimators": [100, 200, 300],
        "max_depth": [None, 8, 15],
        "min_samples_leaf": [1, 3, 5],
    }


def charger_dataset(chemin: str):
    import pandas as pd

    if not os.path.exists(chemin):
        raise FileNotFoundError(
            f"Dataset introuvable : {chemin}\n"
            "  Générez-le d'abord avec :\n"
            "  python3 inference/build_dataset.py --openmeteo"
        )

    df = pd.read_csv(chemin, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    print(f"[TRAIN] Dataset chargé : {len(df)} lignes")
    print(f"[TRAIN] Période : {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"[TRAIN] Source  : {df['source'].value_counts().to_dict()}")

    for f in FEATURES_ALL:
        if f not in df.columns:
            df[f] = 0.0
    for col in FEATURES_ALL:
        if df[col].isna().any():
            df[col] = df[col].fillna(df[col].median())

    return df


def creer_modele_heuristique_chaleur(df) -> dict:
    idx_temp = FEATURES_ALL.index("temp_max")
    print(
        f"[CHALEUR] ⚠️  0 positifs → modèle heuristique sigmoïde"
        f" (centre={T_ALERTE}°C, pente={T_PENTE}°C)"
    )

    clf = HeuristiqueChaleur(t_alerte=T_ALERTE, t_pente=T_PENTE, idx=idx_temp)

    return {
        "clf":    clf,
        "seuil":  0.50,   # 50% ≈ 34°C
        "features": FEATURES_ALL,
        "metriques": {
            "f1": None, "recall": None, "precision": None,
            "auc_roc": None, "f1_cv": None,
        },
        "params_optimaux": {
            "type":       "heuristique_sigmoide",
            "t_alerte":   T_ALERTE,
            "t_pente":    T_PENTE,
        },
        "n_train": len(df),
        "n_test":  0,
        "n_positifs": 0,
        "type": "heuristique",
    }


def seuil_optimal_f1(y_true, y_proba) -> float:
    from sklearn.metrics import f1_score

    meilleur_seuil, meilleur_f1 = 0.5, 0.0
    for s in [i / 100 for i in range(20, 81)]:
        f1 = f1_score(y_true, (y_proba >= s).astype(int), zero_division=0)
        if f1 > meilleur_f1:
            meilleur_f1, meilleur_seuil = f1, s
    return round(meilleur_seuil, 2)


def entrainer_gradient_boosting(nom: str, df, param_grid: dict, verbose: bool) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
    from sklearn.metrics import f1_score, recall_score, precision_score, roc_auc_score
    import numpy as np

    label_col = TARGETS[nom]
    X, y = df[FEATURES_ALL].values, df[label_col].values

    split_idx = int(len(X) * 0.80)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    ratio = max(1, (y_train == 0).sum() / max(1, (y_train == 1).sum()))
    class_weight = {0: 1.0, 1: min(ratio, 10.0)}
    print(f"[{nom.upper()}] Ratio déséquilibre : {ratio:.1f}x → class_weight[1]={class_weight[1]:.1f}")

    calibrated = CalibratedClassifierCV(
        GradientBoostingClassifier(random_state=42), cv=3, method="isotonic"
    )
    tscv = TimeSeriesSplit(n_splits=5)
    n_combis = _count_combinations(param_grid)
    print(f"[{nom.upper()}] GridSearchCV GradientBoosting (5 folds × {n_combis} combinaisons)...")

    grid = GridSearchCV(
        calibrated, param_grid, cv=tscv,
        scoring="f1", n_jobs=-1,
        verbose=1 if verbose else 0, refit=True,
    )
    sw = np.array([class_weight[int(yi)] for yi in y_train])
    grid.fit(X_train, y_train, **{"sample_weight": sw})

    clf = grid.best_estimator_
    meilleurs_params = grid.best_params_
    f1_cv = round(grid.best_score_, 4)
    print(f"[{nom.upper()}] Meilleurs params : {meilleurs_params}")
    print(f"[{nom.upper()}] Meilleur F1 CV   : {f1_cv}")

    folds = list(tscv.split(X_train))
    _, idx_val = folds[-1]
    seuil = seuil_optimal_f1(y_train[idx_val], clf.predict_proba(X_train[idx_val])[:, 1])
    print(f"[{nom.upper()}] Seuil optimal F1 : {seuil}")

    y_proba = clf.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= seuil).astype(int)
    f1 = round(f1_score(y_test, y_pred, zero_division=0), 4)
    recall = round(recall_score(y_test, y_pred, zero_division=0), 4)
    prec = round(precision_score(y_test, y_pred, zero_division=0), 4)
    try:
        auc = round(roc_auc_score(y_test, y_proba), 4)
    except Exception:
        auc = None

    _print_metriques(nom, f1, recall, prec, auc)
    return _build_result(clf, seuil, f1, recall, prec, auc, f1_cv,
                         meilleurs_params, X_train, X_test, int(y.sum()))


def entrainer_random_forest(nom: str, df, param_grid: dict, verbose: bool) -> dict:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
    from sklearn.metrics import f1_score, recall_score, precision_score, roc_auc_score

    label_col = TARGETS[nom]
    X, y = df[FEATURES_ALL].values, df[label_col].values
    split_idx = int(len(X) * 0.80)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    print(f"[{nom.upper()}] → RandomForest (class_weight=balanced_subsample)")

    clf_base = RandomForestClassifier(
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    tscv = TimeSeriesSplit(n_splits=5)
    n_combis = _count_combinations(param_grid)
    print(f"[{nom.upper()}] GridSearchCV RandomForest (5 folds × {n_combis} combinaisons)...")

    grid = GridSearchCV(
        clf_base, param_grid, cv=tscv,
        scoring="f1", n_jobs=1,
        verbose=1 if verbose else 0, refit=True,
        error_score=0.0,
    )
    grid.fit(X_train, y_train)

    clf = grid.best_estimator_
    meilleurs_params = grid.best_params_
    f1_cv = round(grid.best_score_, 4)
    print(f"[{nom.upper()}] Meilleurs params : {meilleurs_params}")
    print(f"[{nom.upper()}] Meilleur F1 CV   : {f1_cv}")

    folds = list(tscv.split(X_train))
    _, idx_val = folds[-1]
    seuil = seuil_optimal_f1(y_train[idx_val], clf.predict_proba(X_train[idx_val])[:, 1])
    print(f"[{nom.upper()}] Seuil optimal F1 : {seuil}")

    y_proba = clf.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= seuil).astype(int)
    f1 = round(f1_score(y_test, y_pred, zero_division=0), 4)
    recall = round(recall_score(y_test, y_pred, zero_division=0), 4)
    prec = round(precision_score(y_test, y_pred, zero_division=0), 4)
    try:
        auc = round(roc_auc_score(y_test, y_proba), 4)
    except Exception:
        auc = None

    _print_metriques(nom, f1, recall, prec, auc)
    return _build_result(clf, seuil, f1, recall, prec, auc, f1_cv,
                         meilleurs_params, X_train, X_test, int(y.sum()))


def _print_metriques(nom, f1, recall, prec, auc):
    print(f"[{nom.upper()}] ── Métriques test ──")
    print(f"[{nom.upper()}]   F1        : {f1}")
    print(f"[{nom.upper()}]   Recall    : {recall}")
    print(f"[{nom.upper()}]   Precision : {prec}")
    print(f"[{nom.upper()}]   AUC-ROC   : {auc}")


def _build_result(clf, seuil, f1, recall, prec, auc, f1_cv,
                  params, X_train, X_test, n_positifs) -> dict:
    return {
        "clf": clf,
        "seuil": seuil,
        "features": FEATURES_ALL,
        "metriques": {
            "f1": f1, "recall": recall, "precision": prec,
            "auc_roc": auc, "f1_cv": f1_cv,
        },
        "params_optimaux": params,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_positifs": n_positifs,
    }


def _count_combinations(param_grid: dict) -> int:
    total = 1
    for v in param_grid.values():
        total *= len(v)
    return total


def entrainer_modele(nom: str, df, fast: bool, prefix: str, verbose: bool) -> dict:
    label_col = TARGETS[nom]
    n_positifs = int(df[label_col].sum())
    n_total = len(df)

    print(f"\n[{nom.upper()}] Positifs : {n_positifs}/{n_total} ({100*n_positifs//max(n_total,1)}%)")
    split_idx = int(len(df) * 0.80)
    print(f"[{nom.upper()}] Train : {split_idx} | Test : {n_total - split_idx}")

    if n_positifs < MIN_POSITIFS_ML:
        return creer_modele_heuristique_chaleur(df)
    if n_positifs < MIN_POSITIFS_CALIB:
        pg = _build_param_grid_rf(fast)
        return entrainer_random_forest(nom, df, pg, verbose)
    pg = _build_param_grid_gb(prefix, fast)
    return entrainer_gradient_boosting(nom, df, pg, verbose)


def sauvegarder_modele(nom: str, result: dict):
    import joblib
    chemin = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
    joblib.dump({
        "clf":      result["clf"],
        "seuil":    result["seuil"],
        "features": result["features"],
    }, chemin)
    print(f"[SAVE] ✅ {chemin} sauvegardé")


def sauvegarder_rapport(resultats: dict):
    chemin = os.path.join(MODELS_DIR, "training_report.json")
    rapport = {
        "version": "V4.4.4",
        "date": datetime.datetime.now().isoformat(),
        "features": FEATURES_ALL,
        "n_features": len(FEATURES_ALL),
        "modeles": {},
    }
    for nom, r in resultats.items():
        rapport["modeles"][nom] = {
            "metriques":      r["metriques"],
            "seuil":          r["seuil"],
            "params_optimaux": r["params_optimaux"],
            "n_train":        r["n_train"],
            "n_test":         r["n_test"],
            "n_positifs":     r["n_positifs"],
            "type":           r.get("type", "ml"),
        }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] ✅ Rapport : {chemin}")
    return rapport


def afficher_resume(rapport: dict):
    print("\n" + "═" * 64)
    print("  SAMCAM V4.4.4 — Résumé de l'entraînement")
    print("═" * 64)
    print(f"  Features utilisées : {rapport['n_features']}")
    print(f"  Date               : {rapport['date'][:19]}")
    print()
    print(f"  {'Modèle':<15} {'Type':<22} {'F1':>6} {'Recall':>8} {'AUC':>7} {'Seuil':>7}")
    print(f"  {'-'*15} {'-'*22} {'-'*6} {'-'*8} {'-'*7} {'-'*7}")
    for nom, m in rapport["modeles"].items():
        mt = m["metriques"]
        tp = m.get("type", "ml")
        f1  = f"{mt['f1']:.4f}"     if mt["f1"]      else "  N/A "
        rec = f"{mt['recall']:.4f}" if mt["recall"]  else "  N/A "
        auc = f"{mt['auc_roc']:.4f}" if mt["auc_roc"] else "  N/A "
        print(f"  {nom:<15} {tp:<22} {f1:>6} {rec:>8} {auc:>7} {m['seuil']:>7.2f}")
    print("═" * 64)
    print("  Note chaleur : heuristique_sigmoide centrée 34°C")
    print("    32°C → ~0.27 (🟢 normal) | 34°C → ~0.50 (🟡) | 36°C → ~0.82 (🔴)")
    print("═" * 64)


def main():
    parser = argparse.ArgumentParser(description="SAMCAM V4.4.4 — Entraînement modèles")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--no-grid", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--modeles", nargs="+", default=["inondation", "secheresse", "chaleur"])
    args = parser.parse_args()

    print("\n" + "═" * 64)
    print("  SAMCAM V4.4.4 — Entraînement avec GridSearchCV")
    print("  Mode : " + ("RAPIDE (sans GridSearchCV)" if args.no_grid else "COMPLET (GridSearchCV + TimeSeriesSplit)"))
    print("═" * 64)

    prefix = _get_param_prefix()
    print(f"  sklearn prefix détecté : '{prefix}' (compat automatique)")

    df = charger_dataset(args.dataset)

    resultats = {}
    for nom in args.modeles:
        if nom not in TARGETS:
            print(f"[TRAIN] ⚠️  Modèle inconnu ignoré : {nom}")
            continue
        result = entrainer_modele(nom, df, fast=args.no_grid, prefix=prefix, verbose=args.verbose)
        sauvegarder_modele(nom, result)
        resultats[nom] = result

    rapport = sauvegarder_rapport(resultats)
    afficher_resume(rapport)


if __name__ == "__main__":
    main()
