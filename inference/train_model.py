#!/usr/bin/env python3
"""
SAMCAM V4.1 — Entraînement du modèle de classification de risque

NOUVEAUTÉS V4.1 :
    - GradientBoostingClassifier à la place de RandomForest
      → meilleur sur données déséquilibrées et séries temporelles
    - Calibration isotonique des probabilités (CalibratedClassifierCV)
      → scores 0-1 vraiment interprétables comme des probabilités
    - StratifiedKFold 5-fold pour évaluation robuste
    - Seuil de décision optimisé par risque (maximise F1 sur val set)
    - Nouvelles features dérivées (16 au total vs 10 avant)
    - Rapport complet dans model_metadata.json

Usage :
    python3 inference/train_model.py
    python3 inference/train_model.py --dataset data/dataset_kribi_historical.csv
    python3 inference/train_model.py --force   # réentraîne même si modèles existants

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

# Features de base (présentes depuis V4)
FEATURES_BASE = [
    "mois", "pluie_7j", "pluie_30j", "pluie_prev_7j",
    "temp_max", "temp_max_3j", "sm_surface", "sm_rootzone",
    "ndvi", "ndwi",
]

# Features dérivées ajoutées en V4.1
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
    return df


def get_features_disponibles(df_columns: list) -> list:
    """Retourne la liste des features disponibles dans le dataset."""
    toutes = FEATURES_BASE + FEATURES_DERIVEES
    dispo  = [f for f in toutes if f in df_columns]
    manquantes = [f for f in FEATURES_DERIVEES if f not in df_columns]
    if manquantes:
        print(f"[TRAIN] Features dérivées absentes (dataset V4 ancien) : {manquantes}")
        print("        Relancez build_dataset.py --no-gee pour les générer.")
    print(f"[TRAIN] Features utilisées ({len(dispo)}) : {dispo}")
    return dispo


def entrainer_classifieur(X_train, y_train, nom: str):
    """
    GradientBoostingClassifier + calibration isotonique.
    - GB : meilleur que RF sur données déséquilibrées temporelles
    - Calibration : transforme les scores en vraies probabilités
    - sample_weight : compense le déséquilibre de classes
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    import numpy as np

    # Calcul du poids pour compenser le déséquilibre
    n_pos = int(y_train.sum())
    n_neg = len(y_train) - n_pos
    ratio = n_neg / max(1, n_pos)
    sample_weight = np.where(y_train == 1, ratio, 1.0)

    base_clf = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=4,           # moins profond = moins d'overfitting
        learning_rate=0.05,    # petit learning rate + plus d'arbres = meilleur
        min_samples_leaf=10,
        subsample=0.8,         # stochastic GB : résistant à l'overfitting
        max_features="sqrt",
        random_state=42,
    )

    # Calibration isotonique : les scores deviennent de vraies probabilités
    clf = CalibratedClassifierCV(base_clf, method="isotonic", cv=3)
    clf.fit(X_train, y_train, **{"sample_weight": sample_weight}
            if hasattr(clf, 'fit') else {})

    # CalibratedClassifierCV ne passe pas sample_weight directement
    # → entraîner le modèle de base seul d'abord, puis calibrer
    base_clf.fit(X_train, y_train, sample_weight=sample_weight)
    clf_final = CalibratedClassifierCV(base_clf, method="isotonic", cv="prefit")
    clf_final.fit(X_train, y_train)

    print(f"[TRAIN] {nom} — GradientBoosting entraîné "
          f"({len(X_train)} exemples, {n_pos} positifs, ratio={ratio:.1f})")
    return clf_final, base_clf


def evaluer_kfold(X, y, features: list, nom: str, n_splits: int = 5) -> dict:
    """Évaluation robuste par StratifiedKFold 5-fold."""
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
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
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
    """
    Trouve le seuil de décision optimal qui maximise le F1-score.
    Par défaut sklearn utilise 0.5, mais ce n'est pas toujours optimal
    avec des données déséquilibrées.
    """
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

    print(f"[SEUIL] {nom:12s} | seuil optimal = {meilleur_seuil:.2f} "
          f"(F1={meilleur_f1:.3f} vs 0.5)")
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
    print(f"         Confusion : {cm}")
    return {**metriques, "confusion_matrix": cm}


