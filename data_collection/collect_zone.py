#!/usr/bin/env python3
"""
SAMCAM v3.1 - Script de collecte multi-zones climatiques

Sources :
- Open-Meteo         : météo historique + prévisions 16j (aucune clé)
- NASA POWER         : rayonnement solaire, précipitations corrigées AG (aucune clé)
- Google Earth Engine :
    · Sentinel-2 COPERNICUS/S2_SR_HARMONIZED  → NDVI, NDWI, NBR, NDRE (10–20m)
    · MODIS MOD13A1                           → NDVI, EVI (500m, fallback S2)
    · NASA SMAP SPL4SMGP/008                  → humidité sol surface + racinaire (9km)
    · CHIRPS UCSB-CHG/CHIRPS/DAILY            → précipitations 5km, latence 2j ★ NOUVEAU
    · ERA5 ECMWF/ERA5_LAND/DAILY_AGGR         → vent, humidité sol ERA5, temp (9km) ★ NOUVEAU

Usage :
    python collect_zone.py                   # Toutes les zones
    python collect_zone.py --zone Kribi      # Une seule zone
    python collect_zone.py --zone Garoua --days 14
    python collect_zone.py --list

Sortie :
    data/<zone_slug>_YYYY-MM-DD.json
"""

import os
import json
import argparse
import datetime
import requests
from typing import Optional

# ─── CONFIG GLOBALE ────────────────────────────────────────────────────────────

PROJECT_ID      = "samcam-499511"
SERVICE_ACCOUNT = "gee-kribi-bot@samcam-499511.iam.gserviceaccount.com"
KEY_PATH = os.environ.get(
    "EE_PRIVATE_KEY_PATH",
    os.path.expanduser("~/.config/gee/kribi-key.json")
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

# Types de zones du nord sahélien — seuils pluviométriques abaissés
ZONES_NORD = ("sahel", "agricole_nord", "elevage")


# ─── ZONES AGRICOLES DU CAMEROUN ──────────────────────────────────────────────

ZONES = [
    {
        "name": "Kribi",
        "lat": 2.9391, "lon": 9.9098,
        "type": "cotier",
        "cultures": ["pêche", "cacao", "palmier à huile"],
        "saison_semis": [3, 4, 9],
    },
    {
        "name": "Ebolowa",
        "lat": 2.9000, "lon": 11.1500,
        "type": "agricole",
        "cultures": ["cacao", "palmier à huile", "vivriers"],
        "saison_semis": [3, 4, 9],
    },
    {
        "name": "Kumba",
        "lat": 4.6333, "lon": 9.4500,
        "type": "agricole",
        "cultures": ["cacao", "bananier", "café robusta"],
        "saison_semis": [3, 4, 9],
    },
    {
        "name": "Bafoussam",
        "lat": 5.4764, "lon": 10.4176,
        "type": "agricole",
        "cultures": ["café arabica", "maïs", "pomme de terre"],
        "saison_semis": [3, 4, 8, 9],
    },
    {
        "name": "Yaounde_peri",
        "lat": 3.9000, "lon": 11.5500,
        "type": "maraichage",
        "cultures": ["maraîchage", "manioc", "plantain"],
        "saison_semis": [3, 4, 9, 10],
    },
    {
        "name": "Ngaoundere",
        "lat": 7.3167, "lon": 13.5833,
        "type": "elevage",
        "cultures": ["élevage bovin", "maïs", "sorgho"],
        "saison_semis": [5, 6],
    },
    {
        "name": "Garoua",
        "lat": 9.3017, "lon": 13.3922,
        "type": "agricole_nord",
        "cultures": ["coton", "sorgho", "mil", "arachide"],
        "saison_semis": [5, 6],
    },
    {
        "name": "Maroua",
        "lat": 10.5910, "lon": 14.3158,
        "type": "sahel",
        "cultures": ["mil", "sorgho", "niébé", "oignon"],
        "saison_semis": [6, 7],
    },
]


# ─── UTILITAIRES ───────────────────────────────────────────────────────────────

def zone_slug(name: str) -> str:
    return name.lower().replace(" ", "_")

def get_zone_by_name(name: str) -> Optional[dict]:
    for z in ZONES:
        if z["name"].lower() == name.lower():
            return z
    return None

def is_semis_period(zone: dict) -> bool:
    return datetime.date.today().month in zone.get("saison_semis", [])


# ─── 1. OPEN-METEO ─────────────────────────────────────────────────────────────

def fetch_openmeteo(lat: float, lon: float, days_back: int = 7) -> dict:
    today = datetime.date.today()
    end   = today - datetime.timedelta(days=1)
    start = end   - datetime.timedelta(days=days_back)

    hist_resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": lat, "longitude": lon,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum",
                      "windspeed_10m_max", "et0_fao_evapotranspiration", "rain_sum"],
            "hourly": ["precipitation", "relative_humidity_2m", "windspeed_10m", "surface_pressure"],
            "timezone": "Africa/Douala",
        },
        timeout=30,
    )
    hist_resp.raise_for_status()

    fcast_resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat, "longitude": lon,
            "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum",
                      "windspeed_10m_max", "precipitation_probability_max",
                      "weathercode", "et0_fao_evapotranspiration"],
            "hourly": ["precipitation", "relative_humidity_2m", "windspeed_10m", "surface_pressure"],
            "forecast_days": 16, "timezone": "Africa/Douala",
        },
        timeout=30,
    )
    fcast_resp.raise_for_status()

    print(f"  [Open-Meteo] ✅ Historique {days_back}j + prévisions 16j")
    return {
        "source": "open-meteo",
        "historique_daily":  hist_resp.json().get("daily",  {}),
        "historique_hourly": hist_resp.json().get("hourly", {}),
        "previsions_daily":  fcast_resp.json().get("daily",  {}),
        "previsions_hourly": fcast_resp.json().get("hourly", {}),
    }


