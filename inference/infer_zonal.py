#!/usr/bin/env python3
"""
infer_zonal.py — Inférence temps-réel des modèles zonaux SAMCAM.

Charge les modèles .pkl produits par training/train_zonal_models.py
et applique chaque modèle sur les données les plus récentes de la zone
pour produire un score de risque (probabilité 0-1) + niveau (FAIBLE/MODÉRÉ/ÉLEVÉ/CRITIQUE).

Usage :
    python inference/infer_zonal.py                          # toutes les zones, tous les risques
    python inference/infer_zonal.py --zone Kribi             # une seule zone
    python inference/infer_zonal.py --zone Ebolowa --risk inondation
    python inference/infer_zonal.py --days 7                 # utiliser les 7 derniers jours
    python inference/infer_zonal.py --output json            # sortie JSON (défaut: pretty)
    python inference/infer_zonal.py --save                   # sauvegarder dans data/predictions/

Sorties :
    - Console : tableau lisible par zone/risque
    - Optionnel : data/predictions/predictions_YYYY-MM-DD.json
"""

import json
import pickle
import argparse
import logging
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Chemins (relatifs à la racine du projet)
# ---------------------------------------------------------------------------
ROOT        = Path(__file__).resolve().parent.parent
DATA_DIR    = ROOT / "data" / "historical"
MODELS_DIR  = ROOT / "models" / "zonal"
METRICS_DIR = ROOT / "models" / "zonal" / "metrics"
PRED_DIR    = ROOT / "data" / "predictions"
PRED_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zones et risques (miroir de train_zonal_models.py)
# ---------------------------------------------------------------------------
RISKS = ["inondation", "secheresse", "chaleur"]

ZONES = [
    "Kribi", "Ebolowa", "Kumba", "Bafoussam",
    "Yaounde_peri", "Ngaoundere", "Garoua", "Maroua",
]

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
# Niveaux de risque
# ---------------------------------------------------------------------------
RISK_LEVELS = [
    (0.70, "CRITIQUE",  "🔴"),
    (0.45, "ÉLEVÉ",     "🟠"),
    (0.25, "MODÉRÉ",    "🟡"),
    (0.00, "FAIBLE",    "🟢"),
]


def proba_to_level(proba: float) -> tuple:
    """Convertit une probabilité en niveau textuel et emoji."""
    for threshold, label, emoji in RISK_LEVELS:
        if proba >= threshold:
            return label, emoji
    return "FAIBLE", "🟢"


# ---------------------------------------------------------------------------
# Chargement du modèle
# ---------------------------------------------------------------------------
def load_model(zone: str, risk: str):
    """
    Charge le bundle {model, threshold, features_used, metadata} depuis le .pkl.
    Compatible ancien format (modèle seul) et nouveau format (dict).
    Retourne None si le fichier n'existe pas.
    """
    model_path = MODELS_DIR / f"model_{risk}_{zone}.pkl"
    if not model_path.exists():
        logger.warning(f"[{zone}/{risk}] Modèle introuvable : {model_path}")
        return None
    with open(model_path, "rb") as f:
        bundle = pickle.load(f)
    if not isinstance(bundle, dict):
        logger.debug(f"[{zone}/{risk}] Bundle ancien format — wrapping")
        bundle = {"model": bundle, "threshold": 0.5, "features_used": None, "metadata": {}}
    return bundle


