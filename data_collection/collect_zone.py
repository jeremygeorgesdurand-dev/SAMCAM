#!/usr/bin/env python3
"""
SAMCAM - Script de collecte multi-zones climatiques

Refactorisation de collect_kribi.py pour supporter plusieurs zones géographiques,
notamment les zones agricoles du Cameroun.

Sources :
- Open-Meteo (météo historique + prévisions) — aucune clé API requise
- Google Earth Engine (Sentinel-2 NDVI/NDWI/NBR/NDRE + fallback MODIS) — via service account
- NASA POWER (rayonnement solaire, précipitations) — aucune clé API requise

Usage :
    python collect_zone.py                        # Toutes les zones
    python collect_zone.py --zone Kribi           # Une seule zone
    python collect_zone.py --zone Garoua --days 14
    python collect_zone.py --list                 # Lister les zones disponibles

Sortie :
    data/<zone_slug>_YYYY-MM-DD.json
"""

import os
import json
import argparse
import datetime
import requests

# ─── CONFIG GLOBALE ────────────────────────────────────────────────────────────

PROJECT_ID      = "samcam-499511"
SERVICE_ACCOUNT = "gee-kribi-bot@samcam-499511.iam.gserviceaccount.com"
KEY_PATH = os.environ.get(
    "EE_PRIVATE_KEY_PATH",
    os.path.expanduser("~/.config/gee/kribi-key.json")
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)


# ─── ZONES AGRICOLES DU CAMEROUN ──────────────────────────────────────────────
#
# Chaque zone est un dict avec :
#   name    : nom affiché et utilisé comme slug de fichier
#   lat/lon : coordonnées GPS du centroïde
#   type    : catégorie (cotier | agricole | agricole_nord | sahel | maraichage | elevage)
#   cultures: principales cultures / activités agricoles
#   saison_semis : mois de semis principaux (pour les alertes agricoles)

ZONES = [
    {
        "name": "Kribi",
        "lat": 2.9391,
        "lon": 9.9098,
        "type": "cotier",
        "cultures": ["pêche", "cacao", "palmier à huile"],
        "saison_semis": [3, 4, 9],
    },
    {
        "name": "Ebolowa",
        "lat": 2.9000,
        "lon": 11.1500,
        "type": "agricole",
        "cultures": ["cacao", "palmier à huile", "vivriers"],
        "saison_semis": [3, 4, 9],
    },
    {
        "name": "Kumba",
        "lat": 4.6333,
        "lon": 9.4500,
        "type": "agricole",
        "cultures": ["cacao", "bananier", "café robusta"],
        "saison_semis": [3, 4, 9],
    },
    {
        "name": "Bafoussam",
        "lat": 5.4764,
        "lon": 10.4176,
        "type": "agricole",
        "cultures": ["café arabica", "maïs", "pomme de terre"],
        "saison_semis": [3, 4, 8, 9],
    },
    {
        "name": "Yaounde_peri",
        "lat": 3.9000,
        "lon": 11.5500,
        "type": "maraichage",
        "cultures": ["maraîchage", "manioc", "plantain"],
        "saison_semis": [3, 4, 9, 10],
    },
    {
        "name": "Ngaoundere",
        "lat": 7.3167,
        "lon": 13.5833,
        "type": "elevage",
        "cultures": ["élevage bovin", "maïs", "sorgho"],
        "saison_semis": [5, 6],
    },
    {
        "name": "Garoua",
        "lat": 9.3017,
        "lon": 13.3922,
        "type": "agricole_nord",
        "cultures": ["coton", "sorgho", "mil", "arachide"],
        "saison_semis": [5, 6],
    },
    {
        "name": "Maroua",
        "lat": 10.5910,
        "lon": 14.3158,
        "type": "sahel",
        "cultures": ["mil", "sorgho", "niébé", "oignon"],
        "saison_semis": [6, 7],
    },
]


# ─── UTILITAIRES ───────────────────────────────────────────────────────────────

def zone_slug(name: str) -> str:
    """Convertit un nom de zone en slug de fichier (ex: 'Yaounde_peri' → 'yaounde_peri')."""
    return name.lower().replace(" ", "_")


