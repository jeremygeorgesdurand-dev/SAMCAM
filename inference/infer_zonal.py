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

    Gère trois formats de bundle pour assurer la rétro-compatibilité :
      1. Objet sklearn brut (ancien format, pas un dict)
         → wrappé en dict avec clé 'model'
      2. Dict avec clé 'clf' (format legacy inference/train_model.py)
         → clé renommée en 'model'
      3. Dict avec clé 'model' (nouveau format training/train_zonal_models.py)
         → utilisé tel quel

    Retourne None si le fichier n'existe pas.
    """
    model_path = MODELS_DIR / f"model_{risk}_{zone}.pkl"
    if not model_path.exists():
        logger.warning(f"[{zone}/{risk}] Modèle introuvable : {model_path}")
        return None
    with open(model_path, "rb") as f:
        bundle = pickle.load(f)

    # Format 1 : objet sklearn brut (pas un dict)
    if not isinstance(bundle, dict):
        logger.debug(f"[{zone}/{risk}] Bundle format brut sklearn — wrapping")
        bundle = {
            "model":         bundle,
            "threshold":     0.5,
            "features_used": None,
            "metadata":      {},
        }
    # Format 2 : dict avec clé 'clf' (legacy train_model.py)
    elif "clf" in bundle and "model" not in bundle:
        logger.debug(f"[{zone}/{risk}] Bundle format legacy ('clf') — migration vers 'model'")
        bundle = {
            "model": bundle.get("clf") or bundle.get("model") or (
            bundle if hasattr(bundle, "predict_proba") else None
        ),

            "threshold":     float(bundle.get("threshold", 0.5)),
            "features_used": bundle.get("features", bundle.get("features_used", None)),
            "metadata":      bundle.get("metadata", bundle.get("metrics", {})),
            # conserve les autres clés au cas où
            **{k: v for k, v in bundle.items() if k not in ("clf", "threshold", "features", "features_used", "metadata", "metrics")},
        }
    # Format 3 : dict avec clé 'model' (nouveau format train_zonal_models.py) → OK tel quel

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
    features_used = bundle.get("features_used") or bundle.get("features")
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


def infer_zone_risk_series(zone: str, risk: str, days: int = 14) -> dict:
    """
    Comme infer_zone_risk(), mais retourne la série JOUR PAR JOUR (date, proba, niveau)
    sur les `days` derniers jours au lieu d'un seul agrégat (last/mean/max).

    Le modèle calcule déjà predict_proba() sur toute la fenêtre de `days` jours en
    interne (infer_zone_risk ne renvoie que last/mean/max) — cette fonction expose
    cette série complète, pour un historique qui reflète l'évolution réelle du risque
    jour après jour au lieu d'être figé sur la valeur du jour courant.
    """
    result = {"zone": zone, "risk": risk, "status": "OK", "serie": []}

    bundle = load_model(zone, risk)
    if bundle is None:
        return {**result, "status": "NO_MODEL",
                "error": f"model_{risk}_{zone}.pkl introuvable dans {MODELS_DIR}"}

    model         = bundle["model"]
    features_used = bundle.get("features_used") or bundle.get("features")

    df_raw = load_zone_data(zone, days=max(days + 90, 120))
    if df_raw is None or df_raw.empty:
        return {**result, "status": "NO_DATA",
                "error": f"Aucune donnée pour {zone} dans {DATA_DIR}"}

    df = compute_derived_features(df_raw)
    col_list = features_used if features_used else RISK_FEATURES[risk]
    cols = [f for f in col_list if f in df.columns]
    if len(cols) < 3:
        return {**result, "status": "INSUFFICIENT_FEATURES",
                "error": f"Seulement {len(cols)} features disponibles (min 3)"}

    fenetre = df.tail(days).copy()
    X = fenetre[cols].copy()
    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(df[col].median())

    try:
        probas = model.predict_proba(X)[:, 1]
    except Exception as e:
        return {**result, "status": "PREDICT_ERROR", "error": str(e)}

    serie = []
    for d, p in zip(fenetre["date"], probas):
        niveau, emoji = proba_to_level(float(p))
        serie.append({
            "date":   pd.Timestamp(d).date().isoformat(),
            "proba":  round(float(p), 4),
            "niveau": niveau,
            "emoji":  emoji,
        })

    return {**result, "serie": serie}


# ---------------------------------------------------------------------------
# Inférence à horizon (J+1/J+3/J+7) — utilise les VRAIES prévisions Open-Meteo
# ---------------------------------------------------------------------------
def _lignes_prevision(previsions_daily: dict, horizon_jours: int) -> pd.DataFrame:
    """
    Construit les lignes journalières futures (jusqu'à horizon_jours inclus) à partir
    du bloc previsions_daily d'Open-Meteo (meteorologie.previsions_daily du JSON de zone).
    Colonnes brutes seulement — les colonnes dérivées sont recalculées après concaténation
    avec l'historique, pour que rain_7d/rain_30d/spi3_approx etc. intègrent la prévision.
    """
    times = previsions_daily.get("time") or []
    n     = min(len(times), horizon_jours + 1)
    if n == 0:
        return pd.DataFrame()

    def serie(cle):
        vals = previsions_daily.get(cle) or []
        return vals[:n] if len(vals) >= n else [None] * n

    tmax = serie("temperature_2m_max")
    tmin = serie("temperature_2m_min")
    rows = {
        "date":                        pd.to_datetime(times[:n]),
        "temperature_2m_max":          tmax,
        "temperature_2m_min":          tmin,
        "temperature_2m_mean":         [
            (a + b) / 2 if a is not None and b is not None else None
            for a, b in zip(tmax, tmin)
        ],
        "precipitation_sum":           serie("precipitation_sum"),
        "et0_fao_evapotranspiration":  serie("et0_fao_evapotranspiration"),
        "wind_speed_10m_max":          serie("windspeed_10m_max"),
    }
    return pd.DataFrame(rows)


_COLONNES_TENDANCE = [
    "soil_moisture_0_to_7cm_mean", "soil_moisture_7_to_28cm_mean", "soil_moisture_28_to_100cm_mean",
]


def _extrapoler_tendance(df_hist: pd.DataFrame, col: str, n_jours_prev: int, fenetre: int = 14) -> list:
    """
    Extrapole la tendance linéaire récente (régression sur les `fenetre` derniers jours
    d'historique réel) sur n_jours_prev jours futurs, au lieu de figer la dernière valeur.

    Pourquoi : l'humidité du sol n'a pas de prévision Open-Meteo, donc sans ça elle reste
    identique à J+1 comme à J+14 — un modèle qui en dépend beaucoup (sécheresse) produit
    alors un score quasi figé sur tous les horizons, même quand le sol s'assèche/s'humidifie
    réellement de jour en jour (visible dans l'historique récent). L'extrapolation de
    tendance capte cette dynamique sans prétendre à une simulation physique précise.
    """
    serie = df_hist[col].dropna().tail(fenetre)
    if len(serie) < 5:
        derniere = df_hist[col].dropna()
        derniere = float(derniere.iloc[-1]) if not derniere.empty else None
        return [derniere] * n_jours_prev

    x = np.arange(len(serie))
    y = serie.to_numpy(dtype=float)
    pente, _ = np.polyfit(x, y, 1)
    derniere_val = float(y[-1])

    return [
        float(np.clip(derniere_val + pente * i, 0.0, 0.6))
        for i in range(1, n_jours_prev + 1)
    ]


def infer_zone_risk_horizon(
    zone: str,
    risk: str,
    previsions_daily: dict,
    horizon_jours: int,
    days: int = 30,
    verbose: bool = False,
) -> dict:
    """
    Comme infer_zone_risk(), mais pour un horizon futur (J+1/J+3/J+7) : prolonge la
    série historique avec les VRAIES prévisions météo Open-Meteo (previsions_daily),
    recalcule les features dérivées (rolling 7/14/30/90j, SPI, anomalies) sur la série
    étendue, puis prédit sur le jour cible (aujourd'hui + horizon_jours).

    Les colonnes sans équivalent dans la prévision (humidité sol, NASA POWER, humidité
    relative, rayonnement — pas de prévision disponible pour ces variables) sont
    maintenues à la dernière valeur observée (persistance), documentée explicitement
    plutôt que simulée par du bruit aléatoire.
    """
    result = {
        "zone": zone, "risk": risk, "horizon_jours": horizon_jours,
        "date_run": date.today().isoformat(), "status": "OK",
    }

    bundle = load_model(zone, risk)
    if bundle is None:
        return {**result, "status": "NO_MODEL",
                "error": f"model_{risk}_{zone}.pkl introuvable dans {MODELS_DIR}"}

    model         = bundle["model"]
    threshold     = float(bundle.get("threshold", 0.5))
    features_used = bundle.get("features_used") or bundle.get("features")
    meta          = bundle.get("metadata", {})
    metrics       = load_metrics(zone, risk)

    df_raw = load_zone_data(zone, days=max(days + 90, 120))
    if df_raw is None or df_raw.empty:
        return {**result, "status": "NO_DATA",
                "error": f"Aucune donnée pour {zone} dans {DATA_DIR}"}

    df_prev = _lignes_prevision(previsions_daily or {}, horizon_jours)
    if df_prev.empty:
        # Pas de prévision dispo → persistance pure (comportement identique à J0)
        return infer_zone_risk(zone, risk, days=days, verbose=verbose)

    df_ext = pd.concat([df_raw, df_prev], ignore_index=True)
    df_ext = df_ext.sort_values("date").drop_duplicates(subset="date", keep="last").reset_index(drop=True)

    # Humidité du sol : extrapolation de tendance (voir _extrapoler_tendance) plutôt
    # que persistance figée, pour qu'elle évolue réellement d'un horizon à l'autre.
    prev_dates = set(df_prev["date"])
    idx_prev = df_ext.index[df_ext["date"].isin(prev_dates)].sort_values()
    for col in _COLONNES_TENDANCE:
        if col not in df_raw.columns:
            continue
        valeurs = _extrapoler_tendance(df_raw, col, len(idx_prev))
        for pos, idx in enumerate(idx_prev):
            df_ext.loc[idx, col] = valeurs[pos]

    # Persistance (dernière valeur connue) pour le reste des variables sans prévision
    # (NASA POWER, humidité relative, rayonnement — pas de tendance de court terme fiable).
    autres_cols = [c for c in df_ext.columns
                   if c not in df_prev.columns and c != "date" and c not in _COLONNES_TENDANCE]
    df_ext[autres_cols] = df_ext[autres_cols].ffill()

    df = compute_derived_features(df_ext)

    col_list = features_used if features_used else RISK_FEATURES[risk]
    cols = [f for f in col_list if f in df.columns]
    if len(cols) < 3:
        return {**result, "status": "INSUFFICIENT_FEATURES",
                "error": f"Seulement {len(cols)} features disponibles (min 3)"}

    # Ligne cible = aujourd'hui + horizon_jours (dernière ligne de la prévision ajoutée)
    date_cible = df_prev["date"].max()
    ligne = df[df["date"] == date_cible]
    if ligne.empty:
        return {**result, "status": "NO_DATA",
                "error": f"Jour cible {date_cible.date()} absent après fusion prévision"}

    X = ligne[cols].copy()
    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(df[col].median())

    try:
        proba = float(model.predict_proba(X)[:, 1][0])
    except Exception as e:
        return {**result, "status": "PREDICT_ERROR", "error": str(e)}

    level, emoji = proba_to_level(proba)

    if verbose:
        logger.info(
            f"  [{zone}/{risk}] J+{horizon_jours} {emoji} {level:<9} "
            f"proba={proba:.3f} (thr={threshold:.2f}, cible={date_cible.date()})"
        )

    result.update({
        "proba":         round(proba, 4),
        "level":         level,
        "emoji":         emoji,
        "date_cible":    date_cible.date().isoformat(),
        "features_used": cols,
        "n_features":    len(cols),
        "threshold":     threshold,
        "model_type":    meta.get("model", "Unknown"),
        "cv_auc":        metrics.get("cv_auc_mean", None),
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