# ─── 2. NASA POWER ─────────────────────────────────────────────────────────────

def fetch_nasa_power(lat: float, lon: float, days_back: int = 7) -> dict:
    today = datetime.date.today()
    end   = today - datetime.timedelta(days=7)
    start = end   - datetime.timedelta(days=days_back)

    resp = requests.get(
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        params={
            "parameters": "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,RH2M,ALLSKY_SFC_SW_DWN,WS10M,PS,QV2M",
            "community": "AG",
            "longitude": lon, "latitude": lat,
            "start": start.strftime("%Y%m%d"),
            "end":   end.strftime("%Y%m%d"),
            "format": "JSON",
        },
        timeout=60,
    )
    resp.raise_for_status()
    print(f"  [NASA POWER] ✅ Données {days_back}j")
    return {
        "source": "nasa-power",
        "parametres": resp.json().get("properties", {}).get("parameter", {}),
    }


# ─── 3. GOOGLE EARTH ENGINE ────────────────────────────────────────────────────

def _init_gee() -> bool:
    try:
        import ee
    except ImportError:
        print("  [GEE] ⚠️  earthengine-api non installé")
        return False
    if not os.path.exists(KEY_PATH):
        print(f"  [GEE] ⚠️  Clé JSON introuvable : {KEY_PATH}")
        return False
    try:
        credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_PATH)
        ee.Initialize(credentials, project=PROJECT_ID)
        return True
    except Exception as e:
        print(f"  [GEE] ❌ Auth échouée : {e}")
        return False