def get_zone_by_name(name: str) -> dict | None:
    """Retourne la config d'une zone par son nom (insensible à la casse)."""
    for z in ZONES:
        if z["name"].lower() == name.lower():
            return z
    return None


def is_semis_period(zone: dict) -> bool:
    """Retourne True si on est dans une période de semis pour cette zone."""
    return datetime.date.today().month in zone.get("saison_semis", [])


# ─── 1. OPEN-METEO ─────────────────────────────────────────────────────────────

def fetch_openmeteo(lat: float, lon: float, days_back: int = 7) -> dict:
    today = datetime.date.today()
    end   = today - datetime.timedelta(days=1)
    start = end   - datetime.timedelta(days=days_back)

    hist_url = "https://archive-api.open-meteo.com/v1/archive"
    hist_params = {
        "latitude":  lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date":   end.isoformat(),
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
        "latitude":  lat,
        "longitude": lon,
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

    print(f"  [Open-Meteo] ✅ Historique {days_back}j + prévisions 16j récupérés")

    return {
        "source": "open-meteo",
        "historique_daily":  hist_data.get("daily",  {}),
        "historique_hourly": hist_data.get("hourly", {}),
        "previsions_daily":  fcast_data.get("daily",  {}),
        "previsions_hourly": fcast_data.get("hourly", {}),
    }


# ─── 2. NASA POWER ─────────────────────────────────────────────────────────────

def fetch_nasa_power(lat: float, lon: float, days_back: int = 7) -> dict:
    today = datetime.date.today()
    end   = today - datetime.timedelta(days=7)
    start = end   - datetime.timedelta(days=days_back)

    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        "parameters": "PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,RH2M,ALLSKY_SFC_SW_DWN,WS10M,PS,QV2M",
        "community":  "AG",
        "longitude":  lon,
        "latitude":   lat,
        "start":  start.strftime("%Y%m%d"),
        "end":    end.strftime("%Y%m%d"),
        "format": "JSON",
    }

    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    print(f"  [NASA POWER] ✅ Données {days_back}j récupérées")

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
        print("  [GEE] ⚠️  earthengine-api non installé : pip install earthengine-api")
        return False

    if not os.path.exists(KEY_PATH):
        print(f"  [GEE] ⚠️  Clé JSON introuvable : {KEY_PATH}")
        return False

    try:
        credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_PATH)
        ee.Initialize(credentials, project=PROJECT_ID)
        return True
    except Exception as e:
        print(f"  [GEE] ❌ Erreur d'authentification : {e}")
        return False


def fetch_gee_sentinel2(lat: float, lon: float, window_days: int = 60) -> dict | None:
    """
    Récupère NDVI, NDWI, NBR, NDRE depuis Sentinel-2.
    - Filtre nuages élargi à 80% pour zone tropicale très nuageuse
    - Fenêtre temporelle 60 jours par défaut
    - Masque nuage pixel par pixel via QA60
    """
    import ee

    today = datetime.date.today()
    start = today - datetime.timedelta(days=window_days)
    point = ee.Geometry.Point([lon, lat])
    zone  = point.buffer(10000)

    def mask_s2_clouds(image):
        qa = image.select("QA60")
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        mask = (
            qa.bitwiseAnd(cloud_bit_mask).eq(0)
            .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
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
    print(f"  [GEE Sentinel-2] 🛰️  {count} image(s) trouvée(s) sur {window_days} jours")

    if count == 0:
        print("  [GEE Sentinel-2] ⚠️  Aucune image → fallback MODIS")
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

    print(f"  [GEE Sentinel-2] ✅ Indices calculés : NDVI, NDWI, NBR, NDRE")
    return {
        "capteur": "Sentinel-2",
        "periode": {"debut": start.isoformat(), "fin": today.isoformat()},
        "nb_images": count,
        "filtre_nuages_pct": 80,
        "indices": stats,
    }


def fetch_gee_modis_fallback(lat: float, lon: float, window_days: int = 60) -> dict:
    """Fallback MODIS Terra (MOD13A1) — résolution 500m, mise à jour 16 jours."""
    import ee

    today = datetime.date.today()
    start = today - datetime.timedelta(days=window_days)
    point = ee.Geometry.Point([lon, lat])
    zone  = point.buffer(10000)

    modis = (
        ee.ImageCollection("MODIS/061/MOD13A1")
        .filterDate(start.isoformat(), today.isoformat())
        .filterBounds(zone)
        .select(["NDVI", "EVI", "SummaryQA"])
    )

    count = modis.size().getInfo()
    print(f"  [GEE MODIS] 🛰️  {count} composite(s) MODIS trouvé(s) sur {window_days} jours")

    if count == 0:
        return {"capteur": "MODIS-fallback", "erreur": "Aucune donnée MODIS disponible"}

    composite = modis.mean().multiply(0.0001)
    stats = composite.select(["NDVI", "EVI"]).reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
        geometry=zone,
        scale=500,
        maxPixels=1e9,
    ).getInfo()

    print(f"  [GEE MODIS] ✅ NDVI et EVI MODIS récupérés (fallback)")
    return {
        "capteur": "MODIS-MOD13A1-500m",
        "periode": {"debut": start.isoformat(), "fin": today.isoformat()},
        "nb_composites": count,
        "indices": stats,
        "note": "Données MODIS (résolution 500m, composition 16j) — utilisées en fallback Sentinel-2",
    }


