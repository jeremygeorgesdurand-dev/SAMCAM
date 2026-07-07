#!/usr/bin/env python3
"""
collect_historical.py — Collecte des données historiques 2015-2025 pour toutes les zones SAMCAM.

Sources :
  - Open-Meteo Historical Weather API (météo journalière)
  - NASA POWER API (rayonnement, température, humidité)

Sortie : data/historical/<zone>_historical.csv

Usage :
  python collect_historical.py                     # toutes les zones, 2015-2025
  python collect_historical.py --zone Kribi        # zone spécifique
  python collect_historical.py --start 2010-01-01  # depuis 2010
"""

import os
import time
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Configuration des zones SAMCAM
# ---------------------------------------------------------------------------
ZONES = {
    "Kribi": {"lat": 2.9399, "lon": 9.9098, "climate": "equatorial"},
    "Ebolowa": {"lat": 2.9000, "lon": 11.1500, "climate": "equatorial"},
    "Kumba": {"lat": 4.6364, "lon": 9.4469, "climate": "equatorial"},
    "Bafoussam": {"lat": 5.4765, "lon": 10.4178, "climate": "tropical_highland"},
    "Yaounde_peri": {"lat": 3.8480, "lon": 11.5021, "climate": "equatorial"},
    "Ngaoundere": {"lat": 7.3220, "lon": 13.5840, "climate": "tropical_highland"},
    "Garoua": {"lat": 9.3000, "lon": 13.3900, "climate": "sahelian"},
    "Maroua": {"lat": 10.5910, "lon": 14.3159, "climate": "sahelian"},
}

# Dates par défaut : 11 ans d'historique
DEFAULT_START = "2015-01-01"
DEFAULT_END = "2025-12-31"

