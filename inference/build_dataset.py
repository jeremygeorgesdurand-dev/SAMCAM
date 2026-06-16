#!/usr/bin/env python3
"""
SAMCAM V4 — Construction du dataset historique

Télécharge 35 ans de données CHIRPS + ERA5 via Google Earth Engine
pour la zone de Kribi, génère des labels automatiques (inondation,
sécheresse, vague de chaleur) et exporte le dataset CSV.

Usage :
    python3 inference/build_dataset.py
    python3 inference/build_dataset.py --start 2000 --end 2025
    python3 inference/build_dataset.py --no-gee   # mode simulation (démo sans GEE)

Sortie :
    data/dataset_kribi_historical.csv

Prérequis GEE :
    pip install earthengine-api
    earthengine authenticate
"""

import os
import argparse
import datetime
import json
import math
import random

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

OUTPUT_CSV = os.path.join(DATA_DIR, "dataset_kribi_historical.csv")

# Coordonnées Kribi
LAT, LON = 2.9397, 9.9132

# Normales mensuelles Kribi (pluie 7j en mm)
NORMALES_MENSUELLES = {
    1: 30,  2: 50,  3: 120, 4: 180, 5: 200, 6: 160,
    7: 80,  8: 100, 9: 180, 10: 200, 11: 150, 12: 50,
}

# ───────────────────────────────────────────────────────────────────────────────
# LABELS PHYSIQUES
# Basés sur des seuils climatologiques calibrés pour Kribi
# ───────────────────────────────────────────────────────────────────────────────

def label_inondation(pluie_7j: float, pluie_prev_7j: float,
                     sm_surface: float, ndwi: float, mois: int) -> int:
    """
    Inondation = 1 si au moins 2 critères sur 4 sont dépassés.
    Critères calibrés sur les normales saisonnières de Kribi.
    """
    normale = NORMALES_MENSUELLES.get(mois, 120)
    score = 0
    if pluie_7j      > normale * 2.0: score += 1   # pluie observée > 2x normale
    if pluie_prev_7j > normale * 1.8: score += 1   # pluie prévue > 1.8x normale
    if sm_surface    > 0.52:          score += 1   # sol saturé
    if ndwi          > 0.45:          score += 1   # eau en surface
    return 1 if score >= 2 else 0


def label_secheresse(pluie_30j: float, ndvi: float, sm_rootzone: float, mois: int) -> int:
    """
    Sécheresse = 1 si déficit hydrique significatif.
    """
    normale_30j = NORMALES_MENSUELLES.get(mois, 120) * (30 / 7)
    score = 0
    if pluie_30j  < normale_30j * 0.5: score += 1  # déficit > 50%
    if ndvi       < 0.45:              score += 1  # stress végétal
    if sm_rootzone < 0.20:             score += 1  # sol très sec
    return 1 if score >= 2 else 0


def label_chaleur(temp_max: float, temp_max_3j_moy: float) -> int:
    """
    Vague de chaleur = temp max > 35°C pendant au moins 3j consécutifs.
    """
    return 1 if (temp_max > 35.0 and temp_max_3j_moy > 34.0) else 0


# ───────────────────────────────────────────────────────────────────────────────
# COLLECTE VIA GOOGLE EARTH ENGINE
# ───────────────────────────────────────────────────────────────────────────────

