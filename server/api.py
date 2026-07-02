#!/usr/bin/env python3
"""
SAMCAM V4 — Serveur FastAPI REST

Expose les données de risque climatique via une API JSON légère.
Permet à l'application mobile (V5) et au dashboard HTML de consommer
les rapports sans lire directement les fichiers locaux.

V4 : L'endpoint /api/risk utilise en priorité le modèle scikit-learn
     (risk_model.py) pour calculer les scores de risque J0/J+3/J+7.
     Si les modèles .pkl sont absents, fallback sur le latest_report.json
     généré par Phi-3 mini (comportement V3).

Endpoints :
    GET /api/risk      — Dernier niveau d'alerte + scores ML J0/J+3/J+7
    GET /api/meteo     — Météo actuelle + prévisions 7j
    GET /api/report    — Rapport complet (texte Phi-3 + données brutes)
    GET /api/history   — Historique des 30 derniers rapports
    GET /health        — Statut du serveur
    GET /docs          — Documentation Swagger auto-générée (FastAPI)

Usage :
    uvicorn server.api:app --host 0.0.0.0 --port 8000
    # ou via le script : bash server/start.sh
"""

import json
import glob
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# ─── CONFIG ───────────────────────────────────────────────────────────────────

ROOT          = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DASHBOARD_DIR = os.path.join(ROOT, "dashboard")
REPORTS_DIR   = os.path.join(ROOT, "reports")
LATEST_JSON   = os.path.join(DASHBOARD_DIR, "latest_report.json")
MODELS_DIR    = os.path.join(ROOT, "models")

# ─── APP ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SAMCAM API",
    description="Système d'Alerte Météorologique du Cameroun — API REST V4",
    version="4.1.0",
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

# ─── CHARGEMENT DU MODÈLE ML (V4) ─────────────────────────────────────────────

def _charger_risk_model():
    """
    Tente d'importer et d'instancier RiskModel depuis inference/risk_model.py.
    Retourne l'instance ou None si non disponible (fallback V3).
    """
    try:
        import sys
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from inference.risk_model import RiskModel
        modele = RiskModel(models_dir=MODELS_DIR)
        modele.charger_modeles()
        return modele
    except Exception as e:
        print(f"[API] ⚠️  Modèle ML non disponible ({e}) — fallback sur latest_report.json")
        return None


# Chargement au démarrage du serveur
_risk_model = _charger_risk_model()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _load_latest() -> dict:
    if not os.path.exists(LATEST_JSON):
        raise HTTPException(
            status_code=503,
            detail="Aucun rapport disponible. Lancez d'abord : python3 inference/pipeline_complet.py"
        )
    with open(LATEST_JSON, encoding="utf-8") as f:
        return json.load(f)


def _niveau_alerte(score_inondation: float, score_secheresse: float, score_chaleur: float) -> str:
    """
    Calcule le niveau d'alerte global à partir des scores de probabilité.
    ROUGE  : au moins un risque >= 0.70
    ORANGE : au moins un risque >= 0.45
    JAUNE  : au moins un risque >= 0.25
    VERT   : tous les risques < 0.25
    """
    max_score = max(score_inondation, score_secheresse, score_chaleur)
    if max_score >= 0.70:
        return "ROUGE"
    elif max_score >= 0.45:
        return "ORANGE"
    elif max_score >= 0.25:
        return "JAUNE"
    return "VERT"


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Statut"])
def health_check():
    rapport_dispo = os.path.exists(LATEST_JSON)
    derniere_maj = None
    if rapport_dispo:
        ts = os.path.getmtime(LATEST_JSON)
        derniere_maj = datetime.fromtimestamp(ts).isoformat()
    return {
        "status":             "ok",
        "version":            "4.1.0",
        "rapport_disponible": rapport_dispo,
        "modele_ml_charge":   _risk_model is not None,
        "derniere_maj":       derniere_maj,
        "serveur_time":       datetime.now().isoformat(),
    }


