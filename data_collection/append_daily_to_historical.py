#!/usr/bin/env python3
"""
append_daily_to_historical.py — Fusionne les collectes quotidiennes
(data/<zone>_*.json) dans l'historique glissant (data/historical/<Zone>_historical.csv)
utilisé par inference/infer_zonal.py pour l'inférence live.

Pourquoi ce script : la collecte quotidienne (JSON, ~8 jours de fenêtre glissante)
et l'historique d'entraînement (CSV, backfill 1990-2025) étaient deux pipelines
déconnectés — rien n'ajoutait les collectes du jour à l'historique, qui restait
figé à la date du dernier backfill. Sans ce pont, infer_zonal.py ne voit jamais
les données récentes et ne peut pas servir de moteur d'inférence live.

Usage :
  python3 data_collection/append_daily_to_historical.py
  python3 data_collection/append_daily_to_historical.py --zones Kribi Garoua
"""

import argparse
import glob
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from inference.infer_zonal import compute_derived_features  # réutilise la même logique que l'inférence

DATA_DIR       = ROOT / "data"
HISTORICAL_DIR = ROOT / "data" / "historical"

CLIMATE_BY_ZONE = {
    "Kribi": "equatorial", "Ebolowa": "equatorial", "Kumba": "equatorial",
    "Bafoussam": "tropical_highland", "Ngaoundere": "tropical_highland",
    "Yaounde_peri": "equatorial", "Garoua": "sahelian", "Maroua": "sahelian",
    # Zones agricoles ajoutées
    "Ndop": "tropical_highland", "Foumbot": "tropical_highland",
    "Kaele": "sahelian", "Guider": "sahelian", "Meiganga": "tropical_highland",
    "Mbalmayo": "equatorial", "Bafia": "equatorial", "Bertoua": "equatorial",
    "Nkongsamba": "equatorial", "Buea": "equatorial",
}

DERIVED_COLS = [
    "year", "month", "day_of_year", "week",
    "rain_7d", "rain_14d", "rain_30d", "rain_90d",
    "spi3_approx", "temp_anom_30d", "temp_max_7d",
]

FFILL_COLS = [
    "soil_moisture_0_to_7cm_mean", "soil_moisture_7_to_28cm_mean", "soil_moisture_28_to_100cm_mean",
    "nasa_allsky_sfc_sw_dwn", "nasa_t2m", "nasa_t2m_max", "nasa_t2m_min",
    "nasa_rh2m", "nasa_prectotcorr", "nasa_ws10m", "nasa_evland", "nasa_gwetroot", "nasa_gwettop",
    "relative_humidity_2m_max", "relative_humidity_2m_min",
    "wind_gusts_10m_max", "shortwave_radiation_sum", "precipitation_hours", "sunshine_duration",
]


def _nasa_last(nasa: dict, key: str):
    v = nasa.get(key)
    if isinstance(v, dict) and v:
        return v[sorted(v.keys())[-1]]
    return None


