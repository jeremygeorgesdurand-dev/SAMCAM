#!/usr/bin/env python3
"""
SAMCAM V4.2 — Entraînement du modèle de classification de risque

NOUVEAUTÉS V4.2 :
    - Validation TEMPORELLE : train 1990-2020 / test 2020-fin
      → évite le data leakage sur séries chronologiques
      → mesure la vraie capacité de généralisation future du modèle
    - Résumé lisible en fin d'entraînement (tableau récapitulatif)
    - Détection automatique de la colonne 'source' (vraies données vs simulation)
    - Avertissement si le dataset est encore en mode simulation

Usage :
    python3 inference/train_model.py
    python3 inference/train_model.py --dataset data/dataset_kribi_historical.csv
    python3 inference/train_model.py --force   # réentraîne même si modèles existants
    python3 inference/train_model.py --split-year 2018  # année de coupure personnalisée

Sortie :
    models/model_inondation.pkl
    models/model_secheresse.pkl
    models/model_chaleur.pkl
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

# Année de coupure par défaut pour la validation temporelle
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


def charger_dataset(chemin: str):
    import pandas as pd
    print(f"[TRAIN] Chargement : {chemin}")
    df = pd.read_csv(chemin, parse_dates=["date"])
    print(f"[TRAIN] {len(df)} lignes, {df.shape[1]} colonnes")

    # Avertissement si données synthétiques
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
    V4.2 — Split TEMPOREL au lieu du split aléatoire.
    Train = toutes les données AVANT split_year
    Test  = toutes les données DEPUIS split_year

    Pourquoi c'est crucial :
    - Un split aléatoire permet au modèle de "voir" des données futures
      pendant l'entraînement → métriques artificiellement gonflées
    - Le split temporel mesure la VRAIE capacité à prédire l'avenir
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
    """Sous-ensemble de validation (20% du train) pour optimisation seuil."""
    n = len(X_train)
    idx_val = int(n * 0.8)
    # Split temporel aussi pour la validation (derniers 20% du train)
    X_tr  = X_train.iloc[:idx_val]
    X_val = X_train.iloc[idx_val:]
    y_tr  = y_train.iloc[:idx_val]
    y_val = y_train.iloc[idx_val:]
    return X_tr, X_val, y_tr, y_val


def entrainer_classifieur(X_train, y_train, nom: str):
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    import numpy as np

    n_pos = int(y_train.sum())
    n_neg = len(y_train) - n_pos
    ratio = n_neg / max(1, n_pos)
    sample_weight = np.where(y_train == 1, ratio, 1.0)

    base_clf = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        min_samples_leaf=10,
        subsample=0.8,
        max_features="sqrt",
        random_state=42,
    )
    base_clf.fit(X_train, y_train, sample_weight=sample_weight)
    clf_final = CalibratedClassifierCV(base_clf, method="isotonic", cv="prefit")
    clf_final.fit(X_train, y_train)

    print(f"[TRAIN] {nom} — GradientBoosting entraîné "
          f"({len(X_train)} exemples, {n_pos} positifs, ratio={ratio:.1f})")
    return clf_final, base_clf


def evaluer_kfold(X, y, nom: str, n_splits: int = 5) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold, cross_validate
    from sklearn.metrics import make_scorer, f1_score, roc_auc_score
    import numpy as np

    if y.sum() < n_splits:
        print(f"[EVAL] {nom} — pas assez de positifs pour KFold ({int(y.sum())})")
        return {}

    clf_cv = GradientBoostingClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        min_samples_leaf=10, subsample=0.8, max_features="sqrt", random_state=42,
    )
    skf = StratifiedKFold(n_splits=n_splits, shuffle=False)  # shuffle=False = respecte l'ordre temporel
    scoring = {
        "f1":      make_scorer(f1_score,      zero_division=0),
        "roc_auc": make_scorer(roc_auc_score, needs_proba=True),
    }
    cv_results = cross_validate(clf_cv, X, y, cv=skf, scoring=scoring, n_jobs=-1)

    f1_mean  = round(float(np.mean(cv_results["test_f1"])),      4)
    auc_mean = round(float(np.mean(cv_results["test_roc_auc"])), 4)
    print(f"[EVAL] {nom:12s} | KFold-{n_splits} F1={f1_mean:.3f} | AUC={auc_mean:.3f}")
    return {"kfold_f1": f1_mean, "kfold_auc": auc_mean}


def optimiser_seuil(clf, X_val, y_val, nom: str) -> float:
    import numpy as np
    from sklearn.metrics import f1_score

    probas = clf.predict_proba(X_val)[:, 1]
    seuils = np.linspace(0.1, 0.9, 81)
    meilleur_f1, meilleur_seuil = 0.0, 0.5

    for s in seuils:
        preds = (probas >= s).astype(int)
        f1 = f1_score(y_val, preds, zero_division=0)
        if f1 > meilleur_f1:
            meilleur_f1, meilleur_seuil = f1, s

    print(f"[SEUIL] {nom:12s} | seuil optimal = {meilleur_seuil:.2f} (F1={meilleur_f1:.3f})")
    return round(float(meilleur_seuil), 2)


def evaluer_final(clf, X_test, y_test, nom: str, seuil: float = 0.5) -> dict:
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score,
        f1_score, roc_auc_score, confusion_matrix,
    )

    y_prob = clf.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= seuil).astype(int)

    metriques = {
        "accuracy":  round(float(accuracy_score(y_test, y_pred)),                    4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)),  4),
        "recall":    round(float(recall_score(y_test, y_pred,    zero_division=0)),  4),
        "f1":        round(float(f1_score(y_test, y_pred,        zero_division=0)),  4),
        "auc_roc":   round(float(roc_auc_score(y_test, y_prob) if y_test.sum() > 0 else 0.5), 4),
        "seuil_decision": seuil,
    }
    cm = confusion_matrix(y_test, y_pred).tolist()
    print(f"[EVAL] {nom:12s} | Acc={metriques['accuracy']:.3f} "
          f"P={metriques['precision']:.3f} R={metriques['recall']:.3f} "
          f"F1={metriques['f1']:.3f} AUC={metriques['auc_roc']:.3f} "
          f"@seuil={seuil:.2f}")
    return {**metriques, "confusion_matrix": cm}


def importance_features(clf_base, features: list, nom: str) -> dict:
    try:
        importances = dict(zip(features,
            [round(float(v), 4) for v in clf_base.feature_importances_]))
        tri = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))
        top3 = ", ".join(f"{k}={v:.3f}" for k, v in list(tri.items())[:3])
        print(f"[FEAT] {nom} — Top 3 : {top3}")
        return tri
    except AttributeError:
        return {}


def afficher_resume(resultats_par_risque: dict, split_year: int):
    """Affiche un tableau récapitulatif lisible des performances."""
    print(f"\n{'='*65}")
    print(f"  RÉSUMÉ — Validation temporelle (test = données depuis {split_year})")
    print(f"{'='*65}")
    print(f"  {'Risque':<15} {'F1':>6} {'AUC':>6} {'Précision':>10} {'Rappel':>8} {'Seuil':>7}")
    print(f"  {'-'*55}")
    for nom, m in resultats_par_risque.items():
        mt = m.get("metriques_test", {})
        print(f"  {nom:<15} {mt.get('f1', 0):>6.3f} {mt.get('auc_roc', 0):>6.3f} "
              f"{mt.get('precision', 0):>10.3f} {mt.get('recall', 0):>8.3f} "
              f"{mt.get('seuil_decision', 0.5):>7.2f}")
    print(f"{'='*65}")
    print(f"  ✅ Modèles sauvegardés dans models/")
    print(f"     Lancez : python3 inference/pipeline_complet.py")
    print(f"{'='*65}\n")


def main():
    import pandas as pd
    import joblib

    parser = argparse.ArgumentParser(description="SAMCAM V4.2 — Entraînement modèles")
    parser.add_argument("--dataset",    type=str, default=DATASET_CSV)
    parser.add_argument("--force",      action="store_true")
    parser.add_argument("--split-year", type=int, default=SPLIT_YEAR_DEFAULT,
                        help=f"Année de coupure train/test (défaut: {SPLIT_YEAR_DEFAULT})")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"[TRAIN] Dataset introuvable : {args.dataset}")
        print("  Lancez : python3 inference/build_dataset.py --openmeteo")
        return

    df = charger_dataset(args.dataset)
    features = get_features_disponibles(list(df.columns))

    manquantes_base = [c for c in features + list(CIBLES.values()) if c not in df.columns]
    if manquantes_base:
        print(f"[TRAIN] Colonnes manquantes : {manquantes_base}")
        return

    # Tri par date (important pour split temporel)
    df = df.sort_values("date").reset_index(drop=True)

    # Vérification que split_year est dans les données
    annees_dispo = df["date"].dt.year.unique()
    if args.split_year not in annees_dispo:
        print(f"[TRAIN] Année de coupure {args.split_year} non trouvée dans le dataset.")
        print(f"        Années disponibles : {annees_dispo.min()} → {annees_dispo.max()}")
        return

    metadata = {
        "version":             "4.2",
        "date_entrainement":   datetime.datetime.now().isoformat(),
        "features":            features,
        "n_features":          len(features),
        "n_total":             len(df),
        "split_year":          args.split_year,
        "algorithme":          "GradientBoosting + CalibratedClassifierCV (isotonic) — validation temporelle",
        "modeles":             {},
    }

    resultats_resume = {}

    for nom, cible in CIBLES.items():
        chemin_pkl = os.path.join(MODELS_DIR, f"model_{nom}.pkl")

        if os.path.exists(chemin_pkl) and not args.force:
            print(f"[TRAIN] Modèle {nom} déjà présent (--force pour réentraîner)")
            continue

        y_all = df[cible]
        if y_all.sum() < 10:
            print(f"[TRAIN] Insuffisant positifs pour {nom} ({int(y_all.sum())}) — ignoré")
            continue

        print(f"\n{'='*60}")
        print(f"[TRAIN] === {nom.upper()} === ({int(y_all.sum())} positifs / {len(y_all)} total)")

        # ── V4.2 : Split TEMPOREL ────────────────────────────────────────────
        X_train, X_test, y_train, y_test = split_temporel(
            df, features, cible, args.split_year
        )

        if len(X_train) < 20 or len(X_test) < 5:
            print(f"[TRAIN] Pas assez de données pour le split temporel — ignoré")
            continue

        # Sous-set validation (derniers 20% du train)
        X_tr, X_val, y_tr, y_val = split_validation(X_train, y_train)

        # Évaluation KFold sur train (ordre temporel respecté)
        kfold_metriques = evaluer_kfold(X_train, y_train, nom)

        # Entraînement final
        clf_cal, clf_base = entrainer_classifieur(X_tr, y_tr, nom)

        # Optimisation seuil sur validation
        seuil_opt = optimiser_seuil(clf_cal, X_val, y_val, nom)

        # Évaluation sur test temporel
        metriques = evaluer_final(clf_cal, X_test, y_test, nom, seuil=seuil_opt)
        importances = importance_features(clf_base, features, nom)

        joblib.dump({"clf": clf_cal, "seuil": seuil_opt, "features": features},
                    chemin_pkl)
        print(f"[TRAIN] Sauvegardé : {chemin_pkl}")

        metadata["modeles"][nom] = {
            "fichier":           f"model_{nom}.pkl",
            "n_train":           len(X_train),
            "n_test":            len(X_test),
            "n_positifs_train":  int(y_train.sum()),
            "n_positifs_test":   int(y_test.sum()),
            "split_year":        args.split_year,
            "seuil_decision":    seuil_opt,
            "metriques_test":    metriques,
            "metriques_kfold":   kfold_metriques,
            "importances":       importances,
        }
        resultats_resume[nom] = metadata["modeles"][nom]

    with open(METADATA_JSON, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"\n[TRAIN] Métadonnées sauvegardées : {METADATA_JSON}")

    if resultats_resume:
        afficher_resume(resultats_resume, args.split_year)

    print("[TRAIN] ✅ Entraînement V4.2 terminé !")


if __name__ == "__main__":
    main()
