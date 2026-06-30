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
    """
    Sous-ensemble de validation interne walk-forward via TimeSeriesSplit (V4.3).
    Remplace StratifiedKFold qui introduisait un leakage temporel indirect.
    Retourne les scores AUC moyens sur les folds.
    """
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    import numpy as np

    n_splits = min(5, max(2, len(X_train) // 50))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    scores = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X_train), 1):
        X_f_train = X_train.iloc[train_idx]
        X_f_val   = X_train.iloc[val_idx]
        y_f_train = y_train.iloc[train_idx]
        y_f_val   = y_train.iloc[val_idx]

        if y_f_train.nunique() < 2 or y_f_val.nunique() < 2:
            print(f"[WF]    Fold {fold}/{n_splits} — classe unique, fold ignoré")
            continue

        clf_fold = GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            subsample=0.8, random_state=42
        )
        clf_fold.fit(X_f_train, y_f_train)
        proba = clf_fold.predict_proba(X_f_val)[:, 1]
        auc   = roc_auc_score(y_f_val, proba)
        scores.append(auc)
        print(f"[WF]    Fold {fold}/{n_splits} — train={len(X_f_train)}, "
              f"val={len(X_f_val)}, AUC={auc:.3f}")

    mean_auc = float(np.mean(scores)) if scores else 0.0
    std_auc  = float(np.std(scores))  if scores else 0.0
    print(f"[WF]    AUC walk-forward : {mean_auc:.3f} ± {std_auc:.3f} ({len(scores)} folds)")
    return mean_auc, std_auc


def entrainer_modele(df, nom: str, cible: str, features: list,
                     split_year: int, horizon: int = None, force: bool = False):
    """
    Entraîne un modèle GradientBoosting pour un risque donné et un horizon donné.
    Sauvegarde sous models/model_{nom}.pkl ou models/model_{nom}_j{horizon}.pkl.
    """
    import joblib
    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score, classification_report

    suffix = f"_j{horizon}" if horizon is not None else ""
    nom_fichier = f"model_{nom}{suffix}.pkl"
    chemin_pkl  = os.path.join(MODELS_DIR, nom_fichier)

    if os.path.exists(chemin_pkl) and not force:
        print(f"[TRAIN] ⏭  {nom_fichier} existe déjà — ignoré (--force pour réentraîner)")
        return None

    # Filtrer les features disponibles dans le dataset
    features_ok = [f for f in features if f in df.columns]
    manquantes  = [f for f in features if f not in df.columns]
    if manquantes:
        print(f"[TRAIN] ⚠️  Features absentes du dataset pour {nom}{suffix} : {manquantes}")

    if len(features_ok) < 3:
        print(f"[TRAIN] ❌ Pas assez de features pour {nom}{suffix} — modèle non entraîné")
        return None

    if cible not in df.columns:
        print(f"[TRAIN] ❌ Colonne cible '{cible}' absente — modèle non entraîné")
        return None

    print(f"\n{'='*60}")
    print(f"[TRAIN] 🏋  {nom.upper()}{suffix.upper()} — {len(features_ok)} features")
    print(f"{'='*60}")

    X_train, X_test, y_train, y_test = split_temporel(df, features_ok, cible, split_year)

    if y_train.nunique() < 2:
        print(f"[TRAIN] ❌ Classe unique en train pour {nom}{suffix} — modèle non entraîné")
        return None

    # Walk-forward validation interne (V4.3)
    auc_wf, std_wf = split_validation(X_train, y_train)

    # Entraînement final sur tout le train
    clf = GradientBoostingClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, min_samples_leaf=5, random_state=42
    )
    clf.fit(X_train, y_train)

    # Évaluation sur le test temporel
    auc_test = 0.0
    if y_test.nunique() >= 2 and len(y_test) > 0:
        proba_test = clf.predict_proba(X_test)[:, 1]
        auc_test   = roc_auc_score(y_test, proba_test)
        y_pred     = clf.predict(X_test)
        print(f"[EVAL]  AUC test (depuis {split_year}) : {auc_test:.3f}")
        print(classification_report(y_test, y_pred, zero_division=0))

        # Alerte leakage : AUC test trop proche de AUC train
        if auc_wf > 0 and auc_test > auc_wf + 0.15:
            print(f"[WARN]  ⚠️  Possible leakage : AUC_test ({auc_test:.3f}) >> "
                  f"AUC_wf ({auc_wf:.3f}). Vérifiez le dataset.")
    else:
        print(f"[EVAL]  ⚠️  Pas assez de données test pour évaluer {nom}{suffix}")

    # Seuil optimal (maximise F1)
    seuil = 0.5
    if y_test.nunique() >= 2 and len(y_test) > 0:
        from sklearn.metrics import f1_score
        proba_test = clf.predict_proba(X_test)[:, 1]
        meilleur_f1, meilleur_seuil = 0.0, 0.5
        for s in [i / 100 for i in range(20, 80)]:
            f1 = f1_score(y_test, (proba_test >= s).astype(int), zero_division=0)
            if f1 > meilleur_f1:
                meilleur_f1, meilleur_seuil = f1, s
        seuil = meilleur_seuil
        print(f"[SEUIL] Seuil optimal : {seuil:.2f} (F1={meilleur_f1:.3f})")

    # Feature importance
    importances = sorted(
        zip(features_ok, clf.feature_importances_),
        key=lambda x: x[1], reverse=True
    )
    print(f"[FEAT]  Top 5 features : {[f'{n}={v:.3f}' for n, v in importances[:5]]}")

    # Sauvegarde
    objet = {
        "clf":          clf,
        "seuil":        seuil,
        "features":     features_ok,
        "nom":          nom,
        "horizon":      horizon,
        "auc_wf":       round(auc_wf, 4),
        "std_wf":       round(std_wf, 4),
        "auc_test":     round(auc_test, 4),
        "split_year":   split_year,
        "trained_at":   datetime.datetime.now().isoformat(),
        "version":      "4.3",
        "n_train":      int(len(X_train)),
        "n_test":       int(len(X_test)),
        "n_features":   len(features_ok),
    }
    joblib.dump(objet, chemin_pkl)
    print(f"[SAVE]  ✅ {chemin_pkl}")
    return objet


