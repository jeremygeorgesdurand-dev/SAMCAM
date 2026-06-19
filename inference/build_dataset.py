#!/usr/bin/env python3
"""
SAMCAM V4.1 — Construction du dataset historique

Télécharge 35 ans de données CHIRPS + ERA5 via Google Earth Engine
pour la zone de Kribi, génère des labels automatiques (inondation,
sécheresse, vague de chaleur) et exporte le dataset CSV.

NOUVEAUTÉS V4.1 :
    - +6 features dérivées : sin_mois, cos_mois, anomalie_pluie_7j,
      ratio_pluie_30j_7j, trend_sm, pluie_prev_7j indépendante
    - Seuil chaleur adapté à Kribi (33°C au lieu de 35°C)
    - Simulation : pluie_prev_7j décorrélée de pluie_7j (bruit indépendant)
    - temp_max_3j calculée réellement (moyenne glissante 3 semaines)

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
# FEATURES DÉRIVÉES
# ───────────────────────────────────────────────────────────────────────────────

def features_derivees(mois: int, pluie_7j: float, pluie_30j: float,
                      sm_surface: float, sm_rootzone: float,
                      sm_surface_prev: float = None) -> dict:
    """
    Calcule les 6 features dérivées qui améliorent significativement le modèle.

    - sin_mois / cos_mois   : encodage cyclique du mois (évite la discontinuité 12→1)
    - anomalie_pluie_7j     : écart à la normale mensuelle normalisé
    - ratio_pluie_30j_7j    : ratio pluie longue/courte période (détecte tendances)
    - trend_sm              : variation humidité sol surface (montée = inondation future)
    - sm_deficit            : déficit hydrique racinaire normalisé (sécheresse)
    """
    normale = NORMALES_MENSUELLES.get(mois, 120)
    normale_30j = normale * (30 / 7)

    sin_m = round(math.sin(2 * math.pi * mois / 12), 4)
    cos_m = round(math.cos(2 * math.pi * mois / 12), 4)

    anomalie = round((pluie_7j - normale) / max(1.0, normale), 4)

    # ratio > 1 → pluies récentes supérieures à la tendance longue
    ratio = round(pluie_30j / max(1.0, pluie_7j * (30 / 7)), 4) if pluie_7j > 0 else 1.0
    ratio = min(ratio, 5.0)  # borne pour éviter divergence si pluie_7j ≈ 0

    # trend_sm : variation sm_surface entre semaine courante et précédente
    trend = round(sm_surface - sm_surface_prev, 4) if sm_surface_prev is not None else 0.0

    # déficit hydrique racinaire : 0 = normal, 1 = très sec
    sm_deficit_racine = round(max(0.0, (0.30 - sm_rootzone) / 0.30), 4)

    return {
        "sin_mois":        sin_m,
        "cos_mois":        cos_m,
        "anomalie_pluie":  anomalie,
        "ratio_30j_7j":    ratio,
        "trend_sm":        trend,
        "sm_deficit":      sm_deficit_racine,
    }


# ───────────────────────────────────────────────────────────────────────────────
# LABELS PHYSIQUES
# ───────────────────────────────────────────────────────────────────────────────

def label_inondation(pluie_7j: float, pluie_prev_7j: float,
                     sm_surface: float, ndwi: float, mois: int) -> int:
    """
    Inondation = 1 si au moins 2 critères sur 4 sont dépassés.
    Seuils calibrés pour ~15% positifs en simulation.
    """
    normale = NORMALES_MENSUELLES.get(mois, 120)
    score = 0
    if pluie_7j      > normale * 1.5:  score += 1
    if pluie_prev_7j > normale * 1.3:  score += 1
    if sm_surface    > 0.45:           score += 1
    if ndwi          > 0.30:           score += 1
    return 1 if score >= 2 else 0


def label_secheresse(pluie_30j: float, ndvi: float, sm_rootzone: float, mois: int) -> int:
    """
    Sécheresse = 1 si déficit hydrique significatif (au moins 2 critères).
    """
    normale_30j = NORMALES_MENSUELLES.get(mois, 120) * (30 / 7)
    score = 0
    if pluie_30j   < normale_30j * 0.65: score += 1
    if ndvi        < 0.55:               score += 1
    if sm_rootzone < 0.25:               score += 1
    return 1 if score >= 2 else 0


def label_chaleur(temp_max: float, temp_max_3j_moy: float) -> int:
    """
    Vague de chaleur adaptée au climat tropical de Kribi.
    Seuil abaissé à 33°C (au lieu de 35°C) car Kribi est côtier/équatorial.
    """
    return 1 if (temp_max > 33.0 and temp_max_3j_moy > 32.0) else 0


# ───────────────────────────────────────────────────────────────────────────────
# COLLECTE VIA GOOGLE EARTH ENGINE
# ───────────────────────────────────────────────────────────────────────────────

def collecter_via_gee(annee_debut: int, annee_fin: int) -> list:
    """
    Collecte les features hebdomadaires via GEE :
    - CHIRPS     : pluie cumulée 7j et 30j
    - ERA5-Land  : temp max, humidité sol (surface + racines)
    - MODIS      : NDVI/NDWI (végétation et eau)
    + Calcul des 6 features dérivées V4.1
    """
    try:
        import ee
        ee.Initialize()
    except Exception as e:
        raise RuntimeError(
            f"Google Earth Engine non disponible : {e}\n"
            "  pip install earthengine-api && earthengine authenticate"
        )

    point = ee.Geometry.Point([LON, LAT])
    lignes = []

    date_debut = datetime.date(annee_debut, 1, 1)
    date_fin   = datetime.date(annee_fin, 12, 31)
    delta      = datetime.timedelta(days=7)
    current    = date_debut
    total_semaines = int((date_fin - date_debut).days / 7)
    compteur = 0
    sm_surface_prev = None

    print(f"[GEE] Collecte de {annee_debut} à {annee_fin} ({total_semaines} semaines)...")

    while current <= date_fin:
        d_str   = current.isoformat()
        d7_str  = (current + delta).isoformat()
        d30_str = (current + datetime.timedelta(days=30)).isoformat()
        mois    = current.month

        try:
            chirps_7j = (
                ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                .filterDate(d_str, d7_str).select("precipitation").sum()
                .reduceRegion(ee.Reducer.mean(), point, 5000)
                .getInfo().get("precipitation", 0) or 0
            )
            chirps_30j = (
                ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                .filterDate(d_str, d30_str).select("precipitation").sum()
                .reduceRegion(ee.Reducer.mean(), point, 5000)
                .getInfo().get("precipitation", 0) or 0
            )
            # Prévisions J+7 : utiliser la semaine suivante dans CHIRPS (proxy)
            chirps_prev = (
                ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                .filterDate(d7_str, (current + datetime.timedelta(days=14)).isoformat())
                .select("precipitation").sum()
                .reduceRegion(ee.Reducer.mean(), point, 5000)
                .getInfo().get("precipitation", 0) or 0
            )
            era5 = (
                ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
                .filterDate(d_str, d7_str)
                .select(["temperature_2m_max", "soil_moisture_0_to_7cm_sum",
                          "soil_moisture_7_to_28cm_sum"])
                .mean().reduceRegion(ee.Reducer.mean(), point, 5000).getInfo()
            )
            # Moyenne glissante 3 semaines pour temp_max_3j
            era5_3j = (
                ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
                .filterDate(d_str, (current + datetime.timedelta(days=21)).isoformat())
                .select(["temperature_2m_max"])
                .mean().reduceRegion(ee.Reducer.mean(), point, 5000).getInfo()
            )
            temp_max    = (era5.get("temperature_2m_max",  298) or 298) - 273.15
            temp_max_3j = (era5_3j.get("temperature_2m_max", 298) or 298) - 273.15
            sm_surface  = float(era5.get("soil_moisture_0_to_7cm_sum",  0.35) or 0.35)
            sm_root     = float(era5.get("soil_moisture_7_to_28cm_sum", 0.30) or 0.30)
            modis = (
                ee.ImageCollection("MODIS/061/MOD13Q1")
                .filterDate(d_str, d30_str).select(["NDVI", "EVI"])
                .mean().reduceRegion(ee.Reducer.mean(), point, 500).getInfo()
            )
            ndvi = (modis.get("NDVI", 6000) or 6000) / 10000
            ndwi = max(0.0, (modis.get("EVI",  4000) or 4000) / 10000 - 0.3)

            deriv = features_derivees(mois, chirps_7j, chirps_30j,
                                      sm_surface, sm_root, sm_surface_prev)
            sm_surface_prev = sm_surface

            row = {
                "date":             d_str,
                "mois":             mois,
                "pluie_7j":         round(chirps_7j,   2),
                "pluie_30j":        round(chirps_30j,  2),
                "pluie_prev_7j":    round(chirps_prev, 2),
                "temp_max":         round(temp_max,    2),
                "temp_max_3j":      round(temp_max_3j, 2),
                "sm_surface":       round(sm_surface,  4),
                "sm_rootzone":      round(sm_root,     4),
                "ndvi":             round(ndvi,        4),
                "ndwi":             round(ndwi,        4),
                **{k: round(v, 4) for k, v in deriv.items()},
                "label_inondation": label_inondation(chirps_7j, chirps_prev, sm_surface, ndwi, mois),
                "label_secheresse": label_secheresse(chirps_30j, ndvi, sm_root, mois),
                "label_chaleur":    label_chaleur(temp_max, temp_max_3j),
            }
            lignes.append(row)

        except Exception as e:
            print(f"[GEE] Erreur semaine {d_str} : {e}")
            sm_surface_prev = None

        compteur += 1
        if compteur % 52 == 0:
            print(f"[GEE] {compteur}/{total_semaines} semaines traitées")
        current += delta

    return lignes


# ───────────────────────────────────────────────────────────────────────────────
# MODE SIMULATION
# ───────────────────────────────────────────────────────────────────────────────

_EL_NINO_ANNEES = {1992, 1994, 1997, 1998, 2002, 2004, 2006, 2009, 2015, 2018, 2023}
_LA_NINA_ANNEES = {1995, 1999, 2000, 2007, 2010, 2011, 2020, 2021, 2022}
_MOIS_POINTE_PLUIES = {4, 5, 6, 9, 10, 11}


def _facteur_enso(annee: int) -> tuple:
    if annee in _EL_NINO_ANNEES:
        return 0.70, 1.40
    elif annee in _LA_NINA_ANNEES:
        return 1.40, 0.60
    return 1.0, 1.0


def generer_simulation(annee_debut: int, annee_fin: int) -> list:
    """
    Génère un dataset synthétique réaliste avec :
    - Modulation ENSO par année
    - pluie_prev_7j INDÉPENDANTE de pluie_7j (bruit séparé) — correction V4.1
    - temp_max_3j = moyenne glissante réelle sur 3 semaines
    - 6 features dérivées calculées sur chaque ligne
    - Injection contrôlée d'événements extrêmes (~15% inondation, ~8% sécheresse)
    """
    print(f"[SIM] Génération simulation {annee_debut}→{annee_fin} (V4.1)...")
    rng = random.Random(42)
    lignes = []

    date_debut = datetime.date(annee_debut, 1, 1)
    date_fin   = datetime.date(annee_fin, 12, 31)
    delta      = datetime.timedelta(days=7)
    current    = date_debut

    n_total_attendu  = int((date_fin - date_debut).days / 7) + 1
    quota_inondation = int(n_total_attendu * 0.15)
    quota_secheresse = int(n_total_attendu * 0.08)
    injections_inond = set(rng.sample(range(n_total_attendu), quota_inondation))
    injections_sech  = set(rng.sample(
        [i for i in range(n_total_attendu) if i not in injections_inond],
        quota_secheresse
    ))

    # Historique glissant pour temp_max_3j (vraie moyenne glissante)
    historique_temp = []
    sm_surface_prev = None
    idx = 0

    while current <= date_fin:
        mois  = current.month
        annee = current.year
        normale_7j  = NORMALES_MENSUELLES[mois]
        normale_30j = normale_7j * (30 / 7)
        facteur_pluie, facteur_sech = _facteur_enso(annee)

        # ── Génération de base ────────────────────────────────────────────────
        pluie_7j   = max(0.0, rng.gauss(normale_7j  * facteur_pluie, normale_7j  * 0.45))
        pluie_30j  = max(0.0, rng.gauss(normale_30j * facteur_pluie, normale_30j * 0.35))
        # pluie_prev : bruit INDÉPENDANT (correction clé V4.1)
        pluie_prev = max(0.0, rng.gauss(normale_7j  * facteur_pluie, normale_7j  * 0.50))

        temp_base = 28.0 + 4.0 * math.sin((mois - 4) * math.pi / 6)
        temp_max  = temp_base + rng.gauss(0, 2.2)

        sm_surface  = max(0.10, min(0.70,
            0.30 + (pluie_7j / max(1, normale_7j) - 1.0) * 0.12 + rng.gauss(0, 0.03)))
        sm_rootzone = max(0.10, min(0.60,
            0.28 + (pluie_30j / max(1, normale_30j) - 1.0) * 0.08
            * facteur_sech + rng.gauss(0, 0.025)))

        ndvi = max(0.20, min(0.95,
            0.72 - max(0, 0.35 - sm_rootzone) * 0.7 + rng.gauss(0, 0.04)))
        ndwi = max(0.00, min(0.80,
            0.18 + (sm_surface - 0.32) * 0.55 + rng.gauss(0, 0.03)))

        # ── Injection événements extrêmes ─────────────────────────────────────
        if idx in injections_inond and mois in _MOIS_POINTE_PLUIES:
            mult = rng.uniform(1.6, 2.8)
            pluie_7j   = normale_7j  * mult
            pluie_prev = normale_7j  * rng.uniform(1.4, 2.2)
            pluie_30j  = normale_30j * rng.uniform(1.4, 2.0)
            sm_surface  = rng.uniform(0.46, 0.68)
            sm_rootzone = rng.uniform(0.38, 0.55)
            ndwi = rng.uniform(0.32, 0.65)
            ndvi = max(0.40, ndvi)
        elif idx in injections_sech:
            pluie_7j   = normale_7j  * rng.uniform(0.20, 0.55)
            pluie_prev = normale_7j  * rng.uniform(0.25, 0.55)
            pluie_30j  = normale_30j * rng.uniform(0.20, 0.50) * facteur_sech
            sm_surface  = rng.uniform(0.10, 0.22)
            sm_rootzone = rng.uniform(0.10, 0.23)
            ndvi = rng.uniform(0.25, 0.52)
            ndwi = rng.uniform(0.00, 0.15)

        # ── temp_max_3j : vraie moyenne glissante 3 semaines ──────────────────
        historique_temp.append(temp_max)
        if len(historique_temp) > 3:
            historique_temp.pop(0)
        temp_max_3j = sum(historique_temp) / len(historique_temp)

        # ── Features dérivées ─────────────────────────────────────────────────
        deriv = features_derivees(mois, pluie_7j, pluie_30j,
                                   sm_surface, sm_rootzone, sm_surface_prev)
        sm_surface_prev = sm_surface

        lignes.append({
            "date":             current.isoformat(),
            "mois":             mois,
            "pluie_7j":         round(pluie_7j,    2),
            "pluie_30j":        round(pluie_30j,   2),
            "pluie_prev_7j":    round(pluie_prev,  2),
            "temp_max":         round(temp_max,    2),
            "temp_max_3j":      round(temp_max_3j, 2),
            "sm_surface":       round(sm_surface,  4),
            "sm_rootzone":      round(sm_rootzone, 4),
            "ndvi":             round(ndvi,        4),
            "ndwi":             round(ndwi,        4),
            **{k: round(v, 4) for k, v in deriv.items()},
            "label_inondation": label_inondation(pluie_7j, pluie_prev, sm_surface, ndwi, mois),
            "label_secheresse": label_secheresse(pluie_30j, ndvi, sm_rootzone, mois),
            "label_chaleur":    label_chaleur(temp_max, temp_max_3j),
        })
        current += delta
        idx += 1

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

    n_inond   = sum(1 for l in lignes if l["label_inondation"] == 1)
    n_sech    = sum(1 for l in lignes if l["label_secheresse"] == 1)
    n_chaleur = sum(1 for l in lignes if l["label_chaleur"]   == 1)
    n = len(lignes)

    print(f"[BUILD] Dataset exporté : {chemin}")
    print(f"        Lignes totales   : {n}")
    print(f"        Features totales : {len(entetes) - 4} (+ date, mois, labels)")
    print(f"        Inondations (1)  : {n_inond}  ({100 * n_inond // n}%)")
    print(f"        Sécheresses (1)  : {n_sech}   ({100 * n_sech  // n}%)")
    print(f"        Chaleurs    (1)  : {n_chaleur} ({100 * n_chaleur // n}%)")


# ───────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ───────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM V4.1 — Build dataset historique")
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
