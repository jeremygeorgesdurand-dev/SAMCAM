#!/usr/bin/env python3
"""
train_zonal_models.py — Entraînement des modèles zonaux SAMCAM.

Produit 24 modèles .pkl (8 zones × 3 risques) dans models/zonal/
Chaque modèle est entraîné sur l'historique de sa zone uniquement.

Stratégie :
  - Walk-forward cross-validation (TimeSeriesSplit, 5 folds, gap=30j)
    → plus robuste qu'un split fixe 80/20 sur ~10 ans de données rares
  - RandomForest + GradientBoosting (sélection par AUC moyen sur les folds)
  - SMOTE adaptatif si ratio négatif/positif > 5:1
  - Seuil de décision optimisé par F1 sur le dernier fold (données les plus récentes)
  - Sauvegarde métriques + importance features

Usage :
  python training/train_zonal_models.py             # toutes les zones
  python training/train_zonal_models.py --zone Kribi
  python training/train_zonal_models.py --risk inondation
  python training/train_zonal_models.py --force     # ré-entraîne même si pkl existant
"""

import os
import json
import pickle
import argparse
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    f1_score, roc_auc_score, precision_score, recall_score,
)
from sklearn.utils.class_weight import compute_sample_weight

warnings.filterwarnings("ignore")

try:
    from imblearn.over_sampling import SMOTE
    SMOTE_AVAILABLE = True
except ImportError:
    SMOTE_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR    = Path("data/historical")
MODELS_DIR  = Path("models/zonal")
METRICS_DIR = Path("models/zonal/metrics")
MODELS_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR.mkdir(parents=True, exist_ok=True)

RISKS = ["inondation", "secheresse", "chaleur"]

WALKFORWARD_FOLDS = 5   # nombre de folds walk-forward
WALKFORWARD_GAP   = 30  # jours de gap entre train et test pour éviter le leakage
SMOTE_RATIO_TRIGGER = 5  # activer SMOTE si neg/pos > ce ratio
SMOTE_TARGET = 0.30      # taux de positifs cible après SMOTE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("models/zonal/train_zonal.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
FEATURE_GROUPS = {
    "meteo": [
        "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
        "precipitation_sum", "et0_fao_evapotranspiration",
        "wind_speed_10m_max", "shortwave_radiation_sum",
        "relative_humidity_2m_max", "relative_humidity_2m_min",
        "precipitation_hours",
    ],
    "nasa": [
        "nasa_allsky_sfc_sw_dwn", "nasa_t2m", "nasa_rh2m",
        "nasa_prectotcorr", "nasa_ws10m", "nasa_evland",
        "nasa_gwetroot", "nasa_gwettop",
    ],
    "soil": [
        "soil_moisture_0_to_7cm_mean", "soil_moisture_7_to_28cm_mean",
        "soil_moisture_28_to_100cm_mean",
    ],
    "derived": [
        "rain_7d", "rain_14d", "rain_30d", "rain_90d",
        "spi3_approx", "temp_anom_30d", "temp_max_7d",
        "month", "day_of_year", "week",
    ],
}

