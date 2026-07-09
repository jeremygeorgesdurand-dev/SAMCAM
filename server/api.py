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

# ─── CONFIG ───────────────────────────────────────────────────────────────────────

ROOT          = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DASHBOARD_DIR = os.path.join(ROOT, "dashboard")
REPORTS_DIR   = os.path.join(ROOT, "reports")
DATA_DIR      = os.path.join(ROOT, "data")
MODELS_DIR    = os.path.join(ROOT, "models")
LATEST_JSON   = os.path.join(DASHBOARD_DIR, "latest_report.json")  # fallback V3

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── CHARGEMENT DU MODÈLE ML ───────────────────────────────────────────────────

# risk_model.py V5 expose des fonctions directement (pas de classe RiskModel)
_predire_risques_fn    = None
_evaluer_previsions_fn = None

def _charger_risk_model():
    global _predire_risques_fn, _evaluer_previsions_fn
    try:
        import sys
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from inference.risk_model import predire_risques, evaluer_previsions
        _predire_risques_fn    = predire_risques
        _evaluer_previsions_fn = evaluer_previsions
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


def _compute_risk_for_zone(zone_name: str, indicateurs: dict) -> dict:
    """
    Calcule les scores ML J0/J+3/J+7 pour une zone via predire_risques().
    Retourne un dict avec risque_actuel, risque_prevu_3j, risque_prevu_7j.
    """
    if _predire_risques_fn is None:
        return {}

    # Construire le dict au format attendu par predire_risques()
    data = {
        "meta":               {"zone": zone_name, "mois": datetime.now().month},
        "indicateurs_risque": indicateurs,
        "meteorologie":       {},
    }

    try:
        pred_j0   = _predire_risques_fn(donnees=data, zone=zone_name)
        scores_j0 = {
            "score_inondation": pred_j0.get("inondation",   {}).get("score", 0.0),
            "score_secheresse": pred_j0.get("secheresse",   {}).get("score", 0.0),
            "score_chaleur":    pred_j0.get("chaleur", {}).get("score", 0.0),
        }

        if _evaluer_previsions_fn:
            prevs     = _evaluer_previsions_fn(zone=zone_name)
            scores_j3 = {
                "score_inondation": prevs.get("j3", {}).get("inondation",   {}).get("score", 0.0),
                "score_secheresse": prevs.get("j3", {}).get("secheresse",   {}).get("score", 0.0),
                "score_chaleur":    prevs.get("j3", {}).get("chaleur", {}).get("score", 0.0),
            }
            scores_j7 = {
                "score_inondation": prevs.get("j7", {}).get("inondation",   {}).get("score", 0.0),
                "score_secheresse": prevs.get("j7", {}).get("secheresse",   {}).get("score", 0.0),
                "score_chaleur":    prevs.get("j7", {}).get("chaleur", {}).get("score", 0.0),
            }
        else:
            scores_j3 = scores_j0
            scores_j7 = scores_j0

        return {
            "risque_actuel":   {"scores": scores_j0, "niveau_alerte": _niveau_alerte(**scores_j0)},
            "risque_prevu_3j": {"scores": scores_j3, "niveau_alerte": _niveau_alerte(**scores_j3)},
            "risque_prevu_7j": {"scores": scores_j7, "niveau_alerte": _niveau_alerte(**scores_j7)},
            "methode_risque":  "ml_gradient_boosting",
        }
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
    risk_scores = _compute_risk_for_zone(zone_name, indicateurs)
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
    except HTTPException:
        indicateurs = {}

    risk_scores = _compute_risk_for_zone(zone_name, indicateurs)

    return {
        "zone":             zone_name,
        "distance_km":      round(distance_km, 1),
        "meteo_live":       meteo_live,
        "risque":           risk_scores,
        "coordonnees":      {"lat": lat, "lon": lon},
        "coordonnees_zone": {"lat": best_zone["lat"], "lon": best_zone["lon"]},
    }


