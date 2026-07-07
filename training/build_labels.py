#!/usr/bin/env python3
"""
build_labels.py — Génération des labels (ground truth) pour l'entraînement SAMCAM.

Stratégie hybride :
  1. Labels par seuils physiques calibrés (SPI, cumuls pluie, température)
  2. Surcharge par événements historiques EM-DAT / OCHA Cameroun connus

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
import logging
from pathlib import Path

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path("data/historical")
OUTPUT_DIR = Path("data/historical")

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
# Seuils physiques par type climatique
# Calibrés sur les normales climatiques camerounaises
# ---------------------------------------------------------------------------
CLIMATE_THRESHOLDS = {
    "equatorial": {
        # Inondation : zone à fortes pluies (Kribi > 3000mm/an)
        "flood_rain_7d": 120,     # mm sur 7 jours
        "flood_rain_24h": 60,     # mm sur 24h
        "flood_rain_intensity": 15,  # mm/heure équivalent journalier
        # Sécheresse : SPI-3 < -1.0 = sécheresse modérée
        "drought_spi3": -1.0,
        "drought_rain_30d": 30,   # mm sur 30j (très bas pour équatorial)
        "drought_soil_moisture": 0.10,  # fraction volumique
        # Chaleur : chaleur extrême rare en zone équatoriale
        "heat_tmax": 36.0,        # °C
        "heat_days_consecutive": 3,
        "heat_anomaly": 3.0,      # °C au-dessus de la normale
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
        "flood_rain_7d": 70,      # pluies rares mais intenses
        "flood_rain_24h": 40,
        "flood_rain_intensity": 10,
        "drought_spi3": -0.8,     # seuil plus sensible
        "drought_rain_30d": 10,   # zone naturellement sèche
        "drought_soil_moisture": 0.05,
        "heat_tmax": 42.0,        # Maroua/Garoua : chaleurs extrêmes normales
        "heat_days_consecutive": 5,
        "heat_anomaly": 4.0,
    },
}

# Événements historiques avérés au Cameroun (EM-DAT + OCHA + presse)
# Format : (zone, date_debut, date_fin, type_risque)
# Sources : EM-DAT International Disaster Database, OCHA ReliefWeb
KNOWN_EVENTS = [
    # Inondations
    ("Maroua", "2012-08-01", "2012-09-30", "inondation"),
    ("Maroua", "2020-08-15", "2020-09-15", "inondation"),
    ("Garoua", "2012-08-01", "2012-09-15", "inondation"),
    ("Garoua", "2020-09-01", "2020-10-15", "inondation"),
    ("Ngaoundere", "2020-08-10", "2020-09-10", "inondation"),
    ("Kribi", "2019-06-01", "2019-07-15", "inondation"),
    ("Kumba", "2020-10-01", "2020-11-15", "inondation"),
    ("Yaounde_peri", "2020-09-01", "2020-10-31", "inondation"),
    ("Bafoussam", "2019-10-01", "2019-10-31", "inondation"),
    ("Ebolowa", "2021-09-01", "2021-10-15", "inondation"),
    # Sécheresses
    ("Maroua", "2017-04-01", "2017-09-30", "secheresse"),
    ("Garoua", "2017-04-01", "2017-09-30", "secheresse"),
    ("Ngaoundere", "2018-01-01", "2018-03-31", "secheresse"),
    ("Garoua", "2021-01-01", "2021-05-31", "secheresse"),
    ("Maroua", "2022-01-01", "2022-06-30", "secheresse"),
    # Vagues de chaleur
    ("Maroua", "2016-03-01", "2016-05-31", "chaleur"),
    ("Garoua", "2016-03-01", "2016-05-31", "chaleur"),
    ("Maroua", "2019-03-01", "2019-05-15", "chaleur"),
    ("Garoua", "2023-03-15", "2023-05-15", "chaleur"),
    ("Ngaoundere", "2021-02-01", "2021-04-30", "chaleur"),
]


# ---------------------------------------------------------------------------
# Fonctions de labellisation
# ---------------------------------------------------------------------------
def label_flood(df: pd.DataFrame, thresholds: dict) -> pd.Series:
    """Label inondation basé sur cumuls pluie et intensité."""
    rain_col = "precipitation_sum" if "precipitation_sum" in df.columns else "nasa_prectotcorr"

    if rain_col not in df.columns:
        logger.warning("Colonne précipitations manquante pour label inondation")
        return pd.Series(0, index=df.index)

    # Critère 1 : cumul 7j dépasse le seuil
    crit1 = df.get("rain_7d", pd.Series(0, index=df.index)) >= thresholds["flood_rain_7d"]

    # Critère 2 : pluie journalière intense
    crit2 = df[rain_col] >= thresholds["flood_rain_24h"]

    # Au moins un critère suffit
    label = (crit1 | crit2).astype(int)
    return label


def label_drought(df: pd.DataFrame, thresholds: dict) -> pd.Series:
    """Label sécheresse basé sur SPI-3 et humidité sol."""
    label = pd.Series(0, index=df.index)

    # Critère SPI-3
    if "spi3_approx" in df.columns:
        label = label | (df["spi3_approx"] < thresholds["drought_spi3"]).astype(int)

    # Critère cumul 30j
    if "rain_30d" in df.columns:
        label = label | (df["rain_30d"] < thresholds["drought_rain_30d"]).astype(int)

    # Critère humidité sol (SMAP ou Open-Meteo)
    sm_col = None
    for col in ["soil_moisture_0_to_7cm_mean", "nasa_gwettop"]:
        if col in df.columns:
            sm_col = col
            break
    if sm_col:
        label = label | (df[sm_col] < thresholds["drought_soil_moisture"]).astype(int)

    return label


def label_heat(df: pd.DataFrame, thresholds: dict) -> pd.Series:
    """Label vague de chaleur basé sur Tmax et anomalie."""
    tmax_col = "temperature_2m_max" if "temperature_2m_max" in df.columns else "nasa_t2m_max"

    if tmax_col not in df.columns:
        logger.warning("Colonne température max manquante pour label chaleur")
        return pd.Series(0, index=df.index)

    # Critère 1 : Tmax dépasse le seuil absolu
    crit1 = df[tmax_col] >= thresholds["heat_tmax"]

    # Critère 2 : anomalie thermique
    crit2 = df.get("temp_anom_30d", pd.Series(0, index=df.index)) >= thresholds["heat_anomaly"]

    # Critère 3 : consécutivité (fenêtre glissante)
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

    for zone, start, end, risk_type in zone_events:
        mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
        col_map = {"inondation": "label_inondation", "secheresse": "label_secheresse", "chaleur": "label_chaleur"}
        if col_map[risk_type] in df.columns:
            df.loc[mask, col_map[risk_type]] = 1
            count = mask.sum()
            logger.info(f"[EM-DAT] {zone} {risk_type} {start}→{end} : {count} jours forcés à 1")

    return df


def build_labels_for_zone(zone_name: str) -> Path:
    """Construit les labels pour une zone et sauvegarde le CSV labellisé."""
    input_path = DATA_DIR / f"{zone_name}_historical.csv"
    output_path = OUTPUT_DIR / f"{zone_name}_labeled.csv"

    if not input_path.exists():
        logger.error(f"Fichier historique manquant : {input_path}")
        logger.error(f"➡️  Lancez d'abord : python data_collection/collect_historical.py --zone {zone_name}")
        return None

    logger.info(f"[Labels] Traitement de {zone_name}...")
    df = pd.read_csv(input_path, parse_dates=["date"])
    climate = df["climate_zone"].iloc[0] if "climate_zone" in df.columns else "equatorial"
    thresholds = CLIMATE_THRESHOLDS.get(climate, CLIMATE_THRESHOLDS["equatorial"])

    # Application des labels physiques
    df["label_inondation"] = label_flood(df, thresholds)
    df["label_secheresse"] = label_drought(df, thresholds)
    df["label_chaleur"] = label_heat(df, thresholds)

    # Surcharge avec événements avérés
    df = apply_known_events(df, zone_name)

    # Statistiques labels
    total = len(df)
    for risk in ["inondation", "secheresse", "chaleur"]:
        col = f"label_{risk}"
        n_pos = df[col].sum()
        pct = 100 * n_pos / total
        logger.info(f"  {risk:12s}: {n_pos:5d}/{total} jours positifs ({pct:.1f}%)")

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

    # Détecter les zones disponibles
    if args.zone:
        zones = [args.zone]
    else:
        zones = [p.stem.replace("_historical", "")
                 for p in DATA_DIR.glob("*_historical.csv")]
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
