#!/usr/bin/env python3
"""
collect_historical.py — Collecte des données historiques 1990-2025 pour toutes les zones SAMCAM.

Sources :
  - Open-Meteo Historical Weather API (météo journalière, ERA5 réanalyse)
  - NASA POWER API (rayonnement, température, humidité, disponible depuis 1981)

Stratégie temporelle par zone :
  - equatorial  (Kribi, Ebolowa, Kumba, Yaounde_peri) : 2000-2025
    Open-Meteo ERA5 fiable à partir de 2000 pour les zones équatoriales côtières.
  - tropical_highland (Bafoussam, Ngaoundere)          : 1990-2025
    Cycles ENSO et anomalies mousson mieux représentés sur 35 ans.
  - sahelian (Garoua, Maroua)                          : 1990-2025
    Sécheresses décennales 1990-2000 essentielles pour le label drought.

Robustesse réseau :
  - Requêtes découpées en chunks annuels (Open-Meteo: 2 ans, NASA: 5 ans)
    pour éviter les timeouts sur les longues séries.
  - Retry automatique jusqu'à MAX_RETRIES tentatives avec backoff exponentiel.

Sortie : data/historical/<zone>_historical.csv

Usage :
  python collect_historical.py                      # toutes les zones, dates par défaut
  python collect_historical.py --zone Kribi         # zone spécifique
  python collect_historical.py --start 1985-01-01   # forcer une date de début
  python collect_historical.py --force              # ré-collecter même si fichier existant
  python collect_historical.py --chunk-years 1      # chunks d'1 an (réseau très lent)
"""

import os
import time
import argparse
import logging
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from pathlib import Path

import requests
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Configuration des zones SAMCAM
# ---------------------------------------------------------------------------
ZONES = {
    "Kribi":        {"lat": 2.9399,  "lon": 9.9098,  "climate": "equatorial",       "start": "2000-01-01"},
    "Ebolowa":      {"lat": 2.9000,  "lon": 11.1500, "climate": "equatorial",       "start": "2000-01-01"},
    "Kumba":        {"lat": 4.6364,  "lon": 9.4469,  "climate": "equatorial",       "start": "2000-01-01"},
    "Bafoussam":    {"lat": 5.4765,  "lon": 10.4178, "climate": "tropical_highland","start": "1990-01-01"},
    "Yaounde_peri": {"lat": 3.8480,  "lon": 11.5021, "climate": "equatorial",       "start": "2000-01-01"},
    "Ngaoundere":   {"lat": 7.3220,  "lon": 13.5840, "climate": "tropical_highland","start": "1990-01-01"},
    "Garoua":       {"lat": 9.3000,  "lon": 13.3900, "climate": "sahelian",         "start": "1990-01-01"},
    "Maroua":       {"lat": 10.5910, "lon": 14.3159, "climate": "sahelian",         "start": "1990-01-01"},
}

DEFAULT_END          = "2025-12-31"
CHUNK_YEARS_OPENMETEO = 2   # Open-Meteo : fenêtre max avant timeout (2 ans)
CHUNK_YEARS_NASA      = 5   # NASA POWER : moins sensible, 5 ans OK
MAX_RETRIES           = 3   # Nombre de tentatives par chunk
RETRY_BACKOFF_BASE    = 5   # Secondes de base pour le backoff exponentiel

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
# Utilitaires
# ---------------------------------------------------------------------------
def date_chunks(start: str, end: str, chunk_years: int):
    """Génère des intervalles (start, end) de chunk_years ans entre start et end."""
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end,   "%Y-%m-%d").date()
    current = s
    while current < e:
        chunk_end = min(current + relativedelta(years=chunk_years) - relativedelta(days=1), e)
        yield current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        current = chunk_end + relativedelta(days=1)


