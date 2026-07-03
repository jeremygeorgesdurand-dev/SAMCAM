#!/usr/bin/env python3
"""
SAMCAM V5.1 — Serveur FastAPI REST multi-zones agricoles

Expose les données de risque climatique via une API JSON légère.
Toutes les routes acceptent désormais un paramètre optionnel `?zone=`
pour interroger n'importe quelle zone agricole collectée.

Zones disponibles (définies dans data_collection/collect_zone.py) :
    Kribi, Ebolowa, Kumba, Bafoussam, Yaounde_peri,
    Ngaoundere, Garoua, Maroua

Endpoints :
    GET /api/risk          — Niveau d'alerte + scores ML J0/J+3/J+7
    GET /api/meteo         — Météo actuelle + prévisions 7j
    GET /api/report        — Rapport complet
    GET /api/history       — Historique des N derniers rapports
    GET /api/zones         — Liste des zones disponibles + statut
    GET /api/nearest       — Zone la plus proche d'une position GPS (lat/lon)
    GET /health            — Statut du serveur
    GET /docs              — Documentation Swagger auto-générée

Usage :
    uvicorn server.api:app --host 0.0.0.0 --port 8000
    bash server/start.sh

Exemples :
    GET /api/risk                         → Kribi (zone par défaut)
    GET /api/risk?zone=Garoua             → Garoua
    GET /api/meteo?zone=Maroua            → Météo de Maroua
    GET /api/history?zone=Bafoussam       → Historique Bafoussam
    GET /api/nearest?lat=4.05&lon=9.70    → Zone la plus proche du point GPS
"""

import json
import glob
import math
import os
from datetime import datetime
from typing import Optional

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


# ─── APP ─────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SAMCAM API",
    description="Système d'Alerte Météorologique du Cameroun — API REST V5.1 multi-zones",
    version="5.1.0",
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

def _charger_risk_model():
    try:
        import sys
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from inference.risk_model import RiskModel
        modele = RiskModel(models_dir=MODELS_DIR)
        modele.charger_modeles()
        print("[API] ✅ Modèle ML chargé")
        return modele
    except Exception as e:
        print(f"[API] ⚠️  Modèle ML non disponible ({e}) — fallback sur JSON")
        return None

_risk_model = _charger_risk_model()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _zone_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def _resolve_zone(zone: str) -> dict:
    """
    Valide le nom de zone et retourne ses méta-données.
    Lève HTTPException 404 si zone inconnue.
    """
    meta = ZONES_NAMES.get(zone.lower())
    if meta is None:
        noms = ", ".join(z["name"] for z in ZONES_META)
        raise HTTPException(
            status_code=404,
            detail=f"Zone '{zone}' inconnue. Zones disponibles : {noms}"
        )
    return meta


def _load_zone_data(zone: str) -> dict:
    """
    Charge le dernier fichier de collecte pour une zone.
    Cherche data/<slug>_YYYY-MM-DD.json (le plus récent).
    Fallback sur latest_report.json si zone == Kribi et aucun fichier trouvé.
    """
    slug = _zone_slug(zone)
    pattern = os.path.join(DATA_DIR, f"{slug}_*.json")
    fichiers = sorted(glob.glob(pattern))

    if fichiers:
        with open(fichiers[-1], encoding="utf-8") as f:
            return json.load(f)

    # Fallback Kribi sur latest_report.json (compatibilité V3/V4)
    if zone.lower() == "kribi" and os.path.exists(LATEST_JSON):
        with open(LATEST_JSON, encoding="utf-8") as f:
            return json.load(f)

    raise HTTPException(
        status_code=503,
        detail=(
            f"Aucune donnée disponible pour la zone '{zone}'. "
            f"Lancez : python3 data_collection/collect_zone.py --zone {zone}"
        )
    )


def _niveau_alerte(score_inondation: float, score_secheresse: float, score_chaleur: float) -> str:
    max_score = max(score_inondation, score_secheresse, score_chaleur)
    if   max_score >= 0.70: return "ROUGE"
    elif max_score >= 0.45: return "ORANGE"
    elif max_score >= 0.25: return "JAUNE"
    return "VERT"


def _last_collect_date(zone: str) -> Optional[str]:
    """Retourne la date ISO du dernier fichier collecté pour une zone."""
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
    """Calcule la distance en km entre deux points GPS (formule de Haversine)."""
    R = 6371.0  # Rayon moyen de la Terre en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── ENDPOINTS ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Statut"])
def health_check():
    zones_status = []
    for z in ZONES_META:
        date = _last_collect_date(z["name"])
        zones_status.append({
            "name":          z["name"],
            "type":          z["type"],
            "derniere_collecte": date,
            "donnees_dispo": date is not None,
        })
    return {
        "status":           "ok",
        "version":          "5.1.0",
        "modele_ml_charge": _risk_model is not None,
        "serveur_time":     datetime.now().isoformat(),
        "zones":            zones_status,
    }


