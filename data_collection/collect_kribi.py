#!/usr/bin/env python3
"""
SAMCAM - Script de collecte automatique des données climatiques de Kribi

Sources :
- Open-Meteo (météo historique + prévisions) — aucune clé API requise
- Google Earth Engine (Sentinel-2 NDVI/NDWI/NBR + fallback MODIS) — via service account
- NASA POWER (rayonnement solaire, précipitations) — aucune clé API requise

Modifications v2.1 :
- Filtre nuages Sentinel-2 élargi à 80% (zone tropicale très nuageuse)
- Fenêtre temporelle élargie à 60 jours
- Fallback automatique sur MODIS si 0 image Sentinel-2 utilisable
- SMAP mis à jour vers NASA/SMAP/SPL4SMGP/008 (ancien dataset déprécié)
- Meilleure gestion des erreurs et logs

Usage :
    python collect_kribi.py
    python collect_kribi.py --days 30

Sortie :
    data/kribi_YYYY-MM-DD.json
"""

import os
import json
import argparse
import datetime
import requests

# ─── CONFIG ────────────────────────────────────────────────────────────────────

LAT = 2.9391
LON = 9.9098
CITY = "Kribi"
PROJECT_ID = "samcam-499511"
SERVICE_ACCOUNT = "gee-kribi-bot@samcam-499511.iam.gserviceaccount.com"

KEY_PATH = os.environ.get(
    "EE_PRIVATE_KEY_PATH",
    os.path.expanduser("~/.config/gee/kribi-key.json")
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)


# ─── 1. OPEN-METEO ─────────────────────────────────────────────────────────────

def fetch_openmeteo(days_back: int = 7) -> dict:
    today = datetime.date.today()
    end = today - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=days_back)

    hist_url = "https://archive-api.open-meteo.com/v1/archive"
    hist_params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "windspeed_10m_max",
            "et0_fao_evapotranspiration",
            "rain_sum",
            "snowfall_sum",
        ],
        "hourly": [
            "precipitation",
            "relative_humidity_2m",
            "windspeed_10m",
            "surface_pressure",
        ],
        "timezone": "Africa/Douala",
    }

    hist_resp = requests.get(hist_url, params=hist_params, timeout=30)
    hist_resp.raise_for_status()
    hist_data = hist_resp.json()

    fcast_url = "https://api.open-meteo.com/v1/forecast"
    fcast_params = {
        "latitude": LAT,
        "longitude": LON,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "windspeed_10m_max",
            "precipitation_probability_max",
            "weathercode",
            "et0_fao_evapotranspiration",
        ],
        "hourly": [
            "precipitation",
            "relative_humidity_2m",
            "windspeed_10m",
            "surface_pressure",
        ],
        "forecast_days": 16,
        "timezone": "Africa/Douala",
    }

    fcast_resp = requests.get(fcast_url, params=fcast_params, timeout=30)
    fcast_resp.raise_for_status()
    fcast_data = fcast_resp.json()

    print(f"[Open-Meteo] ✅ Historique {days_back}j + prévisions 16j récupérés")

    return {
        "source": "open-meteo",
        "historique_daily": hist_data.get("daily", {}),
        "historique_hourly": hist_data.get("hourly", {}),
        "previsions_daily": fcast_data.get("daily", {}),
        "previsions_hourly": fcast_data.get("hourly", {}),
    }


# ─── 2. NASA POWER ─────────────────────────────────────────────────────────────

def fetch_nasa_power(days_back: int = 7) -> dict:
    today = datetime.date.today()
    end = today - datetime.timedelta(days=7)
    start = end - datetime.timedelta(days=days_back)

    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        "parameters": "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,RH2M,ALLSKY_SFC_SW_DWN,WS10M,PS,QV2M",
        "community": "AG",
        "longitude": LON,
        "latitude": LAT,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }

    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    print(f"[NASA POWER] ✅ Données {days_back}j récupérées")

    return {
        "source": "nasa-power",
        "parametres": data.get("properties", {}).get("parameter", {}),
    }


# ─── 3. GOOGLE EARTH ENGINE ────────────────────────────────────────────────────