def _rows_from_zone_json(path: Path) -> list:
    """Extrait toutes les lignes journalières disponibles dans un fichier de collecte."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)

    meta = d.get("meta", {})
    zone = meta.get("zone")
    if not zone:
        return []

    hist  = d.get("meteorologie", {}).get("historique_daily", {})
    times = hist.get("time", [])
    if not times:
        return []

    date_collecte = meta.get("date_collecte")
    smap = d.get("satellitaire", {}).get("smap", {}).get("humidite_sol", {})
    nasa = d.get("nasa_power", {}).get("parametres", {})

    def _serie(cle):
        vals = hist.get(cle, [])
        return vals if len(vals) == len(times) else [None] * len(times)

    tmax  = _serie("temperature_2m_max")
    tmin  = _serie("temperature_2m_min")
    precip = _serie("precipitation_sum")
    rain  = hist.get("rain_sum") if len(hist.get("rain_sum", [])) == len(times) else precip
    et0   = _serie("et0_fao_evapotranspiration")
    wind  = _serie("windspeed_10m_max")

    rows = []
    for i, day in enumerate(times):
        row = {
            "date":                       day,
            "zone":                       zone,
            "source_meteo":               "open-meteo",
            "temperature_2m_max":         tmax[i],
            "temperature_2m_min":         tmin[i],
            "precipitation_sum":          precip[i],
            "rain_sum":                   rain[i],
            "et0_fao_evapotranspiration": et0[i],
            "wind_speed_10m_max":         wind[i],
            "climate_zone":               CLIMATE_BY_ZONE.get(zone, "equatorial"),
        }
        row["temperature_2m_mean"] = (
            (tmax[i] + tmin[i]) / 2 if tmax[i] is not None and tmin[i] is not None else None
        )
        # SMAP/NASA : seulement mesurés au jour de collecte (dernier jour de la fenêtre) —
        # NaN pour les jours antérieurs de la même fenêtre, comblés au ffill/bfill après fusion.
        if day == date_collecte or i == len(times) - 1:
            row["soil_moisture_0_to_7cm_mean"]    = smap.get("sm_surface")
            row["soil_moisture_7_to_28cm_mean"]   = smap.get("sm_rootzone")
            row["soil_moisture_28_to_100cm_mean"] = smap.get("sm_rootzone")
            row["nasa_allsky_sfc_sw_dwn"] = _nasa_last(nasa, "ALLSKY_SFC_SW_DWN")
            row["nasa_t2m"]               = _nasa_last(nasa, "T2M")
            row["nasa_t2m_max"]           = _nasa_last(nasa, "T2M_MAX")
            row["nasa_t2m_min"]           = _nasa_last(nasa, "T2M_MIN")
            row["nasa_rh2m"]              = _nasa_last(nasa, "RH2M")
            row["nasa_prectotcorr"]       = _nasa_last(nasa, "PRECTOTCORR")
            row["nasa_ws10m"]             = _nasa_last(nasa, "WS10M")
        rows.append(row)
    return rows


def append_zone(zone: str) -> None:
    pattern  = DATA_DIR / f"{zone.lower()}_*.json"
    fichiers = sorted(glob.glob(str(pattern)))
    if not fichiers:
        print(f"[{zone}] Aucune collecte quotidienne trouvée ({pattern})")
        return

    all_rows = []
    for f in fichiers:
        all_rows.extend(_rows_from_zone_json(Path(f)))
    if not all_rows:
        print(f"[{zone}] Aucune ligne journalière extraite des collectes")
        return

    df_new = pd.DataFrame(all_rows)
    df_new["date"] = pd.to_datetime(df_new["date"])

    hist_path = HISTORICAL_DIR / f"{zone}_historical.csv"
    if hist_path.exists():
        df_old = pd.read_csv(hist_path, parse_dates=["date"])
        # Repartir des colonnes brutes uniquement : les colonnes dérivées (rolling)
        # sont recalculées sur l'ensemble de la série pour rester cohérentes de bout en bout.
        df_old = df_old.drop(columns=[c for c in DERIVED_COLS if c in df_old.columns])
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    df = df.sort_values("date").drop_duplicates(subset="date", keep="last").reset_index(drop=True)

    ffill_cols = [c for c in FFILL_COLS if c in df.columns]
    df[ffill_cols] = df[ffill_cols].ffill().bfill()

    df["year"] = df["date"].dt.year
    df = compute_derived_features(df)

    df.to_csv(hist_path, index=False)
    print(f"[{zone}] ✅ {hist_path.name} mis à jour — {len(df)} lignes, "
          f"jusqu'au {df['date'].max().date()} ({len(df_new)} lignes fusionnées depuis les collectes)")


def main():
    parser = argparse.ArgumentParser(
        description="Fusionne les collectes quotidiennes dans l'historique glissant SAMCAM")
    parser.add_argument("--zones", nargs="+", default=None,
                         help="Zones à traiter (défaut : toutes celles ayant un historique existant)")
    args = parser.parse_args()

    zones = args.zones or sorted(
        p.stem.replace("_historical", "") for p in HISTORICAL_DIR.glob("*_historical.csv")
    )
    if not zones:
        print("Aucun historique trouvé dans data/historical/ — lancez d'abord collect_historical.py")
        return

    for zone in zones:
        append_zone(zone)


if __name__ == "__main__":
    main()
