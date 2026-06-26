#!/usr/bin/env python3
"""
SAMCAM V4.5.2 — Entraînement des modèles de classification de risques climatiques

FIX V4.5.2 :
    - extraire_feature_importance : calibrated_classifiers_ testé EN PREMIER
      avant 'estimator' pour ne pas récupérer l'estimateur non-entraîné de
      CalibratedClassifierCV (corrige : ⚠️  Impossible d'extraire les importances)
    - sauvegarder_rapport : f1_avant_selection ajouté dans le dict modèle
      pour que afficher_resume() affiche correctement "F1 avant" (corrige : N/A)

FIX V4.5.1 :
    - SyntaxError : 'global SEUIL_IMPORTANCE' déplacée en tête de main()
      avant tout accès à la variable (corrige : name used prior to global declaration)

NOUVEAU V4.5.0 :
    - Feature importance calculée après chaque entraînement ML
    - Feature selection automatique : suppression features < SEUIL_IMPORTANCE (1%)
    - Ré-entraînement avec sous-ensemble de features optimisées
    - Export models/feature_importance.json lisible par le rapport LLM
    - Résumé console avec top-5 features par modèle

FIX V4.4.4 :
    - HeuristiqueChaleur recalibrée pour Kribi (sigmoïde centrée 34°C)
FIX V4.4.3 :
    - HeuristiqueChaleur sérialisable par joblib
FIX V4.4.2 :
    - Chaleur 0 positifs → heuristique ; Inondation <30 → RandomForest
FIX V4.4.1 :
    - PARAM_GRID : détection automatique préfixe estimator__
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

# Seuil de feature selection : features dont l'importance < SEUIL sont supprimées
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

T_ALERTE = 34.0
T_PENTE  = 1.5


class HeuristiqueChaleur:
    """
    Pseudo-estimateur sklearn-compatible sérialisable par joblib.
    Sigmoïde centrée sur T_ALERTE (34°C) pour Kribi.
    """

    def __init__(self, t_alerte=T_ALERTE, t_pente=T_PENTE, idx=0):
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


def _get_param_prefix():
    try:
        import sklearn
        parts = sklearn.__version__.split(".")
        if (int(parts[0]), int(parts[1])) >= (1, 2):
            return "estimator__"
    except Exception:
        pass
    return "base_estimator__"


def _build_param_grid_gb(prefix, fast):
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


def _build_param_grid_rf(fast):
    if fast:
        return {"n_estimators": [200], "max_depth": [None], "min_samples_leaf": [1]}
    return {
        "n_estimators": [100, 200, 300],
        "max_depth": [None, 8, 15],
        "min_samples_leaf": [1, 3, 5],
    }


def _count_combinations(param_grid):
    total = 1
    for v in param_grid.values():
        total *= len(v)
    return total


def charger_dataset(chemin):
    import pandas as pd
    if not os.path.exists(chemin):
        raise FileNotFoundError(
            f"Dataset introuvable : {chemin}\n"
            "  Générez-le avec : python3 inference/build_dataset.py --openmeteo"
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


def creer_modele_heuristique_chaleur(df):
    idx_temp = FEATURES_ALL.index("temp_max")
    print(f"[CHALEUR] ⚠️  0 positifs → heuristique sigmoïde (centre={T_ALERTE}°C, pente={T_PENTE}°C)")
    clf = HeuristiqueChaleur(t_alerte=T_ALERTE, t_pente=T_PENTE, idx=idx_temp)
    return {
        "clf": clf, "seuil": 0.50, "features": FEATURES_ALL,
        "metriques": {"f1": None, "recall": None, "precision": None, "auc_roc": None, "f1_cv": None},
        "params_optimaux": {"type": "heuristique_sigmoide", "t_alerte": T_ALERTE, "t_pente": T_PENTE},
        "n_train": len(df), "n_test": 0, "n_positifs": 0, "type": "heuristique",
        "feature_importance": {}, "features_selectionnees": FEATURES_ALL, "features_supprimees": [],
        "f1_avant_selection": None, "gain_f1_selection": None,
    }


def seuil_optimal_f1(y_true, y_proba):
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

def extraire_feature_importance(clf, features):
    """
    Extrait les importances depuis un estimateur sklearn, y compris lorsqu'il
    est encapsulé dans CalibratedClassifierCV.

    FIX V4.5.2 : on teste calibrated_classifiers_ EN PREMIER pour éviter de
    récupérer l'attribut 'estimator' non-entraîné de CalibratedClassifierCV.
    Ordre de résolution :
      1. calibrated_classifiers_[0].estimator  (CalibratedClassifierCV entraîné)
      2. base_estimator / estimator             (Pipeline ou wrappeur simple)
      3. clf directement
    """
    import numpy as np
    importances = None
    estimateur  = clf

    # 1. CalibratedClassifierCV — accès via calibrated_classifiers_
    if hasattr(clf, "calibrated_classifiers_"):
        val   = clf.calibrated_classifiers_
        if isinstance(val, list) and val:
            inner      = val[0]
            estimateur = getattr(inner, "estimator",
                         getattr(inner, "base_estimator", inner))
    # 2. Wrappeur générique (Pipeline, etc.)
    elif hasattr(clf, "base_estimator"):
        estimateur = clf.base_estimator
    elif hasattr(clf, "estimator"):
        estimateur = clf.estimator

    # Extraction des importances
    if hasattr(estimateur, "feature_importances_"):
        importances = estimateur.feature_importances_
    elif hasattr(estimateur, "estimators_"):
        try:
            importances = np.mean(
                [e.feature_importances_ for e in estimateur.estimators_
                 if hasattr(e, "feature_importances_")], axis=0)
        except Exception:
            pass

    if importances is None:
        print("  [IMPORTANCE] ⚠️  Impossible d'extraire les importances")
        return {}

    importance_dict = {f: round(float(imp), 6) for f, imp in zip(features, importances)}
    return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))


def selectionner_features(importance_dict, seuil, features_all):
    selectionnees = [f for f, imp in importance_dict.items() if imp >= seuil]
    if len(selectionnees) < 5:
        top5 = list(importance_dict.keys())[:5]
        print(f"  [SELECTION] ⚠️  Moins de 5 features → garde top-5 : {top5}")
        return top5
    supprimees = [f for f in features_all if f not in selectionnees]
    if supprimees:
        print(f"  [SELECTION] 🗑️  Supprimées ({len(supprimees)}) : {supprimees}")
    print(f"  [SELECTION] ✅ Retenues : {len(selectionnees)}/{len(features_all)}")
    return selectionnees


def afficher_top_features(nom, importance_dict, n=5):
    print(f"  [IMPORTANCE] Top-{n} features {nom.upper()} :")
    for i, (feat, imp) in enumerate(list(importance_dict.items())[:n], 1):
        bar = "█" * int(imp * 200)
        print(f"    {i}. {feat:<22} {imp:.4f}  {bar}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRAÎNEMENT
# ─────────────────────────────────────────────────────────────────────────────

def _print_metriques(nom, f1, recall, prec, auc):
    print(f"[{nom.upper()}] ── Métriques test ──")
    print(f"[{nom.upper()}]   F1={f1}  Recall={recall}  Precision={prec}  AUC={auc}")


def _build_result(clf, seuil, features, f1, recall, prec, auc, f1_cv, params, X_train, X_test, n_positifs):
    return {
        "clf": clf, "seuil": seuil, "features": features,
        "metriques": {"f1": f1, "recall": recall, "precision": prec, "auc_roc": auc, "f1_cv": f1_cv},
        "params_optimaux": params,
        "n_train": len(X_train), "n_test": len(X_test), "n_positifs": n_positifs,
        "feature_importance": {}, "features_selectionnees": features,
    }


def entrainer_gradient_boosting(nom, df, features, param_grid, verbose):
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
    print(f"[{nom.upper()}] Déséquilibre {ratio:.1f}x → class_weight[1]={class_weight[1]:.1f}")

    calibrated = CalibratedClassifierCV(GradientBoostingClassifier(random_state=42), cv=3, method="isotonic")
    tscv = TimeSeriesSplit(n_splits=5)
    print(f"[{nom.upper()}] GridSearchCV GB (5 folds × {_count_combinations(param_grid)} combinaisons)...")

    grid = GridSearchCV(calibrated, param_grid, cv=tscv, scoring="f1",
                        n_jobs=-1, verbose=1 if verbose else 0, refit=True)
    sw = np.array([class_weight[int(yi)] for yi in y_train])
    grid.fit(X_train, y_train, **{"sample_weight": sw})

    clf = grid.best_estimator_
    f1_cv = round(grid.best_score_, 4)
    print(f"[{nom.upper()}] Best params={grid.best_params_}  F1_cv={f1_cv}")

    folds = list(tscv.split(X_train))
    _, idx_val = folds[-1]
    seuil = seuil_optimal_f1(y_train[idx_val], clf.predict_proba(X_train[idx_val])[:, 1])

    y_proba = clf.predict_proba(X_test)[:, 1]
    y_pred  = (y_proba >= seuil).astype(int)
    f1   = round(f1_score(y_test, y_pred, zero_division=0), 4)
    rec  = round(recall_score(y_test, y_pred, zero_division=0), 4)
    prec = round(precision_score(y_test, y_pred, zero_division=0), 4)
    try:
        auc = round(roc_auc_score(y_test, y_proba), 4)
    except Exception:
        auc = None
    _print_metriques(nom, f1, rec, prec, auc)
    return _build_result(clf, seuil, features, f1, rec, prec, auc, f1_cv,
                         grid.best_params_, X_train, X_test, int(y.sum()))


def entrainer_random_forest(nom, df, features, param_grid, verbose):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
    from sklearn.metrics import f1_score, recall_score, precision_score, roc_auc_score

    label_col = TARGETS[nom]
    X, y = df[features].values, df[label_col].values
    split_idx = int(len(X) * 0.80)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    print(f"[{nom.upper()}] → RandomForest (balanced_subsample)")
    clf_base = RandomForestClassifier(class_weight="balanced_subsample", random_state=42, n_jobs=-1)
    tscv = TimeSeriesSplit(n_splits=5)
    print(f"[{nom.upper()}] GridSearchCV RF (5 folds × {_count_combinations(param_grid)} combinaisons)...")

    grid = GridSearchCV(clf_base, param_grid, cv=tscv, scoring="f1",
                        n_jobs=1, verbose=1 if verbose else 0, refit=True, error_score=0.0)
    grid.fit(X_train, y_train)

    clf = grid.best_estimator_
    f1_cv = round(grid.best_score_, 4)
    print(f"[{nom.upper()}] Best params={grid.best_params_}  F1_cv={f1_cv}")

    folds = list(tscv.split(X_train))
    _, idx_val = folds[-1]
    seuil = seuil_optimal_f1(y_train[idx_val], clf.predict_proba(X_train[idx_val])[:, 1])

    y_proba = clf.predict_proba(X_test)[:, 1]
    y_pred  = (y_proba >= seuil).astype(int)
    f1   = round(f1_score(y_test, y_pred, zero_division=0), 4)
    rec  = round(recall_score(y_test, y_pred, zero_division=0), 4)
    prec = round(precision_score(y_test, y_pred, zero_division=0), 4)
    try:
        auc = round(roc_auc_score(y_test, y_proba), 4)
    except Exception:
        auc = None
    _print_metriques(nom, f1, rec, prec, auc)
    return _build_result(clf, seuil, features, f1, rec, prec, auc, f1_cv,
                         grid.best_params_, X_train, X_test, int(y.sum()))


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE 2 PASSES
# ─────────────────────────────────────────────────────────────────────────────

def entrainer_modele(nom, df, fast, prefix, verbose):
    label_col  = TARGETS[nom]
    n_positifs = int(df[label_col].sum())
    n_total    = len(df)
    print(f"\n[{nom.upper()}] Positifs : {n_positifs}/{n_total} ({100*n_positifs//max(n_total,1)}%)")
    print(f"[{nom.upper()}] Train : {int(n_total*0.80)} | Test : {n_total - int(n_total*0.80)}")

    if n_positifs < MIN_POSITIFS_ML:
        return creer_modele_heuristique_chaleur(df)

    # Passe 1 — rapide sur toutes les features
    print(f"\n[{nom.upper()}] ── Passe 1 : toutes les features ({len(FEATURES_ALL)}) ──")
    if n_positifs < MIN_POSITIFS_CALIB:
        r1 = entrainer_random_forest(nom, df, FEATURES_ALL, _build_param_grid_rf(True), False)
    else:
        r1 = entrainer_gradient_boosting(nom, df, FEATURES_ALL, _build_param_grid_gb(prefix, True), False)

    imp1 = extraire_feature_importance(r1["clf"], FEATURES_ALL)
    if imp1:
        afficher_top_features(nom, imp1)
        features_sel = selectionner_features(imp1, SEUIL_IMPORTANCE, FEATURES_ALL)
    else:
        print("  [SELECTION] Importance indisponible → toutes les features conservées")
        features_sel = FEATURES_ALL

    # Passe 2 — GridSearchCV complet sur features sélectionnées
    if set(features_sel) == set(FEATURES_ALL):
        print(f"\n[{nom.upper()}] ── Passe 2 : toutes features conservées ──")
    else:
        print(f"\n[{nom.upper()}] ── Passe 2 : {len(features_sel)} features sélectionnées ──")

    if n_positifs < MIN_POSITIFS_CALIB:
        r2 = entrainer_random_forest(nom, df, features_sel, _build_param_grid_rf(fast), verbose)
    else:
        r2 = entrainer_gradient_boosting(nom, df, features_sel, _build_param_grid_gb(prefix, fast), verbose)

    imp2  = extraire_feature_importance(r2["clf"], features_sel)
    f1_p1 = r1["metriques"]["f1"]
    f1_p2 = r2["metriques"]["f1"]
    delta = round((f1_p2 - f1_p1) * 100, 2) if f1_p1 and f1_p2 else 0
    print(f"\n[{nom.upper()}] 📊 F1 : {f1_p1} → {f1_p2} ({'+' if delta>=0 else ''}{delta}%)")

    r2["feature_importance"]     = imp2
    r2["feature_importance_all"] = imp1
    r2["features_selectionnees"] = features_sel
    r2["features_supprimees"]    = [f for f in FEATURES_ALL if f not in features_sel]
    r2["f1_avant_selection"]     = f1_p1
    r2["gain_f1_selection"]      = delta
    return r2


# ─────────────────────────────────────────────────────────────────────────────
# SAUVEGARDE
# ─────────────────────────────────────────────────────────────────────────────

def sauvegarder_modele(nom, result):
    import joblib
    chemin = os.path.join(MODELS_DIR, f"model_{nom}.pkl")
    joblib.dump({"clf": result["clf"], "seuil": result["seuil"],
                 "features": result["features_selectionnees"]}, chemin)
    print(f"[SAVE] ✅ {chemin} ({len(result['features_selectionnees'])} features)")


def sauvegarder_feature_importance(resultats):
    import numpy as np
    chemin = os.path.join(MODELS_DIR, "feature_importance.json")
    rapport = {
        "version": "V4.5.2",
        "date": datetime.datetime.now().isoformat(),
        "seuil_selection": SEUIL_IMPORTANCE,
        "modeles": {},
    }
    importances_globales = {}
    for nom, r in resultats.items():
        imp = r.get("feature_importance", {})
        rapport["modeles"][nom] = {
            "top_features":           [{"feature": f, "importance": v} for f, v in list(imp.items())[:10]],
            "features_selectionnees": r.get("features_selectionnees", FEATURES_ALL),
            "features_supprimees":    r.get("features_supprimees", []),
            "n_features_retenues":    len(r.get("features_selectionnees", FEATURES_ALL)),
            "n_features_supprimees":  len(r.get("features_supprimees", [])),
            "gain_f1_selection":      r.get("gain_f1_selection"),
            "f1_avant_selection":     r.get("f1_avant_selection"),
            "f1_apres_selection":     r["metriques"].get("f1"),
        }
        for feat, val in imp.items():
            importances_globales.setdefault(feat, []).append(val)
    global_top = sorted(
        {f: round(float(np.mean(v)), 6) for f, v in importances_globales.items()}.items(),
        key=lambda x: x[1], reverse=True
    )
    rapport["global_top_features"] = [{"feature": f, "importance_moyenne": v} for f, v in global_top[:10]]
    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump(rapport, fh, ensure_ascii=False, indent=2)
    print(f"[SAVE] ✅ Feature importance : {chemin}")
    return rapport


def sauvegarder_rapport(resultats):
    chemin = os.path.join(MODELS_DIR, "training_report.json")
    rapport = {
        "version": "V4.5.2",
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
            "f1_avant_selection":     r.get("f1_avant_selection"),   # FIX V4.5.2
            "gain_f1_selection":      r.get("gain_f1_selection"),
        }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] ✅ Rapport : {chemin}")
    return rapport


def afficher_resume(rapport_train, rapport_fi):
    print("\n" + "═" * 70)
    print("  SAMCAM V4.5.2 — Résumé de l'entraînement")
    print("═" * 70)
    print(f"  Features initiales : {rapport_train['n_features_all']}  |  Seuil : {rapport_train['seuil_selection']*100:.0f}%")
    print()
    print(f"  {'Modèle':<15} {'Type':<22} {'F1 avant':>9} {'F1 après':>9} {'Gain':>7} {'Features':>9}")
    print(f"  {'-'*15} {'-'*22} {'-'*9} {'-'*9} {'-'*7} {'-'*9}")
    for nom, m in rapport_train["modeles"].items():
        mt   = m["metriques"]
        tp   = m.get("type", "ml")
        f1ap = f"{mt['f1']:.4f}"               if mt["f1"]                    else "   N/A "
        f1av = f"{m['f1_avant_selection']:.4f}" if m.get("f1_avant_selection") else "   N/A "
        gain = f"{m['gain_f1_selection']:+.2f}%" if m.get("gain_f1_selection") is not None else "   N/A "
        nsel = len(m.get("features_selectionnees", FEATURES_ALL))
        print(f"  {nom:<15} {tp:<22} {f1av:>9} {f1ap:>9} {gain:>7} {nsel:>5}/{len(FEATURES_ALL)}")
    print("═" * 70)
    if rapport_fi.get("global_top_features"):
        print("\n  🔑 Top-5 features globales :")
        for i, item in enumerate(rapport_fi["global_top_features"][:5], 1):
            bar = "█" * int(item["importance_moyenne"] * 200)
            print(f"    {i}. {item['feature']:<22} {item['importance_moyenne']:.4f}  {bar}")
    print("═" * 70)
    print("  Note chaleur : sigmoïde 34°C  |  32°C→🟢  34°C→🟡  36°C→🔴")
    print("═" * 70)


def main():
    # ── global déclaré EN TÊTE de fonction, avant tout accès ────────────────
    global SEUIL_IMPORTANCE

    parser = argparse.ArgumentParser(description="SAMCAM V4.5.2 — Entraînement modèles")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--no-grid", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--modeles", nargs="+", default=["inondation", "secheresse", "chaleur"])
    parser.add_argument(
        "--seuil-importance", type=float, default=SEUIL_IMPORTANCE,
        help=f"Seuil de feature selection (défaut: {SEUIL_IMPORTANCE} = 1%%)"
    )
    args = parser.parse_args()

    SEUIL_IMPORTANCE = args.seuil_importance

    print("\n" + "═" * 70)
    print("  SAMCAM V4.5.2 — Feature Importance + Sélection automatique")
    print("  Mode : " + ("RAPIDE" if args.no_grid else "COMPLET (GridSearchCV + TimeSeriesSplit)"))
    print(f"  Seuil sélection : {SEUIL_IMPORTANCE*100:.0f}%")
    print("═" * 70)

    prefix = _get_param_prefix()
    print(f"  sklearn prefix : '{prefix}'")

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
