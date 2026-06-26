#!/usr/bin/env python3
"""
SAMCAM V4.4 — Évaluation indépendante des modèles entraînés

Permet de comparer les performances des modèles pkl existants
sur un dataset de test sans réentraîner.

Usage :
    python3 models/evaluate_model.py
    python3 models/evaluate_model.py --dataset data/dataset_kribi_historical.csv
    python3 models/evaluate_model.py --modele secheresse
    python3 models/evaluate_model.py --test-ratio 0.30
"""

import os
import json
import argparse
import warnings
warnings.filterwarnings("ignore")

MODELS_DIR = os.path.join(os.path.dirname(__file__))
DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
DEFAULT_DATASET = os.path.join(DATA_DIR, "dataset_kribi_historical.csv")


def evaluer(dataset_path: str, nom_modele: str, test_ratio: float, verbose: bool):
    import pandas as pd
    import numpy as np
    import joblib
    from sklearn.metrics import (
        f1_score, recall_score, precision_score,
        roc_auc_score, classification_report,
        confusion_matrix
    )

    # ── Charger dataset
    if not os.path.exists(dataset_path):
        print(f"[EVAL] ❌ Dataset introuvable : {dataset_path}")
        return
    df = pd.read_csv(dataset_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # ── Charger modèle
    chemin_pkl = os.path.join(MODELS_DIR, f"model_{nom_modele}.pkl")
    if not os.path.exists(chemin_pkl):
        print(f"[EVAL] ❌ Modèle introuvable : {chemin_pkl}")
        print(f"[EVAL]    Entraînez d'abord avec : python3 models/train_model.py")
        return

    obj = joblib.load(chemin_pkl)
    clf      = obj["clf"]
    seuil    = obj.get("seuil",    0.5)
    features = obj.get("features", [])

    label_col = f"label_{nom_modele}"
    if label_col not in df.columns:
        print(f"[EVAL] ❌ Colonne '{label_col}' absente du dataset")
        return

    features_ok = [f for f in features if f in df.columns]
    features_manquantes = [f for f in features if f not in df.columns]
    if features_manquantes:
        print(f"[EVAL] ⚠️  Features absentes (imputées à 0) : {features_manquantes}")
        for f in features_manquantes:
            df[f] = 0.0

    # ── Split temporel
    split_idx = int(len(df) * (1 - test_ratio))
    df_test = df.iloc[split_idx:].copy()

    X_test = df_test[features].fillna(0).values
    y_test = df_test[label_col].values

    print(f"\n[EVAL] Modèle       : {nom_modele}")
    print(f"[EVAL] Test set     : {len(df_test)} semaines "
          f"({df_test['date'].min().date()} → {df_test['date'].max().date()})")
    print(f"[EVAL] Positifs     : {int(y_test.sum())} ({100*int(y_test.sum())//len(y_test)}%)")
    print(f"[EVAL] Seuil        : {seuil}")
    print(f"[EVAL] Features     : {len(features)}")

    y_proba = clf.predict_proba(X_test)[:, 1]
    y_pred  = (y_proba >= seuil).astype(int)

    f1        = round(f1_score(y_test,        y_pred, zero_division=0), 4)
    recall    = round(recall_score(y_test,    y_pred, zero_division=0), 4)
    precision = round(precision_score(y_test, y_pred, zero_division=0), 4)
    try:
        auc = round(roc_auc_score(y_test, y_proba), 4)
    except Exception:
        auc = None

    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)

    print("\n" + "─" * 50)
    print(f"  RÉSULTATS — {nom_modele.upper()}")
    print("─" * 50)
    print(f"  F1-score  : {f1}")
    print(f"  Recall    : {recall}   (vrais positifs détectés)")
    print(f"  Precision : {precision}")
    print(f"  AUC-ROC   : {auc if auc else 'N/A'}")
    print(f"")
    print(f"  Matrice de confusion :")
    print(f"              Prédit 0   Prédit 1")
    print(f"  Réel 0   :   {tn:>6}     {fp:>6}   (TN / FP)")
    print(f"  Réel 1   :   {fn:>6}     {tp:>6}   (FN / TP)")
    print("─" * 50)

    if verbose:
        print("\n" + classification_report(
            y_test, y_pred,
            target_names=["pas de risque", "risque"],
            zero_division=0
        ))

    # ── Courbe Precision/Recall par seuil
    if verbose:
        print("\n  Seuil  → F1")
        for s in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
            preds = (y_proba >= s).astype(int)
            f = f1_score(y_test, preds, zero_division=0)
            bar = "█" * int(f * 20)
            print(f"  {s:.2f}   → {f:.4f} {bar}")

    return {"f1": f1, "recall": recall, "precision": precision, "auc": auc}


def main():
    parser = argparse.ArgumentParser(description="SAMCAM V4.4 — Évaluation modèles")
    parser.add_argument("--dataset",    default=DEFAULT_DATASET)
    parser.add_argument("--modele",     default=None,
                        help="Un seul modèle (inondation/secheresse/chaleur). Défaut : tous")
    parser.add_argument("--test-ratio", type=float, default=0.20,
                        help="Fraction des données les plus récentes pour le test (défaut 0.20)")
    parser.add_argument("--verbose",    action="store_true")
    args = parser.parse_args()

    modeles = [args.modele] if args.modele else ["inondation", "secheresse", "chaleur"]

    print("\n" + "═" * 50)
    print("  SAMCAM V4.4 — Évaluation des modèles")
    print("═" * 50)

    for nom in modeles:
        evaluer(args.dataset, nom, args.test_ratio, args.verbose)

    print("\n[EVAL] ✅ Évaluation terminée")


if __name__ == "__main__":
    main()
