#!/usr/bin/env python3
"""
build_labels.py — Génération des labels (ground truth) pour l'entraînement SAMCAM.

Stratégie hybride :
  1. Labels par seuils ZONAUX lus depuis config/zones/{slug}.json
     Structure réelle des JSONs :
       - pluie_normales_mensuelles_mm   : dict {"1".."12": float}
       - et0_normales_mensuelles_mm     : dict {"1".."12": float}
       - temp_max_normales_mensuelles_c : dict {"1".."12": float}
       - temp_max_std_mensuelles_c      : dict {"1".."12": float}
       - sm_rootzone_normales           : dict {"1".."12": float}
       - percentiles_hebdo_pluie        : dict {"1".."12": {p25,p50,p75,p90}}
       - seuils_inondation              : {pluie_7j_facteur_normale, sm_surface_seuil_haut, score_min_label_1}
       - seuils_secheresse              : {pluie_30j_facteur_deficit, sm_rootzone_delta_seuil, et0_facteur_stress, score_min_label_1}
       - seuils_chaleur                 : {temp_max_anomalie_sigma, temp_max_3j_anomalie_sigma, pluie_7j_max_sec, score_min_label_1}
       - saisons                        : dict des listes de mois
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
from typing import Optional

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR   = Path("data/historical")
OUTPUT_DIR = Path("data/historical")
CONFIG_DIR = Path("config/zones")

# Créer les dossiers AVANT d'initialiser le FileHandler
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
# Ces seuils sont exprimés dans le MÊME format que les JSONs zonaux
# pour que label_flood/drought/heat puissent s'en servir directement.
# ---------------------------------------------------------------------------
FALLBACK_PROFILES = {
    "equatorial": {
        "pluie_normales_mm":     [50, 80, 150, 230, 250, 200, 30, 40, 200, 280, 200, 70],
        "et0_normales_mm":       [22, 23, 22, 19, 18, 17, 20, 21, 19, 18, 18, 21],
        "tmax_normales_c":       [29, 30, 31, 30, 29, 28, 27, 27, 28, 28, 29, 29],
        "tmax_std_c":            [1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 1.2, 1.2, 1.3, 1.4, 1.5, 1.6],
        "sm_rootzone_normales":  [0.30, 0.32, 0.38, 0.45, 0.47, 0.43, 0.26, 0.28, 0.43, 0.48, 0.44, 0.32],
        "percentiles_p90":       [40, 72, 120, 175, 190, 155, 22, 30, 158, 210, 155, 58],
        "flood_facteur_7j":      1.2,
        "flood_sm_haut":         0.48,
        "flood_score_min":       2,
        "drought_facteur_30j":   0.65,
        "drought_sm_delta":      -0.06,
        "drought_et0_facteur":   1.2,
        "drought_score_min":     2,
        "heat_sigma":            1.0,
        "heat_sigma_3j":         0.5,
        "heat_pluie_max_sec":    10.0,
        "heat_score_min":        2,
    },
    "tropical_highland": {
        "pluie_normales_mm":     [20, 40, 90, 160, 200, 210, 200, 190, 180, 130, 50, 20],
        "et0_normales_mm":       [35, 34, 32, 28, 24, 21, 20, 20, 22, 26, 30, 34],
        "tmax_normales_c":       [26, 28, 29, 28, 27, 25, 24, 24, 25, 26, 26, 26],
        "tmax_std_c":            [2.5, 2.4, 2.2, 2.0, 1.8, 1.6, 1.4, 1.4, 1.6, 1.8, 2.1, 2.4],
        "sm_rootzone_normales":  [0.22, 0.26, 0.34, 0.42, 0.46, 0.47, 0.46, 0.45, 0.43, 0.36, 0.28, 0.22],
        "percentiles_p90":       [30, 58, 110, 165, 190, 195, 188, 180, 172, 125, 60, 30],
        "flood_facteur_7j":      1.3,
        "flood_sm_haut":         0.46,
        "flood_score_min":       2,
        "drought_facteur_30j":   0.60,
        "drought_sm_delta":      -0.08,
        "drought_et0_facteur":   1.3,
        "drought_score_min":     2,
        "heat_sigma":            1.0,
        "heat_sigma_3j":         0.5,
        "heat_pluie_max_sec":    8.0,
        "heat_score_min":        2,
    },
    "sahelian": {
        "pluie_normales_mm":     [0, 0, 2, 10, 35, 80, 155, 180, 115, 20, 1, 0],
        "et0_normales_mm":       [52, 56, 62, 62, 56, 46, 36, 32, 34, 42, 50, 50],
        "tmax_normales_c":       [32, 35, 38, 41, 40, 36, 32, 31, 33, 37, 36, 33],
        "tmax_std_c":            [3.0, 3.2, 3.0, 2.8, 2.5, 2.0, 1.6, 1.5, 1.7, 2.2, 2.6, 2.8],
        "sm_rootzone_normales":  [0.05, 0.05, 0.05, 0.07, 0.11, 0.18, 0.28, 0.32, 0.27, 0.14, 0.07, 0.05],
        "percentiles_p90":       [0, 2, 4, 12, 30, 66, 118, 135, 92, 22, 2, 0],
        "flood_facteur_7j":      1.6,
        "flood_sm_haut":         0.34,
        "flood_score_min":       2,
        "drought_facteur_30j":   0.45,
        "drought_sm_delta":      -0.10,
        "drought_et0_facteur":   1.7,
        "drought_score_min":     1,
        "heat_sigma":            0.7,
        "heat_sigma_3j":         0.4,
        "heat_pluie_max_sec":    3.0,
        "heat_score_min":        1,
    },
}


# ---------------------------------------------------------------------------
# Événements historiques avérés au Cameroun (EM-DAT + OCHA + presse)
# Format : (zone, date_debut, date_fin, type_risque)
# Sources : EM-DAT International Disaster Database, OCHA ReliefWeb,
#           Ministère de l'Environnement Cameroun, presse nationale
# ---------------------------------------------------------------------------
KNOWN_EVENTS = [
    # --- Inondations Nord/Adamaoua ---
    ("Maroua",       "2012-08-01", "2012-09-30", "inondation"),
    ("Maroua",       "2020-08-15", "2020-09-15", "inondation"),
    ("Maroua",       "2022-08-01", "2022-09-30", "inondation"),  # OCHA flash update
    ("Garoua",       "2012-08-01", "2012-09-15", "inondation"),
    ("Garoua",       "2020-09-01", "2020-10-15", "inondation"),
    ("Garoua",       "2022-09-01", "2022-10-15", "inondation"),  # OCHA 2022
    ("Ngaoundere",   "2020-08-10", "2020-09-10", "inondation"),
    ("Ngaoundere",   "2019-09-01", "2019-10-15", "inondation"),
    ("Ngaoundere",   "2023-08-01", "2023-09-15", "inondation"),  # ReliefWeb 2023
    # --- Inondations zones équatoriales/highlands ---
    ("Kribi",        "2019-06-01", "2019-07-15", "inondation"),
    ("Kribi",        "2017-08-01", "2017-09-30", "inondation"),
    ("Kribi",        "2021-06-15", "2021-07-31", "inondation"),
    ("Kribi",        "2022-09-01", "2022-10-15", "inondation"),  # OCHA 2022
    ("Kumba",        "2020-10-01", "2020-11-15", "inondation"),
    ("Kumba",        "2018-09-01", "2018-10-31", "inondation"),
    ("Kumba",        "2022-09-15", "2022-10-31", "inondation"),  # OCHA 2022
    ("Kumba",        "2016-09-01", "2016-10-15", "inondation"),  # EM-DAT 2016
    ("Yaounde_peri", "2020-09-01", "2020-10-31", "inondation"),
    ("Yaounde_peri", "2019-08-15", "2019-09-30", "inondation"),
    ("Yaounde_peri", "2022-08-20", "2022-09-30", "inondation"),  # ReliefWeb 2022
    ("Yaounde_peri", "2016-08-01", "2016-09-30", "inondation"),  # OCHA 2016
    ("Bafoussam",    "2019-10-01", "2019-10-31", "inondation"),
    ("Bafoussam",    "2020-09-15", "2020-10-31", "inondation"),
    ("Bafoussam",    "2023-09-01", "2023-10-15", "inondation"),  # OCHA 2023
    ("Bafoussam",    "2016-09-20", "2016-10-31", "inondation"),  # EM-DAT 2016
    ("Ebolowa",      "2021-09-01", "2021-10-15", "inondation"),
    ("Ebolowa",      "2022-09-01", "2022-10-15", "inondation"),
    ("Ebolowa",      "2019-09-15", "2019-10-31", "inondation"),  # ReliefWeb 2019
    ("Ebolowa",      "2017-09-01", "2017-10-15", "inondation"),  # EM-DAT 2017
    # --- Sécheresses ---
    ("Maroua",       "2017-04-01", "2017-09-30", "secheresse"),
    ("Maroua",       "2022-01-01", "2022-06-30", "secheresse"),
    ("Maroua",       "2015-01-01", "2015-06-30", "secheresse"),  # EM-DAT 2015 Sahel
    ("Garoua",       "2017-04-01", "2017-09-30", "secheresse"),
    ("Garoua",       "2021-01-01", "2021-05-31", "secheresse"),
    ("Garoua",       "2015-01-01", "2015-06-30", "secheresse"),  # EM-DAT 2015 Sahel
    ("Ngaoundere",   "2018-01-01", "2018-03-31", "secheresse"),
    ("Ngaoundere",   "2021-11-01", "2022-03-31", "secheresse"),  # longue saison sèche 2021-22
    ("Ngaoundere",   "2015-11-01", "2016-03-31", "secheresse"),  # EM-DAT 2016
    ("Kribi",        "2015-07-01", "2015-09-30", "secheresse"),
    ("Bafoussam",    "2016-01-01", "2016-03-31", "secheresse"),
    ("Bafoussam",    "2021-12-01", "2022-02-28", "secheresse"),  # sécheresse highland
    ("Yaounde_peri", "2016-01-01", "2016-03-31", "secheresse"),
    ("Yaounde_peri", "2021-12-01", "2022-02-28", "secheresse"),  # OCHA 2022 saison sèche
    ("Kumba",        "2016-01-01", "2016-02-28", "secheresse"),  # EM-DAT 2016
    ("Ebolowa",      "2016-01-01", "2016-02-28", "secheresse"),  # EM-DAT 2016
    # --- Vagues de chaleur ---
    ("Maroua",       "2016-03-01", "2016-05-31", "chaleur"),
    ("Maroua",       "2019-03-01", "2019-05-15", "chaleur"),
    ("Maroua",       "2023-03-15", "2023-05-15", "chaleur"),  # presse nationale 2023
    ("Garoua",       "2016-03-01", "2016-05-31", "chaleur"),
    ("Garoua",       "2023-03-15", "2023-05-15", "chaleur"),
    ("Ngaoundere",   "2021-02-01", "2021-04-30", "chaleur"),
    ("Ngaoundere",   "2019-02-15", "2019-04-30", "chaleur"),
    ("Ngaoundere",   "2023-02-01", "2023-04-15", "chaleur"),  # anomalie thermique 2023
    ("Bafoussam",    "2021-02-01", "2021-04-15", "chaleur"),
    ("Bafoussam",    "2019-02-01", "2019-04-15", "chaleur"),  # chaleur highland 2019
    ("Yaounde_peri", "2022-02-01", "2022-04-30", "chaleur"),
    ("Yaounde_peri", "2019-02-01", "2019-04-30", "chaleur"),  # OCHA 2019
    ("Kumba",        "2023-02-01", "2023-04-15", "chaleur"),  # anomalie 2023
    ("Ebolowa",      "2023-02-15", "2023-04-30", "chaleur"),  # anomalie 2023
]


# ---------------------------------------------------------------------------
# Chargement des seuils zonaux depuis config/zones/{slug}.json
# Lit la VRAIE structure des JSONs SAMCAM (pas per_hazard_thresholds)
# ---------------------------------------------------------------------------
def _dict_to_monthly_list(d: dict) -> list:
    """Convertit {"1": v1, ..., "12": v12} en liste [v1, ..., v12]."""
    return [float(d.get(str(m), 0.0)) for m in range(1, 13)]


def load_zone_config(zone_name: str, climate_type: str = "equatorial") -> dict:
    """
    Charge et normalise la config d'une zone depuis config/zones/{slug}.json.

    Retourne un dict unifié avec toutes les clés nécessaires aux fonctions
    de labellisation, quel que soit le mode de chargement (JSON ou fallback).

    Clés retournées :
      pluie_normales_mm    : list[12]  — normales mensuelles précipitations (mm/mois)
      et0_normales_mm      : list[12]  — ETP mensuelle (mm/mois)
      tmax_normales_c      : list[12]  — Tmax normale mensuelle (°C)
      tmax_std_c           : list[12]  — Tmax écart-type mensuel (°C) → anomalies relatives
      sm_rootzone_normales : list[12]  — humidité sol zone racinaire normale
      percentiles_p90      : list[12]  — percentile 90 pluie hebdomadaire par mois (mm/sem)
      flood_facteur_7j     : float     — seuil = facteur × normale mensuelle (sur 7j)
      flood_sm_haut        : float     — seuil absolu humidité sol (saturation)
      flood_score_min      : int       — nombre de critères requis pour label=1
      drought_facteur_30j  : float     — pluie 30j < facteur × normale → déficit
      drought_sm_delta     : float     — delta SM sous normale → alerte
      drought_et0_facteur  : float     — ET0 > facteur × normale → stress
      drought_score_min    : int
      heat_sigma           : float     — Tmax > normale + sigma × std → alerte journalière
      heat_sigma_3j        : float     — seuil sur anomalie glissante 3j
      heat_pluie_max_sec   : float     — pluie 7j max pour qualifier période sèche
      heat_score_min       : int
      source_json          : bool      — True si chargé depuis JSON, False si fallback
      regime               : str       — identifiant du régime climatique
      saisons              : dict      — mois par saison
    """
    slug = zone_name.lower().replace(" ", "_").replace("-", "_")
    config_path = CONFIG_DIR / f"{slug}.json"

    if not config_path.exists():
        logger.warning(
            f"[Config] Pas de JSON pour '{zone_name}' ({config_path}). "
            f"Fallback vers profil '{climate_type}'."
        )
        fb = FALLBACK_PROFILES.get(climate_type, FALLBACK_PROFILES["equatorial"])
        return {**fb, "source_json": False, "regime": climate_type, "saisons": {}}

    with open(config_path) as f:
        cfg = json.load(f)

    # --- Normales mensuelles (toujours présentes dans les JSONs SAMCAM) ---
    pluie_mm     = _dict_to_monthly_list(cfg.get("pluie_normales_mensuelles_mm", {}))
    et0_mm       = _dict_to_monthly_list(cfg.get("et0_normales_mensuelles_mm", {}))
    tmax_c       = _dict_to_monthly_list(cfg.get("temp_max_normales_mensuelles_c", {}))
    tmax_std_c   = _dict_to_monthly_list(cfg.get("temp_max_std_mensuelles_c", {}))
    sm_rootzone  = _dict_to_monthly_list(cfg.get("sm_rootzone_normales", {}))

    # Percentiles hebdomadaires p90 (mm/semaine) → proxy seuil absolu inondation
    perc_raw = cfg.get("percentiles_hebdo_pluie", {})
    p90_list = [float(perc_raw.get(str(m), {}).get("p90", pluie_mm[m-1] * 0.5)) for m in range(1, 13)]

    # --- Seuils inondation ---
    s_flood = cfg.get("seuils_inondation", {})
    flood_facteur_7j   = float(s_flood.get("pluie_7j_facteur_normale", 1.3))
    flood_sm_haut      = float(s_flood.get("sm_surface_seuil_haut", 0.45))
    flood_score_min    = int(s_flood.get("score_min_label_1", 2))

    # --- Seuils sécheresse ---
    s_drought = cfg.get("seuils_secheresse", {})
    drought_facteur_30j = float(s_drought.get("pluie_30j_facteur_deficit", 0.60))
    drought_sm_delta    = float(s_drought.get("sm_rootzone_delta_seuil", -0.07))
    drought_et0_facteur = float(s_drought.get("et0_facteur_stress", 1.3))
    drought_score_min   = int(s_drought.get("score_min_label_1", 2))

    # --- Seuils chaleur ---
    s_heat = cfg.get("seuils_chaleur", {})
    heat_sigma        = float(s_heat.get("temp_max_anomalie_sigma", 1.0))
    heat_sigma_3j     = float(s_heat.get("temp_max_3j_anomalie_sigma", 0.5))
    heat_pluie_max    = float(s_heat.get("pluie_7j_max_sec", 8.0))
    heat_score_min    = int(s_heat.get("score_min_label_1", 2))

    regime  = cfg.get("_meta", {}).get("regime", "unknown")
    saisons = cfg.get("saisons", {})

    logger.info(
        f"[Config] '{zone_name}' → JSON chargé ({regime}) | "
        f"pluie_normales: {[round(v) for v in pluie_mm]} mm/mois"
    )

    return {
        "pluie_normales_mm":     pluie_mm,
        "et0_normales_mm":       et0_mm,
        "tmax_normales_c":       tmax_c,
        "tmax_std_c":            tmax_std_c,
        "sm_rootzone_normales":  sm_rootzone,
        "percentiles_p90":       p90_list,
        "flood_facteur_7j":      flood_facteur_7j,
        "flood_sm_haut":         flood_sm_haut,
        "flood_score_min":       flood_score_min,
        "drought_facteur_30j":   drought_facteur_30j,
        "drought_sm_delta":      drought_sm_delta,
        "drought_et0_facteur":   drought_et0_facteur,
        "drought_score_min":     drought_score_min,
        "heat_sigma":            heat_sigma,
        "heat_sigma_3j":         heat_sigma_3j,
        "heat_pluie_max_sec":    heat_pluie_max,
        "heat_score_min":        heat_score_min,
        "source_json":           True,
        "regime":                regime,
        "saisons":               saisons,
    }


# ---------------------------------------------------------------------------
# Helpers : vecteurs mensuels alignés sur l'index du DataFrame
# ---------------------------------------------------------------------------
def _monthly_vector(df: pd.DataFrame, monthly_list: list,
                    date_col: str = "date") -> pd.Series:
    """Retourne un vecteur aligné sur df avec la valeur mensuelle correspondante."""
    months = pd.to_datetime(df[date_col]).dt.month if date_col in df.columns \
             else df.index.to_series().dt.month
    return months.map(lambda m: monthly_list[int(m) - 1])


def _get_rain_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["precipitation_sum", "nasa_prectotcorr"]:
        if c in df.columns:
            return c
    return None


def _get_sm_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["soil_moisture_0_to_7cm_mean", "nasa_gwettop", "nasa_gwetroot"]:
        if c in df.columns:
            return c
    return None


def _get_tmax_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["temperature_2m_max", "nasa_t2m_max", "nasa_t2m"]:
        if c in df.columns:
            return c
    return None


# ---------------------------------------------------------------------------
# Fonctions de labellisation — système de score pondéré
# ---------------------------------------------------------------------------
def label_flood(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """
    Label inondation — système de score multi-critères.

    Critères (chacun vaut 1 point) :
      1. Pluie journalière ≥ percentile p90 hebdomadaire mensuel (seuil absolu fort)
      2. Cumul 7j ≥ flood_facteur_7j × normale mensuelle 7j (anomalie relative)
      3. Humidité sol surface ≥ flood_sm_haut (saturation)
    Label = 1 si score ≥ flood_score_min (2 par défaut, 1 pour zones très humides)
    """
    rain_col = _get_rain_col(df)
    sm_col   = _get_sm_col(df)

    score = pd.Series(0, index=df.index)

    # Critère 1 : pluie journalière vs percentile p90 mensuel
    if rain_col:
        p90_vec = _monthly_vector(df, cfg["percentiles_p90"])
        # p90 est hebdomadaire → diviser par 7 pour obtenir équivalent journalier
        crit1 = df[rain_col] >= (p90_vec / 7.0)
        score += crit1.astype(int)

    # Critère 2 : cumul 7j vs normale × facteur
    if "rain_7d" in df.columns:
        # normale 7j ≈ normale mensuelle / 30 × 7
        pluie_norm_7j = _monthly_vector(df, cfg["pluie_normales_mm"]) / 30.0 * 7.0
        crit2 = df["rain_7d"] >= (cfg["flood_facteur_7j"] * pluie_norm_7j)
        score += crit2.astype(int)
    elif rain_col:
        # Fallback : pluie journalière × 1.5 comme proxy 7j
        pluie_norm_7j = _monthly_vector(df, cfg["pluie_normales_mm"]) / 30.0 * 7.0
        crit2 = df[rain_col] * 1.5 >= (cfg["flood_facteur_7j"] * pluie_norm_7j)
        score += crit2.astype(int)

    # Critère 3 : saturation sol
    if sm_col:
        crit3 = df[sm_col] >= cfg["flood_sm_haut"]
        score += crit3.astype(int)

    label = (score >= cfg["flood_score_min"]).astype(int)
    logger.debug(f"  Flood: {label.sum()} jours positifs (score_min={cfg['flood_score_min']})")
    return label


def label_drought(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """
    Label sécheresse — système de score multi-critères avec anomalies relatives.

    Critères (chacun vaut 1 point) :
      1. Pluie 30j < drought_facteur_30j × normale mensuelle (déficit relatif)
      2. Humidité sol racinaire < normale mensuelle + drought_sm_delta (delta relatif)
      3. ET0 > drought_et0_facteur × normale ET0 mensuelle (stress évaporatif)
      4. SPI-3 < -0.8 (signal synthétique si disponible)
    Label = 1 si score ≥ drought_score_min (1 pour zones sahéliennes, 2 sinon)
    """
    score = pd.Series(0, index=df.index)

    # Critère 1 : déficit pluviométrique relatif (30j)
    rain_col = _get_rain_col(df)
    pluie_norm = _monthly_vector(df, cfg["pluie_normales_mm"])

    if "rain_30d" in df.columns:
        seuil_pluie = cfg["drought_facteur_30j"] * pluie_norm
        crit1 = df["rain_30d"] < seuil_pluie
        score += crit1.astype(int)
    elif rain_col:
        # Proxy : pluie journalière × 30 comme estimation
        seuil_pluie = cfg["drought_facteur_30j"] * pluie_norm
        crit1 = df[rain_col] * 30 < seuil_pluie
        score += crit1.astype(int)

    # Critère 2 : déficit humidité sol racinaire (delta relatif à la normale)
    sm_col = None
    for c in ["soil_moisture_28_to_100cm_mean", "nasa_gwetroot",
              "soil_moisture_7_to_28cm_mean", "soil_moisture_0_to_7cm_mean", "nasa_gwettop"]:
        if c in df.columns:
            sm_col = c
            break
    if sm_col:
        sm_norm = _monthly_vector(df, cfg["sm_rootzone_normales"])
        seuil_sm = sm_norm + cfg["drought_sm_delta"]  # ex: 0.32 + (-0.06) = 0.26
        crit2 = df[sm_col] < seuil_sm
        score += crit2.astype(int)

    # Critère 3 : stress évaporatif — ET0 > facteur × normale
    et0_col = None
    for c in ["et0_fao_evapotranspiration", "nasa_evland"]:
        if c in df.columns:
            et0_col = c
            break
    if et0_col:
        et0_norm_daily = _monthly_vector(df, cfg["et0_normales_mm"]) / 30.0
        crit3 = df[et0_col] > (cfg["drought_et0_facteur"] * et0_norm_daily)
        score += crit3.astype(int)

    # Critère 4 : SPI-3 (signal intégré si disponible)
    if "spi3_approx" in df.columns:
        crit4 = df["spi3_approx"] < -0.8
        score += crit4.astype(int)

    label = (score >= cfg["drought_score_min"]).astype(int)
    logger.debug(f"  Drought: {label.sum()} jours positifs (score_min={cfg['drought_score_min']})")
    return label


def label_heat(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """
    Label vague de chaleur — anomalies relatives à la normale mensuelle + std.

    Principe : utilise (Tmax - normale_mensuelle) / std_mensuelle = anomalie sigma
    → adapté aux zones d'altitude (Bafoussam 26°C ≠ Maroua 41°C en absolu)

    Critères (chacun vaut 1 point) :
      1. Anomalie journalière ≥ heat_sigma × std_mensuelle
      2. Anomalie glissante 3j ≥ heat_sigma_3j × std_mensuelle
      3. Période sèche concomitante : pluie 7j ≤ heat_pluie_max_sec
    Label = 1 si score ≥ heat_score_min
    """
    tmax_col = _get_tmax_col(df)
    if tmax_col is None:
        logger.warning("Colonne Tmax manquante pour label chaleur")
        return pd.Series(0, index=df.index)

    score = pd.Series(0, index=df.index)

    tmax_norm = _monthly_vector(df, cfg["tmax_normales_c"])
    tmax_std  = _monthly_vector(df, cfg["tmax_std_c"])
    # Protéger contre std=0
    tmax_std  = tmax_std.clip(lower=0.5)

    anomalie_j = df[tmax_col] - tmax_norm

    # Critère 1 : anomalie journalière
    crit1 = anomalie_j >= (cfg["heat_sigma"] * tmax_std)
    score += crit1.astype(int)

    # Critère 2 : anomalie glissante 3j
    anom_3j = anomalie_j.rolling(3, min_periods=2).mean()
    crit2 = anom_3j >= (cfg["heat_sigma_3j"] * tmax_std)
    score += crit2.fillna(False).astype(int)

    # Critère 3 : période sèche concomitante
    rain_col = _get_rain_col(df)
    if "rain_7d" in df.columns:
        crit3 = df["rain_7d"] <= cfg["heat_pluie_max_sec"]
        score += crit3.astype(int)
    elif rain_col:
        crit3 = df[rain_col] * 7 <= cfg["heat_pluie_max_sec"]
        score += crit3.astype(int)

    label = (score >= cfg["heat_score_min"]).astype(int)
    logger.debug(f"  Heat: {label.sum()} jours positifs (score_min={cfg['heat_score_min']})")
    return label


# ---------------------------------------------------------------------------
# Surcharge avec événements historiques avérés
# ---------------------------------------------------------------------------
def apply_known_events(df: pd.DataFrame, zone_name: str) -> pd.DataFrame:
    """Surcharge les labels avec les événements historiques avérés."""
    zone_events = [(z, s, e, t) for z, s, e, t in KNOWN_EVENTS if z == zone_name]

    if not zone_events:
        return df

    col_map = {
        "inondation": "label_inondation",
        "secheresse":  "label_secheresse",
        "chaleur":     "label_chaleur",
    }
    for zone, start, end, risk_type in zone_events:
        mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
        col = col_map.get(risk_type)
        if col and col in df.columns:
            df.loc[mask, col] = 1
            count = int(mask.sum())
            logger.info(f"  [EM-DAT/OCHA] {zone} {risk_type} {start}→{end} : {count} jours forcés à 1")

    return df


# ---------------------------------------------------------------------------
# Pipeline principal pour une zone
# ---------------------------------------------------------------------------
def build_labels_for_zone(zone_name: str) -> Path:
    """Construit les labels pour une zone et sauvegarde le CSV labellisé."""
    input_path  = DATA_DIR   / f"{zone_name}_historical.csv"
    output_path = OUTPUT_DIR / f"{zone_name}_labeled.csv"

    if not input_path.exists():
        logger.error(f"Fichier historique manquant : {input_path}")
        logger.error(f"➡️  Lancez d'abord : python data_collection/collect_historical.py --zone {zone_name}")
        return None

    logger.info(f"\n{'='*55}")
    logger.info(f"[Labels] Traitement de {zone_name}...")
    logger.info(f"{'='*55}")

    df = pd.read_csv(input_path, parse_dates=["date"])

    # Déterminer le type climatique de fallback depuis la colonne ou un mapping
    climate_fallback = "equatorial"
    if "climate_zone" in df.columns:
        cz = df["climate_zone"].iloc[0]
        if "sahelian" in str(cz).lower() or "sahel" in str(cz).lower():
            climate_fallback = "sahelian"
        elif "highland" in str(cz).lower() or "altitude" in str(cz).lower():
            climate_fallback = "tropical_highland"

    # Charger la config zonale (JSON ou fallback)
    cfg = load_zone_config(zone_name, climate_fallback)

    if cfg["source_json"]:
        logger.info(f"  ✅ Config JSON individuelle → régime : {cfg['regime']}")
    else:
        logger.info(f"  ⚠️  Fallback générique (profil: {climate_fallback})")

    # Générer les labels
    df["label_inondation"] = label_flood(df, cfg)
    df["label_secheresse"] = label_drought(df, cfg)
    df["label_chaleur"]    = label_heat(df, cfg)

    # Surcharge avec événements avérés
    df = apply_known_events(df, zone_name)

    # Statistiques
    total = len(df)
    for risk in ["inondation", "secheresse", "chaleur"]:
        col   = f"label_{risk}"
        n_pos = int(df[col].sum())
        pct   = 100 * n_pos / total
        flag  = "⚠️ " if pct < 2 or pct > 45 else "   "
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
        print("\n➡️  Étape suivante : python training/train_zonal_models.py --force")


if __name__ == "__main__":
    main()