def load_metrics(zone: str, risk: str) -> dict:
    """Charge les métriques JSON associées au modèle."""
    metrics_path = METRICS_DIR / f"metrics_{risk}_{zone}.json"
    if not metrics_path.exists():
        return {}
    with open(metrics_path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Chargement des données
# ---------------------------------------------------------------------------
def load_zone_data(zone: str, days: int = 30):
    """
    Cherche le CSV/Parquet historique de la zone dans DATA_DIR.
    Retourne les `days` dernières lignes triées par date.
    """
    candidates = [
        DATA_DIR / f"{zone}.csv",
        DATA_DIR / f"{zone}_historical.csv",
        DATA_DIR / f"{zone.lower()}.csv",
        DATA_DIR / f"{zone.lower()}_historical.csv",
    ]
    candidates += list(DATA_DIR.glob(f"{zone}*.parquet"))
    candidates += list(DATA_DIR.glob(f"{zone.lower()}*.parquet"))

    df = None
    for path in candidates:
        if path.exists():
            logger.debug(f"[{zone}] Lecture {path.name}")
            df = (
                pd.read_parquet(path)
                if str(path).endswith(".parquet")
                else pd.read_csv(path, parse_dates=True, low_memory=False)
            )
            break

    if df is None:
        logger.warning(f"[{zone}] Aucun fichier trouvé dans {DATA_DIR}")
        return None

    date_col = next(
        (c for c in ["date", "Date", "DATE", "time", "Time"] if c in df.columns), None
    )
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.sort_values(date_col).dropna(subset=[date_col])

    return df.tail(days).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Features dérivées (calculées si absentes du CSV)
# ---------------------------------------------------------------------------
def compute_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule les colonnes dérivées manquantes à partir de precipitation_sum
    et temperature_2m_mean. N'écrase pas les colonnes déjà présentes.
    """
    df = df.copy()

    if "precipitation_sum" in df.columns:
        rain = df["precipitation_sum"].fillna(0)
        if "rain_7d"     not in df.columns: df["rain_7d"]     = rain.rolling(7,  min_periods=1).sum()
        if "rain_14d"    not in df.columns: df["rain_14d"]    = rain.rolling(14, min_periods=1).sum()
        if "rain_30d"    not in df.columns: df["rain_30d"]    = rain.rolling(30, min_periods=1).sum()
        if "rain_90d"    not in df.columns: df["rain_90d"]    = rain.rolling(90, min_periods=1).sum()
        if "spi3_approx" not in df.columns:
            mu  = rain.rolling(90, min_periods=30).mean()
            std = rain.rolling(90, min_periods=30).std().replace(0, np.nan)
            df["spi3_approx"] = ((rain - mu) / std).clip(-3, 3).fillna(0)

    if "temperature_2m_mean" in df.columns:
        temp = df["temperature_2m_mean"]
        if "temp_anom_30d" not in df.columns:
            df["temp_anom_30d"] = (temp - temp.rolling(30, min_periods=10).mean()).fillna(0)
        if "temp_max_7d" not in df.columns:
            tmax = df.get("temperature_2m_max", temp)
            df["temp_max_7d"] = tmax.rolling(7, min_periods=1).max()

    date_col = next(
        (c for c in ["date", "Date", "time"] if c in df.columns), None
    )
    if date_col:
        dt = pd.to_datetime(df[date_col], errors="coerce")
        if "month"       not in df.columns: df["month"]       = dt.dt.month
        if "day_of_year" not in df.columns: df["day_of_year"] = dt.dt.dayofyear
        if "week"        not in df.columns: df["week"]        = dt.dt.isocalendar().week.astype(int)

    return df


# ---------------------------------------------------------------------------
# Inférence pour une zone + un risque
# ---------------------------------------------------------------------------
def infer_zone_risk(
    zone: str,
    risk: str,
    days: int = 30,
    verbose: bool = False,
) -> dict:
    """
    Retourne un dict de résultat pour (zone, risk) avec :
      proba_last, proba_mean, proba_max, level, emoji,
      n_days_used, features_used, threshold, model_type, cv_auc
    """
    result = {
        "zone":     zone,
        "risk":     risk,
        "date_run": date.today().isoformat(),
        "status":   "OK",
    }

    # 1. Modèle
    bundle = load_model(zone, risk)
    if bundle is None:
        return {**result, "status": "NO_MODEL",
                "error": f"model_{risk}_{zone}.pkl introuvable dans {MODELS_DIR}"}

    model         = bundle["model"]
    threshold     = float(bundle.get("threshold", 0.5))
    features_used = bundle.get("features_used", None)
    meta          = bundle.get("metadata", {})
    metrics       = load_metrics(zone, risk)

    # 2. Données — charger +90j pour alimenter les rollings
    df_raw = load_zone_data(zone, days=max(days + 90, 120))
    if df_raw is None or df_raw.empty:
        return {**result, "status": "NO_DATA",
                "error": f"Aucune donnée pour {zone} dans {DATA_DIR}"}

    # 3. Features dérivées
    df = compute_derived_features(df_raw)

    # 4. Sélection des colonnes dans l'ordre d'entraînement
    col_list = features_used if features_used else RISK_FEATURES[risk]
    cols = [f for f in col_list if f in df.columns]

    if verbose and features_used:
        missing = [f for f in features_used if f not in df.columns]
        if missing:
            logger.warning(f"[{zone}/{risk}] {len(missing)} features manquantes: {missing[:5]}")

    if len(cols) < 3:
        return {**result, "status": "INSUFFICIENT_FEATURES",
                "error": f"Seulement {len(cols)} features disponibles (min 3)"}

    # 5. Fenêtre d'inférence = `days` derniers jours
    X = df.tail(days)[cols].copy()
    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(df[col].median())

    # 6. Prédiction
    try:
        probas = model.predict_proba(X)[:, 1]
    except Exception as e:
        return {**result, "status": "PREDICT_ERROR", "error": str(e)}

    proba_last = float(probas[-1])
    proba_mean = float(np.mean(probas))
    proba_max  = float(np.max(probas))

    # Score de référence conservateur = max(last, mean)
    score_ref = max(proba_last, proba_mean)
    level, emoji = proba_to_level(score_ref)

    if verbose:
        logger.info(
            f"  [{zone}/{risk}] {emoji} {level:<9} "
            f"last={proba_last:.3f} mean={proba_mean:.3f} max={proba_max:.3f} "
            f"(thr={threshold:.2f}, {len(cols)} features, {len(X)} jours)"
        )

    result.update({
        "proba_last":    round(proba_last, 4),
        "proba_mean":    round(proba_mean, 4),
        "proba_max":     round(proba_max,  4),
        "level":         level,
        "emoji":         emoji,
        "n_days_used":   len(X),
        "features_used": cols,
        "n_features":    len(cols),
        "threshold":     threshold,
        "model_type":    meta.get("model", "Unknown"),
        "cv_auc":        metrics.get("cv_auc_mean", None),
        "cv_auc_std":    metrics.get("cv_auc_std",  None),
    })
    return result


# ---------------------------------------------------------------------------
# Inférence batch
# ---------------------------------------------------------------------------
def run_inference(
    zones: list,
    risks: list,
    days: int = 30,
    verbose: bool = False,
) -> list:
    """Lance l'inférence sur toutes les combinaisons zone × risque."""
    results = []
    for zone in zones:
        for risk in risks:
            results.append(infer_zone_risk(zone, risk, days=days, verbose=verbose))
    return results


# ---------------------------------------------------------------------------
# Affichage terminal
# ---------------------------------------------------------------------------
def print_results_table(results: list):
    """Affiche un tableau lisible avec niveaux colorés par emoji."""
    print()
    print(
        f"{'Zone':<18} {'Risque':<12} {'Niveau':<11} "
        f"{'Proba(j0)':>10} {'Moy':>7} {'Max':>7} {'AUC':>7}  Statut"
    )
    print("-" * 88)
    for r in results:
        if r["status"] != "OK":
            print(
                f"{r['zone']:<18} {r['risk']:<12} {'—':<11} "
                f"{'—':>10} {'—':>7} {'—':>7} {'—':>7}  ⚠️  {r.get('error', '?')}"
            )
            continue
        auc_str = f"{r['cv_auc']:.3f}" if r.get("cv_auc") else "—"
        print(
            f"{r['zone']:<18} {r['risk']:<12} "
            f"{r['emoji']} {r['level']:<8} "
            f"{r['proba_last']:>10.3f} "
            f"{r['proba_mean']:>7.3f} "
            f"{r['proba_max']:>7.3f} "
            f"{auc_str:>7}"
        )
    print()


def save_results(results: list, output_dir: Path = PRED_DIR) -> Path:
    """Sauvegarde les résultats en JSON horodaté dans data/predictions/."""
    today    = date.today().isoformat()
    out_path = output_dir / f"predictions_{today}.json"
    payload  = {
        "date_run":    today,
        "n_results":   len(results),
        "predictions": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Résultats sauvegardés → {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Inférence temps-réel des modèles zonaux SAMCAM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--zone", type=str, default=None,
        help="Nom de la zone (ex: Kribi). Défaut: toutes."
    )
    parser.add_argument(
        "--risk", type=str, default=None, choices=RISKS,
        help="Risque cible. Défaut: tous."
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Nombre de jours récents à utiliser (défaut: 30)."
    )
    parser.add_argument(
        "--output", type=str, default="pretty", choices=["pretty", "json"],
        help="Format de sortie (défaut: pretty)."
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Sauvegarder les résultats dans data/predictions/."
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Logs détaillés par fold."
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    zones = [args.zone] if args.zone else ZONES
    risks = [args.risk] if args.risk else RISKS

    logger.info(
        f"Inférence SAMCAM — {len(zones)} zone(s) × {len(risks)} risque(s), {args.days} jours"
    )

    results = run_inference(zones, risks, days=args.days, verbose=args.verbose)

    ok  = sum(1 for r in results if r["status"] == "OK")
    err = len(results) - ok
    logger.info(f"Terminé : {ok} succès, {err} erreurs sur {len(results)} inférences")

    if args.output == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_results_table(results)

    if args.save:
        save_results(results)

    return results


if __name__ == "__main__":
    main()