OUTPUT_DIR = Path("data/historical")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("data/historical/collect_historical.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Open-Meteo Historical
# ---------------------------------------------------------------------------
def collect_openmeteo_historical(zone_name: str, lat: float, lon: float,
                                  start: str, end: str) -> pd.DataFrame:
    """Collecte météo journalière via Open-Meteo Historical Weather API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "precipitation_sum",
            "rain_sum",
            "et0_fao_evapotranspiration",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "shortwave_radiation_sum",
            "relative_humidity_2m_max",
            "relative_humidity_2m_min",
            "soil_moisture_0_to_7cm_mean",
            "soil_moisture_7_to_28cm_mean",
            "soil_moisture_28_to_100cm_mean",
            "precipitation_hours",
            "sunshine_duration",
        ],
        "timezone": "Africa/Douala",
    }

    logger.info(f"[Open-Meteo] {zone_name} {start} → {end}")
    try:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        if not daily or "time" not in daily:
            logger.warning(f"[Open-Meteo] Pas de données pour {zone_name}")
            return pd.DataFrame()
        df = pd.DataFrame(daily)
        df.rename(columns={"time": "date"}, inplace=True)
        df["date"] = pd.to_datetime(df["date"])
        df["zone"] = zone_name
        df["source_meteo"] = "open-meteo"
        logger.info(f"[Open-Meteo] {zone_name} : {len(df)} jours collectés")
        return df
    except Exception as e:
        logger.error(f"[Open-Meteo] Erreur {zone_name}: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# NASA POWER Historical
# ---------------------------------------------------------------------------
def collect_nasa_power_historical(zone_name: str, lat: float, lon: float,
                                   start: str, end: str) -> pd.DataFrame:
    """Collecte rayonnement, humidité, température via NASA POWER."""
    # NASA POWER accepte les dates au format YYYYMMDD
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")

    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,T2M,T2M_MAX,T2M_MIN,RH2M,PRECTOTCORR,WS10M,EVLAND,GWETROOT,GWETTOP",
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start_fmt,
        "end": end_fmt,
        "format": "JSON",
    }

    logger.info(f"[NASA POWER] {zone_name} {start} → {end}")
    try:
        resp = requests.get(url, params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        props = data.get("properties", {}).get("parameter", {})
        if not props:
            logger.warning(f"[NASA POWER] Pas de données pour {zone_name}")
            return pd.DataFrame()

        # Reconstruction DataFrame depuis le dict {PARAM: {YYYYMMDD: val}}
        dates = list(list(props.values())[0].keys())
        df = pd.DataFrame({"date_str": dates})
        for param, values in props.items():
            df[f"nasa_{param.lower()}"] = [values.get(d, np.nan) for d in dates]

        # Remplacer les valeurs manquantes codées -999
        df.replace(-999.0, np.nan, inplace=True)
        df["date"] = pd.to_datetime(df["date_str"], format="%Y%m%d")
        df.drop(columns=["date_str"], inplace=True)
        df["zone"] = zone_name
        logger.info(f"[NASA POWER] {zone_name} : {len(df)} jours collectés")
        return df
    except Exception as e:
        logger.error(f"[NASA POWER] Erreur {zone_name}: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Fusion et enrichissement
# ---------------------------------------------------------------------------
def merge_and_enrich(df_meteo: pd.DataFrame, df_nasa: pd.DataFrame,
                     zone_name: str, climate: str) -> pd.DataFrame:
    """Fusionne Open-Meteo et NASA POWER, ajoute des features dérivées."""
    if df_meteo.empty and df_nasa.empty:
        return pd.DataFrame()

    if df_meteo.empty:
        df = df_nasa.copy()
    elif df_nasa.empty:
        df = df_meteo.copy()
    else:
        df = pd.merge(df_meteo, df_nasa, on=["date", "zone"], how="outer", suffixes=("", "_nasa"))

    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # --- Features dérivées temporelles ---
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["day_of_year"] = df["date"].dt.dayofyear
    df["week"] = df["date"].dt.isocalendar().week.astype(int)

    # --- Cumuls glissants précipitations ---
    rain_col = "precipitation_sum" if "precipitation_sum" in df.columns else "nasa_prectotcorr"
    if rain_col in df.columns:
        df["rain_7d"] = df[rain_col].rolling(7, min_periods=1).sum()
        df["rain_14d"] = df[rain_col].rolling(14, min_periods=1).sum()
        df["rain_30d"] = df[rain_col].rolling(30, min_periods=1).sum()
        df["rain_90d"] = df[rain_col].rolling(90, min_periods=1).sum()

        # SPI-3 simplifié (Z-score glissant 90j)
        mean_90 = df["rain_90d"].expanding(min_periods=30).mean()
        std_90 = df["rain_90d"].expanding(min_periods=30).std().replace(0, np.nan)
        df["spi3_approx"] = (df["rain_90d"] - mean_90) / std_90

    # --- Anomalie température (vs moyenne mobile 30j) ---
    temp_col = "temperature_2m_mean" if "temperature_2m_mean" in df.columns else "nasa_t2m"
    if temp_col in df.columns:
        df["temp_anom_30d"] = df[temp_col] - df[temp_col].rolling(30, min_periods=7).mean()
        df["temp_max_7d"] = df[temp_col].rolling(7, min_periods=1).max()

    # --- Métadonnées zone ---
    df["climate_zone"] = climate

    logger.info(f"[Merge] {zone_name} : {len(df)} lignes, {len(df.columns)} colonnes")
    return df


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
def collect_zone_historical(zone_name: str, start: str, end: str,
                             force: bool = False) -> Path:
    """Collecte et sauvegarde les données historiques pour une zone."""
    output_path = OUTPUT_DIR / f"{zone_name}_historical.csv"

    if output_path.exists() and not force:
        logger.info(f"[Skip] {zone_name} déjà collecté ({output_path}). Utilisez --force pour ré-collecter.")
        return output_path

    if zone_name not in ZONES:
        logger.error(f"Zone inconnue : {zone_name}")
        return None

    info = ZONES[zone_name]
    lat, lon, climate = info["lat"], info["lon"], info["climate"]

    df_meteo = collect_openmeteo_historical(zone_name, lat, lon, start, end)
    time.sleep(1)  # Respecter les rate limits API
    df_nasa = collect_nasa_power_historical(zone_name, lat, lon, start, end)
    time.sleep(1)

    df = merge_and_enrich(df_meteo, df_nasa, zone_name, climate)

    if df.empty:
        logger.error(f"[Erreur] Aucune donnée collectée pour {zone_name}")
        return None

    df.to_csv(output_path, index=False)
    logger.info(f"[Sauvegarde] {output_path} ({len(df)} lignes)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Collecte données historiques SAMCAM")
    parser.add_argument("--zone", default=None, help="Nom de la zone (défaut: toutes)")
    parser.add_argument("--start", default=DEFAULT_START, help="Date de début YYYY-MM-DD")
    parser.add_argument("--end", default=DEFAULT_END, help="Date de fin YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Ré-collecter même si fichier existant")
    args = parser.parse_args()

    zones_to_collect = [args.zone] if args.zone else list(ZONES.keys())
    logger.info(f"Collecte historique {args.start} → {args.end} pour : {zones_to_collect}")

    results = []
    for zone in zones_to_collect:
        path = collect_zone_historical(zone, args.start, args.end, args.force)
        results.append({"zone": zone, "status": "OK" if path else "ERREUR", "fichier": str(path)})
        time.sleep(2)

    # Résumé
    print("\n" + "="*60)
    print("RÉSUMÉ COLLECTE HISTORIQUE")
    print("="*60)
    for r in results:
        status_icon = "✅" if r["status"] == "OK" else "❌"
        print(f"{status_icon} {r['zone']:20s} → {r['fichier']}")
    print("="*60)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    print(f"\n{ok_count}/{len(results)} zones collectées avec succès.")
    if ok_count == len(results):
        print("\n➡️  Étape suivante : python training/build_labels.py")


if __name__ == "__main__":
    main()