@app.get("/api/risk", tags=["Risque climatique"])
def get_latest_risk():
    """
    Retourne le dernier niveau d'alerte et les scores de risque.

    - Si le modèle ML est chargé (V4) : scores calculés par GradientBoosting
      pour J0, J+3 et J+7 à partir des dernières données collectées.
    - Sinon (fallback V3) : données issues de latest_report.json (Phi-3 mini).

    Le champ 'methode_risque' indique la source utilisée :
      'ml_gradient_boosting' | 'regles_physiques' | 'phi3_llm'
    """
    # ── Chemin V4 : modèle ML disponible ────────────────────────────────────
    if _risk_model is not None:
        try:
            # Récupère les dernières données collectées depuis latest_report.json
            data = _load_latest()
            indicateurs = data.get("indicateurs", {})

            # Construction du vecteur de features depuis les indicateurs disponibles
            features = {
                "mois":           datetime.now().month,
                "pluie_7j":       indicateurs.get("pluie_cumulee_7j_mm", 0),
                "pluie_30j":      indicateurs.get("pluie_cumulee_30j_mm",
                                    indicateurs.get("pluie_cumulee_7j_mm", 0) * 4),
                "pluie_prev_7j":  indicateurs.get("pluie_prevue_7j_mm", 0),
                "temp_max":       indicateurs.get("temp_max", 29.0),
                "temp_max_3j":    indicateurs.get("temp_max_3j", 29.0),
                "sm_surface":     indicateurs.get("sm_surface", 0.35),
                "sm_rootzone":    indicateurs.get("sm_rootzone", 0.30),
                "ndvi":           indicateurs.get("ndvi_moyen", 0.60),
                "ndwi":           indicateurs.get("ndwi_moyen", 0.15),
            }

            # Prédictions multi-horizon
            pred_j0 = _risk_model.predire(features, horizon=None)
            pred_j3 = _risk_model.predire(features, horizon=3)
            pred_j7 = _risk_model.predire(features, horizon=7)

            niveau = _niveau_alerte(
                pred_j0.get("inondation", 0),
                pred_j0.get("secheresse", 0),
                pred_j0.get("chaleur", 0),
            )

            return {
                "date":           data.get("date"),
                "zone":           data.get("zone", "Kribi"),
                "niveau_alerte":  niveau,
                "methode_risque": "ml_gradient_boosting",
                "risque_actuel": {
                    "scores":          pred_j0,
                    "niveau_alerte":   niveau,
                },
                "risque_prevu_3j": {
                    "scores":        pred_j3,
                    "niveau_alerte": _niveau_alerte(
                        pred_j3.get("inondation", 0),
                        pred_j3.get("secheresse", 0),
                        pred_j3.get("chaleur", 0),
                    ),
                },
                "risque_prevu_7j": {
                    "scores":        pred_j7,
                    "niveau_alerte": _niveau_alerte(
                        pred_j7.get("inondation", 0),
                        pred_j7.get("secheresse", 0),
                        pred_j7.get("chaleur", 0),
                    ),
                },
                "indicateurs": indicateurs,
                "capteur":     data.get("capteur", "Open-Meteo"),
            }

        except Exception as e:
            print(f"[API] Erreur prédiction ML : {e} — fallback latest_report.json")

    # ── Fallback V3 : latest_report.json (Phi-3 mini) ───────────────────────
    data = _load_latest()
    return {
        "date":            data.get("date"),
        "zone":            data.get("zone", "Kribi"),
        "niveau_alerte":   data.get("niveau_alerte", "INCONNU"),
        "methode_risque":  data.get("methode_risque", "phi3_llm"),
        "risque_actuel":   data.get("risque_actuel",   {}),
        "risque_prevu_3j": data.get("risque_prevu_3j", {}),
        "risque_prevu_7j": data.get("risque_prevu_7j", {}),
        "indicateurs":     data.get("indicateurs", {}),
        "capteur":         data.get("capteur", "?"),
    }


@app.get("/api/meteo", tags=["Météorologie"])
def get_meteo():
    data = _load_latest()
    meteo = data.get("meteorologie", {})
    if not meteo:
        raise HTTPException(status_code=404, detail="Données météo non disponibles.")
    return meteo


@app.get("/api/report", tags=["Rapport complet"])
def get_full_report():
    return _load_latest()


@app.get("/api/history", tags=["Historique"])
def get_history(limit: int = 30):
    limit = min(limit, 90)
    pattern = os.path.join(REPORTS_DIR, "rapport_kribi_*.json")
    fichiers = sorted(glob.glob(pattern))[-limit:]

    if not fichiers:
        return {"count": 0, "history": []}

    history = []
    for path in reversed(fichiers):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            history.append({
                "date":            d.get("date"),
                "niveau_alerte":   d.get("niveau_alerte", "INCONNU"),
                "methode_risque":  d.get("methode_risque", "?"),
                "risque_actuel":   d.get("risque_actuel",   {}).get("scores", {}),
                "risque_prevu_3j": d.get("risque_prevu_3j", {}).get("scores", {}),
                "risque_prevu_7j": d.get("risque_prevu_7j", {}).get("scores", {}),
                "indicateurs": {
                    "pluie_cumulee_7j_mm": d.get("indicateurs", {}).get("pluie_cumulee_7j_mm"),
                    "pluie_prevue_7j_mm":  d.get("indicateurs", {}).get("pluie_prevue_7j_mm"),
                    "ndvi_moyen":          d.get("indicateurs", {}).get("ndvi_moyen"),
                },
            })
        except Exception:
            continue

    return {"count": len(history), "history": history}


# ─── STATIC FILES ─────────────────────────────────────────────────────────────

if os.path.isdir(DASHBOARD_DIR):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")


# ─── POINT D'ENTRÉE DIRECT ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.api:app", host="0.0.0.0", port=8000, reload=True)