def _init_gee() -> bool:
    """Initialise GEE, retourne True si succès."""
    try:
        import ee
    except ImportError:
        print("[GEE] ⚠️  earthengine-api non installé : pip install earthengine-api")
        return False

    if not os.path.exists(KEY_PATH):
        print(f"[GEE] ⚠️  Clé JSON introuvable : {KEY_PATH}")
        return False

    try:
        credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_PATH)
        ee.Initialize(credentials, project=PROJECT_ID)
        return True
    except Exception as e:
        print(f"[GEE] ❌ Erreur d'authentification : {e}")
        return False


def fetch_gee_sentinel2(window_days: int = 60) -> dict:
    """
    Récupère NDVI, NDWI, NBR, NDRE depuis Sentinel-2.
    - Filtre nuages élargi à 80% pour zone tropicale très nuageuse
    - Fenêtre temporelle 60 jours par défaut
    - Masque nuage pixel par pixel via QA60
    """
    import ee

    today = datetime.date.today()
    start = today - datetime.timedelta(days=window_days)
    point = ee.Geometry.Point([LON, LAT])
    zone  = point.buffer(10000)

    def mask_s2_clouds(image):
        qa = image.select("QA60")
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
            qa.bitwiseAnd(cirrus_bit_mask).eq(0)
        )
        return image.updateMask(mask).divide(10000)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start.isoformat(), today.isoformat())
        .filterBounds(zone)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
        .map(mask_s2_clouds)
    )

    count = collection.size().getInfo()
    print(f"[GEE Sentinel-2] 🛰️  {count} image(s) trouvée(s) sur {window_days} jours (filtre nuages 80%)")

    if count == 0:
        print("[GEE Sentinel-2] ⚠️  Aucune image après masquage → passage au fallback MODIS")
        return None

    composite = collection.median()

    ndvi = composite.normalizedDifference(["B8",  "B4"]).rename("NDVI")
    ndwi = composite.normalizedDifference(["B3",  "B8"]).rename("NDWI")
    nbr  = composite.normalizedDifference(["B8",  "B12"]).rename("NBR")
    ndre = composite.normalizedDifference(["B8",  "B5"]).rename("NDRE")

    indices = composite.addBands([ndvi, ndwi, nbr, ndre])

    stats = indices.select(["NDVI", "NDWI", "NBR", "NDRE"]).reduceRegion(
        reducer=ee.Reducer.mean().combine(
            ee.Reducer.stdDev(), sharedInputs=True
        ).combine(
            ee.Reducer.minMax(), sharedInputs=True
        ),
        geometry=zone,
        scale=20,
        maxPixels=1e9,
    ).getInfo()

    print(f"[GEE Sentinel-2] ✅ Indices calculés : NDVI, NDWI, NBR, NDRE")

    return {
        "capteur": "Sentinel-2",
        "periode": {"debut": start.isoformat(), "fin": today.isoformat()},
        "nb_images": count,
        "filtre_nuages_pct": 80,
        "indices": stats,
    }


def fetch_gee_modis_fallback(window_days: int = 60) -> dict:
    """
    Fallback MODIS Terra (MOD13A1) — résolution 500m, mise à jour 16 jours.
    Disponible même par forte couverture nuageuse grâce à la composition temporelle.
    """
    import ee

    today = datetime.date.today()
    start = today - datetime.timedelta(days=window_days)
    point = ee.Geometry.Point([LON, LAT])
    zone  = point.buffer(10000)

    modis = (
        ee.ImageCollection("MODIS/061/MOD13A1")
        .filterDate(start.isoformat(), today.isoformat())
        .filterBounds(zone)
        .select(["NDVI", "EVI", "SummaryQA"])
    )

    count = modis.size().getInfo()
    print(f"[GEE MODIS] 🛰️  {count} composite(s) MODIS trouvé(s) sur {window_days} jours")

    if count == 0:
        return {
            "capteur": "MODIS-fallback",
            "erreur": "Aucune donnée MODIS disponible",
        }

    composite = modis.mean().multiply(0.0001)

    stats = composite.select(["NDVI", "EVI"]).reduceRegion(
        reducer=ee.Reducer.mean().combine(
            ee.Reducer.minMax(), sharedInputs=True
        ),
        geometry=zone,
        scale=500,
        maxPixels=1e9,
    ).getInfo()

    print(f"[GEE MODIS] ✅ NDVI et EVI MODIS récupérés (fallback)")

    return {
        "capteur": "MODIS-MOD13A1-500m",
        "periode": {"debut": start.isoformat(), "fin": today.isoformat()},
        "nb_composites": count,
        "indices": stats,
        "note": "Données MODIS (résolution 500m, composition 16j) — utilisées en fallback Sentinel-2",
    }


