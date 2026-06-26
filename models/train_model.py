#!/usr/bin/env python3
"""
SAMCAM V4.5.0 — Entraînement des modèles de classification de risques climatiques

NOUVEAU V4.5.0 :
    - Feature importance calculée après chaque entraînement ML
    - Feature selection automatique : suppression features < SEUIL_IMPORTANCE (1%)
    - Ré-entraînement avec sous-ensemble de features optimisées
    - Export models/feature_importance.json lisible par le rapport LLM
    - Résumé console avec top-5 features par modèle

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

# Seuil de feature selection : features dont l'importance moyenne < SEUIL sont supprimées
SEUIL_IMPORTANCE = 0.01   # 1%

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
        "seuil":  0.50,
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
        "feature_importance": {},   # vide pour heuristique
        "features_selectionnees": FEATURES_ALL,
    }


def seuil_optimal_f1(y_true, y_proba) -> float:
    from sklearn.metrics import f1_score

    meilleur_seuil, meilleur_f1 = 0.5, 0.0
    for s in [i / 100 for i in range(20, 81)]:
        f1 = f1_score(y_true, (y_proba >= s).astype(int), zero_division=0)
        if f1 > meilleur_f1:
            meilleur_f1, meilleur_seuil = f1, s
    return round(meilleur_seuil, 2)


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE IMPORTANCE & SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def extraire_feature_importance(clf, features: list) -> dict:
    """
    Extrait les importances de features depuis un estimateur sklearn.
    Retourne un dict {feature: importance} trié par importance décroissante.
    Compatible avec : RandomForest, GradientBoosting, CalibratedClassifierCV.
    """
    import numpy as np

    importances = None

    # CalibratedClassifierCV wraps l'estimateur
    estimateur = clf
    for attr in ("base_estimator", "estimator", "calibrated_classifiers_"):
        if hasattr(clf, attr):
            val = getattr(clf, attr)
            if attr == "calibrated_classifiers_" and isinstance(val, list) and val:
                inner = val[0]
                estimateur = getattr(inner, "estimator", getattr(inner, "base_estimator", inner))
            else:
                estimateur = val
            break

    if hasattr(estimateur, "feature_importances_"):
        importances = estimateur.feature_importances_
    elif hasattr(estimateur, "estimators_"):
        # Ensemble d'estimateurs (CalibratedClassifierCV avec plusieurs folds)
        try:
            importances = np.mean(
                [e.feature_importances_ for e in estimateur.estimators_
                 if hasattr(e, "feature_importances_")],
                axis=0,
            )
        except Exception:
            pass

    if importances is None:
        print("  [IMPORTANCE] ⚠️  Impossible d'extraire les importances (estimateur non compatible)")
        return {}

    importance_dict = {f: round(float(imp), 6) for f, imp in zip(features, importances)}
    return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))


def selectionner_features(importance_dict: dict, seuil: float, features_all: list) -> list:
    """
    Retourne la liste des features dont l'importance >= seuil.
    Garde au minimum 5 features pour éviter un modèle dégénéré.
    """
    selectionnees = [f for f, imp in importance_dict.items() if imp >= seuil]

    # Sécurité : minimum 5 features
    if len(selectionnees) < 5:
        top5 = list(importance_dict.keys())[:5]
        print(f"  [SELECTION] ⚠️  Moins de 5 features sélectionnées → garde les top-5 : {top5}")
        return top5

    supprimees = [f for f in features_all if f not in selectionnees]
    if supprimees:
        print(f"  [SELECTION] 🗑️  Features supprimées ({len(supprimees)}) : {supprimees}")
    print(f"  [SELECTION] ✅ Features retenues : {len(selectionnees)}/{len(features_all)}")
    return selectionnees


def afficher_top_features(nom: str, importance_dict: dict, n: int = 5):
    print(f"  [IMPORTANCE] Top-{n} features {nom.upper()} :")
    for i, (feat, imp) in enumerate(list(importance_dict.items())[:n], 1):
        bar = "█" * int(imp * 200)
        print(f"    {i}. {feat:<22} {imp:.4f}  {bar}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRAÎNEMENT
# ─────────────────────────────────────────────────────────────────────────────

def entrainer_gradient_boosting(nom: str, df, features: list,
                                 param_grid: dict, verbose: bool) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
    from sklearn.metrics import f1_score, recall_score, precision_score, roc_auc_score
    import numpy as np

    label_col = TARGETS[nom]
    X, y = df[features].values, df[label_col].values

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
    return _build_result(clf, seuil, features, f1, recall, prec, auc, f1_cv,
                         meilleurs_params, X_train, X_test, int(y.sum()))


def entrainer_random_forest(nom: str, df, features: list,
                             param_grid: dict, verbose: bool) -> dict:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
    from sklearn.metrics import f1_score, recall_score, precision_score, roc_auc_score

    label_col = TARGETS[nom]
    X, y = df[features].values, df[label_col].values
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
    return _build_result(clf, seuil, features, f1, recall, prec, auc, f1_cv,
                         meilleurs_params, X_train, X_test, int(y.sum()))


def _print_metriques(nom, f1, recall, prec, auc):
    print(f"[{nom.upper()}] ── Métriques test ──")
    print(f"[{nom.upper()}]   F1        : {f1}")
    print(f"[{nom.upper()}]   Recall    : {recall}")
    print(f"[{nom.upper()}]   Precision : {prec}")
    print(f"[{nom.upper()}]   AUC-ROC   : {auc}")


def _build_result(clf, seuil, features, f1, recall, prec, auc, f1_cv,
                  params, X_train, X_test, n_positifs) -> dict:
    return {
        "clf": clf,
        "seuil": seuil,
        "features": features,
        "metriques": {
            "f1": f1, "recall": recall, "precision": prec,
            "auc_roc": auc, "f1_cv": f1_cv,
        },
        "params_optimaux": params,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_positifs": n_positifs,
        "feature_importance": {},      # rempli après par entrainer_modele
        "features_selectionnees": features,
    }


def _count_combinations(param_grid: dict) -> int:
    total = 1
    for v in param_grid.values():
        total *= len(v)
    return total


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL AVEC FEATURE SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def entrainer_modele(nom: str, df, fast: bool, prefix: str, verbose: bool) -> dict:
    """
    Pipeline en 2 passes :
      1. Entraînement sur toutes les features → calcul feature importance
      2. Sélection des features >= SEUIL_IMPORTANCE → ré-entraînement optimisé
    """
    label_col = TARGETS[nom]
    n_positifs = int(df[label_col].sum())
    n_total = len(df)

    print(f"\n[{nom.upper()}] Positifs : {n_positifs}/{n_total} ({100*n_positifs//max(n_total,1)}%)")
    split_idx = int(len(df) * 0.80)
    print(f"[{nom.upper()}] Train : {split_idx} | Test : {n_total - split_idx}")

    # ── Modèle heuristique : pas de feature selection ────────────────────────
    if n_positifs < MIN_POSITIFS_ML:
        return creer_modele_heuristique_chaleur(df)

    # ── PASSE 1 : entraînement sur toutes les features ───────────────────────
    print(f"\n[{nom.upper()}] ── Passe 1 : toutes les features ({len(FEATURES_ALL)}) ──")
    if n_positifs < MIN_POSITIFS_CALIB:
        pg = _build_param_grid_rf(fast=True)   # toujours rapide en passe 1
        result_p1 = entrainer_random_forest(nom, df, FEATURES_ALL, pg, verbose=False)
    else:
        pg = _build_param_grid_gb(prefix, fast=True)
        result_p1 = entrainer_gradient_boosting(nom, df, FEATURES_ALL, pg, verbose=False)

    # ── Calcul feature importance (passe 1) ──────────────────────────────────
    importance_p1 = extraire_feature_importance(result_p1["clf"], FEATURES_ALL)
    if importance_p1:
        afficher_top_features(nom, importance_p1)
        features_sel = selectionner_features(importance_p1, SEUIL_IMPORTANCE, FEATURES_ALL)
    else:
        print(f"  [SELECTION] Importance non disponible → garde toutes les features")
        features_sel = FEATURES_ALL

    # ── PASSE 2 : ré-entraînement sur features sélectionnées ─────────────────
    if set(features_sel) == set(FEATURES_ALL):
        print(f"\n[{nom.upper()}] ── Passe 2 : toutes les features conservées (pas de gain attendu) ──")
    else:
        print(f"\n[{nom.upper()}] ── Passe 2 : {len(features_sel)} features sélectionnées ──")

    if n_positifs < MIN_POSITIFS_CALIB:
        pg2 = _build_param_grid_rf(fast)
        result_p2 = entrainer_random_forest(nom, df, features_sel, pg2, verbose)
    else:
        pg2 = _build_param_grid_gb(prefix, fast)
        result_p2 = entrainer_gradient_boosting(nom, df, features_sel, pg2, verbose)

    # ── Calcul feature importance finale (passe 2) ───────────────────────────
    importance_finale = extraire_feature_importance(result_p2["clf"], features_sel)

    # Comparaison F1 passe 1 vs passe 2
    f1_p1 = result_p1["metriques"]["f1"]
    f1_p2 = result_p2["metriques"]["f1"]
    delta = round((f1_p2 - f1_p1) * 100, 2) if f1_p1 and f1_p2 else 0
    sign = "+" if delta >= 0 else ""
    print(f"\n[{nom.upper()}] 📊 F1 passe 1 : {f1_p1} → passe 2 : {f1_p2} ({sign}{delta}%)")

    result_p2["feature_importance"]      = importance_finale
    result_p2["feature_importance_all"]  = importance_p1   # passe 1 pour référence
    result_p2["features_selectionnees"]  = features_sel
    result_p2["features_supprimees"]     = [f for f in FEATURES_ALL if f not in features_sel]
    result_p2["f1_avant_selection"]      = f1_p1
    result_p2["gain_f1_selection"]       = delta

    return result_p2


# ─────────────────────────────────────────────────────────────────────────────
# SAUVEGARDE
# ─────────────────────────────────────────────────────────────────────────────

def sauvegarder_modele(nom: str, result: dict):
    import joblib
    chemin = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
    joblib.dump({
        "clf":      result["clf"],
        "seuil":    result["seuil"],
        "features": result["features_selectionnees"],
    }, chemin)
    print(f"[SAVE] ✅ {chemin} sauvegardé ({len(result['features_selectionnees'])} features)")


def sauvegarder_feature_importance(resultats: dict):
    """
    Sauvegarde models/feature_importance.json — utilisé par le rapport LLM.
    Structure :
    {
        "version": "V4.5.0",
        "date": "...",
        "seuil_selection": 0.01,
        "modeles": {
            "inondation": {
                "top_features": [{"feature": "pluie_7j", "importance": 0.35}, ...],
                "features_supprimees": [...],
                "gain_f1_selection": +1.2
            },
            ...
        },
        "global_top_features": [{"feature": "...", "importance_moyenne": 0.xx}, ...]
    }
    """
    import numpy as np

    chemin = os.path.join(MODELS_DIR, "feature_importance.json")

    rapport = {
        "version": "V4.5.0",
        "date": datetime.datetime.now().isoformat(),
        "seuil_selection": SEUIL_IMPORTANCE,
        "modeles": {},
    }

    # Importance par modèle
    importances_globales = {}
    for nom, r in resultats.items():
        imp = r.get("feature_importance", {})
        top = [{"feature": f, "importance": v} for f, v in list(imp.items())[:10]]
        rapport["modeles"][nom] = {
            "top_features": top,
            "features_selectionnees": r.get("features_selectionnees", FEATURES_ALL),
            "features_supprimees": r.get("features_supprimees", []),
            "n_features_retenues": len(r.get("features_selectionnees", FEATURES_ALL)),
            "n_features_supprimees": len(r.get("features_supprimees", [])),
            "gain_f1_selection": r.get("gain_f1_selection", None),
            "f1_avant_selection": r.get("f1_avant_selection", None),
            "f1_apres_selection": r["metriques"].get("f1"),
        }
        # Accumulation pour top global
        for feat, val in imp.items():
            if feat not in importances_globales:
                importances_globales[feat] = []
            importances_globales[feat].append(val)

    # Top features global (moyenne sur tous les modèles ML)
    global_imp = {
        f: round(float(np.mean(vals)), 6)
        for f, vals in importances_globales.items()
    }
    global_top = sorted(global_imp.items(), key=lambda x: x[1], reverse=True)
    rapport["global_top_features"] = [
        {"feature": f, "importance_moyenne": v} for f, v in global_top[:10]
    ]

    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump(rapport, fh, ensure_ascii=False, indent=2)
    print(f"[SAVE] ✅ Feature importance : {chemin}")
    return rapport


def sauvegarder_rapport(resultats: dict):
    chemin = os.path.join(MODELS_DIR, "training_report.json")
    rapport = {
        "version": "V4.5.0",
        "date": datetime.datetime.now().isoformat(),
        "features_all": FEATURES_ALL,
        "n_features_all": len(FEATURES_ALL),
        "seuil_selection": SEUIL_IMPORTANCE,
        "modeles": {},
    }
    for nom, r in resultats.items():
        rapport["modeles"][nom] = {
            "metriques":              r["metriques"],
            "seuil":                  r["seuil"],
            "params_optimaux":        r["params_optimaux"],
            "n_train":                r["n_train"],
            "n_test":                 r["n_test"],
            "n_positifs":             r["n_positifs"],
            "type":                   r.get("type", "ml"),
            "features_selectionnees": r.get("features_selectionnees", FEATURES_ALL),
            "features_supprimees":    r.get("features_supprimees", []),
            "gain_f1_selection":      r.get("gain_f1_selection", None),
        }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] ✅ Rapport : {chemin}")
    return rapport


def afficher_resume(rapport_train: dict, rapport_fi: dict):
    print("\n" + "═" * 70)
    print("  SAMCAM V4.5.0 — Résumé de l'entraînement")
    print("═" * 70)
    print(f"  Features initiales : {rapport_train['n_features_all']}")
    print(f"  Seuil de sélection : {rapport_train['seuil_selection']*100:.0f}%")
    print(f"  Date               : {rapport_train['date'][:19]}")
    print()
    print(f"  {'Modèle':<15} {'Type':<22} {'F1 avant':>9} {'F1 après':>9} {'Gain':>7} {'Features':>9}")
    print(f"  {'-'*15} {'-'*22} {'-'*9} {'-'*9} {'-'*7} {'-'*9}")
    for nom, m in rapport_train["modeles"].items():
        mt = m["metriques"]
        tp = m.get("type", "ml")
        f1_ap = f"{mt['f1']:.4f}"    if mt["f1"]     else "   N/A "
        f1_av = f"{m['f1_avant_selection']:.4f}" if m.get("f1_avant_selection") else "   N/A "
        gain  = f"{m['gain_f1_selection']:+.2f}%" if m.get("gain_f1_selection") is not None else "   N/A "
        n_sel = len(m.get("features_selectionnees", FEATURES_ALL))
        print(f"  {nom:<15} {tp:<22} {f1_av:>9} {f1_ap:>9} {gain:>7} {n_sel:>5}/{len(FEATURES_ALL)}")
    print("═" * 70)

    # Top features global
    if rapport_fi.get("global_top_features"):
        print("\n  🔑 Top-5 features globales (moyenne tous modèles ML) :")
        for i, item in enumerate(rapport_fi["global_top_features"][:5], 1):
            bar = "█" * int(item["importance_moyenne"] * 200)
            print(f"    {i}. {item['feature']:<22} {item['importance_moyenne']:.4f}  {bar}")
    print("═" * 70)
    print("  Note chaleur : heuristique_sigmoide centrée 34°C")
    print("    32°C → ~0.27 (🟢 normal) | 34°C → ~0.50 (🟡) | 36°C → ~0.82 (🔴)")
    print("═" * 70)


def main():
    parser = argparse.ArgumentParser(description="SAMCAM V4.5.0 — Entraînement modèles")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--no-grid", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--modeles", nargs="+", default=["inondation", "secheresse", "chaleur"])
    parser.add_argument(
        "--seuil-importance", type=float, default=SEUIL_IMPORTANCE,
        help=f"Seuil de feature selection (défaut: {SEUIL_IMPORTANCE} = 1%%)"
    )
    args = parser.parse_args()

    # Surcharge du seuil si fourni en argument
    global SEUIL_IMPORTANCE
    SEUIL_IMPORTANCE = args.seuil_importance

    print("\n" + "═" * 70)
    print("  SAMCAM V4.5.0 — Entraînement avec Feature Importance + Sélection")
    print("  Mode : " + ("RAPIDE (sans GridSearchCV)" if args.no_grid else "COMPLET (GridSearchCV + TimeSeriesSplit)"))
    print(f"  Seuil sélection : {SEUIL_IMPORTANCE*100:.0f}%")
    print("═" * 70)

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

    rapport_train = sauvegarder_rapport(resultats)
    rapport_fi    = sauvegarder_feature_importance(resultats)
    afficher_resume(rapport_train, rapport_fi)


if __name__ == "__main__":
    main()