def request_with_retry(url: str, params: dict, timeout: int, label: str) -> dict | None:
    """GET avec retry exponentiel. Retourne le JSON ou None en cas d'échec total."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(f"[Retry {attempt}/{MAX_RETRIES}] Timeout {label} — attente {wait}s")
            if attempt < MAX_RETRIES:
                time.sleep(wait)
        except requests.exceptions.HTTPError as e:
            wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(f"[Retry {attempt}/{MAX_RETRIES}] HTTP {e} {label} — attente {wait}s")
            if attempt < MAX_RETRIES:
                time.sleep(wait)
        except Exception as e:
            logger.error(f"[Erreur fatale] {label}: {e}")
            return None
    logger.error(f"[Échec] {label} après {MAX_RETRIES} tentatives")
    return None


# ---------------------------------------------------------------------------
# Open-Meteo Historical (chunked + retry)
# ---------------------------------------------------------------------------
OPENMETEO_DAILY_VARS = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "precipitation_sum", "rain_sum", "et0_fao_evapotranspiration",
    "wind_speed_10m_max", "wind_gusts_10m_max", "shortwave_radiation_sum",
    "relative_humidity_2m_max", "relative_humidity_2m_min",
    "soil_moisture_0_to_7cm_mean", "soil_moisture_7_to_28cm_mean",
    "soil_moisture_28_to_100cm_mean", "precipitation_hours", "sunshine_duration",
]

def collect_openmeteo_historical(zone_name: str, lat: float, lon: float,
                                  start: str, end: str,
                                  chunk_years: int = CHUNK_YEARS_OPENMETEO) -> pd.DataFrame:
    """Collecte météo journalière Open-Meteo en chunks pour éviter les timeouts."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    chunks_list = list(date_chunks(start, end, chunk_years))
    logger.info(f"[Open-Meteo] {zone_name} {start} → {end} ({len(chunks_list)} chunks de {chunk_years} an(s))")

    frames = []
    for chunk_start, chunk_end in chunks_list:
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": chunk_start, "end_date": chunk_end,
            "daily": OPENMETEO_DAILY_VARS,
            "timezone": "Africa/Douala",
        }
        label = f"Open-Meteo {zone_name} {chunk_start}→{chunk_end}"
        data = request_with_retry(url, params, timeout=90, label=label)
        if data is None:
            logger.warning(f"[Open-Meteo] Chunk ignoré : {chunk_start}→{chunk_end} pour {zone_name}")
            continue
        daily = data.get("daily", {})
        if not daily or "time" not in daily:
            logger.warning(f"[Open-Meteo] Aucune donnée dans le chunk {chunk_start}→{chunk_end}")
            continue
        df_chunk = pd.DataFrame(daily)
        df_chunk.rename(columns={"time": "date"}, inplace=True)
        df_chunk["date"] = pd.to_datetime(df_chunk["date"])
        frames.append(df_chunk)
        time.sleep(0.5)  # politesse API

    if not frames:
        logger.error(f"[Open-Meteo] Aucune donnée collectée pour {zone_name}")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True).drop_duplicates("date").sort_values("date")
    df["zone"] = zone_name
    df["source_meteo"] = "open-meteo"
    logger.info(f"[Open-Meteo] {zone_name} : {len(df)} jours collectés ({start} → {end})")
    return df


# ---------------------------------------------------------------------------
# NASA POWER Historical (chunked + retry)
# ---------------------------------------------------------------------------
NASA_PARAMS = "ALLSKY_SFC_SW_DWN,T2M,T2M_MAX,T2M_MIN,RH2M,PRECTOTCORR,WS10M,EVLAND,GWETROOT,GWETTOP"

def collect_nasa_power_historical(zone_name: str, lat: float, lon: float,
                                   start: str, end: str,
                                   chunk_years: int = CHUNK_YEARS_NASA) -> pd.DataFrame:
    """Collecte NASA POWER en chunks de chunk_years ans."""
    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    chunks_list = list(date_chunks(start, end, chunk_years))
    logger.info(f"[NASA POWER] {zone_name} {start} → {end} ({len(chunks_list)} chunks de {chunk_years} an(s))")

    frames = []
    for chunk_start, chunk_end in chunks_list:
        params = {
            "parameters": NASA_PARAMS,
            "community": "AG",
            "longitude": lon, "latitude": lat,
            "start": chunk_start.replace("-", ""),
            "end":   chunk_end.replace("-", ""),
            "format": "JSON",
        }
        label = f"NASA POWER {zone_name} {chunk_start}→{chunk_end}"
        data = request_with_retry(url, params, timeout=120, label=label)
        if data is None:
            logger.warning(f"[NASA POWER] Chunk ignoré : {chunk_start}→{chunk_end} pour {zone_name}")
            continue
        props = data.get("properties", {}).get("parameter", {})
        if not props:
            logger.warning(f"[NASA POWER] Aucune donnée dans le chunk {chunk_start}→{chunk_end}")
            continue
        dates = list(list(props.values())[0].keys())
        df_chunk = pd.DataFrame({"date_str": dates})
        for param, values in props.items():
            df_chunk[f"nasa_{param.lower()}"] = [values.get(d, np.nan) for d in dates]
        df_chunk.replace(-999.0, np.nan, inplace=True)
        df_chunk["date"] = pd.to_datetime(df_chunk["date_str"], format="%Y%m%d")
        df_chunk.drop(columns=["date_str"], inplace=True)
        frames.append(df_chunk)
        time.sleep(0.5)

    if not frames:
        logger.error(f"[NASA POWER] Aucune donnée collectée pour {zone_name}")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True).drop_duplicates("date").sort_values("date")
    df["zone"] = zone_name
    logger.info(f"[NASA POWER] {zone_name} : {len(df)} jours collectés ({start} → {end})")
    return df