@app.get("/api/zones", tags=["Zones"])
def list_zones():
    """
    Liste toutes les zones agricoles supportées avec leur statut de données.
    """
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
    Retourne la zone SAMCAM la plus proche de la position GPS fournie,
    avec la distance en km et les données météo/risque en temps réel.

    - Si `hors_zone` est `true`, l'utilisateur est à plus de 200 km de toute zone.
    - Utilise la formule de Haversine pour le calcul de distance.

    Exemple : GET /api/nearest?lat=4.05&lon=9.70
    """
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(
            status_code=422,
            detail="Coordonnées GPS invalides. lat ∈ [-90, 90], lon ∈ [-180, 180]."
        )

    # Trouver la zone la plus proche
    best_zone = min(
        ZONES_META,
        key=lambda z: _haversine(lat, lon, z["lat"], z["lon"])
    )
    distance_km = _haversine(lat, lon, best_zone["lat"], best_zone["lon"])
    zone_name   = best_zone["name"]
    hors_zone   = distance_km > MAX_ZONE_DISTANCE_KM

    # Charger les données météo/risque de cette zone
    try:
        data        = _load_zone_data(zone_name)
        meteo       = data.get("meteorologie", {})
        indicateurs = data.get("indicateurs_risque", data.get("indicateurs", {}))
        donnees_dispo = True
    except HTTPException:
        meteo         = {}
        indicateurs   = {}
        donnees_dispo = False

    return {
        "zone":               zone_name,
        "distance_km":        round(distance_km, 1),
        "hors_zone":          hors_zone,
        "position_utilisateur": {"lat": lat, "lon": lon},
        "coordonnees_zone":   {"lat": best_zone["lat"], "lon": best_zone["lon"]},
        "type":               best_zone["type"],
        "cultures":           best_zone["cultures"],
        "donnees_dispo":      donnees_dispo,
        "meteo":              meteo,
        "indicateurs":        indicateurs,
    }


@app.get("/api/risk", tags=["Risque climatique"])
def get_risk(
    zone: str = Query(default=DEFAULT_ZONE, description="Nom de la zone (ex: Kribi, Garoua, Maroua)")
):
    """
    Retourne le niveau d'alerte et les scores de risque ML J0/J+3/J+7.

    Paramètres :
    - **zone** : Nom de la zone à interroger (défaut : Kribi)

    Méthode :
    - Si le modèle ML est chargé : scores GradientBoosting
    - Sinon : fallback sur les indicateurs du rapport JSON
    """
    _resolve_zone(zone)
    data = _load_zone_data(zone)
    indicateurs = data.get("indicateurs_risque", data.get("indicateurs", {}))
    meta = data.get("meta", {})

    # ── Chemin V4 : modèle ML disponible
    if _risk_model is not None:
        try:
            features = {
                "mois":          datetime.now().month,
                "pluie_7j":      indicateurs.get("pluie_cumulee_7j_mm", 0),
                "pluie_30j":     indicateurs.get("pluie_cumulee_30j_mm",
                                    indicateurs.get("pluie_cumulee_7j_mm", 0) * 4),
                "pluie_prev_7j": indicateurs.get("pluie_prevue_7j_mm", 0),
                "temp_max":      indicateurs.get("temp_max", 29.0),
                "temp_max_3j":   indicateurs.get("temp_max_3j", 29.0),
                "sm_surface":    indicateurs.get("humidite_sol_sm_surface",
                                    indicateurs.get("sm_surface", 0.35)),
                "sm_rootzone":   indicateurs.get("sm_rootzone", 0.30),
                "ndvi":          indicateurs.get("ndvi_moyen", 0.60),
                "ndwi":          indicateurs.get("ndwi_moyen", 0.15),
            }

            pred_j0 = _risk_model.predire(features, horizon=None)
            pred_j3 = _risk_model.predire(features, horizon=3)
            pred_j7 = _risk_model.predire(features, horizon=7)

            niveau = _niveau_alerte(
                pred_j0.get("inondation", 0),
                pred_j0.get("secheresse", 0),
                pred_j0.get("chaleur",    0),
            )

            return {
                "date":            meta.get("date_collecte"),
                "zone":            zone,
                "zone_type":       meta.get("zone_type"),
                "cultures":        meta.get("cultures", []),
                "niveau_alerte":   niveau,
                "methode_risque":  "ml_gradient_boosting",
                "risque_actuel":   {"scores": pred_j0, "niveau_alerte": niveau},
                "risque_prevu_3j": {
                    "scores": pred_j3,
                    "niveau_alerte": _niveau_alerte(
                        pred_j3.get("inondation", 0),
                        pred_j3.get("secheresse", 0),
                        pred_j3.get("chaleur",    0),
                    ),
                },
                "risque_prevu_7j": {
                    "scores": pred_j7,
                    "niveau_alerte": _niveau_alerte(
                        pred_j7.get("inondation", 0),
                        pred_j7.get("secheresse", 0),
                        pred_j7.get("chaleur",    0),
                    ),
                },
                "indicateurs":           indicateurs,
                "alerte_semis":          indicateurs.get("alerte_semis"),
                "periode_semis_active":  indicateurs.get("periode_semis_active", False),
                "capteur":               meta.get("capteur_satellite", "Open-Meteo"),
            }
        except Exception as e:
            print(f"[API] Erreur prédiction ML ({zone}) : {e} — fallback JSON")

    # ── Fallback : indicateurs bruts du JSON
    risque_ino  = indicateurs.get("risque_inondation_observe", "inconnu")
    risque_sec  = indicateurs.get("risque_secheresse",         "inconnu")
    score_ino   = 0.70 if risque_ino == "élevé" else (0.40 if risque_ino == "modéré" else 0.10)
    score_sec   = 0.70 if risque_sec == "élevé" else (0.40 if risque_sec == "modéré" else 0.10)
    niveau      = _niveau_alerte(score_ino, score_sec, 0.0)

    return {
        "date":           meta.get("date_collecte"),
        "zone":           zone,
        "zone_type":      meta.get("zone_type"),
        "cultures":       meta.get("cultures", []),
        "niveau_alerte":  niveau,
        "methode_risque": "regles_physiques",
        "risque_actuel":  {
            "scores":       {"inondation": score_ino, "secheresse": score_sec, "chaleur": 0.0},
            "niveau_alerte": niveau,
        },
        "indicateurs":          indicateurs,
        "alerte_semis":         indicateurs.get("alerte_semis"),
        "periode_semis_active": indicateurs.get("periode_semis_active", False),
        "capteur":              meta.get("capteur_satellite", "Open-Meteo"),
    }


@app.get("/api/meteo", tags=["Météorologie"])
def get_meteo(
    zone: str = Query(default=DEFAULT_ZONE, description="Nom de la zone (ex: Kribi, Garoua)")
):
    """Retourne la météo actuelle + prévisions 7j pour la zone demandée."""
    _resolve_zone(zone)
    data = _load_zone_data(zone)
    meteo = data.get("meteorologie", {})
    if not meteo:
        raise HTTPException(status_code=404, detail=f"Données météo non disponibles pour '{zone}'.")
    return {
        "zone":  zone,
        "date":  data.get("meta", {}).get("date_collecte"),
        "meteo": meteo,
    }


@app.get("/api/report", tags=["Rapport complet"])
def get_full_report(
    zone: str = Query(default=DEFAULT_ZONE, description="Nom de la zone")
):
    """Retourne le rapport complet (météo + satellitaire + indicateurs) pour la zone."""
    _resolve_zone(zone)
    return _load_zone_data(zone)


@app.get("/api/history", tags=["Historique"])
def get_history(
    zone:  str = Query(default=DEFAULT_ZONE, description="Nom de la zone"),
    limit: int = Query(default=30, ge=1, le=90, description="Nombre de rapports (max 90)")
):
    """
    Retourne l'historique des N derniers rapports pour une zone.
    Cherche dans reports/ (rapports d'analyse) et data/ (collectes brutes).
    """
    _resolve_zone(zone)
    slug = _zone_slug(zone)

    # Cherche d'abord les rapports d'analyse (reports/rapport_<slug>_*.json)
    pattern_reports = os.path.join(REPORTS_DIR, f"rapport_{slug}_*.json")
    # Sinon les fichiers de collecte bruts (data/<slug>_*.json)
    pattern_data    = os.path.join(DATA_DIR,    f"{slug}_*.json")

    fichiers = sorted(glob.glob(pattern_reports))
    if not fichiers:
        fichiers = sorted(glob.glob(pattern_data))

    fichiers = fichiers[-limit:]
    if not fichiers:
        return {"zone": zone, "count": 0, "history": []}

    history = []
    for path in reversed(fichiers):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            meta        = d.get("meta", {})
            indicateurs = d.get("indicateurs_risque", d.get("indicateurs", {}))
            history.append({
                "date":           meta.get("date_collecte") or d.get("date"),
                "zone":           zone,
                "niveau_alerte":  d.get("niveau_alerte", "N/A"),
                "methode_risque": d.get("methode_risque", "N/A"),
                "indicateurs": {
                    "pluie_cumulee_7j_mm":  indicateurs.get("pluie_cumulee_7j_mm"),
                    "pluie_prevue_7j_mm":   indicateurs.get("pluie_prevue_7j_mm"),
                    "bilan_hydrique_7j_mm": indicateurs.get("bilan_hydrique_7j_mm"),
                    "ndvi_moyen":           indicateurs.get("ndvi_moyen"),
                    "ndre_moyen":           indicateurs.get("ndre_moyen"),
                    "stress_vegetal":       indicateurs.get("stress_vegetal"),
                    "alerte_semis":         indicateurs.get("alerte_semis"),
                },
                "risque_actuel":   d.get("risque_actuel",   {}).get("scores", {}),
                "risque_prevu_3j": d.get("risque_prevu_3j", {}).get("scores", {}),
                "risque_prevu_7j": d.get("risque_prevu_7j", {}).get("scores", {}),
            })
        except Exception:
            continue

    return {"zone": zone, "count": len(history), "history": history}


# ─── STATIC FILES ──────────────────────────────────────────────────────────────

if os.path.isdir(DASHBOARD_DIR):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")


# ─── POINT D'ENTRÉE DIRECT ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.api:app", host="0.0.0.0", port=8000, reload=True)
