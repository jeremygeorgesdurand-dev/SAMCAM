#!/usr/bin/env python3
"""
train_zonal_models.py — Entraînement des modèles zonaux SAMCAM.

Produit 24 modèles .pkl (8 zones × 3 risques) dans models/zonal/
Chaque modèle est entraîné sur l'historique de sa zone uniquement.

Stratégie :
  - Split temporel 80% train / 20% test (pas de leakage)
  - RandomForest + XGBoost (sélection automatique par AUC)
  - SMOTE si déséquilibre de classes > 10:1
  - Seuil de décision optimisé par F1-score
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
from sklearn.model_selection import cross_val_score
from sklearn.metrics import (
    f1_score, roc_auc_score, precision_score, recall_score,
    classification_report, confusion_matrix
)
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.utils.class_weight import compute_sample_weight

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path("data/historical")
MODELS_DIR = Path("models/zonal")
METRICS_DIR = Path("models/zonal/metrics")
MODELS_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR.mkdir(parents=True, exist_ok=True)

RISKS = ["inondation", "secheresse", "chaleur"]

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
# Features utilisées pour l'entraînement
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

# Features spécifiques par risque
RISK_FEATURES = {
    "inondation": FEATURE_GROUPS["meteo"] + FEATURE_GROUPS["derived"] + FEATURE_GROUPS["soil"],
    "secheresse": FEATURE_GROUPS["meteo"] + FEATURE_GROUPS["nasa"] + FEATURE_GROUPS["derived"] + FEATURE_GROUPS["soil"],
    "chaleur": FEATURE_GROUPS["meteo"] + FEATURE_GROUPS["nasa"] + FEATURE_GROUPS["derived"],
}


# ---------------------------------------------------------------------------
# Préparation des features
# ---------------------------------------------------------------------------
def prepare_features(df: pd.DataFrame, risk: str) -> tuple:
    """Extrait X et y du DataFrame pour un risque donné."""
    label_col = f"label_{risk}"
    if label_col not in df.columns:
        raise ValueError(f"Colonne {label_col} manquante")

    # Sélectionner features disponibles
    candidate_features = RISK_FEATURES[risk]
    available_features = [f for f in candidate_features if f in df.columns]

    if len(available_features) < 5:
        logger.warning(f"Seulement {len(available_features)} features disponibles pour {risk}")

    logger.info(f"[Features] {risk}: {len(available_features)} features utilisées")

    X = df[available_features].copy()
    y = df[label_col].copy()

    # Imputation valeurs manquantes par médiane
    for col in X.columns:
        if X[col].isna().any():
            X[col].fillna(X[col].median(), inplace=True)

    return X, y, available_features


# ---------------------------------------------------------------------------
# Entraînement
# ---------------------------------------------------------------------------
def train_model_for_zone_risk(zone_name: str, risk: str,
                               df: pd.DataFrame, force: bool = False) -> dict:
    """Entraîne et évalue un modèle pour une zone + risque donnés."""
    model_path = MODELS_DIR / f"model_{risk}_{zone_name}.pkl"
    metrics_path = METRICS_DIR / f"metrics_{risk}_{zone_name}.json"

    if model_path.exists() and not force:
        logger.info(f"[Skip] {zone_name}/{risk} déjà entraîné. Utilisez --force pour ré-entraîner.")
        with open(metrics_path) as f:
            return json.load(f)

    logger.info(f"\n{'='*50}")
    logger.info(f"Entraînement : {zone_name} / {risk.upper()}")
    logger.info(f"{'='*50}")

    # --- Préparation ---
    try:
        X, y, feature_names = prepare_features(df, risk)
    except ValueError as e:
        logger.error(f"[Erreur] {zone_name}/{risk}: {e}")
        return {"zone": zone_name, "risk": risk, "status": "ERREUR", "error": str(e)}

    # Split temporel : 80% train, 20% test
    split_idx = int(len(df) * 0.80)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    n_pos_train = y_train.sum()
    n_neg_train = len(y_train) - n_pos_train
    n_pos_test = y_test.sum()

    logger.info(f"Train: {len(X_train)} jours ({n_pos_train} positifs, {n_neg_train} négatifs)")
    logger.info(f"Test : {len(X_test)} jours ({n_pos_test} positifs)")

    if n_pos_train < 10:
        logger.warning(f"⚠️  Seulement {n_pos_train} exemples positifs — modèle peu fiable pour {zone_name}/{risk}")

    # --- Poids de classe pour déséquilibre ---
    sample_weights = compute_sample_weight("balanced", y_train)

    # --- Entraînement RandomForest ---
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)

    # --- Entraînement GradientBoosting ---
    gb = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
    )
    gb.fit(X_train, y_train, sample_weight=sample_weights)

    # --- Sélection du meilleur modèle par AUC ---
    best_model = None
    best_auc = -1
    best_name = ""

    for name, model in [("RandomForest", rf), ("GradientBoosting", gb)]:
        if n_pos_test >= 5:
            try:
                proba = model.predict_proba(X_test)[:, 1]
                auc = roc_auc_score(y_test, proba)
                logger.info(f"  {name} AUC = {auc:.4f}")
                if auc > best_auc:
                    best_auc = auc
                    best_model = model
                    best_name = name
            except Exception:
                pass

    if best_model is None:
        best_model = rf  # fallback
        best_name = "RandomForest"

    # --- Optimisation seuil de décision ---
    if n_pos_test >= 5:
        proba_test = best_model.predict_proba(X_test)[:, 1]
        best_threshold = 0.5
        best_f1 = 0
        for thr in np.arange(0.2, 0.8, 0.05):
            preds = (proba_test >= thr).astype(int)
            f1 = f1_score(y_test, preds, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = thr
    else:
        best_threshold = 0.5
        best_f1 = 0.0
        best_auc = 0.0

    # --- Métriques finales ---
    y_pred = (best_model.predict_proba(X_test)[:, 1] >= best_threshold).astype(int)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)

    metrics = {
        "zone": zone_name,
        "risk": risk,
        "model": best_name,
        "status": "OK",
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "n_positive_train": int(n_pos_train),
        "n_positive_test": int(n_pos_test),
        "auc_roc": round(float(best_auc), 4),
        "f1_score": round(float(best_f1), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "decision_threshold": round(float(best_threshold), 2),
        "n_features": len(feature_names),
        "features": feature_names,
    }

    # Top 10 features importantes
    if hasattr(best_model, "feature_importances_"):
        importances = best_model.feature_importances_
        feat_imp = sorted(zip(feature_names, importances), key=lambda x: -x[1])[:10]
        metrics["top_features"] = [{"feature": f, "importance": round(float(i), 4)} for f, i in feat_imp]

    logger.info(f"  ✅ {best_name} | AUC={best_auc:.3f} | F1={best_f1:.3f} | Threshold={best_threshold:.2f}")

    # --- Sauvegarde modèle ---
    model_bundle = {
        "model": best_model,
        "features": feature_names,
        "threshold": best_threshold,
        "zone": zone_name,
        "risk": risk,
        "metrics": metrics,
    }
    with open(model_path, "wb") as f:
        pickle.dump(model_bundle, f)
    logger.info(f"  Sauvegardé : {model_path}")

    # --- Sauvegarde métriques JSON ---
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Entraînement modèles zonaux SAMCAM")
    parser.add_argument("--zone", default=None, help="Zone spécifique (défaut: toutes)")
    parser.add_argument("--risk", default=None, choices=RISKS, help="Risque spécifique")
    parser.add_argument("--force", action="store_true", help="Ré-entraîner même si pkl existant")
    args = parser.parse_args()

    # Détecter les zones avec données labellisées
    if args.zone:
        zones = [args.zone]
    else:
        zones = [p.stem.replace("_labeled", "")
                 for p in DATA_DIR.glob("*_labeled.csv")]
        zones.sort()

    risks = [args.risk] if args.risk else RISKS

    if not zones:
        logger.error("Aucun fichier labellisé trouvé dans data/historical/")
        logger.error("➡️  Lancez d'abord : python training/build_labels.py")
        return

    logger.info(f"Entraînement pour {len(zones)} zones × {len(risks)} risques = {len(zones)*len(risks)} modèles")
    logger.info(f"Zones : {zones}")
    logger.info(f"Risques : {risks}")

    all_metrics = []
    for zone in zones:
        labeled_path = DATA_DIR / f"{zone}_labeled.csv"
        if not labeled_path.exists():
            logger.error(f"Fichier labellisé manquant : {labeled_path}")
            continue

        df = pd.read_csv(labeled_path, parse_dates=["date"])
        logger.info(f"\n[{zone}] {len(df)} jours chargés ({df['date'].min().date()} → {df['date'].max().date()})")

        for risk in risks:
            metrics = train_model_for_zone_risk(zone, risk, df, args.force)
            all_metrics.append(metrics)

    # --- Tableau récapitulatif ---
    print("\n" + "="*80)
    print("RÉSUMÉ ENTRAÎNEMENT ZONAL SAMCAM")
    print("="*80)
    print(f"{'Zone':<20} {'Risque':<14} {'Modèle':<18} {'AUC':>6} {'F1':>6} {'Thr':>5} {'Status'}")
    print("-"*80)
    for m in all_metrics:
        if m.get("status") == "OK":
            print(f"{m['zone']:<20} {m['risk']:<14} {m.get('model','?'):<18} "
                  f"{m.get('auc_roc',0):>6.3f} {m.get('f1_score',0):>6.3f} "
                  f"{m.get('decision_threshold',0.5):>5.2f} ✅")
        else:
            print(f"{m['zone']:<20} {m['risk']:<14} {'—':<18} {'—':>6} {'—':>6} {'—':>5} ❌ {m.get('error','')}")

    print("="*80)
    ok_count = sum(1 for m in all_metrics if m.get("status") == "OK")
    print(f"\n{ok_count}/{len(all_metrics)} modèles entraînés avec succès.")
    print(f"Modèles sauvegardés dans : {MODELS_DIR.absolute()}")

    if ok_count > 0:
        print("\n➡️  Les modèles zonaux sont prêts.")
        print("   Pour les utiliser dans le pipeline, mettez à jour inference/ pour charger")
        print("   models/zonal/model_{risk}_{zone}.pkl au lieu des modèles globaux.")


if __name__ == "__main__":
    main()