def fetch_gee_soil_moisture(lat: float, lon: float) -> dict:
    """
    Humidité du sol via SMAP Level-4 (NASA/SMAP/SPL4SMGP/008).
    Résolution ~9km, latence ~3 jours.
    """
    import ee

    today = datetime.date.today()
    start = today - datetime.timedelta(days=30)
    point = ee.Geometry.Point([lon, lat])
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
        print(f"  [GEE SMAP] ✅ Humidité du sol récupérée (SPL4SMGP/008)")
        return {
            "source": "SMAP-SPL4SMGP-008",
            "humidite_sol": stats,
            "legende": {
                "sm_surface":  "humidité 0-5cm (m³/m³)",
                "sm_rootzone": "humidité 0-100cm (m³/m³)",
            },
        }
    except Exception as e:
        print(f"  [GEE SMAP] ⚠️  Indisponible : {e}")
        return {"source": "SMAP-SPL4SMGP-008", "erreur": str(e)}


def fetch_gee_all(lat: float, lon: float) -> dict:
    """Orchestre toutes les collectes GEE pour une zone (lat, lon)."""
    if not _init_gee():
        return {"source": "gee", "erreur": "Initialisation GEE impossible"}

    result = {"source": "gee"}

    s2 = fetch_gee_sentinel2(lat, lon, window_days=60)
    if s2 is not None:
        result["sentinel2"] = s2
    else:
        result["modis"] = fetch_gee_modis_fallback(lat, lon, window_days=60)

    result["smap"] = fetch_gee_soil_moisture(lat, lon)
    return result


# ─── 4. CALCUL DES INDICATEURS AGRICOLES ──────────────────────────────────────

