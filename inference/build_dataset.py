#!/usr/bin/env python3
"""
SAMCAM V4.4.4 — Construction du dataset historique

FIX V4.4.4 :
    - Année de début par défaut : 1990 → 1984
      Raison : ERA5-Land (sm_surface, sm_rootzone, ET0) est fiable dès 1984.
      NDVI/NDWI avant 1990 est interp. par Open-Meteo depuis NOAA AVHRR (8km)
      mais le volume de données supplémentaire (+6 ans = ~312 semaines)
      compense largement le bruit introduit.

NOUVEAUTÉS V4.3 :
    - et0_semaine ajouté comme feature dans toutes les lignes du dataset
      (modes openmeteo, gee, simulation)
    - ratio_et0_pluie calculé dans features_derivees
      → bilan hydrique synthétique direct pour le risque sécheresse

NOUVEAUTÉS V4.2 :
    - Mode --openmeteo : télécharge les VRAIES données historiques via
      Open-Meteo Historical API (gratuit, sans clé API, données depuis 1940)
    - Variables récupérées : pluie, température max, humidité sol
      (surface + racines), rayonnement (proxy NDVI/NDWI), ET0
    - Fallback simulation conservé si pas d'accès réseau (--no-gee)

Usage :
    python3 inference/build_dataset.py --openmeteo          # RECOMMANDÉ (vraies données)
    python3 inference/build_dataset.py --openmeteo --start 2000 --end 2025
    python3 inference/build_dataset.py --no-gee              # simulation (démo offline)
    python3 inference/build_dataset.py                       # via GEE (nécessite auth)

Sortie :
    data/dataset_kribi_historical.csv

Prérequis (mode --openmeteo) :
    pip install openmeteo-requests requests-cache retry-requests
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

# Normales mensuelles Kribi (pluie 7j en mm) — calibrées sur données réelles
NORMALES_MENSUELLES = {
    1: 30,  2: 50,  3: 120, 4: 180, 5: 200, 6: 160,
    7: 80,  8: 100, 9: 180, 10: 200, 11: 150, 12: 50,
}

# ET0 normales mensuelles Kribi (mm/semaine) — estimées clima ERA5-Land
# Saison sèche (déc-fév) : ET0 plus élevée car ensoleillement fort + vent
# Saison des pluies (mai-oct) : ET0 modérée (humidité élevée)
ET0_NORMALES_MENSUELLES = {
    1: 25, 2: 27, 3: 24, 4: 21, 5: 20, 6: 19,
    7: 18, 8: 18, 9: 19, 10: 20, 11: 21, 12: 23,
}


# ───────────────────────────────────────────────────────────────────────────────
# FEATURES DÉRIVÉES
# ───────────────────────────────────────────────────────────────────────────────

def features_derivees(mois: int, pluie_7j: float, pluie_30j: float,
                      sm_surface: float, sm_rootzone: float,
                      et0_semaine: float = 0.0,
                      sm_surface_prev: float = None) -> dict:
    normale = NORMALES_MENSUELLES.get(mois, 120)

    sin_m = round(math.sin(2 * math.pi * mois / 12), 4)
    cos_m = round(math.cos(2 * math.pi * mois / 12), 4)
    anomalie = round((pluie_7j - normale) / max(1.0, normale), 4)
    ratio = round(pluie_30j / max(1.0, pluie_7j * (30 / 7)), 4) if pluie_7j > 0 else 1.0
    ratio = min(ratio, 5.0)
    trend = round(sm_surface - sm_surface_prev, 4) if sm_surface_prev is not None else 0.0
    sm_deficit_racine = round(max(0.0, (0.30 - sm_rootzone) / 0.30), 4)

    # V4.3 — Bilan hydrique : ratio ET0 / pluie
    # > 1 : la végétation perd plus d'eau qu'elle n'en reçoit → stress hydrique
    # < 1 : excédent d'eau → potentiel inondation
    ratio_et0_pluie = round(et0_semaine / max(1.0, pluie_7j), 4)
    ratio_et0_pluie = min(ratio_et0_pluie, 10.0)  # cap à 10 pour éviter outliers

    return {
        "sin_mois":        sin_m,
        "cos_mois":        cos_m,
        "anomalie_pluie":  anomalie,
        "ratio_30j_7j":    ratio,
        "trend_sm":        trend,
        "sm_deficit":      sm_deficit_racine,
        "ratio_et0_pluie": ratio_et0_pluie,
    }


# ───────────────────────────────────────────────────────────────────────────────
# LABELS PHYSIQUES
# ───────────────────────────────────────────────────────────────────────────────

def label_inondation(pluie_7j, pluie_prev_7j, sm_surface, ndwi, mois):
    normale = NORMALES_MENSUELLES.get(mois, 120)
    score = 0
    if pluie_7j      > normale * 1.5:  score += 1
    if pluie_prev_7j > normale * 1.3:  score += 1
    if sm_surface    > 0.45:           score += 1
    if ndwi          > 0.30:           score += 1
    return 1 if score >= 2 else 0


def label_secheresse(pluie_30j, ndvi, sm_rootzone, mois, et0_semaine=0.0):
    normale_30j = NORMALES_MENSUELLES.get(mois, 120) * (30 / 7)
    et0_normale = ET0_NORMALES_MENSUELLES.get(mois, 21)
    score = 0
    if pluie_30j   < normale_30j * 0.65:     score += 1
    if ndvi        < 0.55:                   score += 1
    if sm_rootzone < 0.25:                   score += 1
    # V4.3 : ET0 élevée + pluie faible = stress hydrique confirmé
    if et0_semaine > et0_normale * 1.2 and pluie_30j < normale_30j * 0.80:
        score += 1
    return 1 if score >= 2 else 0


def label_chaleur(temp_max, temp_max_3j_moy):
    return 1 if (temp_max > 33.0 and temp_max_3j_moy > 32.0) else 0


# ───────────────────────────────────────────────────────────────────────────────
# MODE OPEN-METEO HISTORIQUE — DONNÉES RÉELLES GRATUITES
# ───────────────────────────────────────────────────────────────────────────────

def collecter_via_openmeteo(annee_debut: int, annee_fin: int) -> list:
    """
    Télécharge les données météo historiques réelles via Open-Meteo Historical API.
    Totalement gratuit, sans clé API, données depuis 1940.
    Variables : précipitations, température max, humidité sol (ERA5-Land), ET0.

    Documentation : https://open-meteo.com/en/docs/historical-weather-api
    """
    try:
        import openmeteo_requests
        import requests_cache
        from retry_requests import retry
        import pandas as pd
    except ImportError:
        raise ImportError(
            "Dépendances manquantes. Installez avec :\n"
            "  pip install openmeteo-requests requests-cache retry-requests pandas"
        )

    cache_session = requests_cache.CachedSession(
        os.path.join(DATA_DIR, ".openmeteo_cache"), expire_after=3600
    )
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    client = openmeteo_requests.Client(session=retry_session)

    print(f"[OPEN-METEO] Téléchargement données réelles {annee_debut}→{annee_fin} pour Kribi...")
    print(f"             (Peut prendre 1-2 minutes selon la connexion)")

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":  LAT,
        "longitude": LON,
        "start_date": f"{annee_debut}-01-01",
        "end_date":   f"{annee_fin}-12-31",
        "daily": [
            "precipitation_sum",
            "temperature_2m_max",
            "soil_moisture_0_to_7cm_mean",
            "soil_moisture_7_to_28cm_mean",
            "shortwave_radiation_sum",
            "et0_fao_evapotranspiration",
        ],
        "timezone": "Africa/Douala",
    }

    responses = client.weather_api(url, params=params)
    response  = responses[0]
    daily     = response.Daily()

    dates = pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s"),
        end=pd.to_datetime(daily.TimeEnd(), unit="s"),
        freq=pd.Timedelta(seconds=daily.Interval()),
        inclusive="left"
    )

    df_daily = pd.DataFrame({
        "date":       dates,
        "precip":     daily.Variables(0).ValuesAsNumpy(),
        "temp_max":   daily.Variables(1).ValuesAsNumpy(),
        "sm_surface": daily.Variables(2).ValuesAsNumpy(),
        "sm_root":    daily.Variables(3).ValuesAsNumpy(),
        "radiation":  daily.Variables(4).ValuesAsNumpy(),
        "et0":        daily.Variables(5).ValuesAsNumpy(),
    })
    df_daily = df_daily.ffill().fillna(0)

    print(f"[OPEN-METEO] {len(df_daily)} jours téléchargés ({annee_debut}→{annee_fin})")

    lignes = []
    sm_surface_prev = None
    historique_temp = []

    date_debut = datetime.date(annee_debut, 1, 1)
    date_fin   = datetime.date(annee_fin, 12, 31)
    current    = date_debut
    delta_7j   = datetime.timedelta(days=7)
    delta_30j  = datetime.timedelta(days=30)

    total = int((date_fin - date_debut).days / 7)
    compteur = 0

    while current + delta_7j <= date_fin:
        mois = current.month
        fin_7j  = current + delta_7j
        fin_30j = current + delta_30j

        mask_7j  = (df_daily["date"].dt.date >= current) & (df_daily["date"].dt.date < fin_7j)
        mask_30j = (df_daily["date"].dt.date >= current) & (df_daily["date"].dt.date < fin_30j)
        mask_prev = (df_daily["date"].dt.date >= fin_7j) & \
                    (df_daily["date"].dt.date < current + datetime.timedelta(days=14))

        w7  = df_daily[mask_7j]
        w30 = df_daily[mask_30j]
        wp  = df_daily[mask_prev]

        if len(w7) == 0:
            current += delta_7j
            continue

        pluie_7j    = float(w7["precip"].sum())
        pluie_30j   = float(w30["precip"].sum()) if len(w30) > 0 else pluie_7j * 4
        pluie_prev  = float(wp["precip"].sum())  if len(wp)  > 0 else pluie_7j
        temp_max    = float(w7["temp_max"].max())
        sm_surface  = float(w7["sm_surface"].mean())
        sm_rootzone = float(w7["sm_root"].mean())
        et0_semaine = float(w7["et0"].sum())

        historique_temp.append(temp_max)
        if len(historique_temp) > 3:
            historique_temp.pop(0)
        temp_max_3j = sum(historique_temp) / len(historique_temp)

        rad_mean = float(w7["radiation"].mean())
        ndvi = min(0.95, max(0.20,
            0.45 + (sm_rootzone - 0.25) * 0.8 + (rad_mean - 15) * 0.005))
        ndwi = min(0.80, max(0.00,
            0.10 + (sm_surface - 0.25) * 0.6 + (pluie_7j / max(1, NORMALES_MENSUELLES[mois]) - 1) * 0.08))

        deriv = features_derivees(mois, pluie_7j, pluie_30j,
                                   sm_surface, sm_rootzone,
                                   et0_semaine=et0_semaine,
                                   sm_surface_prev=sm_surface_prev)
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
            "et0_semaine":      round(et0_semaine, 2),
            **{k: round(v, 4) for k, v in deriv.items()},
            "label_inondation": label_inondation(pluie_7j, pluie_prev, sm_surface, ndwi, mois),
            "label_secheresse": label_secheresse(pluie_30j, ndvi, sm_rootzone, mois, et0_semaine),
            "label_chaleur":    label_chaleur(temp_max, temp_max_3j),
            "source":           "open-meteo-real",
        })

        compteur += 1
        if compteur % 52 == 0:
            print(f"[OPEN-METEO] {compteur}/{total} semaines traitées")
        current += delta_7j

    print(f"[OPEN-METEO] ✅ {len(lignes)} semaines construites (V4.4.4 — 1984→{annee_fin})")
    return lignes


# ───────────────────────────────────────────────────────────────────────────────
# COLLECTE VIA GOOGLE EARTH ENGINE
# ───────────────────────────────────────────────────────────────────────────────

def collecter_via_gee(annee_debut: int, annee_fin: int) -> list:
    try:
        import ee
        ee.Initialize()
    except Exception as e:
        raise RuntimeError(
            f"Google Earth Engine non disponible : {e}\n"
            "  pip install earthengine-api && earthengine authenticate\n"
            "  Ou utilisez --openmeteo pour des données réelles sans GEE."
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

            et0_semaine = float(ET0_NORMALES_MENSUELLES.get(mois, 21))

            deriv = features_derivees(mois, chirps_7j, chirps_30j,
                                      sm_surface, sm_root,
                                      et0_semaine=et0_semaine,
                                      sm_surface_prev=sm_surface_prev)
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
                "et0_semaine":      round(et0_semaine, 2),
                **{k: round(v, 4) for k, v in deriv.items()},
                "label_inondation": label_inondation(chirps_7j, chirps_prev, sm_surface, ndwi, mois),
                "label_secheresse": label_secheresse(chirps_30j, ndvi, sm_root, mois, et0_semaine),
                "label_chaleur":    label_chaleur(temp_max, temp_max_3j),
                "source":           "gee",
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
# MODE SIMULATION (conservé comme fallback)
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
    print(f"[SIM] Génération simulation {annee_debut}→{annee_fin} (V4.4.4)...")
    print(f"[SIM] ⚠️  Mode simulation : données synthétiques uniquement.")
    print(f"[SIM]    Utilisez --openmeteo pour de vraies données historiques.")
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

    historique_temp = []
    sm_surface_prev = None
    idx = 0

    while current <= date_fin:
        mois  = current.month
        annee = current.year
        normale_7j  = NORMALES_MENSUELLES[mois]
        normale_30j = normale_7j * (30 / 7)
        et0_normale = ET0_NORMALES_MENSUELLES[mois]
        facteur_pluie, facteur_sech = _facteur_enso(annee)

        pluie_7j   = max(0.0, rng.gauss(normale_7j  * facteur_pluie, normale_7j  * 0.45))
        pluie_30j  = max(0.0, rng.gauss(normale_30j * facteur_pluie, normale_30j * 0.35))
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

        et0_semaine = max(5.0, rng.gauss(et0_normale * facteur_sech, et0_normale * 0.15))

        if idx in injections_inond and mois in _MOIS_POINTE_PLUIES:
            mult = rng.uniform(1.6, 2.8)
            pluie_7j   = normale_7j  * mult
            pluie_prev = normale_7j  * rng.uniform(1.4, 2.2)
            pluie_30j  = normale_30j * rng.uniform(1.4, 2.0)
            sm_surface  = rng.uniform(0.46, 0.68)
            sm_rootzone = rng.uniform(0.38, 0.55)
            ndwi = rng.uniform(0.32, 0.65)
            ndvi = max(0.40, ndvi)
            et0_semaine = max(5.0, et0_semaine * rng.uniform(0.7, 0.9))
        elif idx in injections_sech:
            pluie_7j   = normale_7j  * rng.uniform(0.20, 0.55)
            pluie_prev = normale_7j  * rng.uniform(0.25, 0.55)
            pluie_30j  = normale_30j * rng.uniform(0.20, 0.50) * facteur_sech
            sm_surface  = rng.uniform(0.10, 0.22)
            sm_rootzone = rng.uniform(0.10, 0.23)
            ndvi = rng.uniform(0.25, 0.52)
            ndwi = rng.uniform(0.00, 0.15)
            et0_semaine = et0_semaine * rng.uniform(1.1, 1.4)

        historique_temp.append(temp_max)
        if len(historique_temp) > 3:
            historique_temp.pop(0)
        temp_max_3j = sum(historique_temp) / len(historique_temp)

        deriv = features_derivees(mois, pluie_7j, pluie_30j,
                                   sm_surface, sm_rootzone,
                                   et0_semaine=et0_semaine,
                                   sm_surface_prev=sm_surface_prev)
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
            "et0_semaine":      round(et0_semaine, 2),
            **{k: round(v, 4) for k, v in deriv.items()},
            "label_inondation": label_inondation(pluie_7j, pluie_prev, sm_surface, ndwi, mois),
            "label_secheresse": label_secheresse(pluie_30j, ndvi, sm_rootzone, mois, et0_semaine),
            "label_chaleur":    label_chaleur(temp_max, temp_max_3j),
            "source":           "simulation",
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
    source = lignes[0].get("source", "?") if lignes else "?"

    print(f"\n[BUILD] Dataset exporté : {chemin}")
    print(f"        Version         : V4.4.4 (1984→{lignes[-1]['date'][:4]})")
    print(f"        Source          : {source}")
    print(f"        Lignes totales  : {n}")
    print(f"        Features        : {len(entetes) - 5} (+ date, mois, labels, source)")
    print(f"        Inondations (1) : {n_inond}  ({100 * n_inond // n}%)")
    print(f"        Sécheresses (1) : {n_sech}   ({100 * n_sech  // n}%)")
    print(f"        Chaleurs    (1) : {n_chaleur} ({100 * n_chaleur // n}%)")
    if source == "simulation":
        print(f"\n[BUILD] 💡 Pour des données réelles, relancez avec --openmeteo")


# ───────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ───────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM V4.4.4 — Build dataset historique")
    parser.add_argument(
        "--start", type=int, default=1984,
        help="Année de début (défaut: 1984 — limite basse ERA5-Land fiable)"
    )
    parser.add_argument("--end",       type=int, default=2024, help="Année de fin (défaut: 2024)")
    parser.add_argument("--no-gee",    action="store_true",   help="Mode simulation (démo sans réseau)")
    parser.add_argument("--openmeteo", action="store_true",   help="[RECOMMANDÉ] Vraies données Open-Meteo (sans clé API)")
    args = parser.parse_args()

    if args.openmeteo:
        lignes = collecter_via_openmeteo(args.start, args.end)
    elif args.no_gee:
        lignes = generer_simulation(args.start, args.end)
    else:
        lignes = collecter_via_gee(args.start, args.end)

    exporter_csv(lignes, OUTPUT_CSV)


if __name__ == "__main__":
    main()
