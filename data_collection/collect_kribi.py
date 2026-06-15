#!/usr/bin/env python3
"""
SAMCAM - Script de collecte automatique des données climatiques de Kribi

Sources :
- Open-Meteo (météo historique + prévisions) — aucune clé API requise
- Google Earth Engine (Sentinel-2 NDVI, NDWI, NBR) — via service account
- NASA POWER (rayonnement solaire, précipitations) — aucune clé API requise

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
import time

# ─── CONFIG ────────────────────────────────────────────────────────────────────

LAT = 2.9391
LON = 9.9098
CITY = "Kribi"
PROJECT_ID = "samcam-499511"
SERVICE_ACCOUNT = "gee-kribi-bot@samcam-499511.iam.gserviceaccount.com"

# Chemin local vers la clé JSON — NE PAS COMMITTER CE FICHIER
KEY_PATH = os.environ.get(
    "EE_PRIVATE_KEY_PATH",
    os.path.expanduser("~/.config/gee/kribi-key.json")
)

# Dossier de sortie
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)


# ─── 1. OPEN-METEO ─────────────────────────────────────────────────────────────

def fetch_openmeteo(days_back: int = 7) -> dict:
    """
    Récupère les données météo historiques et les prévisions 7 jours
    depuis Open-Meteo (gratuit, aucune clé requise).
    """
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days_back)

    # Données historiques
    hist_url = "https://archive-api.open-meteo.com/v1/archive"
    hist_params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "windspeed_10m_max",
            "et0_fao_evapotranspiration",
            "rain_sum",
        ],
        "timezone": "Africa/Douala",
    }

    hist_resp = requests.get(hist_url, params=hist_params, timeout=30)
    hist_resp.raise_for_status()
    hist_data = hist_resp.json()

    # Prévisions 7 jours
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
        ],
        "forecast_days": 7,
        "timezone": "Africa/Douala",
    }

    fcast_resp = requests.get(fcast_url, params=fcast_params, timeout=30)
    fcast_resp.raise_for_status()
    fcast_data = fcast_resp.json()

    print(f"[Open-Meteo] ✅ Historique {days_back}j + prévisions 7j récupérés")

    return {
        "source": "open-meteo",
        "historique": hist_data.get("daily", {}),
        "previsions": fcast_data.get("daily", {}),
    }


# ─── 2. NASA POWER ─────────────────────────────────────────────────────────────

def fetch_nasa_power(days_back: int = 7) -> dict:
    """
    Récupère les données de rayonnement solaire et de précipitations
    depuis NASA POWER (gratuit, aucune clé requise).
    """
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days_back)

    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        "parameters": "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,RH2M,ALLSKY_SFC_SW_DWN,WS10M",
        "community": "AG",
        "longitude": LON,
        "latitude": LAT,
        "start": start.strftime("%Y%m%d"),
        "end": today.strftime("%Y%m%d"),
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

def fetch_gee_sentinel2() -> dict:
    """
    Récupère les indices NDVI, NDWI, NBR depuis Sentinel-2 (GEE)
    pour la zone de Kribi (zone tampon 10km).
    Retourne un dict avec les statistiques des 30 derniers jours.
    """
    try:
        import ee
    except ImportError:
        print("[GEE] ⚠️  earthengine-api non installé. Installe avec: pip install earthengine-api")
        return {"source": "gee", "erreur": "earthengine-api non installé"}

    if not os.path.exists(KEY_PATH):
        print(f"[GEE] ⚠️  Clé JSON introuvable : {KEY_PATH}")
        print("      Définis la variable d'environnement EE_PRIVATE_KEY_PATH")
        return {"source": "gee", "erreur": f"Clé introuvable: {KEY_PATH}"}

    try:
        credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_PATH)
        ee.Initialize(credentials, project=PROJECT_ID)
    except Exception as e:
        print(f"[GEE] ❌ Erreur d'authentification : {e}")
        return {"source": "gee", "erreur": str(e)}

    today = datetime.date.today()
    start = today - datetime.timedelta(days=30)

    point = ee.Geometry.Point([LON, LAT])
    zone  = point.buffer(10000)  # 10 km autour de Kribi

    # Chargement Sentinel-2 L2A avec masque nuages
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
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .map(mask_s2_clouds)
    )

    count = collection.size().getInfo()
    print(f"[GEE] 🛰️  {count} image(s) Sentinel-2 trouvée(s) pour les 30 derniers jours")

    if count == 0:
        return {"source": "gee", "erreur": "Aucune image disponible (couverture nuageuse trop élevée)"}

    composite = collection.median()

    # Calcul des indices
    ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndwi = composite.normalizedDifference(["B3", "B8"]).rename("NDWI")
    nbr  = composite.normalizedDifference(["B8", "B12"]).rename("NBR")

    indices = composite.addBands([ndvi, ndwi, nbr])

    stats = indices.select(["NDVI", "NDWI", "NBR"]).reduceRegion(
        reducer=ee.Reducer.mean().combine(
            ee.Reducer.stdDev(), sharedInputs=True
        ).combine(
            ee.Reducer.minMax(), sharedInputs=True
        ),
        geometry=zone,
        scale=20,
        maxPixels=1e9,
    ).getInfo()

    # Récupération de l'humidité du sol (SMAP si disponible)
    try:
        smap = (
            ee.ImageCollection("NASA_USDA/HSL/SMAP10KM_soil_moisture")
            .filterDate(start.isoformat(), today.isoformat())
            .filterBounds(zone)
            .select("ssm")
            .mean()
        )
        smap_stats = smap.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone,
            scale=10000,
            maxPixels=1e9,
        ).getInfo()
    except Exception:
        smap_stats = {}

    print(f"[GEE] ✅ Indices calculés : NDVI, NDWI, NBR")

    return {
        "source": "gee",
        "periode": {"debut": start.isoformat(), "fin": today.isoformat()},
        "nb_images": count,
        "indices": stats,
        "humidite_sol_smap": smap_stats,
    }


# ─── 4. AGRÉGATION & SAUVEGARDE ────────────────────────────────────────────────

def aggregate_and_save(openmeteo: dict, nasa: dict, gee: dict) -> str:
    """
    Agrège toutes les sources en un seul JSON structuré
    lisible par Phi-3 mini.
    """
    today = datetime.date.today().isoformat()

    # Calcul indicateurs de risque simples
    pluie_7j = 0.0
    try:
        precips = openmeteo["historique"].get("precipitation_sum", [])
        pluie_7j = sum(p for p in precips if p is not None)
    except Exception:
        pass

    ndvi_val = None
    ndwi_val = None
    try:
        ndvi_val = round(gee["indices"].get("NDVI_mean", 0), 4)
        ndwi_val = round(gee["indices"].get("NDWI_mean", 0), 4)
    except Exception:
        pass

    # Score de risque simplifié (sera affiné par Phi-3)
    risque_inondation = "élevé" if pluie_7j > 150 else ("modéré" if pluie_7j > 80 else "faible")
    risque_secheresse = "élevé" if (ndvi_val is not None and ndvi_val < 0.2) else "faible"
    risque_submersion = "élevé" if (ndwi_val is not None and ndwi_val > 0.3) else "faible"

    payload = {
        "meta": {
            "date_collecte": today,
            "zone": CITY,
            "latitude": LAT,
            "longitude": LON,
            "projet": "SAMCAM",
        },
        "meteorologie": openmeteo,
        "nasa_power": nasa,
        "satellitaire": gee,
        "indicateurs_risque": {
            "pluie_cumulee_7j_mm": round(pluie_7j, 2),
            "ndvi_moyen": ndvi_val,
            "ndwi_moyen": ndwi_val,
            "risque_inondation": risque_inondation,
            "risque_secheresse": risque_secheresse,
            "risque_submersion_cotiere": risque_submersion,
        },
        "contexte_phi3": (
            f"Date: {today}. Zone: {CITY} (Cameroun côtier, latitude {LAT}, longitude {LON}). "
            f"Pluie cumulée 7 derniers jours: {round(pluie_7j,1)} mm. "
            f"Indice végétation NDVI moyen: {ndvi_val}. "
            f"Indice eau NDWI moyen: {ndwi_val}. "
            f"Risque inondation estimé: {risque_inondation}. "
            f"Risque sécheresse estimé: {risque_secheresse}. "
            f"Risque submersion côtière estimé: {risque_submersion}."
        ),
    }

    filename = os.path.join(OUT_DIR, f"kribi_{today}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[SAMCAM] 💾 Données sauvegardées : {filename}")
    return filename


# ─── 5. POINT D'ENTRÉE ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SAMCAM — Collecte données Kribi")
    parser.add_argument(
        "--days", type=int, default=7,
        help="Nombre de jours historiques à récupérer (défaut: 7)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"SAMCAM — Collecte automatique {CITY}")
    print(f"Date : {datetime.date.today().isoformat()}")
    print("=" * 60)

    print("\n[1/3] Récupération Open-Meteo...")
    openmeteo = fetch_openmeteo(days_back=args.days)

    print("\n[2/3] Récupération NASA POWER...")
    nasa = fetch_nasa_power(days_back=args.days)

    print("\n[3/3] Récupération Google Earth Engine (Sentinel-2)...")
    gee = fetch_gee_sentinel2()

    print("\n[4/4] Agrégation et sauvegarde...")
    output_file = aggregate_and_save(openmeteo, nasa, gee)

    print("\n" + "=" * 60)
    print("✅ Collecte terminée")
    print(f"📄 Fichier : {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