def importance_features(clf_base, features: list, nom: str) -> dict:
    """Importance des features depuis le GradientBoosting de base."""
    try:
        importances = dict(zip(features,
            [round(float(v), 4) for v in clf_base.feature_importances_]))
        tri = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))
        top3 = ", ".join(f"{k}={v:.3f}" for k, v in list(tri.items())[:3])
        print(f"[FEAT] {nom} — Top 3 : {top3}")
        return tri
    except AttributeError:
        return {}


def main():
    import pandas as pd
    import joblib
    import numpy as np
    from sklearn.model_selection import train_test_split

    parser = argparse.ArgumentParser(description="SAMCAM V4.1 — Entraînement modèles de risque")
    parser.add_argument("--dataset", type=str,        default=DATASET_CSV)
    parser.add_argument("--force",   action="store_true", help="Réentraîne même si modèles existants")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"[TRAIN] Dataset introuvable : {args.dataset}")
        print("  Lancez d'abord : python3 inference/build_dataset.py --no-gee")
        return

    df = charger_dataset(args.dataset)
    features = get_features_disponibles(list(df.columns))

    manquantes_base = [c for c in features + list(CIBLES.values()) if c not in df.columns]
    if manquantes_base:
        print(f"[TRAIN] Colonnes manquantes : {manquantes_base}")
        return

    X = df[features].fillna(df[features].median())

    metadata = {
        "version":             "4.1",
        "date_entrainement":   datetime.datetime.now().isoformat(),
        "features":            features,
        "n_features":          len(features),
        "n_total":             len(df),
        "algorithme":          "GradientBoosting + CalibratedClassifierCV (isotonic)",
        "modeles":             {},
    }

    for nom, cible in CIBLES.items():
        chemin_pkl = os.path.join(MODELS_DIR, f"model_{nom}.pkl")

        if os.path.exists(chemin_pkl) and not args.force:
            print(f"[TRAIN] Modèle {nom} déjà présent (--force pour réentraîner)")
            continue

        y = df[cible]
        if y.sum() < 10:
            print(f"[TRAIN] Insuffisant positifs pour {nom} ({int(y.sum())}) — ignoré")
            continue

        print(f"\n{'='*60}")
        print(f"[TRAIN] === {nom.upper()} === ({int(y.sum())} positifs / {len(y)} total)")

        # Split stratifié (80/20)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        # Sous-ensemble validation pour optimisation seuil
        X_tr, X_val, y_tr, y_val = train_test_split(
            X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
        )

        # Évaluation KFold (utilise tout X_train)
        kfold_metriques = evaluer_kfold(X_train, y_train, features, nom)

        # Entraînement final
        clf_cal, clf_base = entrainer_classifieur(X_tr, y_tr, nom)

        # Optimisation seuil sur validation
        seuil_opt = optimiser_seuil(clf_cal, X_val, y_val, nom)

        # Évaluation finale sur test
        metriques = evaluer_final(clf_cal, X_test, y_test, nom, seuil=seuil_opt)
        importances = importance_features(clf_base, features, nom)

        # Sauvegarde
        joblib.dump({"clf": clf_cal, "seuil": seuil_opt, "features": features},
                    chemin_pkl)
        print(f"[TRAIN] Sauvegardé : {chemin_pkl}")

        metadata["modeles"][nom] = {
            "fichier":           f"model_{nom}.pkl",
            "n_train":           len(X_train),
            "n_positifs_train":  int(y_train.sum()),
            "seuil_decision":    seuil_opt,
            "metriques_test":    metriques,
            "metriques_kfold":   kfold_metriques,
            "importances":       importances,
        }

    with open(METADATA_JSON, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"\n[TRAIN] Métadonnées sauvegardées : {METADATA_JSON}")
    print("[TRAIN] ✅ Entraînement V4.1 terminé !")
    print("        Lancez ensuite : python3 inference/pipeline_complet.py")


if __name__ == "__main__":
    main()