RISK_FEATURES = {
    "inondation": FEATURE_GROUPS["meteo"] + FEATURE_GROUPS["derived"] + FEATURE_GROUPS["soil"],
    "secheresse": FEATURE_GROUPS["meteo"] + FEATURE_GROUPS["nasa"]   + FEATURE_GROUPS["derived"] + FEATURE_GROUPS["soil"],
    "chaleur":    FEATURE_GROUPS["meteo"] + FEATURE_GROUPS["nasa"]   + FEATURE_GROUPS["derived"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def prepare_features(df: pd.DataFrame, risk: str) -> tuple:
    """Extrait X et y pour un risque donné."""
    label_col = f"label_{risk}"
    if label_col not in df.columns:
        raise ValueError(f"Colonne {label_col} manquante")

    available = [f for f in RISK_FEATURES[risk] if f in df.columns]
    if len(available) < 5:
        logger.warning(f"Seulement {len(available)} features disponibles pour {risk}")

    logger.info(f"[Features] {risk}: {len(available)} features")
    X = df[available].copy()
    y = df[label_col].copy()

    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median())

    return X, y, available


def apply_smote_if_needed(X_train: pd.DataFrame, y_train: pd.Series,
                          zone: str, risk: str, fold: int) -> tuple:
    """Applique SMOTE si le ratio de déséquilibre dépasse SMOTE_RATIO_TRIGGER."""
    n_pos = y_train.sum()
    n_neg = len(y_train) - n_pos

    if n_pos < 5:
        logger.debug(f"  [SMOTE fold {fold}] Skip — seulement {n_pos} positifs")
        return X_train, y_train, False

    ratio = n_neg / max(n_pos, 1)
    if ratio <= SMOTE_RATIO_TRIGGER:
        return X_train, y_train, False

    if not SMOTE_AVAILABLE:
        logger.warning("  [SMOTE] imbalanced-learn non installé — skip (pip install imbalanced-learn)")
        return X_train, y_train, False

    try:
        smote = SMOTE(sampling_strategy=SMOTE_TARGET, random_state=42, k_neighbors=min(5, n_pos - 1))
        X_res, y_res = smote.fit_resample(X_train, y_train)
        logger.debug(f"  [SMOTE fold {fold}] ratio {ratio:.1f}:1 → appliqué ({len(y_res)} exemples)")
        return pd.DataFrame(X_res, columns=X_train.columns), pd.Series(y_res), True
    except Exception as e:
        logger.warning(f"  [SMOTE fold {fold}] Échec : {e}")
        return X_train, y_train, False


# ---------------------------------------------------------------------------
# Entraînement principal
# ---------------------------------------------------------------------------
def train_model_for_zone_risk(zone_name: str, risk: str,
                               df: pd.DataFrame, force: bool = False) -> dict:
    """Walk-forward CV + sélection du meilleur modèle + sauvegarde."""
    model_path   = MODELS_DIR  / f"model_{risk}_{zone_name}.pkl"
    metrics_path = METRICS_DIR / f"metrics_{risk}_{zone_name}.json"

    if model_path.exists() and not force:
        logger.info(f"[Skip] {zone_name}/{risk} déjà entraîné. --force pour ré-entraîner.")
        with open(metrics_path) as f:
            return json.load(f)

    logger.info(f"\n{'='*50}")
    logger.info(f"Entraînement : {zone_name} / {risk.upper()}")
    logger.info(f"{'='*50}")

    try:
        X, y, feature_names = prepare_features(df, risk)
    except ValueError as e:
        logger.error(f"[Erreur] {zone_name}/{risk}: {e}")
        return {"zone": zone_name, "risk": risk, "status": "ERREUR", "error": str(e)}

    n_pos_total = y.sum()
    n_neg_total = len(y) - n_pos_total
    ratio_total = n_neg_total / max(n_pos_total, 1)
    logger.info(f"Dataset : {len(df)} jours | {n_pos_total} positifs ({100*n_pos_total/len(df):.1f}%) | ratio {ratio_total:.1f}:1")

    if n_pos_total < 10:
        logger.warning(f"⚠️  {n_pos_total} exemples positifs — modèle peu fiable pour {zone_name}/{risk}")

    # --- Walk-forward Cross-Validation ---
    tscv = TimeSeriesSplit(n_splits=WALKFORWARD_FOLDS, gap=WALKFORWARD_GAP)

    rf_aucs, gb_aucs = [], []
    smote_used_folds = 0
    valid_folds = 0
    last_X_test, last_y_test = None, None  # dernier fold pour optimisation seuil
    last_rf, last_gb = None, None

    for fold, (train_idx, test_idx) in enumerate(tscv.split(X), start=1):
        X_train_f = X.iloc[train_idx]
        y_train_f = y.iloc[train_idx]
        X_test_f  = X.iloc[test_idx]
        y_test_f  = y.iloc[test_idx]

        n_pos_f = y_test_f.sum()
        if n_pos_f < 3:
            logger.debug(f"  Fold {fold} : seulement {n_pos_f} positifs dans le test → skip AUC")
            continue

        # SMOTE sur le train de ce fold
        X_tr, y_tr, smote_applied = apply_smote_if_needed(
            X_train_f, y_train_f, zone_name, risk, fold
        )
        if smote_applied:
            smote_used_folds += 1

        sample_weights_f = compute_sample_weight("balanced", y_tr)

        # RandomForest
        rf_f = RandomForestClassifier(
            n_estimators=300, max_depth=12, min_samples_leaf=5,
            class_weight="balanced", random_state=42, n_jobs=-1,
        )
        rf_f.fit(X_tr, y_tr)

        # GradientBoosting
        gb_f = GradientBoostingClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            subsample=0.8, random_state=42,
        )
        gb_f.fit(X_tr, y_tr, sample_weight=sample_weights_f)

        try:
            auc_rf = roc_auc_score(y_test_f, rf_f.predict_proba(X_test_f)[:, 1])
            auc_gb = roc_auc_score(y_test_f, gb_f.predict_proba(X_test_f)[:, 1])
            rf_aucs.append(auc_rf)
            gb_aucs.append(auc_gb)
            logger.info(f"  Fold {fold:2d} | RF={auc_rf:.3f} | GB={auc_gb:.3f} | pos={n_pos_f}")
            valid_folds += 1
            last_X_test, last_y_test = X_test_f, y_test_f
            last_rf, last_gb = rf_f, gb_f
        except Exception as e:
            logger.debug(f"  Fold {fold} AUC error: {e}")

    # --- Sélection du meilleur algorithme ---
    mean_rf = np.mean(rf_aucs) if rf_aucs else 0.0
    mean_gb = np.mean(gb_aucs) if gb_aucs else 0.0
    std_rf  = np.std(rf_aucs)  if rf_aucs else 0.0
    std_gb  = np.std(gb_aucs)  if gb_aucs else 0.0

    logger.info(f"  CV AUC → RF={mean_rf:.3f}±{std_rf:.3f} | GB={mean_gb:.3f}±{std_gb:.3f} ({valid_folds} folds utiles)")

    if mean_gb >= mean_rf:
        best_model = last_gb
        best_name  = "GradientBoosting"
        cv_auc_mean, cv_auc_std = mean_gb, std_gb
    else:
        best_model = last_rf
        best_name  = "RandomForest"
        cv_auc_mean, cv_auc_std = mean_rf, std_rf

    if best_model is None:
        # Aucun fold valide : entraînement simple sur tout le dataset
        logger.warning(f"  Aucun fold walk-forward valide pour {zone_name}/{risk}. Fallback entraînement complet.")
        best_model = RandomForestClassifier(
            n_estimators=300, max_depth=12, min_samples_leaf=5,
            class_weight="balanced", random_state=42, n_jobs=-1,
        )
        best_model.fit(X, y)
        best_name = "RandomForest"
        cv_auc_mean, cv_auc_std = 0.0, 0.0

    # --- Optimisation du seuil sur le dernier fold ---
    if last_X_test is not None and last_y_test is not None and last_y_test.sum() >= 3:
        proba_last = best_model.predict_proba(last_X_test)[:, 1]
        best_threshold, best_f1 = 0.5, 0.0
        for thr in np.arange(0.15, 0.85, 0.05):
            preds = (proba_last >= thr).astype(int)
            f1    = f1_score(last_y_test, preds, zero_division=0)
            if f1 > best_f1:
                best_f1, best_threshold = f1, float(thr)
    else:
        best_threshold, best_f1 = 0.5, 0.0

    # Métriques sur le dernier fold (données les plus récentes)
    if last_X_test is not None and last_y_test is not None:
        proba_final = best_model.predict_proba(last_X_test)[:, 1]
        y_pred_final = (proba_final >= best_threshold).astype(int)
        precision_final = precision_score(last_y_test, y_pred_final, zero_division=0)
        recall_final    = recall_score(last_y_test,    y_pred_final, zero_division=0)
        n_pos_test_final = int(last_y_test.sum())
        n_test_final     = int(len(last_y_test))
    else:
        precision_final = recall_final = 0.0
        n_pos_test_final = n_test_final = 0

    metrics = {
        "zone":                 zone_name,
        "risk":                 risk,
        "model":                best_name,
        "status":               "OK",
        "n_total":              int(len(X)),
        "n_positive_total":     int(n_pos_total),
        "class_ratio":          round(float(ratio_total), 2),
        "cv_folds":             valid_folds,
        "cv_auc_mean":          round(float(cv_auc_mean), 4),
        "cv_auc_std":           round(float(cv_auc_std),  4),
        "smote_applied_folds":  smote_used_folds,
        "n_test_last_fold":     n_test_final,
        "n_positive_last_fold": n_pos_test_final,
        "f1_last_fold":         round(float(best_f1), 4),
        "precision_last_fold":  round(float(precision_final), 4),
        "recall_last_fold":     round(float(recall_final), 4),
        "decision_threshold":   round(float(best_threshold), 2),
        "n_features":           len(feature_names),
        "features":             feature_names,
    }

    if hasattr(best_model, "feature_importances_"):
        imp = best_model.feature_importances_
        feat_imp = sorted(zip(feature_names, imp), key=lambda x: -x[1])[:10]
        metrics["top_features"] = [
            {"feature": f, "importance": round(float(i), 4)} for f, i in feat_imp
        ]

    logger.info(
        f"  ✅ {best_name} | CV AUC={cv_auc_mean:.3f}±{cv_auc_std:.3f} "
        f"| F1={best_f1:.3f} | Thr={best_threshold:.2f} "
        f"| SMOTE: {smote_used_folds}/{valid_folds} folds"
    )

    model_bundle = {
        "model":     best_model,
        "features":  feature_names,
        "threshold": best_threshold,
        "zone":      zone_name,
        "risk":      risk,
        "metrics":   metrics,
    }
    with open(model_path, "wb") as f:
        pickle.dump(model_bundle, f)
    logger.info(f"  Sauvegardé : {model_path}")

    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Entraînement modèles zonaux SAMCAM")
    parser.add_argument("--zone",  default=None, help="Zone spécifique (défaut: toutes)")
    parser.add_argument("--risk",  default=None, choices=RISKS)
    parser.add_argument("--force", action="store_true", help="Ré-entraîner même si pkl existant")
    args = parser.parse_args()

    if args.zone:
        zones = [args.zone]
    else:
        zones = [
            p.stem.replace("_labeled", "")
            for p in DATA_DIR.glob("*_labeled.csv")
        ]
        zones.sort()

    risks = [args.risk] if args.risk else RISKS

    if not zones:
        logger.error("Aucun fichier labellisé trouvé dans data/historical/")
        logger.error("➡️  Lancez d'abord : python training/build_labels.py")
        return

    if not SMOTE_AVAILABLE:
        logger.warning("⚠️  imbalanced-learn non installé — SMOTE désactivé. pip install imbalanced-learn")

    logger.info(f"Entraînement : {len(zones)} zones × {len(risks)} risques = {len(zones)*len(risks)} modèles")
    logger.info(f"Walk-forward : {WALKFORWARD_FOLDS} folds, gap={WALKFORWARD_GAP}j, SMOTE trigger={SMOTE_RATIO_TRIGGER}:1")

    all_metrics = []
    for zone in zones:
        labeled_path = DATA_DIR / f"{zone}_labeled.csv"
        if not labeled_path.exists():
            logger.error(f"Fichier labellisé manquant : {labeled_path}")
            continue

        df = pd.read_csv(labeled_path, parse_dates=["date"])
        logger.info(f"\n[{zone}] {len(df)} jours ({df['date'].min().date()} → {df['date'].max().date()})")

        for risk in risks:
            m = train_model_for_zone_risk(zone, risk, df, args.force)
            all_metrics.append(m)

    # Tableau récapitulatif
    print("\n" + "="*95)
    print("RÉSUMÉ ENTRAÎNEMENT ZONAL SAMCAM — WALK-FORWARD CV")
    print("="*95)
    print(f"{'Zone':<18} {'Risque':<13} {'Modèle':<18} {'CV AUC±σ':>12} {'F1':>6} {'Thr':>5} {'SMOTE':>6} {'Status'}")
    print("-"*95)
    for m in all_metrics:
        if m.get("status") == "OK":
            smote_info = f"{m.get('smote_applied_folds',0)}/{m.get('cv_folds',0)}"
            print(
                f"{m['zone']:<18} {m['risk']:<13} {m.get('model','?'):<18} "
                f"{m.get('cv_auc_mean',0):>6.3f}±{m.get('cv_auc_std',0):<5.3f} "
                f"{m.get('f1_last_fold',0):>6.3f} {m.get('decision_threshold',0.5):>5.2f} "
                f"{smote_info:>6} ✅"
            )
        else:
            print(f"{m['zone']:<18} {m['risk']:<13} {'—':<18} {'—':>12} {'—':>6} {'—':>5} {'—':>6} ❌ {m.get('error','')}")
    print("="*95)
    ok = sum(1 for m in all_metrics if m.get("status") == "OK")
    print(f"\n{ok}/{len(all_metrics)} modèles entraînés avec succès.")
    print(f"Modèles sauvegardés dans : {MODELS_DIR.absolute()}")
    if ok > 0:
        print("\n➡️  Réentraînement terminé. Relancez le pipeline pour utiliser les nouveaux modèles.")


if __name__ == "__main__":
    main()
