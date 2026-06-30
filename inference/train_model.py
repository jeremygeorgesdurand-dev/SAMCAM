#!/usr/bin/env python3
"""
SAMCAM V4.3 — Entraînement du modèle de classification de risque

NOUVEAUTÉS V4.3 :
    - Validation interne walk-forward via TimeSeriesSplit (remplace StratifiedKFold
      qui pouvait introduire un leakage temporel indirect).
    - Support --horizon 1/3/7 pour entraîner des modèles spécifiques par horizon
      (model_inondation_j1.pkl, model_inondation_j3.pkl, etc.).
    - Support --all-horizons pour tout entraîner en un seul appel.
    - FEATURES_PAR_HORIZON aligné sur risk_model V4.7+.

NOUVEAUTÉS V4.2 :
    - Validation TEMPORELLE : train 1990-2020 / test 2020-fin
      → évite le data leakage sur séries chronologiques
      → mesure la vraie capacité de généralisation future du modèle
    - Résumé lisible en fin d'entraînement (tableau récapitulatif)
    - Détection automatique de la colonne 'source' (vraies données vs simulation)
    - Avertissement si le dataset est encore en mode simulation

Usage :
    python3 inference/train_model.py                      # modèles J0
    python3 inference/train_model.py --horizon 1          # modèles J+1
    python3 inference/train_model.py --horizon 3          # modèles J+3
    python3 inference/train_model.py --horizon 7          # modèles J+7
    python3 inference/train_model.py --all-horizons       # J0 + J+1 + J+3 + J+7
    python3 inference/train_model.py --force              # réentraîne même si existants
    python3 inference/train_model.py --split-year 2018

Sortie :
    models/model_inondation.pkl          (J0)
    models/model_inondation_j1.pkl       (--horizon 1 ou --all-horizons)
    models/model_inondation_j3.pkl       (--horizon 3 ou --all-horizons)
    models/model_inondation_j7.pkl       (--horizon 7 ou --all-horizons)
    models/model_{secheresse,chaleur}.pkl / _j1 / _j3 / _j7
    models/model_metadata.json
"""

import os
import json
import argparse
import datetime
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

DATASET_CSV   = os.path.join(DATA_DIR,   "dataset_kribi_historical.csv")
METADATA_JSON = os.path.join(MODELS_DIR, "model_metadata.json")

SPLIT_YEAR_DEFAULT = 2020

FEATURES_BASE = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi",
]

FEATURES_DERIVEES = [
    "sin_mois", "cos_mois",
    "anomalie_pluie", "ratio_30j_7j",
    "trend_sm", "sm_deficit",
]

CIBLES = {
    "inondation": "label_inondation",
    "secheresse":  "label_secheresse",
    "chaleur":     "label_chaleur",
}

# Features spécifiques par horizon — alignées sur risk_model.py V4.7+
# Seules les colonnes présentes dans le dataset historique sont listées.
FEATURES_J1 = [
    "mois", "sin_mois", "cos_mois",
    "pluie_7j", "pluie_prev_7j", "pluie_30j",
    "sm_surface", "sm_rootzone", "ndvi", "ndwi",
    "temp_max", "temp_max_3j",
    "anomalie_pluie", "ratio_30j_7j", "trend_sm", "sm_deficit",
]
FEATURES_J3 = [
    "mois", "sin_mois", "cos_mois",
    "pluie_prev_7j", "anomalie_pluie", "pluie_30j",
    "sm_surface", "sm_rootzone", "ndvi", "ndwi",
    "temp_max_3j", "ratio_30j_7j", "sm_deficit",
]
FEATURES_J7 = [
    "mois", "sin_mois", "cos_mois",
    "pluie_prev_7j", "anomalie_pluie", "pluie_30j",
    "ndvi", "sm_rootzone", "sm_deficit", "temp_max",
]
FEATURES_PAR_HORIZON = {None: None, 1: FEATURES_J1, 3: FEATURES_J3, 7: FEATURES_J7}


def charger_dataset(chemin: str):
    import pandas as pd
    print(f"[TRAIN] Chargement : {chemin}")
    df = pd.read_csv(chemin, parse_dates=["date"])
    print(f"[TRAIN] {len(df)} lignes, {df.shape[1]} colonnes")

    if "source" in df.columns:
        sources = df["source"].value_counts().to_dict()
        if sources.get("simulation", 0) > 0 and sources.get("open-meteo-real", 0) == 0:
            print(f"[TRAIN] ⚠️  ATTENTION : dataset encore en mode simulation synthétique.")
            print(f"[TRAIN]    Pour de meilleures prédictions, relancez :")
            print(f"[TRAIN]    python3 inference/build_dataset.py --openmeteo")
        elif sources.get("open-meteo-real", 0) > 0:
            print(f"[TRAIN] ✅ Dataset contient de vraies données Open-Meteo ({sources.get('open-meteo-real', 0)} semaines)")
    return df


def get_features_disponibles(df_columns: list) -> list:
    toutes = FEATURES_BASE + FEATURES_DERIVEES
    dispo  = [f for f in toutes if f in df_columns]
    manquantes = [f for f in FEATURES_DERIVEES if f not in df_columns]
    if manquantes:
        print(f"[TRAIN] Features dérivées absentes : {manquantes}")
        print("        Relancez build_dataset.py pour les générer.")
    print(f"[TRAIN] Features utilisées ({len(dispo)}) : {dispo}")
    return dispo


def split_temporel(df, features: list, cible: str, split_year: int):
    """
    V4.2 — Split TEMPOREL.
    Train = données AVANT split_year / Test = données DEPUIS split_year.
    """
    mask_train = df["date"].dt.year < split_year
    mask_test  = df["date"].dt.year >= split_year

    X_train = df.loc[mask_train, features].fillna(df[features].median())
    X_test  = df.loc[mask_test,  features].fillna(df[features].median())
    y_train = df.loc[mask_train, cible]
    y_test  = df.loc[mask_test,  cible]

    print(f"[SPLIT] Train : {mask_train.sum()} semaines (avant {split_year}) "
          f"| {int(y_train.sum())} positifs")
    print(f"[SPLIT] Test  : {mask_test.sum()} semaines (depuis {split_year}) "
          f"| {int(y_test.sum())} positifs")

    return X_train, X_test, y_train, y_test


def split_validation(X_train, y_train):
    """Sous-ensemble de validation t