#!/usr/bin/env python3
"""
SAMCAM V5.3 — Serveur FastAPI REST multi-zones agricoles

Expose les données de risque climatique via une API JSON légère.
Toutes les routes acceptent désormais un paramètre optionnel `?zone=`
pour interroger n'importe quelle zone agricole collectée.

Zones disponibles (définies dans data_collection/collect_zone.py) :
    Kribi, Ebolowa, Kumba, Bafoussam, Yaounde_peri,
    Ngaoundere, Garoua, Maroua

Endpoints :
    GET /api/risk            — Niveau d'alerte + scores ML J0/J+3/J+7
    GET /api/meteo           — Météo actuelle + prévisions 7j
    GET /api/report          — Rapport complet
    GET /api/history         — Historique des N derniers rapports
    GET /api/zones           — Liste des zones disponibles + statut
    GET /api/nearest         — Zone la plus proche d'une position GPS (lat/lon)
    GET /api/nearest-live    — Météo EN TEMPS RÉEL à la position GPS exacte (Open-Meteo)
    GET /health              — Statut du serveur
    GET /docs                — Documentation Swagger auto-générée

Usage :
    uvicorn server.api:app --host 0.0.0.0 --port 8000
    bash server/start.sh

Exemples :
    GET /api/risk                              → Kribi (zone par défaut)
    GET /api/risk?zone=Garoua                  → Garoua
    GET /api/meteo?zone=Maroua                 → Météo de Maroua
    GET /api/history?zone=Bafoussam            → Historique Bafoussam
    GET /api/nearest?lat=4.05&lon=9.70         → Zone la plus proche du point GPS
    GET /api/nearest-live?lat=4.05&lon=9.77    → Météo temps réel à Douala
"""

import json
import glob
import math
import os
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ─── CONFIG ───────────────────────────────────────────────────────────────────────

ROOT          = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DASHBOARD_DIR = os.path.join(ROOT, "dashboard")
REPORTS_DIR   = os.path.join(ROOT, "reports")
DATA_DIR      = os.path.join(ROOT, "data")
MODELS_DIR    = os.path.join(ROOT, "models")
LATEST_JSON   = os.path.join(DASHBOARD_DIR, "latest_report.json")  # fallback V3
PRED_CACHE_PATH = os.path.join(ROOT, "data", "predictions", "latest.json")

DEFAULT_ZONE  = "Kribi"

# Référence des zones — utilisée pour /api/zones et la validation
ZONES_META = [
    {"name": "Kribi",        "type": "cotier",       "lat": 2.9391,  "lon": 9.9098,  "cultures": ["pêche", "cacao", "palmier à huile"]},
    {"name": "Ebolowa",      "type": "agricole",     "lat": 2.9000,  "lon": 11.1500, "cultures": ["cacao", "palmier à huile", "vivriers"]},
    {"name": "Kumba",        "type": "agricole",     "lat": 4.6333,  "lon": 9.4500,  "cultures": ["cacao", "bananier", "café robusta"]},
    {"name": "Bafoussam",    "type": "agricole",     "lat": 5.4764,  "lon": 10.4176, "cultures": ["café arabica", "maïs", "pomme de terre"]},
    {"name": "Yaounde_peri", "type": "maraichage",   "lat": 3.9000,  "lon": 11.5500, "cultures": ["maraîchage", "manioc", "plantain"]},
    {"name": "Ngaoundere",   "type": "elevage",      "lat": 7.3167,  "lon": 13.5833, "cultures": ["élevage bovin", "maïs", "sorgho"]},
    {"name": "Garoua",       "type": "agricole_nord","lat": 9.3017,  "lon": 13.3922, "cultures": ["coton", "sorgho", "mil", "arachide"]},
    {"name": "Maroua",       "type": "sahel",        "lat": 10.5910, "lon": 14.3158, "cultures": ["mil", "sorgho", "niébé", "oignon"]},
    # Zones agricoles ajoutées
    {"name": "Ndop",         "type": "maraichage",   "lat": 5.9833,  "lon": 10.4500, "cultures": ["riz", "maraîchage"]},
    {"name": "Foumbot",      "type": "agricole",     "lat": 5.5167,  "lon": 10.6333, "cultures": ["maïs", "maraîchage", "haricot"]},
    {"name": "Kaele",        "type": "sahel",        "lat": 10.1167, "lon": 14.4500, "cultures": ["sorgho", "mil"]},
    {"name": "Guider",       "type": "agricole_nord","lat": 9.9333,  "lon": 13.9500, "cultures": ["coton", "sorgho", "arachide"]},
    {"name": "Meiganga",     "type": "elevage",      "lat": 6.5167,  "lon": 14.3000, "cultures": ["élevage bovin", "maïs"]},
    {"name": "Mbalmayo",     "type": "maraichage",   "lat": 3.5167,  "lon": 11.5000, "cultures": ["manioc", "plantain", "maraîchage"]},
    {"name": "Bafia",        "type": "agricole",     "lat": 4.7500,  "lon": 11.2333, "cultures": ["arachide", "manioc", "maïs"]},
    {"name": "Bertoua",      "type": "agricole",     "lat": 4.5833,  "lon": 13.6833, "cultures": ["café robusta", "cacao"]},
    {"name": "Nkongsamba",   "type": "agricole",     "lat": 4.9547,  "lon": 9.9401,  "cultures": ["cacao", "bananier"]},
    {"name": "Buea",         "type": "agricole",     "lat": 4.1560,  "lon": 9.2420,  "cultures": ["palmier à huile", "bananier"]},
]
ZONES_NAMES = {z["name"].lower(): z for z in ZONES_META}