def fetch_gee_soil_moisture() -> dict:
    """
    Humidité du sol via SMAP Level-4 (NASA/SMAP/SPL4SMGP/008).
    Remplace l'ancien dataset NASA_USDA/HSL/SMAP10KM_soil_moisture (déprécié).
    Résolution ~9km, latence ~3 jours.
    Variables :
        sm_surface      = humidité 0-5cm (m³/m³)
        sm_rootzone     = humidité 0-100cm (m³/m³)
    """
    import ee

    today = datetime.date.today()
    start = today - datetime.timedelta(days=30)
    point = ee.Geometry.Point([LON, LAT])
    zone  = point.buffer(10000)

    try:
        smap = (
            ee.ImageCollection("NASA/SMAP/SPL4SMGP/008")
            .filterDate(start.isoformat(), today.isoformat())
            .filterBounds(zone)
            .select(["sm_surface", "sm_rootzone"])
            .mean()
        )
        stats = smap.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone,
            scale=9000,
            maxPixels=1e9,
        ).getInfo()
        print(f"[GEE SMAP] ✅ Humidité du sol récupérée (SPL4SMGP/008)")
        return {
            "source": "SMAP-SPL4SMGP-008",
            "humidite_sol": stats,
            "legende": {
                "sm_surface": "humidité 0-5cm (m³/m³)",
                "sm_rootzone": "humidité 0-100cm (m³/m³)",
            }
        }
    except Exception as e:
        print(f"[GEE SMAP] ⚠️  Indisponible : {e}")
        return {"source": "SMAP-SPL4SMGP-008", "erreur": str(e)}


def fetch_gee_all() -> dict:
    """
    Orchestre toutes les collectes GEE :
    1. Sentinel-2 (filtre 80%, 60 jours)
    2. Fallback MODIS si Sentinel-2 vide
    3. SMAP humidité du sol (dataset v008)
    """
    if not _init_gee():
        return {"source": "gee", "erreur": "Initialisation GEE impossible"}

    result = {"source": "gee"}

    s2 = fetch_gee_sentinel2(window_days=60)
    if s2 is not None:
        result["sentinel2"] = s2
    else:
        result["modis"] = fetch_gee_modis_fallback(window_days=60)

    result["smap"] = fetch_gee_soil_moisture()

    return result


# ─── 4. AGRÉGATION & SAUVEGARDE ────────────────────────────────────────────────