def fetch_gee_sentinel2(lat: float, lon: float, window_days: int = 60) -> Optional[dict]:
    import ee
    today = datetime.date.today()
    start = today - datetime.timedelta(days=window_days)
    zone  = ee.Geometry.Point([lon, lat]).buffer(10000)

    def mask_s2_clouds(img):
        qa = img.select("QA60")
        mask = (qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0)))
        return img.updateMask(mask).divide(10000)

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start.isoformat(), today.isoformat())
        .filterBounds(zone)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
        .map(mask_s2_clouds)
    )
    count = col.size().getInfo()
    print(f"  [GEE S2] 🛰  {count} image(s) — {window_days}j")
    if count == 0:
        return None

    comp = col.median()
    indices = comp.addBands([
        comp.normalizedDifference(["B8",  "B4"]).rename("NDVI"),
        comp.normalizedDifference(["B3",  "B8"]).rename("NDWI"),
        comp.normalizedDifference(["B8",  "B12"]).rename("NBR"),
        comp.normalizedDifference(["B8",  "B5"]).rename("NDRE"),
    ])
    stats = indices.select(["NDVI","NDWI","NBR","NDRE"]).reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True)
                                 .combine(ee.Reducer.minMax(), sharedInputs=True),
        geometry=zone, scale=20, maxPixels=1e9,
    ).getInfo()
    print("  [GEE S2] ✅ NDVI, NDWI, NBR, NDRE")
    return {
        "capteur": "Sentinel-2",
        "periode": {"debut": start.isoformat(), "fin": today.isoformat()},
        "nb_images": count, "filtre_nuages_pct": 80, "indices": stats,
    }


def fetch_gee_modis_fallback(lat: float, lon: float, window_days: int = 60) -> dict:
    import ee
    today = datetime.date.today()
    start = today - datetime.timedelta(days=window_days)
    zone  = ee.Geometry.Point([lon, lat]).buffer(10000)

    modis = (
        ee.ImageCollection("MODIS/061/MOD13A1")
        .filterDate(start.isoformat(), today.isoformat())
        .filterBounds(zone)
        .select(["NDVI","EVI","SummaryQA"])
    )
    count = modis.size().getInfo()
    if count == 0:
        return {"capteur": "MODIS-fallback", "erreur": "Aucune donnée MODIS"}

    stats = modis.mean().multiply(0.0001).select(["NDVI","EVI"]).reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
        geometry=zone, scale=500, maxPixels=1e9,
    ).getInfo()
    print(f"  [GEE MODIS] ✅ NDVI, EVI (fallback 500m, {count} composites)")
    return {
        "capteur": "MODIS-MOD13A1-500m",
        "periode": {"debut": start.isoformat(), "fin": today.isoformat()},
        "nb_composites": count, "indices": stats,
        "note": "Fallback Sentinel-2 — résolution 500m, composition 16j",
    }


def fetch_gee_soil_moisture(lat: float, lon: float) -> dict:
    """Humidité du sol SMAP Level-4 (NASA/SMAP/SPL4SMGP/008) — ~9km, latence ~3j."""
    import ee
    today = datetime.date.today()
    start = today - datetime.timedelta(days=30)
    zone  = ee.Geometry.Point([lon, lat]).buffer(10000)
    try:
        stats = (
            ee.ImageCollection("NASA/SMAP/SPL4SMGP/008")
            .filterDate(start.isoformat(), today.isoformat())
            .filterBounds(zone)
            .select(["sm_surface","sm_rootzone"])
            .mean()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=zone, scale=9000, maxPixels=1e9)
            .getInfo()
        )
        print("  [GEE SMAP] ✅ Humidité sol surface + racinaire")
        return {
            "source": "SMAP-SPL4SMGP-008",
            "humidite_sol": stats,
            "legende": {"sm_surface": "0-5cm (m³/m³)", "sm_rootzone": "0-100cm (m³/m³)"},
        }
    except Exception as e:
        print(f"  [GEE SMAP] ⚠️  Indisponible : {e}")
        return {"source": "SMAP-SPL4SMGP-008", "erreur": str(e)}