@app.get("/api/risk", tags=["Risque"])
def get_risk(zone: str = Query(DEFAULT_ZONE, description="Nom de la zone (ex: Kribi, Garoua)")):
    """
    Retourne le niveau d'alerte + scores ML J0/J+3/J+7 pour la zone demandée.
    """
    _resolve_zone(zone)

    try:
        data        = _load_zone_data(zone)
        indicateurs = data.get("indicateurs_risque", data.get("indicateurs", {}))
        meta        = data.get("meta", {})
    except HTTPException as e:
        raise e

    risque = _compute_risk_for_zone(zone, indicateurs)

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
            "risque_prevu_3j": {"scores": {}, "niveau_alerte": niveau},
            "risque_prevu_7j": {"scores": {}, "niveau_alerte": niveau},
        }

    return {
        "zone":           zone,
        "date_collecte":  meta.get("date_collecte"),
        "methode_risque": risque.get("methode_risque", "N/A"),
        "risque_actuel":  risque.get("risque_actuel",  {}),
        "risque_prevu_3j":risque.get("risque_prevu_3j",{}),
        "risque_prevu_7j":risque.get("risque_prevu_7j",{}),
        "indicateurs":    indicateurs,
    }


@app.get("/api/meteo", tags=["Météo"])
def get_meteo(zone: str = Query(DEFAULT_ZONE, description="Nom de la zone")):
    """Retourne la météo actuelle + prévisions 7j pour la zone demandée."""
    _resolve_zone(zone)
    data  = _load_zone_data(zone)
    meteo = data.get("meteorologie", {})
    meta  = data.get("meta", {})
    return {
        "zone":          zone,
        "date_collecte": meta.get("date_collecte"),
        "meteo":         meteo,
    }


@app.get("/api/report", tags=["Rapport"])
def get_report(zone: str = Query(DEFAULT_ZONE, description="Nom de la zone")):
    """Retourne le rapport complet (météo + risques + indicateurs) pour la zone."""
    _resolve_zone(zone)
    data        = _load_zone_data(zone)
    indicateurs = data.get("indicateurs_risque", data.get("indicateurs", {}))
    risk        = _compute_risk_for_zone(zone, indicateurs)
    if risk:
        pred_j0 = risk["risque_actuel"]["scores"]
        niveau  = risk["risque_actuel"]["niveau_alerte"]
        data["indicateurs_risque"] = {
            **indicateurs,
            "methode_risque":  "ml_gradient_boosting",
            "risque_actuel":   risk["risque_actuel"],
            "risque_prevu_3j": risk["risque_prevu_3j"],
            "risque_prevu_7j": risk["risque_prevu_7j"],
            "niveau_alerte":   niveau,
        }
    else:
        print(f"[API] Erreur prédiction ML ({zone}) — fallback JSON")

    return data


@app.get("/api/history", tags=["Historique"])
def get_history(
    zone:  str = Query(DEFAULT_ZONE, description="Nom de la zone"),
    limit: int = Query(7, ge=1, le=30, description="Nombre de rapports à retourner"),
):
    """Retourne l'historique des N derniers rapports collectés pour la zone."""
    _resolve_zone(zone)
    slug     = _zone_slug(zone)
    pattern  = os.path.join(DATA_DIR, f"{slug}_*.json")
    fichiers = sorted(glob.glob(pattern))[-limit:]

    history = []
    for f in fichiers:
        try:
            with open(f, encoding="utf-8") as fp:
                d = json.load(fp)
            indicateurs = d.get("indicateurs_risque", d.get("indicateurs", {}))
            risk        = _compute_risk_for_zone(zone, indicateurs)
            history.append({
                "date":            d.get("meta", {}).get("date_collecte"),
                "methode_risque":  "ml_gradient_boosting" if risk else "N/A",
                "risque_actuel":   risk.get("risque_actuel",   {}).get("scores", {}),
                "niveau_alerte":   risk.get("risque_actuel",   {}).get("niveau_alerte", "N/A"),
                "risque_prevu_3j": risk.get("risque_prevu_3j", {}),
                "risque_prevu_7j": risk.get("risque_prevu_7j", {}),
            })
        except Exception:
            continue

    return {"zone": zone, "history": history, "total": len(history)}


# ─── STATIC FILES ──────────────────────────────────────────────────────────────

_dashboard_path = os.path.join(ROOT, "dashboard")
if os.path.isdir(_dashboard_path):
    app.mount("/dashboard", StaticFiles(directory=_dashboard_path, html=True), name="dashboard")