# Distance maximale (km) au-delà de laquelle on signale que l'utilisateur est hors zone
MAX_ZONE_DISTANCE_KM = 200

# URL Open-Meteo
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


# ─── APP ─────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SAMCAM API",
    description="Système d'Alerte Météorologique du Cameroun — API REST V5.3 multi-zones",
    version="5.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── CHARGEMENT DU MODÈLE ML ───────────────────────────────────────────────────

# risk_model.py V5 expose des fonctions directement (pas de classe RiskModel)
_predire_risques_fn              = None
_evaluer_previsions_fn           = None
_construire_features_fn          = None
# infer_zonal.py — moteur d'inférence PRIORITAIRE : calcule les vraies features
# d'entraînement (rolling 7/14/30/90j, SPI, etc.) depuis l'historique zonal, au
# lieu du snapshot quotidien à 8 jours (insuffisant pour les modèles zonaux V5).
_infer_zone_risk_fn              = None
_infer_zone_risk_horizon_fn      = None
_infer_zone_risk_series_fn       = None

def _charger_risk_model():
    global _predire_risques_fn, _evaluer_previsions_fn, _construire_features_fn
    global _infer_zone_risk_fn, _infer_zone_risk_horizon_fn, _infer_zone_risk_series_fn
    try:
        import sys
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from inference.risk_model import (
            predire_risques, evaluer_previsions, construire_features_depuis_json,
        )
        _predire_risques_fn     = predire_risques
        _evaluer_previsions_fn  = evaluer_previsions
        _construire_features_fn = construire_features_depuis_json
        try:
            from inference.infer_zonal import (
                infer_zone_risk, infer_zone_risk_horizon, infer_zone_risk_series,
            )
            _infer_zone_risk_fn         = infer_zone_risk
            _infer_zone_risk_horizon_fn = infer_zone_risk_horizon
            _infer_zone_risk_series_fn  = infer_zone_risk_series
            print("[API] ✅ Moteur zonal chargé (infer_zonal.py, prioritaire)")
        except Exception as e:
            print(f"[API] ⚠️  infer_zonal.py indisponible ({e}) — utilisation de risk_model.py seul")
        print("[API] ✅ Modèle ML chargé (predire_risques / evaluer_previsions)")
        return True
    except Exception as e:
        print(f"[API] ⚠️  Modèle ML non disponible ({e}) — fallback sur JSON")
        return None

_risk_model = _charger_risk_model()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _zone_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def _resolve_zone(zone: str) -> dict:
    meta = ZONES_NAMES.get(zone.lower())
    if meta is None:
        noms = ", ".join(z["name"] for z in ZONES_META)
        raise HTTPException(
            status_code=404,
            detail=f"Zone '{zone}' inconnue. Zones disponibles : {noms}"
        )
    return meta


def _load_zone_data(zone: str) -> dict:
    slug = _zone_slug(zone)
    pattern = os.path.join(DATA_DIR, f"{slug}_*.json")
    fichiers = sorted(glob.glob(pattern))

    if fichiers:
        with open(fichiers[-1], encoding="utf-8") as f:
            return json.load(f)

    if zone.lower() == "kribi" and os.path.exists(LATEST_JSON):
        with open(LATEST_JSON, encoding="utf-8") as f:
            return json.load(f)

    raise HTTPException(
        status_code=503,
        detail=(
            f"Aucune donnée disponible pour la zone '{zone}'. "
            f"Lancez : python3 data_collection/collect_all_zones.py --zones {zone}"
        )
    )


def _niveau_alerte(score_inondation: float = 0, score_secheresse: float = 0, score_chaleur: float = 0, **_) -> str:
    max_score = max(score_inondation, score_secheresse, score_chaleur)
    if   max_score >= 0.70: return "ROUGE"
    elif max_score >= 0.45: return "ORANGE"
    elif max_score >= 0.25: return "JAUNE"
    return "VERT"


def _last_collect_date(zone: str) -> Optional[str]:
    slug = _zone_slug(zone)
    fichiers = sorted(glob.glob(os.path.join(DATA_DIR, f"{slug}_*.json")))
    if not fichiers:
        return None
    try:
        with open(fichiers[-1], encoding="utf-8") as f:
            d = json.load(f)
        return d.get("meta", {}).get("date_collecte")
    except Exception:
        return None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