def fetch_gee_chirps(lat: float, lon: float, days_back: int = 30) -> dict:
    """
    Précipitations CHIRPS (Climate Hazards Group InfraRed Precipitation with Stations).
    Source : UCSB-CHG/CHIRPS/DAILY — résolution ~5km, latence ~2 jours.
    """
    import ee
    today = datetime.date.today()
    start = today - datetime.timedelta(days=max(days_back, 30))
    zone  = ee.Geometry.Point([lon, lat]).buffer(10000)

    try:
        col = (
            ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterDate(start.isoformat(), today.isoformat())
            .filterBounds(zone)
            .select(["precipitation"])
        )
        count = col.size().getInfo()
        if count == 0:
            raise ValueError("Aucune image CHIRPS disponible")

        stats_full = col.sum().reduceRegion(
            reducer=ee.Reducer.mean(), geometry=zone, scale=5000, maxPixels=1e9,
        ).getInfo()

        start_7j = today - datetime.timedelta(days=7)
        stats_7j = (
            col.filterDate(start_7j.isoformat(), today.isoformat())
            .sum()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=zone, scale=5000, maxPixels=1e9)
            .getInfo()
        )

        max_stats = col.max().reduceRegion(
            reducer=ee.Reducer.max(), geometry=zone, scale=5000, maxPixels=1e9,
        ).getInfo()

        jours_pluie = (
            col.map(lambda img: img.gt(1).rename("rainy"))
            .sum()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=zone, scale=5000, maxPixels=1e9)
            .getInfo()
        )

        pluie_7j  = round(stats_7j.get("precipitation")  or 0, 2)
        pluie_30j = round(stats_full.get("precipitation") or 0, 2)
        intensite = round(max_stats.get("precipitation")  or 0, 2)
        nb_jours  = round(jours_pluie.get("rainy")        or 0, 1)

        print(f"  [GEE CHIRPS] ✅ Pluie 7j={pluie_7j}mm, 30j={pluie_30j}mm, max/j={intensite}mm")
        return {
            "source": "CHIRPS-UCSB-CHG-DAILY-5km",
            "periode": {"debut": start.isoformat(), "fin": today.isoformat()},
            "pluie_chirps_7j_mm":  pluie_7j,
            "pluie_chirps_30j_mm": pluie_30j,
            "intensite_max_mm":    intensite,
            "jours_pluie_30j":     nb_jours,
            "note": "IR satellite + pluviomètres sol fusionnés — 5km de résolution",
        }
    except Exception as e:
        print(f"  [GEE CHIRPS] ⚠️  Indisponible : {e}")
        return {"source": "CHIRPS-UCSB-CHG-DAILY-5km", "erreur": str(e)}


def fetch_gee_era5(lat: float, lon: float, days_back: int = 7) -> dict:
    """
    Données ERA5-Land (ECMWF/ERA5_LAND/DAILY_AGGR) via GEE.
    Résolution ~9km, disponibilité J-5 environ.
    """
    import ee
    today = datetime.date.today()
    end   = today - datetime.timedelta(days=5)
    start = end   - datetime.timedelta(days=days_back)
    zone  = ee.Geometry.Point([lon, lat]).buffer(25000)

    ERA5_BANDS = [
        "temperature_2m",
        "u_component_of_wind_10m",
        "v_component_of_wind_10m",
        "volumetric_soil_water_layer_1",
        "volumetric_soil_water_layer_2",
        "surface_runoff",
        "total_evaporation",
    ]

    try:
        col = (
            ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
            .filterDate(start.isoformat(), end.isoformat())
            .filterBounds(zone)
            .select(ERA5_BANDS)
        )
        count = col.size().getInfo()
        if count == 0:
            raise ValueError("Aucune donnée ERA5 disponible pour la période")

        stats = col.mean().reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone,
            scale=9000,
            maxPixels=1e9,
        ).getInfo()

        u = stats.get("u_component_of_wind_10m") or 0
        v = stats.get("v_component_of_wind_10m") or 0
        vent_ms  = round((u ** 2 + v ** 2) ** 0.5, 2)
        vent_kmh = round(vent_ms * 3.6, 1)

        temp_k = stats.get("temperature_2m")
        temp_c = round(temp_k - 273.15, 1) if temp_k else None

        sm1 = round(stats.get("volumetric_soil_water_layer_1") or 0, 4)
        sm2 = round(stats.get("volumetric_soil_water_layer_2") or 0, 4)

        runoff_sum = col.select(["surface_runoff"]).sum().reduceRegion(
            reducer=ee.Reducer.mean(), geometry=zone, scale=9000, maxPixels=1e9,
        ).getInfo()
        ruissellement_mm = round((runoff_sum.get("surface_runoff") or 0) * 1000, 2)

        evap_sum = (
            col.select(["total_evaporation"]).sum()
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=zone, scale=9000, maxPixels=1e9)
            .getInfo()
        )
        etp_era5_mm = round(abs((evap_sum.get("total_evaporation") or 0)) * 1000, 2)

        print(f"  [GEE ERA5] ✅ Vent {vent_kmh}km/h, sol sm1={sm1}, ruiss={ruissellement_mm}mm")
        return {
            "source": "ERA5-Land-ECMWF-9km",
            "periode": {"debut": start.isoformat(), "fin": end.isoformat()},
            "nb_jours": count,
            "temperature_2m_c":           temp_c,
            "vent_ms":                    round(vent_ms, 2),
            "vent_kmh":                   vent_kmh,
            "humidite_sol_era5_0_7cm":    sm1,
            "humidite_sol_era5_7_28cm":   sm2,
            "ruissellement_cumule_mm":    ruissellement_mm,
            "etp_era5_cumule_mm":         etp_era5_mm,
            "note": "Rétroanalyse ECMWF — latence ~5j, résolution 9km",
        }
    except Exception as e:
        print(f"  [GEE ERA5] ⚠️  Indisponible : {e}")
        return {"source": "ERA5-Land-ECMWF-9km", "erreur": str(e)}


