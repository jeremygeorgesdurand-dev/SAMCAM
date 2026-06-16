#!/usr/bin/env python3
"""
SAMCAM V3 — Serveur FastAPI REST

Expose les données de risque climatique via une API JSON légère.
Permet à l'application mobile (V5) et au dashboard HTML de consommer
les rapports sans lire directement les fichiers locaux.

Endpoints :
    GET /api/risk      — Dernier niveau d'alerte + indicateurs
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

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DASHBOARD_DIR = os.path.join(ROOT, "dashboard")
REPORTS_DIR   = os.path.join(ROOT, "reports")
LATEST_JSON   = os.path.join(DASHBOARD_DIR, "latest_report.json")

# ─── APP ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SAMCAM API",
    description="Système d'Alerte Météorologique du Cameroun — API REST V3",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS : autorise l'app mobile et le dashboard à appeler l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _load_latest() -> dict:
    """Charge le dernier rapport JSON. Lève 503 si absent."""
    if not os.path.exists(LATEST_JSON):
        raise HTTPException(
            status_code=503,
            detail="Aucun rapport disponible. Lancez d'abord : python3 inference/pipeline_complet.py"
        )
    with open(LATEST_JSON, encoding="utf-8") as f:
        return json.load(f)


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Statut"])
def health_check():
    """
    Vérifie que le serveur est en ligne et qu'un rapport est disponible.
    Retourne aussi la date du dernier rapport.
    """
    rapport_dispo = os.path.exists(LATEST_JSON)
    derniere_maj = None
    if rapport_dispo:
        ts = os.path.getmtime(LATEST_JSON)
        derniere_maj = datetime.fromtimestamp(ts).isoformat()

    return {
        "status": "ok",
        "version": "3.0.0",
        "rapport_disponible": rapport_dispo,
        "derniere_maj": derniere_maj,
        "serveur_time": datetime.now().isoformat(),
    }


@app.get("/api/risk", tags=["Risque climatique"])
def get_latest_risk():
    """
    Retourne le dernier niveau d'alerte et les indicateurs de risque.

    Niveau d'alerte possible : VERT | JAUNE | ORANGE | ROUGE

    Utilisé par l'application mobile pour afficher la bannière d'alerte principale.
    Réponse légère — ne contient pas le texte complet du rapport.
    """
    data = _load_latest()
    return {
        "date": data.get("date"),
        "zone": data.get("zone", "Kribi"),
        "niveau_alerte": data.get("niveau_alerte", "INCONNU"),
        "indicateurs": data.get("indicateurs", {}),
        "capteur": data.get("capteur", "?"),
    }


@app.get("/api/meteo", tags=["Météorologie"])
def get_meteo():
    """
    Retourne les données météo actuelles et les prévisions des 7 prochains jours.

    Source : Open-Meteo (mise à jour toutes les 6h via cron).
    Contient : températures, précipitations, vent, humidité, prévisions journalières.
    """
    data = _load_latest()
    meteo = data.get("meteorologie", {})
    if not meteo:
        raise HTTPException(status_code=404, detail="Données météo non disponibles dans le rapport.")
    return meteo


@app.get("/api/report", tags=["Rapport complet"])
def get_full_report():
    """
    Retourne le rapport complet : texte Phi-3, niveau d'alerte, indicateurs,
    données météo et satellitaires brutes.

    Réponse volumineuse — à utiliser pour afficher le rapport détaillé
    ou pour le debug. Préférer /api/risk pour l'affichage mobile.
    """
    return _load_latest()


@app.get("/api/history", tags=["Historique"])
def get_history(limit: int = 30):
    """
    Retourne l'historique des derniers rapports (défaut : 30 jours).

    Chaque entrée contient : date, niveau_alerte, indicateurs résumés.
    Utile pour afficher la courbe d'évolution du risque dans l'app mobile.

    Paramètre :
        limit (int) : nombre de rapports à retourner (max 90)
    """
    limit = min(limit, 90)  # sécurité : max 90 entrées
    pattern = os.path.join(REPORTS_DIR, "rapport_kribi_*.json")
    fichiers = sorted(glob.glob(pattern))[-limit:]

    if not fichiers:
        return {"count": 0, "history": []}

    history = []
    for path in reversed(fichiers):  # du plus récent au plus ancien
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            history.append({
                "date": d.get("date"),
                "niveau_alerte": d.get("niveau_alerte", "INCONNU"),
                "indicateurs": {
                    "pluie_cumulee_7j_mm": d.get("indicateurs", {}).get("pluie_cumulee_7j_mm"),
                    "pluie_prevue_7j_mm":  d.get("indicateurs", {}).get("pluie_prevue_7j_mm"),
                    "ndvi_moyen":           d.get("indicateurs", {}).get("ndvi_moyen"),
                    "risque_inondation_observe": d.get("indicateurs", {}).get("risque_inondation_observe"),
                    "risque_secheresse":    d.get("indicateurs", {}).get("risque_secheresse"),
                },
            })
        except Exception:
            continue

    return {"count": len(history), "history": history}


# ─── STATIC FILES — sert le dashboard HTML ────────────────────────────────────
# Accessible sur http://localhost:8000/dashboard/samcam-v4-dashboard.html

if os.path.isdir(DASHBOARD_DIR):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")


# ─── POINT D'ENTRÉE DIRECT ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.api:app", host="0.0.0.0", port=8000, reload=True)