_RISQUES = ("inondation", "secheresse", "chaleur")

# Cache mémoire du fichier de prédictions précalculées (voir
# inference/compute_daily_predictions.py) — évite de relire le JSON à chaque requête.
_pred_cache_data  = None
_pred_cache_mtime = None


def _lire_cache_predictions() -> dict:
    """
    Charge data/predictions/latest.json (précalculé par
    inference/compute_daily_predictions.py, lancé après la collecte quotidienne).
    Recharge automatiquement si le fichier a changé depuis le dernier appel.
    Retourne {} si absent (le calcul live prend le relais).
    """
    global _pred_cache_data, _pred_cache_mtime
    try:
        mtime = os.path.getmtime(PRED_CACHE_PATH)
    except OSError:
        return {}

    if _pred_cache_data is None or mtime != _pred_cache_mtime:
        try:
            with open(PRED_CACHE_PATH, encoding="utf-8") as f:
                _pred_cache_data = json.load(f)
            _pred_cache_mtime = mtime
        except Exception as e:
            print(f"[API] ⚠️  Cache prédictions illisible ({e})")
            return {}

    return _pred_cache_data or {}


# Horizons exposés par l'API — clé interne (jX) → nom du champ JSON exposé.
# J+10/J+14 restent dans la fenêtre de fiabilité des prévisions Open-Meteo (16j).
_HORIZONS = (3, 7, 10, 14)
_HORIZON_FIELD = {3: "risque_prevu_3j", 7: "risque_prevu_7j",
                  10: "risque_prevu_10j", 14: "risque_prevu_14j"}


def _build_risque_response(scores_par_horizon: dict, methode: str, extra: Optional[dict] = None) -> dict:
    """
    scores_par_horizon : {"j0": {...}, "j3": {...}, "j7": {...}, "j10": {...}, "j14": {...}}
    Construit la réponse standard {risque_actuel, risque_prevu_3j/7j/10j/14j, methode_risque}.
    """
    out = {"risque_actuel": {
        "scores": scores_par_horizon["j0"],
        "niveau_alerte": _niveau_alerte(**scores_par_horizon["j0"]),
    }}
    for h in _HORIZONS:
        scores = scores_par_horizon.get(f"j{h}")
        if scores is None:
            continue
        out[_HORIZON_FIELD[h]] = {"scores": scores, "niveau_alerte": _niveau_alerte(**scores)}
    out["methode_risque"] = methode
    if extra:
        out.update(extra)
    return out


def _scores_depuis_cache(zone_name: str) -> Optional[dict]:
    """Construit risque_actuel/prevu_3j/7j/10j/14j depuis le cache précalculé, si complet."""
    cache = _lire_cache_predictions()
    zone_pred = cache.get(zone_name)
    if not zone_pred or "risques" not in zone_pred:
        return None

    scores_par_horizon = {"j0": {}}
    for h in _HORIZONS:
        scores_par_horizon[f"j{h}"] = {}

    for risque in _RISQUES:
        r = zone_pred["risques"].get(risque)
        if not r or r.get("j0", {}).get("status") != "OK":
            return None
        scores_par_horizon["j0"][f"score_{risque}"] = r["j0"]["score"]
        for h in _HORIZONS:
            scores_par_horizon[f"j{h}"][f"score_{risque}"] = r.get(f"j{h}", r["j0"])["score"]

    return _build_risque_response(
        scores_par_horizon, "ml_zonal_infer (cache)",
        extra={"date_calcul_cache": zone_pred.get("date_calcul")},
    )


def _compute_risk_for_zone_zonal(zone_name: str, meteo: Optional[dict] = None) -> dict:
    """
    Calcule les scores J0/J+3/J+7/J+10/J+14 via inference/infer_zonal.py — le moteur
    qui calcule les VRAIES features d'entraînement (rolling 7/14/30/90j, SPI-3,
    anomalies) depuis l'historique zonal complet (data/historical/<Zone>_historical.csv),
    au lieu du snapshot quotidien à 8 jours utilisé par risk_model.py (insuffisant
    pour les modèles zonaux V5 qui attendent 23-31 features).

    Essaie d'abord le cache précalculé (data/predictions/latest.json, rapide),
    puis calcule en direct si absent/incomplet pour cette zone.

    Retourne {} si un seul des 3 risques échoue (NO_MODEL/NO_DATA/...), pour
    déclencher le fallback vers _compute_risk_for_zone_legacy côté appelant.
    """
    cached = _scores_depuis_cache(zone_name)
    if cached:
        return cached

    if _infer_zone_risk_fn is None or _infer_zone_risk_horizon_fn is None:
        return {}

    previsions_daily = (meteo or {}).get("previsions_daily")
    scores_par_horizon = {"j0": {}}
    for h in _HORIZONS:
        scores_par_horizon[f"j{h}"] = {}

    for risque in _RISQUES:
        r0 = _infer_zone_risk_fn(zone_name, risque, days=30)
        if r0.get("status") != "OK":
            return {}
        score_j0 = r0.get("proba_last", 0.0)
        scores_par_horizon["j0"][f"score_{risque}"] = score_j0

        for h in _HORIZONS:
            if previsions_daily:
                rh = _infer_zone_risk_horizon_fn(zone_name, risque, previsions_daily, h, days=30)
                scores_par_horizon[f"j{h}"][f"score_{risque}"] = \
                    rh.get("proba", score_j0) if rh.get("status") == "OK" else score_j0
            else:
                scores_par_horizon[f"j{h}"][f"score_{risque}"] = score_j0

    return _build_risque_response(scores_par_horizon, "ml_zonal_infer")