def fetch_gee_all(lat: float, lon: float, zone_type: str = "agricole") -> dict:
    """
    Orchestre toutes les collectes GEE.
    CHIRPS et ERA5 sont activés pour TOUTES les zones.
    """
    if not _init_gee():
        return {"source": "gee", "erreur": "Initialisation GEE impossible"}

    result = {"source": "gee"}

    s2 = fetch_gee_sentinel2(lat, lon, window_days=60)
    if s2 is not None:
        result["sentinel2"] = s2
    else:
        result["modis"] = fetch_gee_modis_fallback(lat, lon, window_days=60)

    result["smap"]   = fetch_gee_soil_moisture(lat, lon)
    result["chirps"] = fetch_gee_chirps(lat, lon, days_back=30)
    result["era5"]   = fetch_gee_era5(lat, lon, days_back=7)

    return result


# ─── 4. CALCUL DES INDICATEURS AGRICOLES ──────────────────────────────────────

def compute_agricultural_indicators(zone: dict, openmeteo: dict, gee: dict) -> dict:
    today = datetime.date.today()
    zone_type = zone.get("type", "agricole")

    pluie_7j, pluie_prev_7j = 0.0, 0.0
    try:
        pluie_7j = sum(
            p for p in openmeteo["historique_daily"].get("precipitation_sum", [])[-7:]
            if p is not None
        )
    except Exception:
        pass
    try:
        pluie_prev_7j = sum(
            p for p in openmeteo["previsions_daily"].get("precipitation_sum", [])[:7]
            if p is not None
        )
    except Exception:
        pass

    chirps_7j  = gee.get("chirps", {}).get("pluie_chirps_7j_mm")
    chirps_30j = gee.get("chirps", {}).get("pluie_chirps_30j_mm")
    pluie_ref_7j  = chirps_7j  if chirps_7j  is not None else pluie_7j
    pluie_ref_30j = chirps_30j if chirps_30j is not None else (pluie_7j * 4)

    etp_7j = 0.0
    try:
        etp_7j = sum(
            e for e in openmeteo["historique_daily"].get("et0_fao_evapotranspiration", [])[-7:]
            if e is not None
        )
    except Exception:
        pass

    etp_era5 = gee.get("era5", {}).get("etp_era5_cumule_mm")
    etp_ref  = etp_era5 if (etp_era5 and etp_era5 > 0) else etp_7j
    bilan_hydrique_7j = round(pluie_ref_7j - etp_ref, 2)

    vent_kmh         = gee.get("era5", {}).get("vent_kmh")
    ruissellement_mm = gee.get("era5", {}).get("ruissellement_cumule_mm")

    humidite_sol = None
    sm_rootzone  = None
    try:
        humidite_sol = gee["smap"]["humidite_sol"].get("sm_surface")
        sm_rootzone  = gee["smap"]["humidite_sol"].get("sm_rootzone")
    except Exception:
        pass
    if humidite_sol is None:
        humidite_sol = gee.get("era5", {}).get("humidite_sol_era5_0_7cm")
    if sm_rootzone is None:
        sm_rootzone = gee.get("era5", {}).get("humidite_sol_era5_7_28cm")

    ndvi_val, ndwi_val, ndre_val, capteur = None, None, None, "inconnu"
    try:
        if "sentinel2" in gee:
            idx = gee["sentinel2"]["indices"]
            ndvi_val = round(idx.get("NDVI_mean") or 0, 4)
            ndwi_val = round(idx.get("NDWI_mean") or 0, 4)
            ndre_val = round(idx.get("NDRE_mean") or 0, 4)
            capteur  = "Sentinel-2"
        elif "modis" in gee:
            idx = gee["modis"]["indices"]
            ndvi_val = round(idx.get("NDVI_mean") or 0, 4)
            capteur  = "MODIS"
    except Exception:
        pass

    est_nord = zone_type in ZONES_NORD
    seuil_inond_eleve  = 80  if est_nord else 150
    seuil_inond_modere = 40  if est_nord else 80
    seuil_vent_chaleur = 30

    risque_inondation = (
        "élevé"  if pluie_ref_7j > seuil_inond_eleve
        else "modéré" if pluie_ref_7j > seuil_inond_modere
        else "faible"
    )
    risque_inondation_prev = (
        "élevé"  if pluie_prev_7j > seuil_inond_eleve
        else "modéré" if pluie_prev_7j > seuil_inond_modere
        else "faible"
    )
    risque_secheresse = (
        "élevé"  if (ndvi_val is not None and ndvi_val < 0.2) or bilan_hydrique_7j < -30
        else "modéré" if bilan_hydrique_7j < -10
        else "faible"
    )
    risque_submersion    = "élevé" if (ndwi_val is not None and ndwi_val > 0.3) else "faible"
    risque_sol_sature    = "élevé" if (humidite_sol is not None and humidite_sol > 0.4) else "faible"
    risque_chaleur_vent  = (
        "élevé"  if est_nord and (vent_kmh or 0) > seuil_vent_chaleur and bilan_hydrique_7j < -20
        else "modéré" if est_nord and (vent_kmh or 0) > seuil_vent_chaleur
        else "faible"
    )
    risque_ruissellement = (
        "élevé"  if (ruissellement_mm or 0) > 20
        else "modéré" if (ruissellement_mm or 0) > 8
        else "faible"
    )
    stress_vegetal = (
        "élevé"  if (ndre_val is not None and ndre_val < 0.15)
        else "modéré" if (ndre_val is not None and ndre_val < 0.25)
        else "faible"
    )

    alerte_semis = None
    if is_semis_period(zone):
        if risque_inondation in ("modéré", "élevé"):
            alerte_semis = "⚠️ Période de semis — risque d'inondation : retarder ou protéger les semis"
        elif risque_secheresse == "élevé":
            alerte_semis = "⚠️ Période de semis — risque de sécheresse : irrigation recommandée"
        elif risque_chaleur_vent == "élevé":
            alerte_semis = "⚠️ Période de semis — vent chaud intense : paillis et ombrage recommandés"
        else:
            alerte_semis = "✅ Période de semis — conditions favorables"

    return {
        "pluie_cumulee_7j_mm":      round(pluie_ref_7j,   2),
        "pluie_cumulee_30j_mm":     round(pluie_ref_30j,  2),
        "pluie_prevue_7j_mm":       round(pluie_prev_7j,  2),
        "pluie_source":             "CHIRPS" if chirps_7j is not None else "Open-Meteo",
        "etp_cumulee_7j_mm":        round(etp_ref,         2),
        "etp_source":               "ERA5" if (etp_era5 and etp_era5 > 0) else "Open-Meteo-FAO56",
        "bilan_hydrique_7j_mm":     bilan_hydrique_7j,
        "vent_kmh_era5":            vent_kmh,
        "ruissellement_mm_era5":    ruissellement_mm,
        "humidite_sol_sm_surface":  humidite_sol,
        "humidite_sol_sm_rootzone": sm_rootzone,
        "ndvi_moyen":               ndvi_val,
        "ndwi_moyen":               ndwi_val,
        "ndre_moyen":               ndre_val,
        "capteur_satellite":        capteur,
        "risque_inondation_observe":  risque_inondation,
        "risque_inondation_prevu":    risque_inondation_prev,
        "risque_secheresse":          risque_secheresse,
        "risque_chaleur_vent":        risque_chaleur_vent,
        "risque_ruissellement":       risque_ruissellement,
        "risque_submersion_cotiere":  risque_submersion,
        "risque_sol_sature":          risque_sol_sature,
        "stress_vegetal":             stress_vegetal,
        "alerte_semis":               alerte_semis,
        "periode_semis_active":       is_semis_period(zone),
    }