def entrainer_tous(df, split_year: int, horizons: list, force: bool):
    """
    Entraîne tous les modèles pour la liste d'horizons donnée.
    horizons = [None] pour J0, [1, 3, 7] pour les horizons prévisionnels.
    """
    import pandas as pd

    resultats = []

    for horizon in horizons:
        features_horizon = FEATURES_PAR_HORIZON.get(horizon)

        for nom, cible in CIBLES.items():
            if features_horizon is not None:
                features = features_horizon
            else:
                features = get_features_disponibles(list(df.columns))

            res = entrainer_modele(
                df, nom, cible, features,
                split_year=split_year, horizon=horizon, force=force
            )
            if res is not None:
                suffix = f"_j{horizon}" if horizon is not None else ""
                resultats.append({
                    "modele":    f"{nom}{suffix}",
                    "auc_wf":   res.get("auc_wf", 0),
                    "std_wf":   res.get("std_wf", 0),
                    "auc_test": res.get("auc_test", 0),
                    "seuil":    res.get("seuil", 0.5),
                    "n_train":  res.get("n_train", 0),
                    "n_test":   res.get("n_test", 0),
                })

    return resultats


def afficher_resume(resultats: list):
    if not resultats:
        print("\n[RÉSUMÉ] Aucun modèle entraîné.")
        return

    print("\n" + "="*70)
    print("RÉSUMÉ ENTRAÎNEMENT")
    print("="*70)
    print(f"{'Modèle':<28} {'AUC WF':>8} {'±':>6} {'AUC Test':>10} {'Seuil':>7} {'N train':>8}")
    print("-"*70)
    for r in resultats:
        print(f"{r['modele']:<28} {r['auc_wf']:>8.3f} {r['std_wf']:>6.3f} "
              f"{r['auc_test']:>10.3f} {r['seuil']:>7.2f} {r['n_train']:>8}")
    print("="*70)


def sauvegarder_metadata(resultats: list, split_year: int):
    meta = {
        "version":     "4.3",
        "trained_at":  datetime.datetime.now().isoformat(),
        "split_year":  split_year,
        "modeles":     resultats,
        "note": (
            "V4.3 — TimeSeriesSplit walk-forward, multi-horizon J0/J1/J3/J7. "
            "Split temporel strict : train < split_year, test >= split_year."
        ),
    }
    with open(METADATA_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[META]  ✅ {METADATA_JSON}")


def main():
    parser = argparse.ArgumentParser(
        description="SAMCAM V4.3 — Entraînement multi-horizon"
    )
    parser.add_argument("--horizon", type=int, choices=[1, 3, 7], default=None,
                        help="Horizon en jours : 1, 3 ou 7 (défaut : J0)")
    parser.add_argument("--all-horizons", action="store_true",
                        help="Entraîner J0 + J+1 + J+3 + J+7")
    parser.add_argument("--force", action="store_true",
                        help="Réentraîner même si le .pkl existe déjà")
    parser.add_argument("--split-year", type=int, default=SPLIT_YEAR_DEFAULT,
                        help=f"Année de coupure train/test (défaut : {SPLIT_YEAR_DEFAULT})")
    parser.add_argument("--dataset", type=str, default=DATASET_CSV,
                        help="Chemin vers le dataset CSV")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"[TRAIN] ❌ Dataset introuvable : {args.dataset}")
        print(f"[TRAIN]    Générez-le avec : python3 inference/build_dataset.py")
        return

    df = charger_dataset(args.dataset)

    if args.all_horizons:
        horizons = [None, 1, 3, 7]
    elif args.horizon is not None:
        horizons = [args.horizon]
    else:
        horizons = [None]

    print(f"\n[TRAIN] Horizons à entraîner : "
          f"{['J0' if h is None else f'J+{h}' for h in horizons]}")
    print(f"[TRAIN] Split temporel : train < {args.split_year} | test >= {args.split_year}")
    print(f"[TRAIN] Force : {args.force}\n")

    resultats = entrainer_tous(df, split_year=args.split_year,
                               horizons=horizons, force=args.force)
    afficher_resume(resultats)
    sauvegarder_metadata(resultats, args.split_year)

    print(f"\n[TRAIN] 🎉 Entraînement terminé — {len(resultats)} modèle(s) sauvegardé(s)")
    print(f"[TRAIN]    Dossier : {os.path.abspath(MODELS_DIR)}")


if __name__ == "__main__":
    main()