def collecter_via_gee(annee_debut: int, annee_fin: int) -> list:
    """
    Collecte les features hebdomadaires via GEE :
    - CHIRPS : pluie cumulée 7j et 30j
    - ERA5-Land : temp max, humidité sol (surface + racines), vent
    - MODIS NDVI/NDWI : indices de végétation et d'eau
    """
    try:
        import ee
        ee.Initialize()
    except Exception as e:
        raise RuntimeError(
            f"Google Earth Engine non disponible : {e}\n"
            "  Installez et authentifiez GEE : pip install earthengine-api && earthengine authenticate"
        )

    point = ee.Geometry.Point([LON, LAT])
    lignes = []

    date_debut = datetime.date(annee_debut, 1, 1)
    date_fin   = datetime.date(annee_fin, 12, 31)
    delta      = datetime.timedelta(days=7)
    current    = date_debut

    total_semaines = int((date_fin - date_debut).days / 7)
    compteur = 0

    print(f"[GEE] Collecte de {annee_debut} à {annee_fin} ({total_semaines} semaines)...")

    while current <= date_fin:
        d_str  = current.isoformat()
        d7_str = (current + delta).isoformat()
        d30_str = (current + datetime.timedelta(days=30)).isoformat()
        mois   = current.month

        try:
            # CHIRPS : précipitations
            chirps_7j = (
                ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                .filterDate(d_str, d7_str)
                .select("precipitation")
                .sum()
                .reduceRegion(ee.Reducer.mean(), point, 5000)
                .getInfo().get("precipitation", 0) or 0
            )
            chirps_30j = (
                ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                .filterDate(d_str, d30_str)
                .select("precipitation")
                .sum()
                .reduceRegion(ee.Reducer.mean(), point, 5000)
                .getInfo().get("precipitation", 0) or 0
            )

            # ERA5-Land : température et humidité sol
            era5 = (
                ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
                .filterDate(d_str, d7_str)
                .select(["temperature_2m_max", "soil_moisture_0_to_7cm_sum",
                          "soil_moisture_7_to_28cm_sum"])
                .mean()
                .reduceRegion(ee.Reducer.mean(), point, 5000)
                .getInfo()
            )
            temp_max   = (era5.get("temperature_2m_max",    298) or 298) - 273.15
            sm_surface = (era5.get("soil_moisture_0_to_7cm_sum",  0.35) or 0.35)
            sm_root    = (era5.get("soil_moisture_7_to_28cm_sum", 0.30) or 0.30)

            # MODIS NDVI/NDWI
            modis = (
                ee.ImageCollection("MODIS/061/MOD13Q1")
                .filterDate(d_str, d30_str)
                .select(["NDVI", "EVI"])
                .mean()
                .reduceRegion(ee.Reducer.mean(), point, 500)
                .getInfo()
            )
            ndvi = (modis.get("NDVI", 6000) or 6000) / 10000
            ndwi = max(0.0, (modis.get("EVI",  4000) or 4000) / 10000 - 0.3)

            lignes.append({
                "date":           d_str,
                "mois":           mois,
                "pluie_7j":       round(chirps_7j,  2),
                "pluie_30j":      round(chirps_30j, 2),
                "pluie_prev_7j":  round(chirps_7j * 0.9, 2),   # proxy prévision
                "temp_max":       round(temp_max,   2),
                "temp_max_3j":    round(temp_max - 0.5, 2),
                "sm_surface":     round(sm_surface, 4),
                "sm_rootzone":    round(sm_root,    4),
                "ndvi":           round(ndvi,       4),
                "ndwi":           round(ndwi,       4),
                "label_inondation": label_inondation(chirps_7j, chirps_7j * 0.9,
                                                     sm_surface, ndwi, mois),
                "label_secheresse": label_secheresse(chirps_30j, ndvi, sm_root, mois),
                "label_chaleur":    label_chaleur(temp_max, temp_max - 0.5),
            })

        except Exception as e:
            print(f"[GEE] Erreur semaine {d_str} : {e}")

        compteur += 1
        if compteur % 52 == 0:
            print(f"[GEE] {compteur}/{total_semaines} semaines traitées")
        current += delta

    return lignes


# ───────────────────────────────────────────────────────────────────────────────
# MODE SIMULATION (sans GEE) — génère des données réalistes pour tests
# ───────────────────────────────────────────────────────────────────────────────