# ─── 5. AGRÉGATION & SAUVEGARDE ────────────────────────────────────────────────

def aggregate_and_save(zone: dict, openmeteo: dict, nasa: dict, gee: dict) -> str:
    today       = datetime.date.today().isoformat()
    indicateurs = compute_agricultural_indicators(zone, openmeteo, gee)
    slug        = zone_slug(zone["name"])
    saison_mois = datetime.date.today().month
    saison      = "pluies" if saison_mois in [3, 4, 5, 6, 9, 10, 11] else "sèche"

    payload = {
        "meta": {
            "version":           "3.1-multizone-chirps-era5",
            "date_collecte":     today,
            "zone":              zone["name"],
            "zone_type":         zone["type"],
            "cultures":          zone["cultures"],
            "latitude":          zone["lat"],
            "longitude":         zone["lon"],
            "saison":            saison,
            "projet":            "SAMCAM",
            "capteur_satellite": indicateurs["capteur_satellite"],
            "sources": [
                "Open-Meteo (météo historique + prévisions 16j)",
                "NASA POWER (rayonnement solaire, AG)",
                "Copernicus Sentinel-2 via GEE (NDVI/NDWI/NDRE/NBR 10-20m)",
                "NASA SMAP SPL4SMGP/008 via GEE (humidité sol 9km)",
                "CHIRPS UCSB-CHG/DAILY via GEE (précipitations 5km)",
                "ERA5-Land ECMWF via GEE (vent, sol, ruissellement 9km)",
            ],
        },
        "meteorologie":       openmeteo,
        "nasa_power":         nasa,
        "satellitaire":       gee,
        "indicateurs_risque": indicateurs,
        "contexte_phi3": (
            f"Date: {today}. Zone: {zone['name']}, Cameroun ({zone['type']}) "
            f"(lat {zone['lat']}, lon {zone['lon']}). Saison: {saison}. "
            f"Cultures: {', '.join(zone['cultures'])}. "
            f"Pluie 7j ({indicateurs['pluie_source']}): {indicateurs['pluie_cumulee_7j_mm']} mm. "
            f"Pluie 30j: {indicateurs['pluie_cumulee_30j_mm']} mm. "
            f"Pluie prévue 7j: {indicateurs['pluie_prevue_7j_mm']} mm. "
            f"ETP 7j ({indicateurs['etp_source']}): {indicateurs['etp_cumulee_7j_mm']} mm. "
            f"Bilan hydrique 7j: {indicateurs['bilan_hydrique_7j_mm']} mm. "
            f"Vent ERA5: {indicateurs['vent_kmh_era5']} km/h. "
            f"Ruissellement ERA5: {indicateurs['ruissellement_mm_era5']} mm. "
            f"NDVI ({indicateurs['capteur_satellite']}): {indicateurs['ndvi_moyen']}. "
            f"NDRE: {indicateurs['ndre_moyen']}. "
            f"Humidité sol: {indicateurs['humidite_sol_sm_surface']} m³/m³. "
            f"Risque inondation: {indicateurs['risque_inondation_observe']}. "
            f"Risque sécheresse: {indicateurs['risque_secheresse']}. "
            f"Risque chaleur/vent: {indicateurs['risque_chaleur_vent']}. "
            f"Stress végétal: {indicateurs['stress_vegetal']}. "
            f"Alerte semis: {indicateurs['alerte_semis']}."
        ),
    }

    filename = os.path.join(OUT_DIR, f"{slug}_{today}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"  [SAMCAM] 💾 Sauvegardé : {filename}")
    return filename


# ─── 6. COLLECTE D'UNE ZONE ────────────────────────────────────────────────────

def collect(zone: Optional[dict] = None, zone_name: Optional[str] = None, days: int = 7) -> str:
    """Point d'entrée principal. Accepte un dict zone ou un nom de zone."""
    if zone is None:
        if zone_name is None:
            raise ValueError("Fournir zone= ou zone_name=")
        zone = get_zone_by_name(zone_name)
        if zone is None:
            raise ValueError(f"Zone '{zone_name}' introuvable")

    lat, lon = zone["lat"], zone["lon"]
    print(f"  [1/4] Open-Meteo...")
    openmeteo = fetch_openmeteo(lat, lon, days_back=days)
    print(f"  [2/4] NASA POWER...")
    nasa = fetch_nasa_power(lat, lon, days_back=days)
    print(f"  [3/4] GEE (S2/MODIS + SMAP + CHIRPS + ERA5)...")
    gee = fetch_gee_all(lat, lon, zone_type=zone.get("type", "agricole"))
    print(f"  [4/4] Agrégation et sauvegarde...")
    return aggregate_and_save(zone, openmeteo, nasa, gee)


def collect_zone_func(zone: dict, days: int = 7) -> str:
    return collect(zone=zone, days=days)


# ─── 7. POINT D'ENTRÉE CLI ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM v3.1 — Collecte multi-zones")
    parser.add_argument("--zone", type=str, default=None,
                        help="Zone à collecter (ex: Kribi, Garoua)")
    parser.add_argument("--days", type=int, default=7,
                        help="Jours d'historique météo (défaut: 7)")
    parser.add_argument("--list", action="store_true",
                        help="Lister les zones disponibles et quitter")
    args = parser.parse_args()

    if args.list:
        print("\n📍 Zones SAMCAM :")
        print(f"{'Nom':<20} {'Type':<18} {'Lat':>8} {'Lon':>9}  Cultures")
        print("-" * 80)
        for z in ZONES:
            print(f"{z['name']:<20} {z['type']:<18} {z['lat']:>8.4f} {z['lon']:>9.4f}  {', '.join(z['cultures'])}")
        return

    zones_to_collect = ZONES if not args.zone else [get_zone_by_name(args.zone)]
    if None in zones_to_collect:
        print(f"❌ Zone '{args.zone}' introuvable. Utilisez --list.")
        return

    print("=" * 60)
    print(f"SAMCAM v3.1 — Collecte multi-zones")
    print(f"Date    : {datetime.date.today().isoformat()}")
    print(f"Zones   : {len(zones_to_collect)} zone(s)")
    print(f"Sources : Open-Meteo · NASA POWER · S2/MODIS · SMAP · CHIRPS · ERA5")
    print("=" * 60)

    results, errors = [], []
    for i, zone in enumerate(zones_to_collect, 1):
        print(f"\n[{i}/{len(zones_to_collect)}] 📍 {zone['name']} ({zone['type']})")
        try:
            path = collect(zone=zone, days=args.days)
            results.append((zone["name"], path))
        except Exception as e:
            print(f"  ❌ Erreur : {e}")
            errors.append((zone["name"], str(e)))

    print("\n" + "=" * 60)
    print(f"✅ {len(results)} OK   ❌ {len(errors)} erreur(s)")
    for name, path in results:
        print(f"  📄 {name:<20} → {path}")
    if errors:
        for name, err in errors:
            print(f"  ❌ {name:<20} : {err}")
    print("=" * 60)


if __name__ == "__main__":
    main()