def _compute_risk_for_zone(zone_name: str, indicateurs: dict, meteo: Optional[dict] = None) -> dict:
    """
    Calcule les scores ML J0/J+3/J+7 pour une zone. Essaie d'abord le moteur
    zonal (infer_zonal.py, features complètes depuis l'historique), puis
    retombe sur risk_model.py (legacy, features limitées au snapshot du jour)
    si le premier échoue pour cette zone (données/modèle indisponibles).
    """
    try:
        zonal = _compute_risk_for_zone_zonal(zone_name, meteo)
        if zonal:
            return zonal
    except Exception as e:
        print(f"[API] infer_zonal indisponible pour {zone_name} ({e}) — fallback risk_model.py")

    return _compute_risk_for_zone_legacy(zone_name, indicateurs, meteo)


def _compute_risk_for_zone_legacy(zone_name: str, indicateurs: dict, meteo: Optional[dict] = None) -> dict:
    """
    Ancien chemin (risk_model.py) — conservé comme repli si infer_zonal.py
    n'a pas de modèle/données pour la zone.
    """
    if _predire_risques_fn is None or _construire_features_fn is None:
        return {}

    # Construire le dict brut au format JSON de zone, puis le convertir en
    # features PLATES (précipitation_24h, sm_surface, ndvi, ...) — predire_risques()
    # attend des features directement à la racine, pas le JSON imbriqué.
    data = {
        "meta":               {"zone": zone_name, "mois": datetime.now().month},
        "indicateurs_risque": indicateurs,
        "meteorologie":       meteo or {},
    }
    features          = _construire_features_fn(data)
    previsions_daily  = (meteo or {}).get("previsions_daily")

    try:
        pred_j0   = _predire_risques_fn(donnees=features, zone=zone_name)
        scores_par_horizon = {"j0": {
            "score_inondation": pred_j0.get("inondation",   {}).get("score", 0.0),
            "score_secheresse": pred_j0.get("secheresse",   {}).get("score", 0.0),
            "score_chaleur":    pred_j0.get("chaleur", {}).get("score", 0.0),
        }}

        if _evaluer_previsions_fn:
            prevs = _evaluer_previsions_fn(
                zone=zone_name, donnees_base=features, previsions_daily=previsions_daily)
            for h in _HORIZONS:
                bloc = prevs.get(f"j{h}", {})
                scores_par_horizon[f"j{h}"] = {
                    "score_inondation": bloc.get("inondation", {}).get("score", 0.0),
                    "score_secheresse": bloc.get("secheresse", {}).get("score", 0.0),
                    "score_chaleur":    bloc.get("chaleur",    {}).get("score", 0.0),
                }
        else:
            for h in _HORIZONS:
                scores_par_horizon[f"j{h}"] = scores_par_horizon["j0"]

        return _build_risque_response(scores_par_horizon, "ml_gradient_boosting")
    except Exception as e:
        print(f"[API] Erreur _compute_risk_for_zone ({zone_name}): {e}")
        return {}


# ─── ENDPOINTS ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Statut"])
def health_check():
    zones_status = []
    for z in ZONES_META:
        date = _last_collect_date(z["name"])
        zones_status.append({
            "name":              z["name"],
            "type":              z["type"],
            "derniere_collecte": date,
            "donnees_dispo":     date is not None,
        })
    return {
        "status":           "ok",
        "version":          "5.3.0",
        "modele_ml_charge": _risk_model is not None,
        "serveur_time":     datetime.now().isoformat(),
        "zones":            zones_status,
    }


@app.get("/api/zones", tags=["Zones"])
def list_zones():
    result = []
    for z in ZONES_META:
        date = _last_collect_date(z["name"])
        result.append({
            **z,
            "derniere_collecte": date,
            "donnees_dispo":     date is not None,
        })
    return {"zones": result, "total": len(result)}


