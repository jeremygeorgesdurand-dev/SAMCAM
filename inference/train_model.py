#!/usr/bin/env python3
"""
SAMCAM V4 — Entraînement du modèle de classification de risque

Lit le dataset historique CSV et entraîne 3 classifieurs RandomForest :
    - modèle inondation  → models/model_inondation.pkl
    - modèle sécheresse  → models/model_secheresse.pkl
    - modèle vague chaleur → models/model_chaleur.pkl

Usage :
    python3 inference/train_model.py
    python3 inference/train_model.py --dataset data/dataset_kribi_historical.csv
    python3 inference/train_model.py --force   # reentraîne même si modèles existants

Sortie :
    models/model_inondation.pkl
    models/model_secheresse.pkl
    models/model_chaleur.pkl
    models/model_metadata.json  ← métriques + features utilisées
"""

import os
import json
import argparse
import datetime

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

DATASET_CSV  = os.path.join(DATA_DIR,   "dataset_kribi_historical.csv")
METADATA_JSON = os.path.join(MODELS_DIR, "model_metadata.json")

FEATURES = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi",
]

CIBLES = {
    "inondation": "label_inondation",
    "secheresse":  "label_secheresse",
    "chaleur":     "label_chaleur",
}


def charger_dataset(chemin: str):
    import pandas as pd
    print(f"[TRAIN] Chargement : {chemin}")
    df = pd.read_csv(chemin, parse_dates=["date"])
    print(f"[TRAIN] {len(df)} lignes chargées")
    return df


def entrainer_classifieur(X_train, y_train, nom: str):
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.utils.class_weight import compute_class_weight
    import numpy as np

    # RandomForest avec class_weight='balanced' pour gérer le déséquilibre
    clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=8,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    print(f"[TRAIN] Modèle {nom} entraîné ({len(X_train)} exemples, "
          f"{int(y_train.sum())} positifs)")
    return clf


def evaluer(clf, X_test, y_test, nom: str) -> dict:
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score,
        f1_score, roc_auc_score, confusion_matrix,
    )
    import numpy as np

    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)[:, 1]

    metriques = {
        "accuracy":  round(float(accuracy_score(y_test, y_pred)),  4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall":    round(float(recall_score(y_test, y_pred,    zero_division=0)), 4),
        "f1":        round(float(f1_score(y_test, y_pred,        zero_division=0)), 4),
        "auc_roc":   round(float(roc_auc_score(y_test, y_prob) if y_test.sum() > 0 else 0.5), 4),
    }
    cm = confusion_matrix(y_test, y_pred).tolist()

    print(f"[EVAL] {nom:12s} | Acc: {metriques['accuracy']:.3f} | "
          f"P: {metriques['precision']:.3f} | R: {metriques['recall']:.3f} | "
          f"F1: {metriques['f1']:.3f} | AUC: {metriques['auc_roc']:.3f}")
    print(f"         Matrice de confusion : {cm}")
    return {**metriques, "confusion_matrix": cm}


def importance_features(clf, features: list, nom: str) -> dict:
    importances = dict(zip(features, [round(float(v), 4) for v in clf.feature_importances_]))
    tri = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))
    print(f"[FEAT] {nom} — Top 3 features : " +
          ", ".join(f"{k}={v:.3f}" for k, v in list(tri.items())[:3]))
    return tri


def main():
    import pandas as pd
    import joblib
    from sklearn.model_selection import train_test_split

    parser = argparse.ArgumentParser(description="SAMCAM V4 — Entraînement modèles de risque")
    parser.add_argument("--dataset", type=str, default=DATASET_CSV)
    parser.add_argument("--force",   action="store_true", help="Réentraîne même si modèles existants")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"[TRAIN] Dataset introuvable : {args.dataset}")
        print("  Lancez d'abord : python3 inference/build_dataset.py --no-gee")
        return

    df = charger_dataset(args.dataset)

    # Vérifier les colonnes requises
    manquantes = [c for c in FEATURES + list(CIBLES.values()) if c not in df.columns]
    if manquantes:
        print(f"[TRAIN] Colonnes manquantes dans le dataset : {manquantes}")
        return

    X = df[FEATURES].fillna(df[FEATURES].median())
    metadata = {
        "date_entrainement": datetime.datetime.now().isoformat(),
        "features": FEATURES,
        "n_total": len(df),
        "modeles": {},
    }

    for nom, cible in CIBLES.items():
        chemin_pkl = os.path.join(MODELS_DIR, f"model_{nom}.pkl")

        if os.path.exists(chemin_pkl) and not args.force:
            print(f"[TRAIN] Modèle {nom} déjà présent (--force pour réentraîner)")
            continue

        y = df[cible]
        if y.sum() < 10:
            print(f"[TRAIN] Insuffisant positifs pour {nom} ({y.sum()}) — ignoré")
            continue

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        clf = entrainer_classifieur(X_train, y_train, nom)
        metriques = evaluer(clf, X_test, y_test, nom)
        importances = importance_features(clf, FEATURES, nom)

        joblib.dump(clf, chemin_pkl)
        print(f"[TRAIN] Sauvegardé : {chemin_pkl}")

        metadata["modeles"][nom] = {
            "fichier":     f"model_{nom}.pkl",
            "n_train":     len(X_train),
            "n_positifs":  int(y_train.sum()),
            "metriques":   metriques,
            "importances": importances,
        }

    with open(METADATA_JSON, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"[TRAIN] Métadonnées sauvegardées : {METADATA_JSON}")
    print("\n[TRAIN] ✅ Entraînement terminé !")
    print("        Lancez ensuite : python3 inference/pipeline_complet.py")


if __name__ == "__main__":
    main()