def compute_agricultural_indicators(zone: dict, openmeteo: dict, gee: dict) -> dict:
    """
    Calcule les indicateurs de risque adaptés au contexte agricole de la zone.
    Inclut les alertes semis et les indicateurs spécifiques à chaque type de zone.
    """
    today = datetime.date.today()

    # ── Pluie cumulée et prévue
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

    # ── ETP cumulée 7 jours (évapotranspiration potentielle FAO-56)
    etp_7j = 0.0
    try:
        etp_7j = sum(
            e for e in openmeteo["historique_daily"].get("et0_fao_evapotranspiration", [])[-7:]
            if e is not None
        )
    except Exception:
        pass

    # ── Bilan hydrique simplifié (P - ETP)
    bilan_hydrique_7j = round(pluie_7j - etp_7j, 2)

    # ── Indices satellitaires
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

    humidite_sol = None
    try:
        humidite_sol = gee["smap"]["humidite_sol"].get("sm_surface")
    except Exception:
        pass

    # ── Seuils adaptés par type de zone
    zone_type = zone.get("type", "agricole")
    # Zones sèches du nord : seuils de pluie abaissés
    seuil_inond_eleve  = 100 if zone_type in ("sahel", "agricole_nord") else 150
    seuil_inond_modere = 50  if zone_type in ("sahel", "agricole_nord") else 80

    # ── Risques
    risque_inondation      = "élevé"  if pluie_7j      > seuil_inond_eleve  else ("modéré" if pluie_7j      > seuil_inond_modere else "faible")
    risque_inondation_prev = "élevé"  if pluie_prev_7j > seuil_inond_eleve  else ("modéré" if pluie_prev_7j > seuil_inond_modere else "faible")
    risque_secheresse      = "élevé"  if (ndvi_val is not None and ndvi_val < 0.2) or bilan_hydrique_7j < -30 else ("modéré" if bilan_hydrique_7j < -10 else "faible")
    risque_submersion      = "élevé"  if (ndwi_val is not None and ndwi_val > 0.3) else "faible"
    risque_sol_sature      = "élevé"  if (humidite_sol is not None and humidite_sol > 0.4) else "faible"

    # ── Stress végétal (NDRE > NDVI pour cultures)
    stress_vegetal = "élevé" if (ndre_val is not None and ndre_val < 0.15) else ("modéré" if (ndre_val is not None and ndre_val < 0.25) else "faible")

    # ── Alerte semis
    alerte_semis = None
    if is_semis_period(zone):
        if risque_inondation in ("modéré", "élevé"):
            alerte_semis = "⚠️ Période de semis — risque d'inondation : retarder ou protéger les semis"
        elif risque_secheresse == "élevé":
            alerte_semis = "⚠️ Période de semis — risque de sécheresse : irrigation recommandée"
        else:
            alerte_semis = "✅ Période de semis — conditions favorables"

    return {
        "pluie_cumulee_7j_mm":    round(pluie_7j,      2),
        "pluie_prevue_7j_mm":     round(pluie_prev_7j, 2),
        "etp_cumulee_7j_mm":      round(etp_7j,        2),
        "bilan_hydrique_7j_mm":   bilan_hydrique_7j,
        "ndvi_moyen":             ndvi_val,
        "ndwi_moyen":             ndwi_val,
        "ndre_moyen":             ndre_val,
        "humidite_sol_sm_surface": humidite_sol,
        "capteur_satellite":      capteur,
        "risque_inondation_observe":  risque_inondation,
        "risque_inondation_prevu":    risque_inondation_prev,
        "risque_secheresse":          risque_secheresse,
        "risque_submersion_cotiere":  risque_submersion,
        "risque_sol_sature":          risque_sol_sature,
        "stress_vegetal":             stress_vegetal,
        "alerte_semis":               alerte_semis,
        "periode_semis_active":       is_semis_period(zone),
    }


# ─── 5. AGRÉGATION & SAUVEGARDE ────────────────────────────────────────────────