@app.get("/api/overview", tags=["Zones"])
def get_overview():
    """
    Vue d'ensemble : niveau de risque ACTUEL des 8 zones en un seul appel.
    Lit le cache précalculé (data/predictions/latest.json) — quasi-instantané,
    avec repli sur le calcul direct si le cache est absent pour une zone.
    """
    result = []
    for z in ZONES_META:
        zone_name = z["name"]
        try:
            data        = _load_zone_data(zone_name)
            indicateurs = data.get("indicateurs_risque", data.get("indicateurs", {}))
            meteo       = data.get("meteorologie", {})
        except HTTPException:
            indicateurs, meteo = {}, {}

        risk   = _compute_risk_for_zone(zone_name, indicateurs, meteo)
        actuel = risk.get("risque_actuel", {})
        result.append({
            "zone":          zone_name,
            "type":          z["type"],
            "niveau_alerte": actuel.get("niveau_alerte", "INCONNU"),
            "scores":        actuel.get("scores", {}),
        })

    return {"zones": result}


@app.get("/api/nearest", tags=["Zones"])
def get_nearest_zone(
    lat: float = Query(..., description="Latitude GPS de l'utilisateur (ex: 4.05)"),
    lon: float = Query(..., description="Longitude GPS de l'utilisateur (ex: 9.70)"),
):
    """
    Retourne la zone SAMCAM la plus proche de la position GPS fournie.

    La réponse inclut les scores de risque ML pré-calculés (risque_actuel,
    risque_prevu_3j, risque_prevu_7j) directement dans les indicateurs,
    afin que le client Flutter n'ait pas besoin d'un second appel.

    Latence typique : < 50 ms (lecture fichier JSON + calcul ML)
    """
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=422, detail="Coordonnées GPS invalides.")

    best_zone   = min(ZONES_META, key=lambda z: _haversine(lat, lon, z["lat"], z["lon"]))
    distance_km = _haversine(lat, lon, best_zone["lat"], best_zone["lon"])
    zone_name   = best_zone["name"]
    hors_zone   = distance_km > MAX_ZONE_DISTANCE_KM

    try:
        data        = _load_zone_data(zone_name)
        meteo       = data.get("meteorologie", {})
        indicateurs = data.get("indicateurs_risque", data.get("indicateurs", {}))
        meta        = data.get("meta", {})
        donnees_dispo = True
    except HTTPException:
        meteo         = {}
        indicateurs   = {}
        meta          = {}
        donnees_dispo = False

    # Calcule les scores ML et les injecte directement dans indicateurs
    # pour que Flutter puisse les lire sans second appel
    risk_scores = _compute_risk_for_zone(zone_name, indicateurs, meteo)
    if risk_scores:
        indicateurs = {
            **indicateurs,
            **risk_scores,
            "date_collecte":  meta.get("date_collecte"),
            "methode_risque": risk_scores.get("methode_risque", "ml_gradient_boosting"),
        }

    return {
        "zone":                  zone_name,
        "distance_km":           round(distance_km, 1),
        "hors_zone":             hors_zone,
        "position_utilisateur":  {"lat": lat, "lon": lon},
        "coordonnees_zone":      {"lat": best_zone["lat"], "lon": best_zone["lon"]},
        "type":                  best_zone["type"],
        "cultures":              best_zone["cultures"],
        "donnees_dispo":         donnees_dispo,
        "meteo":                 meteo,
        "indicateurs":           indicateurs,
    }