def aggregate_and_save(openmeteo: dict, nasa: dict, gee: dict) -> str:
    today = datetime.date.today().isoformat()

    pluie_7j = 0.0
    try:
        precips = openmeteo["historique_daily"].get("precipitation_sum", [])
        pluie_7j = sum(p for p in precips[-7:] if p is not None)
    except Exception:
        pass

    pluie_prev_7j = 0.0
    try:
        precips_prev = openmeteo["previsions_daily"].get("precipitation_sum", [])
        pluie_prev_7j = sum(p for p in precips_prev[:7] if p is not None)
    except Exception:
        pass

    ndvi_val = None
    ndwi_val = None
    capteur = "inconnu"
    try:
        if "sentinel2" in gee:
            ndvi_val = round(gee["sentinel2"]["indices"].get("NDVI_mean", 0) or 0, 4)
            ndwi_val = round(gee["sentinel2"]["indices"].get("NDWI_mean", 0) or 0, 4)
            capteur = "Sentinel-2"
        elif "modis" in gee:
            ndvi_val = round(gee["modis"]["indices"].get("NDVI_mean", 0) or 0, 4)
            capteur = "MODIS"
    except Exception:
        pass

    humidite_sol = None
    try:
        humidite_sol = gee["smap"]["humidite_sol"].get("sm_surface")
    except Exception:
        pass

    risque_inondation      = "élevé" if pluie_7j > 150 else ("modéré" if pluie_7j > 80 else "faible")
    risque_inondation_prev = "élevé" if pluie_prev_7j > 150 else ("modéré" if pluie_prev_7j > 80 else "faible")
    risque_secheresse      = "élevé" if (ndvi_val is not None and ndvi_val < 0.2) else "faible"
    risque_submersion      = "élevé" if (ndwi_val is not None and ndwi_val > 0.3) else "faible"
    risque_sol_sature      = "élevé" if (humidite_sol is not None and humidite_sol > 0.4) else "faible"

    payload = {
        "meta": {
            "version": "2.1",
            "date_collecte": today,
            "zone": CITY,
            "latitude": LAT,
            "longitude": LON,
            "projet": "SAMCAM",
            "capteur_satellite": capteur,
        },
        "meteorologie": openmeteo,
        "nasa_power": nasa,
        "satellitaire": gee,
        "indicateurs_risque": {
            "pluie_cumulee_7j_mm": round(pluie_7j, 2),
            "pluie_prevue_7j_mm": round(pluie_prev_7j, 2),
            "ndvi_moyen": ndvi_val,
            "ndwi_moyen": ndwi_val,
            "humidite_sol_sm_surface": humidite_sol,
            "risque_inondation_observe": risque_inondation,
            "risque_inondation_prevu": risque_inondation_prev,
            "risque_secheresse": risque_secheresse,
            "risque_submersion_cotiere": risque_submersion,
            "risque_sol_sature": risque_sol_sature,
        },
        "contexte_phi3": (
            f"Date: {today}. Zone: {CITY}, Cameroun côtier (lat {LAT}, lon {LON}). "
            f"Saison: {'pluies' if datetime.date.today().month in [3,4,5,6,9,10,11] else 'sèche'}. "
            f"Pluie observée 7 derniers jours: {round(pluie_7j,1)} mm. "
            f"Pluie prévue 7 prochains jours: {round(pluie_prev_7j,1)} mm. "
            f"Indice végétation NDVI ({capteur}): {ndvi_val}. "
            f"Indice eau NDWI: {ndwi_val}. "
            f"Humidité sol surface SMAP: {humidite_sol} m³/m³. "
            f"Risque inondation observé: {risque_inondation}. "
            f"Risque inondation prévu: {risque_inondation_prev}. "
            f"Risque sécheresse: {risque_secheresse}. "
            f"Risque submersion côtière: {risque_submersion}. "
            f"Risque sol saturé: {risque_sol_sature}."
        ),
    }

    filename = os.path.join(OUT_DIR, f"kribi_{today}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[SAMCAM] 💾 Données sauvegardées : {filename}")
    return filename


# ─── 5. POINT D'ENTRÉE ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM v2.1 — Collecte données Kribi")
    parser.add_argument("--days", type=int, default=7,
                        help="Jours d'historique météo (défaut: 7)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"SAMCAM v2.1 — Collecte automatique {CITY}")
    print(f"Date : {datetime.date.today().isoformat()}")
    print("=" * 60)

    print("\n[1/3] Open-Meteo...")
    openmeteo = fetch_openmeteo(days_back=args.days)

    print("\n[2/3] NASA POWER...")
    nasa = fetch_nasa_power(days_back=args.days)

    print("\n[3/3] Google Earth Engine (Sentinel-2 → MODIS fallback + SMAP)...")
    gee = fetch_gee_all()

    print("\n[4/4] Agrégation et sauvegarde...")
    output_file = aggregate_and_save(openmeteo, nasa, gee)

    print("\n" + "=" * 60)
    print("✅ Collecte terminée")
    print(f"📄 Fichier : {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