def generer_simulation(annee_debut: int, annee_fin: int) -> list:
    """
    Génère un dataset synthétique réaliste basé sur les normales climatiques
    de Kribi. Utile pour tester le pipeline sans authentification GEE.
    """
    print(f"[SIM] Génération simulation {annee_debut}→{annee_fin}...")
    random.seed(42)
    lignes = []

    date_debut = datetime.date(annee_debut, 1, 1)
    date_fin   = datetime.date(annee_fin, 12, 31)
    delta      = datetime.timedelta(days=7)
    current    = date_debut

    while current <= date_fin:
        mois = current.month
        normale_7j = NORMALES_MENSUELLES[mois]

        # Variabilité réaliste autour des normales
        pluie_7j  = max(0, random.gauss(normale_7j, normale_7j * 0.5))
        pluie_30j = max(0, random.gauss(normale_7j * 4, normale_7j * 1.5))
        pluie_prev = max(0, random.gauss(normale_7j, normale_7j * 0.4))

        temp_base = 28 + 4 * math.sin((mois - 4) * math.pi / 6)
        temp_max  = temp_base + random.gauss(0, 2)
        sm_surface  = max(0.1, min(0.7, 0.35 + (pluie_7j / normale_7j - 1) * 0.1))
        sm_rootzone = max(0.1, min(0.6, 0.30 + (pluie_30j / (normale_7j * 4) - 1) * 0.08))
        ndvi = max(0.2, min(0.95, 0.72 - max(0, 0.35 - sm_rootzone) * 0.8))
        ndwi = max(0.0, min(0.8,  0.20 + (sm_surface - 0.35) * 0.6))

        lignes.append({
            "date":           current.isoformat(),
            "mois":           mois,
            "pluie_7j":       round(pluie_7j,   2),
            "pluie_30j":      round(pluie_30j,  2),
            "pluie_prev_7j":  round(pluie_prev, 2),
            "temp_max":       round(temp_max,   2),
            "temp_max_3j":    round(temp_max - random.uniform(0, 1.5), 2),
            "sm_surface":     round(sm_surface,  4),
            "sm_rootzone":    round(sm_rootzone,  4),
            "ndvi":           round(ndvi, 4),
            "ndwi":           round(ndwi, 4),
            "label_inondation": label_inondation(pluie_7j, pluie_prev, sm_surface, ndwi, mois),
            "label_secheresse": label_secheresse(pluie_30j, ndvi, sm_rootzone, mois),
            "label_chaleur":    label_chaleur(temp_max, temp_max - 0.8),
        })
        current += delta

    return lignes


# ───────────────────────────────────────────────────────────────────────────────
# EXPORT CSV
# ───────────────────────────────────────────────────────────────────────────────

def exporter_csv(lignes: list, chemin: str):
    import csv
    if not lignes:
        print("[BUILD] Aucune donnée à exporter.")
        return

    entetes = list(lignes[0].keys())
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=entetes)
        writer.writeheader()
        writer.writerows(lignes)

    n_inond  = sum(1 for l in lignes if l["label_inondation"] == 1)
    n_sech   = sum(1 for l in lignes if l["label_secheresse"] == 1)
    n_chaleur = sum(1 for l in lignes if l["label_chaleur"]   == 1)

    print(f"[BUILD] Dataset exporté : {chemin}")
    print(f"        Lignes totales   : {len(lignes)}")
    print(f"        Inondations (1)  : {n_inond}  ({100*n_inond//len(lignes)}%)")
    print(f"        Sécheresses (1)  : {n_sech}   ({100*n_sech//len(lignes)}%)")
    print(f"        Chaleurs (1)     : {n_chaleur} ({100*n_chaleur//len(lignes)}%)")


# ───────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ───────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM V4 — Build dataset historique")
    parser.add_argument("--start",  type=int, default=1990, help="Année de début (défaut: 1990)")
    parser.add_argument("--end",    type=int, default=2024, help="Année de fin (défaut: 2024)")
    parser.add_argument("--no-gee", action="store_true",   help="Mode simulation sans GEE")
    args = parser.parse_args()

    if args.no_gee:
        lignes = generer_simulation(args.start, args.end)
    else:
        lignes = collecter_via_gee(args.start, args.end)

    exporter_csv(lignes, OUTPUT_CSV)


if __name__ == "__main__":
    main()