@app.get("/api/nearest-live", tags=["Zones"])
async def get_nearest_live(
    lat: float = Query(..., description="Latitude GPS exacte de l'utilisateur (ex: 4.05)"),
    lon: float = Query(..., description="Longitude GPS exacte de l'utilisateur (ex: 9.77)"),
):
    """
    Récupère la météo EN TEMPS RÉEL à la position GPS exacte via Open-Meteo.
    Calcule aussi le risque ML basé sur la zone SAMCAM la plus proche.
    """
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=422, detail="Coordonnées GPS invalides.")

    params = {
        "latitude":      lat,
        "longitude":     lon,
        "current":       "temperature_2m,relative_humidity_2m,weathercode,windspeed_10m,precipitation",
        "hourly":        "temperature_2m,precipitation_probability,weathercode",
        "daily":         "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
        "timezone":      "Africa/Douala",
        "forecast_days": 7,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            meteo_live = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout : Open-Meteo n'a pas répondu à temps.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Erreur Open-Meteo : {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Impossible de joindre Open-Meteo : {e}")

    best_zone   = min(ZONES_META, key=lambda z: _haversine(lat, lon, z["lat"], z["lon"]))
    distance_km = _haversine(lat, lon, best_zone["lat"], best_zone["lon"])
    zone_name   = best_zone["name"]

    try:
        zone_data   = _load_zone_data(zone_name)
        indicateurs = zone_data.get("indicateurs_risque", zone_data.get("indicateurs", {}))
        meteo       = zone_data.get("meteorologie", {})
    except HTTPException:
        indicateurs = {}
        meteo       = {}

    risk_scores = _compute_risk_for_zone(zone_name, indicateurs, meteo)

    return {
        "zone":             zone_name,
        "distance_km":      round(distance_km, 1),
        "meteo_live":       meteo_live,
        "risque":           risk_scores,
        "coordonnees":      {"lat": lat, "lon": lon},
        "coordonnees_zone": {"lat": best_zone["lat"], "lon": best_zone["lon"]},
    }


def _get_full_risk_payload(zone: str) -> dict:
    """
    Calcule le bulletin de risque complet d'une zone (scores J0→J+14 +
    indicateurs). Factorisé hors de get_risk() pour être réutilisé par
    l'assistant IA (/api/assistant) et le bot WhatsApp — les deux doivent
    répondre à partir des MÊMES données que celles affichées dans l'app,
    jamais d'un recalcul divergent.
    """
    try:
        data        = _load_zone_data(zone)
        indicateurs = data.get("indicateurs_risque", data.get("indicateurs", {}))
        meteo       = data.get("meteorologie", {})
        meta        = data.get("meta", {})
    except HTTPException as e:
        raise e

    risque = _compute_risk_for_zone(zone, indicateurs, meteo)

    if not risque:
        # Fallback règles physiques depuis indicateurs JSON
        niveau = "VERT"
        for k, v in indicateurs.items():
            if isinstance(v, str) and v in ("modere", "eleve", "fort"):
                niveau = "ORANGE" if v == "modere" else "ROUGE"
                break
        risque = {
            "methode_risque": "regles_physiques",
            "risque_actuel":  {
                "scores": {
                    "score_inondation": 0.0,
                    "score_secheresse": 0.0,
                    "score_chaleur":    0.0,
                },
                "niveau_alerte": niveau,
            },
            "risque_prevu_3j":  {"scores": {}, "niveau_alerte": niveau},
            "risque_prevu_7j":  {"scores": {}, "niveau_alerte": niveau},
            "risque_prevu_10j": {"scores": {}, "niveau_alerte": niveau},
            "risque_prevu_14j": {"scores": {}, "niveau_alerte": niveau},
        }

    return {
        "zone":             zone,
        "date_collecte":    meta.get("date_collecte"),
        "methode_risque":   risque.get("methode_risque", "N/A"),
        "risque_actuel":    risque.get("risque_actuel",    {}),
        "risque_prevu_3j":  risque.get("risque_prevu_3j",  {}),
        "risque_prevu_7j":  risque.get("risque_prevu_7j",  {}),
        "risque_prevu_10j": risque.get("risque_prevu_10j", {}),
        "risque_prevu_14j": risque.get("risque_prevu_14j", {}),
        "indicateurs":      indicateurs,
    }


@app.get("/api/risk", tags=["Risque"])
def get_risk(zone: str = Query(DEFAULT_ZONE, description="Nom de la zone (ex: Kribi, Garoua)")):
    """
    Retourne le niveau d'alerte + scores ML J0/J+3/J+7 pour la zone demandée.
    """
    _resolve_zone(zone)
    return _get_full_risk_payload(zone)


# ─── ASSISTANT IA (Ollama) ──────────────────────────────────────────────────
#
# Les 24 modèles de risque (.pkl) restent l'unique source des scores — un LLM
# ne calcule JAMAIS un risque. Ollama sert uniquement à REFORMULER en langage
# naturel des données déjà calculées (RAG léger) : le prompt injecte le JSON
# réel du bulletin, ce qui empêche le modèle d'inventer des chiffres.
# Réutilisé tel quel par le bot WhatsApp (server/whatsapp_bot.py).

OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi3:mini")

_ASSISTANT_SYSTEM = (
    "Tu es l'assistant SAMCAM, un système d'alerte climatique pour le Cameroun. "
    "Tu réponds UNIQUEMENT à partir des données réelles fournies (jamais d'invention "
    "de chiffres). Ton public est un habitant, un agriculteur ou une autorité locale : "
    "réponds en français simple, concret, sans jargon technique. "
    "Sois bref : 3 à 5 phrases maximum, sauf si on te demande plus de détails."
)


class AssistantRequest(BaseModel):
    zone: str = Field(..., min_length=2, max_length=50)
    question: Optional[str] = Field(
        None, max_length=500,
        description="Question libre. Si absente, un résumé du bulletin est généré.")


def _construire_prompt_assistant(zone: str, bulletin: dict, question: Optional[str]) -> str:
    resume = json.dumps(bulletin, ensure_ascii=False, indent=None)
    if question:
        return (
            f"Données réelles du bulletin de risque pour {zone} :\n{resume}\n\n"
            f"Question de l'utilisateur : {question}\n\n"
            "Réponds à cette question en te basant uniquement sur ces données."
        )
    return (
        f"Données réelles du bulletin de risque pour {zone} :\n{resume}\n\n"
        "Résume la situation climatique de cette zone en langage simple : "
        "niveau de risque actuel, tendance sur les prochains jours, et un "
        "conseil pratique si le risque est modéré ou élevé."
    )


def _appeler_ollama(prompt: str) -> str:
    payload = {
        "model":   OLLAMA_MODEL,
        "system":  _ASSISTANT_SYSTEM,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0.2, "top_p": 0.9, "num_predict": 350},
    }
    try:
        # Le premier appel après inactivité charge le modèle en mémoire
        # (peut prendre 30-90 s sur un CPU de Raspberry Pi) ; les appels
        # suivants sont rapides tant qu'Ollama garde le modèle chargé.
        resp = httpx.post(OLLAMA_URL, json=payload, timeout=120.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Assistant indisponible : Ollama ne répond pas (lancez 'ollama serve').")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Erreur Ollama : {e}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="L'assistant met trop de temps à répondre.")

    return resp.json().get("response", "").strip()


@app.post("/api/assistant", tags=["Assistant"])
def poser_question_assistant(req: AssistantRequest):
    """
    Assistant IA (Ollama + Phi-3 mini) qui commente ou répond à une question
    sur le bulletin de risque RÉEL d'une zone. Ne calcule jamais de risque
    lui-même — il reformule les scores déjà produits par les modèles ML.
    """
    _resolve_zone(req.zone)
    bulletin = _get_full_risk_payload(req.zone)
    prompt   = _construire_prompt_assistant(req.zone, bulletin, req.question)
    reponse  = _appeler_ollama(prompt)
    return {"zone": req.zone, "question": req.question, "reponse": reponse}


@app.get("/api/meteo", tags=["Météo"])
def get_meteo(zone: str = Query(DEFAULT_ZONE, description="Nom de la zone")):
    """Retourne la météo actuelle + prévisions 7j pour la zone demandée."""
    _resolve_zone(zone)
    try:
        data  = _load_zone_data(zone)
        meteo = data.get("meteorologie", {})
        meta  = data.get("meta", {})
        return {
            "zone":          zone,
            "date_collecte": meta.get("date_collecte"),
            "meteo":         meteo,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Erreur /api/meteo ({zone}) : {e}")
        raise HTTPException(status_code=500, detail="Erreur interne lors de la lecture des données météo")


@app.get("/api/report", tags=["Rapport"])
def get_report(zone: str = Query(DEFAULT_ZONE, description="Nom de la zone")):
    """Retourne le rapport complet (météo + risques + indicateurs) pour la zone."""
    _resolve_zone(zone)
    try:
        data        = _load_zone_data(zone)
        indicateurs = data.get("indicateurs_risque", data.get("indicateurs", {}))
        meteo       = data.get("meteorologie", {})
        risk        = _compute_risk_for_zone(zone, indicateurs, meteo)
        if risk:
            niveau  = risk["risque_actuel"]["niveau_alerte"]
            data["indicateurs_risque"] = {
                **indicateurs,
                "methode_risque":   risk.get("methode_risque", "ml_gradient_boosting"),
                "risque_actuel":    risk["risque_actuel"],
                "risque_prevu_3j":  risk.get("risque_prevu_3j", {}),
                "risque_prevu_7j":  risk.get("risque_prevu_7j", {}),
                "risque_prevu_10j": risk.get("risque_prevu_10j", {}),
                "risque_prevu_14j": risk.get("risque_prevu_14j", {}),
                "niveau_alerte":    niveau,
            }
        else:
            print(f"[API] Erreur prédiction ML ({zone}) — fallback JSON")

        return data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Erreur /api/report ({zone}) : {e}")
        raise HTTPException(status_code=500, detail="Erreur interne lors de la génération du rapport")


@app.get("/api/history", tags=["Historique"])
def get_history(
    zone: str = Query(DEFAULT_ZONE, description="Nom de la zone"),
    days: int = Query(14, ge=1, le=90, description="Nombre de jours d'historique"),
):
    """
    Retourne l'évolution RÉELLE jour par jour des scores de risque pour la zone,
    calculée directement depuis les modèles zonaux (infer_zonal.py) sur les `days`
    derniers jours.

    Ancien comportement (abandonné) : relisait chaque snapshot JSON quotidien et
    recalculait le risque via _compute_risk_for_zone(), qui passe désormais par le
    cache de prédictions (data/predictions/latest.json) — celui-ci ne contient que
    la valeur du jour courant, donc chaque jour de l'historique affichait la même
    valeur figée. Ici on lit la série jour par jour que le modèle calcule déjà en
    interne (une probabilité par jour de la fenêtre d'inférence), donc chaque jour
    a sa propre valeur et l'historique évolue réellement.
    """
    _resolve_zone(zone)

    if _infer_zone_risk_series_fn is None:
        raise HTTPException(status_code=503, detail="Moteur d'inférence indisponible")

    series = {}
    for risque in _RISQUES:
        r = _infer_zone_risk_series_fn(zone, risque, days=days)
        series[risque] = {e["date"]: e["proba"] for e in r.get("serie", [])} \
            if r.get("status") == "OK" else {}

    toutes_dates = sorted(set().union(*[s.keys() for s in series.values()])) if any(series.values()) else []

    history = []
    for d in toutes_dates:
        scores = {f"score_{r}": series[r].get(d, 0.0) for r in _RISQUES}
        history.append({
            "date":           d,
            "risque_actuel":  scores,
            "niveau_alerte":  _niveau_alerte(**scores),
            "methode_risque": "ml_zonal_infer",
        })

    return {"zone": zone, "history": history, "total": len(history)}


# ─── SIGNALEMENTS COMMUNAUTAIRES ───────────────────────────────────────────────
#
# Les utilisateurs de l'app peuvent signaler un événement climatique observé
# sur le terrain (inondation constatée, sécheresse, vague de chaleur…).
# Ces observations sont stockées en JSONL et serviront de vérité terrain pour
# recalibrer les labels des modèles (aujourd'hui basés sur des seuils
# climatologiques, pas sur des événements confirmés).

SIGNALEMENTS_PATH = os.path.join(ROOT, "data", "community_reports", "signalements.jsonl")
_TYPES_EVENEMENT = {"inondation", "secheresse", "chaleur", "autre"}


class Signalement(BaseModel):
    zone: str = Field(..., min_length=2, max_length=50)
    type_evenement: str = Field(..., description="inondation|secheresse|chaleur|autre")
    description: str = Field("", max_length=1000)
    date_observation: Optional[str] = Field(None, description="YYYY-MM-DD (défaut : aujourd'hui)")
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)


@app.post("/api/signalement", tags=["Communauté"])
def post_signalement(s: Signalement):
    """Enregistre un signalement d'événement climatique observé sur le terrain."""
    if s.type_evenement not in _TYPES_EVENEMENT:
        raise HTTPException(
            status_code=422,
            detail=f"type_evenement invalide (attendu : {sorted(_TYPES_EVENEMENT)})",
        )
    # La zone doit être une zone SAMCAM connue (évite le stockage de déchets)
    _resolve_zone(s.zone)

    date_obs = s.date_observation or datetime.now().strftime("%Y-%m-%d")
    try:
        datetime.strptime(date_obs, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="date_observation invalide (format YYYY-MM-DD)")

    entree = {
        "zone":             s.zone,
        "type_evenement":   s.type_evenement,
        "description":      s.description.strip(),
        "date_observation": date_obs,
        "lat":              s.lat,
        "lon":              s.lon,
        "recu_le":          datetime.now().isoformat(timespec="seconds"),
    }
    try:
        os.makedirs(os.path.dirname(SIGNALEMENTS_PATH), exist_ok=True)
        with open(SIGNALEMENTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[api] Erreur écriture signalement : {e}")
        raise HTTPException(status_code=500, detail="Impossible d'enregistrer le signalement")

    return {"status": "OK", "signalement": entree}


@app.get("/api/signalements", tags=["Communauté"])
def get_signalements(
    zone: Optional[str] = Query(None, description="Filtrer par zone"),
    limit: int = Query(50, ge=1, le=500),
):
    """Liste les derniers signalements communautaires (les plus récents d'abord)."""
    if not os.path.isfile(SIGNALEMENTS_PATH):
        return {"signalements": [], "total": 0}
    try:
        with open(SIGNALEMENTS_PATH, encoding="utf-8") as f:
            entrees = [json.loads(l) for l in f if l.strip()]
    except (OSError, json.JSONDecodeError) as e:
        print(f"[api] Erreur lecture signalements : {e}")
        raise HTTPException(status_code=500, detail="Impossible de lire les signalements")

    if zone:
        entrees = [e for e in entrees if e.get("zone", "").lower() == zone.lower()]
    entrees = entrees[::-1][:limit]
    return {"signalements": entrees, "total": len(entrees)}


# ─── STATIC FILES ──────────────────────────────────────────────────────────────

_dashboard_path = os.path.join(ROOT, "dashboard")
if os.path.isdir(_dashboard_path):
    app.mount("/dashboard", StaticFiles(directory=_dashboard_path, html=True), name="dashboard")


# ─── BOT WHATSAPP ────────────────────────────────────────────────────────────
# Simple façade sur l'API ci-dessus (voir server/whatsapp_bot.py). Reste actif
# même sans les identifiants Meta configurés — répond juste 503 à l'envoi
# tant qu'ils sont absents ; n'affecte jamais le reste du serveur.
try:
    import sys as _sys
    if ROOT not in _sys.path:
        _sys.path.insert(0, ROOT)
    from server.whatsapp_bot import router as _whatsapp_router
    app.include_router(_whatsapp_router)
    print("[API] ✅ Bot WhatsApp monté (/webhook/whatsapp)")
except Exception as e:
    print(f"[API] ⚠️  Bot WhatsApp non monté : {e}")