def aggregate_and_save(
    zone: dict,
    openmeteo: dict,
    nasa: dict,
    gee: dict,
) -> str:
    today       = datetime.date.today().isoformat()
    indicateurs = compute_agricultural_indicators(zone, openmeteo, gee)
    slug        = zone_slug(zone["name"])

    saison_mois = datetime.date.today().month
    saison = "pluies" if saison_mois in [3, 4, 5, 6, 9, 10, 11] else "sèche"

    payload = {
        "meta": {
            "version":     "3.0-multizone",
            "date_collecte": today,
            "zone":        zone["name"],
            "zone_type":   zone["type"],
            "cultures":    zone["cultures"],
            "latitude":    zone["lat"],
            "longitude":   zone["lon"],
            "saison":      saison,
            "projet":      "SAMCAM",
            "capteur_satellite": indicateurs["capteur_satellite"],
        },
        "meteorologie": openmeteo,
        "nasa_power":    nasa,
        "satellitaire":  gee,
        "indicateurs_risque": indicateurs,
        "contexte_phi3": (
            f"Date: {today}. Zone: {zone['name']}, Cameroun ({zone['type']}) "
            f"(lat {zone['lat']}, lon {zone['lon']}). Saison: {saison}. "
            f"Cultures principales: {', '.join(zone['cultures'])}. "
            f"Pluie observée 7j: {indicateurs['pluie_cumulee_7j_mm']} mm. "
            f"Pluie prévue 7j: {indicateurs['pluie_prevue_7j_mm']} mm. "
            f"ETP 7j: {indicateurs['etp_cumulee_7j_mm']} mm. "
            f"Bilan hydrique 7j: {indicateurs['bilan_hydrique_7j_mm']} mm. "
            f"NDVI ({indicateurs['capteur_satellite']}): {indicateurs['ndvi_moyen']}. "
            f"NDRE: {indicateurs['ndre_moyen']}. "
            f"Humidité sol: {indicateurs['humidite_sol_sm_surface']} m³/m³. "
            f"Risque inondation: {indicateurs['risque_inondation_observe']}. "
            f"Risque sécheresse: {indicateurs['risque_secheresse']}. "
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

def collect_zone(zone: dict, days: int = 7) -> str:
    """Collecte toutes les données pour une zone géographique donnée."""
    lat, lon = zone["lat"], zone["lon"]

    print(f"  [1/3] Open-Meteo...")
    openmeteo = fetch_openmeteo(lat, lon, days_back=days)

    print(f"  [2/3] NASA POWER...")
    nasa = fetch_nasa_power(lat, lon, days_back=days)

    print(f"  [3/3] Google Earth Engine (Sentinel-2 → MODIS + SMAP)...")
    gee = fetch_gee_all(lat, lon)

    print(f"  [4/4] Agrégation et sauvegarde...")
    return aggregate_and_save(zone, openmeteo, nasa, gee)


# ─── 7. POINT D'ENTRÉE ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SAMCAM v3.0 — Collecte multi-zones agricoles"
    )
    parser.add_argument(
        "--zone", type=str, default=None,
        help="Nom de la zone à collecter (ex: Kribi, Garoua). Par défaut : toutes les zones."
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="Jours d'historique météo (défaut: 7)"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Lister toutes les zones disponibles et quitter"
    )
    args = parser.parse_args()

    if args.list:
        print("\n📍 Zones disponibles dans SAMCAM :")
        print(f"{'Nom':<20} {'Type':<18} {'Lat':>8} {'Lon':>9}  Cultures")
        print("-" * 80)
        for z in ZONES:
            print(f"{z['name']:<20} {z['type']:<18} {z['lat']:>8.4f} {z['lon']:>9.4f}  {', '.join(z['cultures'])}")
        return

    zones_to_collect = ZONES
    if args.zone:
        found = get_zone_by_name(args.zone)
        if found is None:
            print(f"❌ Zone '{args.zone}' introuvable. Utilisez --list pour voir les zones disponibles.")
            return
        zones_to_collect = [found]

    print("=" * 60)
    print(f"SAMCAM v3.0 — Collecte multi-zones agricoles")
    print(f"Date  : {datetime.date.today().isoformat()}")
    print(f"Zones : {len(zones_to_collect)} zone(s) à collecter")
    print("=" * 60)

    results = []
    errors  = []

    for i, zone in enumerate(zones_to_collect, 1):
        print(f"\n[{i}/{len(zones_to_collect)}] 📍 Zone : {zone['name']} ({zone['type']})")
        try:
            output_file = collect_zone(zone, days=args.days)
            results.append((zone["name"], output_file))
        except Exception as e:
            print(f"  ❌ Erreur sur {zone['name']} : {e}")
            errors.append((zone["name"], str(e)))

    print("\n" + "=" * 60)
    print(f"✅ Collecte terminée — {len(results)} zone(s) OK, {len(errors)} erreur(s)")
    for name, path in results:
        print(f"  📄 {name:<20} → {path}")
    if errors:
        print("\n⚠️  Erreurs :")
        for name, err in errors:
            print(f"  ❌ {name:<20} : {err}")
    print("=" * 60)


if __name__ == "__main__":
    main()
