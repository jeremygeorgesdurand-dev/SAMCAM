#!/usr/bin/env python3
"""
build_labels.py — Génération des labels (ground truth) pour l'entraînement SAMCAM.

Stratégie hybride :
  1. Labels par seuils physiques ZONAUX lus depuis config/zones/{slug}.json
     (seuils per_hazard_thresholds + normales mensuelles pour labels saisonniers)
  2. Fallback vers profils climatiques génériques si JSON absent
  3. Surcharge par événements historiques EM-DAT / OCHA Cameroun connus

Risques labellisés :
  - inondation  : 0 (normal) / 1 (risque)
  - secheresse  : 0 (normal) / 1 (risque)
  - chaleur     : 0 (normal) / 1 (risque)

Sortie : data/historical/<zone>_labeled.csv

Usage :
  python training/build_labels.py
  python training/build_labels.py --zone Maroua
"""

import argparse
import json
import logging
from pathlib import Path

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path("data/historical")
OUTPUT_DIR = Path("data/historical")
CONFIG_DIR = Path("config/zones")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("data/historical/build_labels.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profils climatiques génériques (fallback si JSON de zone absent)
# ---------------------------------------------------------------------------
CLIMATE_THRESHOLDS_FALLBACK = {
    "equatorial": {
        "flood_rain_7d": 120,
        "flood_rain_24h": 60,
        "flood_rain_intensity": 15,
        "drought_spi3": -1.0,
        "drought_rain_30d": 30,
        "drought_soil_moisture": 0.10,
        "heat_tmax": 36.0,
        "heat_days_consecutive": 3,
        "heat_anomaly": 3.0,
    },
    "tropical_highland": {
        "flood_rain_7d": 100,
        "flood_rain_24h": 50,
        "flood_rain_intensity": 12,
        "drought_spi3": -1.0,
        "drought_rain_30d": 25,
        "drought_soil_moisture": 0.09,
        "heat_tmax": 34.0,
        "heat_days_consecutive": 3,
        "heat_anomaly": 3.5,
    },
    "sahelian": {
        "flood_rain_7d": 70,
        "flood_rain_24h": 40,
        "flood_rain_intensity": 10,
        "drought_spi3": -0.8,
        "drought_rain_30d": 10,
        "drought_soil_moisture": 0.05,
        "heat_tmax": 42.0,
        "heat_days_consecutive": 5,
        "heat_anomaly": 4.0,
    },
}

# ---------------------------------------------------------------------------
# Événements historiques avérés au Cameroun (EM-DAT + OCHA + presse)
# Format : (zone, date_debut, date_fin, type_risque)
# Sources : EM-DAT International Disaster Database, OCHA ReliefWeb
# ---------------------------------------------------------------------------
KNOWN_EVENTS = [
    # --- Inondations Nord/Adamaoua ---
    ("Maroua",       "2012-08-01", "2012-09-30", "inondation"),
    ("Maroua",       "2020-08-15", "2020-09-15", "inondation"),
    ("Garoua",       "2012-08-01", "2012-09-15", "inondation"),
    ("Garoua",       "2020-09-01", "2020-10-15", "inondation"),
    ("Ngaoundere",   "2020-08-10", "2020-09-10", "inondation"),
    ("Ngaoundere",   "2019-09-01", "2019-10-15", "inondation"),
    # --- Inondations zones équatoriales/highlands ---
    ("Kribi",        "2019-06-01", "2019-07-15", "inondation"),
    ("Kribi",        "2017-08-01", "2017-09-30", "inondation"),
    ("Kribi",        "2021-06-15", "2021-07-31", "inondation"),
    ("Kumba",        "2020-10-01", "2020-11-15", "inondation"),
    ("Kumba",        "2018-09-01", "2018-10-31", "inondation"),
    ("Yaounde_peri", "2020-09-01", "2020-10-31", "inondation"),
    ("Yaounde_peri", "2019-08-15", "2019-09-30", "inondation"),
    ("Bafoussam",    "2019-10-01", "2019-10-31", "inondation"),
    ("Bafoussam",    "2020-09-15", "2020-10-31", "inondation"),
    ("Ebolowa",      "2021-09-01", "2021-10-15", "inondation"),
    ("Ebolowa",      "2022-09-01", "2022-10-15", "inondation"),
    # --- Sécheresses ---
    ("Maroua",       "2017-04-01", "2017-09-30", "secheresse"),
    ("Maroua",       "2022-01-01", "2022-06-30", "secheresse"),
    ("Garoua",       "2017-04-01", "2017-09-30", "secheresse"),
    ("Garoua",       "2021-01-01", "2021-05-31", "secheresse"),
    ("Ngaoundere",   "2018-01-01", "2018-03-31", "secheresse"),
    ("Kribi",        "2015-07-01", "2015-09-30", "secheresse"),
    ("Bafoussam",    "2016-01-01", "2016-03-31", "secheresse"),
    ("Yaounde_peri", "2016-01-01", "2016-03-31", "secheresse"),
    # --- Vagues de chaleur ---
    ("Maroua",       "2016-03-01", "2016-05-31", "chaleur"),
    ("Maroua",       "2019-03-01", "2019-05-15", "chaleur"),
    ("Garoua",       "2016-03-01", "2016-05-31", "chaleur"),
    ("Garoua",       "2023-03-15", "2023-05-15", "chaleur"),
    ("Ngaoundere",   "2021-02-01", "2021-04-30", "chaleur"),
    ("Ngaoundere",   "2019-02-15", "2019-04-30", "chaleur"),
    ("Bafoussam",    "2021-02-01", "2021-04-15", "chaleur"),
    ("Yaounde_peri", "2022-02-01", "2022-04-30", "chaleur"),
]


# ---------------------------------------------------------------------------
# Chargement des seuils zonaux depuis config/zones/{slug}.json
# ---------------------------------------------------------------------------
def load_zone_thresholds(zone_name: str, climate_type: str = "equatorial") -> tuple:
    """
    Charge les seuils depuis config/zones/{slug}.json.
    Retourne (thresholds_dict, monthly_rain_normals_list_ou_None, found_json).
    """
    slug = zone_name.lower().replace(" ", "_").replace("-", "_")
    config_path = CONFIG_DIR / f"{slug}.json"

    if not config_path.exists():
        logger.warning(
            f"[Config] Pas de JSON pour '{zone_name}' ({config_path}). "
            f"Fallback vers profil climatique '{climate_type}'."
        )
        return CLIMATE_THRESHOLDS_FALLBACK.get(climate_type, CLIMATE_THRESHOLDS_FALLBACK["equatorial"]), None, False

    with open(config_path) as f:
        cfg = json.load(f)

    # Lire les seuils par risque (per_hazard_thresholds)
    hazard_cfg = cfg.get("per_hazard_thresholds", {})
    flood_cfg  = hazard_cfg.get("flood", {})
    drought_cfg = hazard_cfg.get("drought", {})
    heat_cfg   = hazard_cfg.get("heat", {})

    thresholds = {
        "flood_rain_7d":            flood_cfg.get("rain_7d_mm",        80),
        "flood_rain_24h":           flood_cfg.get("rain_24h_mm",       50),
        "flood_rain_intensity":     flood_cfg.get("intensity_mm_h",    10),
        "flood_runoff_threshold":   flood_cfg.get("runoff_threshold",  0.0),
        "drought_spi3":             drought_cfg.get("spi3_threshold",  -1.0),
        "drought_rain_30d":         drought_cfg.get("rain_30d_mm",     25),
        "drought_soil_moisture":    drought_cfg.get("sm_rootzone_min", 0.10),
        "drought_et0_ratio":        drought_cfg.get("et0_ratio",        1.1),
        "heat_tmax":                heat_cfg.get("tmax_abs",           36.0),
        "heat_days_consecutive":    heat_cfg.get("consecutive_days",    3),
        "heat_anomaly":             heat_cfg.get("anomaly_c",           3.0),
    }

    # Normales mensuelles de pluie pour seuils saisonniers
    monthly_normals = cfg.get("monthly_normals", {}).get("rain", None)

    logger.info(f"[Config] '{zone_name}' : seuils chargés depuis {config_path.name}")
    return thresholds, monthly_normals, True


# ---------------------------------------------------------------------------
# Fonctions de labellisation
# ---------------------------------------------------------------------------
def label_flood(df: pd.DataFrame, thresholds: dict,
                monthly_rain_normals=None) -> pd.Series:
    """Label inondation.

    Si monthly_rain_normals est fourni (liste de 12 valeurs), utilise un
    seuil dynamique = 1.8 × normale mensuelle + critère journalier absolu.
    Sinon, utilise les seuils fixes du dictionnaire.
    """
    rain_col = "precipitation_sum" if "precipitation_sum" in df.columns else "nasa_prectotcorr"

    if rain_col not in df.columns:
        logger.warning("Colonne précipitations manquante pour label inondation")
        return pd.Series(0, index=df.index)

    # Critère journalier absolu (toujours actif)
    crit_abs = df[rain_col] >= thresholds["flood_rain_24h"]

    if monthly_rain_normals is not None and len(monthly_rain_normals) == 12:
        # Seuil dynamique saisonnier : 1.8 × normale mensuelle
        df_tmp = df[["date"]].copy() if "date" in df.columns else df.index.to_frame(name="date")
        month_idx = pd.to_datetime(df["date"]).dt.month - 1 if "date" in df.columns \
                    else df.index.to_series().dt.month - 1
        rain_normal = month_idx.map(lambda m: monthly_rain_normals[int(m)])
        dynamic_threshold = rain_normal * 1.8
        crit_seasonal = df[rain_col] >= dynamic_threshold

        # Critère cumul 7j
        crit_7d = df.get("rain_7d", pd.Series(0, index=df.index)) >= thresholds["flood_rain_7d"]

        label = (crit_abs | crit_seasonal | crit_7d).astype(int)
        logger.debug(f"  Flood saisonnier : {label.sum()} jours positifs")
    else:
        # Fallback : seuils fixes
        crit_7d = df.get("rain_7d", pd.Series(0, index=df.index)) >= thresholds["flood_rain_7d"]
        label = (crit_abs | crit_7d).astype(int)

    return label


def label_drought(df: pd.DataFrame, thresholds: dict,
                  monthly_rain_normals=None) -> pd.Series:
    """Label sécheresse.

    Utilise SPI-3, cumul 30j (dynamique si normales disponibles), humidité sol.
    """
    label = pd.Series(0, index=df.index)

    # Critère SPI-3
    if "spi3_approx" in df.columns:
        label = label | (df["spi3_approx"] < thresholds["drought_spi3"]).astype(int)

    # Critère cumul 30j (dynamique si normales disponibles)
    if "rain_30d" in df.columns:
        if monthly_rain_normals is not None and len(monthly_rain_normals) == 12:
            month_idx = pd.to_datetime(df["date"]).dt.month - 1 if "date" in df.columns \
                        else df.index.to_series().dt.month - 1
            rain_normal_30d = month_idx.map(lambda m: monthly_rain_normals[int(m)])
            # Sécheresse si pluie 30j < 65% de la normale mensuelle
            crit_rain = df["rain_30d"] < (rain_normal_30d * 0.65)
        else:
            crit_rain = df["rain_30d"] < thresholds["drought_rain_30d"]
        label = label | crit_rain.astype(int)

    # Critère humidité sol
    sm_col = None
    for col in ["soil_moisture_0_to_7cm_mean", "nasa_gwettop", "nasa_gwetroot"]:
        if col in df.columns:
            sm_col = col
            break
    if sm_col:
        label = label | (df[sm_col] < thresholds["drought_soil_moisture"]).astype(int)

    # Critère pluie_7j (signal fort si < 20mm ET déficit 30j)
    if "rain_7d" in df.columns and "rain_30d" in df.columns:
        deficit_30j = df["rain_30d"] < thresholds["drought_rain_30d"] * 1.2
        signal_fort = (df["rain_7d"] < 20) & deficit_30j
        label = label | signal_fort.astype(int)

    return label


def label_heat(df: pd.DataFrame, thresholds: dict) -> pd.Series:
    """Label vague de chaleur basé sur Tmax et anomalie."""
    tmax_col = "temperature_2m_max" if "temperature_2m_max" in df.columns else "nasa_t2m_max"

    if tmax_col not in df.columns:
        logger.warning("Colonne température max manquante pour label chaleur")
        return pd.Series(0, index=df.index)

    crit1 = df[tmax_col] >= thresholds["heat_tmax"]
    crit2 = df.get("temp_anom_30d", pd.Series(0.0, index=df.index)) >= thresholds["heat_anomaly"]

    hot_days = (crit1 | crit2).astype(int)
    n_consec = thresholds["heat_days_consecutive"]
    crit3 = hot_days.rolling(n_consec, min_periods=n_consec).sum() >= n_consec

    label = (crit1 | crit2 | crit3.fillna(False)).astype(int)
    return label


def apply_known_events(df: pd.DataFrame, zone_name: str) -> pd.DataFrame:
    """Surcharge les labels avec les événements historiques avérés."""
    zone_events = [(z, s, e, t) for z, s, e, t in KNOWN_EVENTS if z == zone_name]

    if not zone_events:
        return df

    col_map = {
        "inondation": "label_inondation",
        "secheresse": "label_secheresse",
        "chaleur":    "label_chaleur",
    }
    for zone, start, end, risk_type in zone_events:
        mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
        col = col_map.get(risk_type)
        if col and col in df.columns:
            df.loc[mask, col] = 1
            count = mask.sum()
            logger.info(f"[EM-DAT] {zone} {risk_type} {start}→{end} : {count} jours forcés à 1")

    return df


def build_labels_for_zone(zone_name: str) -> Path:
    """Construit les labels pour une zone et sauvegarde le CSV labellisé."""
    input_path  = DATA_DIR   / f"{zone_name}_historical.csv"
    output_path = OUTPUT_DIR / f"{zone_name}_labeled.csv"

    if not input_path.exists():
        logger.error(f"Fichier historique manquant : {input_path}")
        logger.error(f"➡️  Lancez d'abord : python data_collection/collect_historical.py --zone {zone_name}")
        return None

    logger.info(f"[Labels] Traitement de {zone_name}...")
    df = pd.read_csv(input_path, parse_dates=["date"])

    # Déterminer le type climatique de fallback
    climate = df["climate_zone"].iloc[0] if "climate_zone" in df.columns else "equatorial"

    # Charger les seuils : JSON zonal en priorité, fallback générique sinon
    thresholds, monthly_rain_normals, used_json = load_zone_thresholds(zone_name, climate)

    if used_json:
        logger.info(f"  → Seuils individuels chargés depuis config/zones/{zone_name.lower()}.json")
    else:
        logger.info(f"  → Seuils génériques fallback (profil: {climate})")

    # Application des labels physiques
    df["label_inondation"] = label_flood(df, thresholds, monthly_rain_normals)
    df["label_secheresse"] = label_drought(df, thresholds, monthly_rain_normals)
    df["label_chaleur"]    = label_heat(df, thresholds)

    # Surcharge avec événements avérés EM-DAT/OCHA
    df = apply_known_events(df, zone_name)

    # Statistiques labels
    total = len(df)
    for risk in ["inondation", "secheresse", "chaleur"]:
        col   = f"label_{risk}"
        n_pos = df[col].sum()
        pct   = 100 * n_pos / total
        flag  = "⚠️ " if pct < 3 or pct > 40 else "   "
        logger.info(f"{flag} {risk:12s}: {n_pos:5d}/{total} jours positifs ({pct:.1f}%)")

    df.to_csv(output_path, index=False)
    logger.info(f"[Sauvegarde] {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Construction labels SAMCAM")
    parser.add_argument("--zone", default=None, help="Zone spécifique (défaut: toutes)")
    args = parser.parse_args()

    if args.zone:
        zones = [args.zone]
    else:
        zones = [
            p.stem.replace("_historical", "")
            for p in DATA_DIR.glob("*_historical.csv")
        ]
        zones.sort()

    if not zones:
        logger.error("Aucun fichier historique trouvé dans data/historical/")
        logger.error("➡️  Lancez d'abord : python data_collection/collect_historical.py")
        return

    logger.info(f"Labellisation de {len(zones)} zones : {zones}")
    results = []
    for zone in zones:
        path = build_labels_for_zone(zone)
        results.append({"zone": zone, "status": "OK" if path else "ERREUR"})

    print("\n" + "="*60)
    print("RÉSUMÉ LABELLISATION")
    print("="*60)
    for r in results:
        icon = "✅" if r["status"] == "OK" else "❌"
        print(f"{icon} {r['zone']}")
    print("="*60)
    ok = sum(1 for r in results if r["status"] == "OK")
    print(f"\n{ok}/{len(results)} zones labellisées.")
    if ok == len(results):
        print("\n➡️  Étape suivante : python training/train_zonal_models.py")


if __name__ == "__main__":
    main()