# ---------------------------------------------------------------------------
# Fusion et enrichissement
# ---------------------------------------------------------------------------
def merge_and_enrich(df_meteo: pd.DataFrame, df_nasa: pd.DataFrame,
                     zone_name: str, climate: str) -> pd.DataFrame:
    """Fusionne Open-Meteo et NASA POWER, calcule les features dérivées."""
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

    # Features temporelles
    df["year"]       = df["date"].dt.year
    df["month"]      = df["date"].dt.month
    df["day_of_year"] = df["date"].dt.dayofyear
    df["week"]       = df["date"].dt.isocalendar().week.astype(int)

    # Cumuls glissants précipitations
    rain_col = "precipitation_sum" if "precipitation_sum" in df.columns else "nasa_prectotcorr"
    if rain_col in df.columns:
        df["rain_7d"]  = df[rain_col].rolling(7,  min_periods=1).sum()
        df["rain_14d"] = df[rain_col].rolling(14, min_periods=1).sum()
        df["rain_30d"] = df[rain_col].rolling(30, min_periods=1).sum()
        df["rain_90d"] = df[rain_col].rolling(90, min_periods=1).sum()

        # SPI-3 simplifié (Z-score glissant 90j) — plus fiable avec 35 ans de baseline
        mean_90 = df["rain_90d"].expanding(min_periods=90).mean()
        std_90  = df["rain_90d"].expanding(min_periods=90).std().replace(0, np.nan)
        df["spi3_approx"] = (df["rain_90d"] - mean_90) / std_90

    # Anomalie température vs moyenne mobile 30j
    temp_col = "temperature_2m_mean" if "temperature_2m_mean" in df.columns else "nasa_t2m"
    if temp_col in df.columns:
        df["temp_anom_30d"] = df[temp_col] - df[temp_col].rolling(30, min_periods=7).mean()
        df["temp_max_7d"]   = df[temp_col].rolling(7, min_periods=1).max()

    # Métadonnées zone
    df["climate_zone"] = climate

    logger.info(f"[Merge] {zone_name} : {len(df)} lignes, {len(df.columns)} colonnes")
    return df


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
def collect_zone_historical(zone_name: str, start: str, end: str,
                             force: bool = False,
                             chunk_years_om: int = CHUNK_YEARS_OPENMETEO,
                             chunk_years_nasa: int = CHUNK_YEARS_NASA) -> Path | None:
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

    df_meteo = collect_openmeteo_historical(zone_name, lat, lon, start, end, chunk_years=chunk_years_om)
    time.sleep(2)
    df_nasa = collect_nasa_power_historical(zone_name, lat, lon, start, end, chunk_years=chunk_years_nasa)
    time.sleep(2)

    df = merge_and_enrich(df_meteo, df_nasa, zone_name, climate)

    if df.empty:
        logger.error(f"[Erreur] Aucune donnée collectée pour {zone_name}")
        return None

    df.to_csv(output_path, index=False)
    logger.info(f"[Sauvegarde] {output_path} ({len(df)} lignes)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Collecte données historiques SAMCAM (1990-2025)")
    parser.add_argument("--zone",        default=None,        help="Nom de la zone (défaut: toutes)")
    parser.add_argument("--start",       default=None,        help="Date de début YYYY-MM-DD (écrase le défaut par zone)")
    parser.add_argument("--end",         default=DEFAULT_END, help=f"Date de fin YYYY-MM-DD (défaut: {DEFAULT_END})")
    parser.add_argument("--force",       action="store_true", help="Ré-collecter même si fichier existant")
    parser.add_argument("--chunk-years", type=int, default=None,
                        help="Taille des chunks en années (Open-Meteo et NASA). Défaut: 2 pour OM, 5 pour NASA.")
    args = parser.parse_args()

    chunk_om   = args.chunk_years or CHUNK_YEARS_OPENMETEO
    chunk_nasa = args.chunk_years or CHUNK_YEARS_NASA

    zones_to_collect = [args.zone] if args.zone else list(ZONES.keys())

    # Résolution des dates de début par zone
    zone_starts = {}
    for z in zones_to_collect:
        if args.start:
            zone_starts[z] = args.start
        else:
            zone_starts[z] = ZONES[z].get("start", "1990-01-01")

    logger.info(f"Collecte historique → {args.end} pour : {zones_to_collect}")
    for z in zones_to_collect:
        logger.info(f"  {z:20s} : {zone_starts[z]} → {args.end}")

    results = []
    for zone in zones_to_collect:
        path = collect_zone_historical(
            zone, zone_starts[zone], args.end,
            force=args.force,
            chunk_years_om=chunk_om,
            chunk_years_nasa=chunk_nasa,
        )
        results.append({"zone": zone, "status": "OK" if path else "ERREUR", "fichier": str(path)})
        time.sleep(2)

    # Résumé
    print("\n" + "="*60)
    print("RÉSUMÉ COLLECTE HISTORIQUE")
    print("="*60)
    for r in results:
        icon = "✅" if r["status"] == "OK" else "❌"
        print(f"{icon} {r['zone']:20s} → {r['fichier']}")
    print("="*60)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    print(f"\n{ok_count}/{len(results)} zones collectées avec succès.")
    if ok_count == len(results):
        print("\n➡️  Étape suivante : python training/build_labels.py")
    else:
        failed = [r["zone"] for r in results if r["status"] != "OK"]
        print(f"\n⚠️  Zones en erreur : {failed}")
        print("    → Relancez avec --force --zone <zone> pour retry individuel")


if __name__ == "__main__":
    main()
