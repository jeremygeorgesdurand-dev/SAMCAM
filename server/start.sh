#!/usr/bin/env bash
# ============================================================
# SAMCAM — Démarrage du serveur + scheduler de collecte
# ============================================================
# Usage :
#   bash server/start.sh           # production
#   bash server/start.sh --dev     # hot-reload
#   bash server/start.sh --collect # collecte immédiate puis serveur
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Couleurs
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

echo -e "${BLUE}\n══════════════════════════════════════════════"
echo -e "  SAMCAM — Serveur + Scheduler"
echo -e "══════════════════════════════════════════════${NC}\n"

# ── Environnement virtuel ─────────────────────────────────────────────────────
if [ -f "venv/bin/activate" ]; then
    echo -e "${GREEN}[venv]${NC} Activation de l'environnement virtuel..."
    source venv/bin/activate
else
    echo -e "${YELLOW}[venv]${NC} Pas de venv trouvé — utilisation du Python système"
fi

PYTHON="$(which python3)"
echo -e "${GREEN}[python]${NC} $PYTHON"

# ── Dépendances ───────────────────────────────────────────────────────────────
echo -e "${GREEN}[deps]${NC} Vérification des dépendances..."
pip install -q -r server/requirements.txt

# ── Création des répertoires nécessaires ─────────────────────────────────────
mkdir -p data reports logs dashboard models

# ── Pipeline quotidien complet : collecte → fusion historique → prédictions ───
# 1. collect_all_zones.py            : météo/satellite du jour, 8 zones
# 2. append_daily_to_historical.py   : fusionne dans data/historical/*.csv
#    (sans ça, infer_zonal.py ne voit jamais les données récentes)
# 3. compute_daily_predictions.py    : précalcule J0/J+1/J+3/J+7, lu par l'API
#    (data/predictions/latest.json) au lieu de recalculer à chaque requête
run_daily_pipeline() {
    $PYTHON data_collection/collect_all_zones.py || true
    $PYTHON data_collection/append_daily_to_historical.py || true
    $PYTHON inference/compute_daily_predictions.py || true
}

# ── Collecte immédiate si demandée ou si aucune donnée ────────────────────────
if [[ "${1:-}" == "--collect" ]] || [ -z "$(ls data/*.json 2>/dev/null)" ]; then
    echo -e "${YELLOW}[collect]${NC} Lancement du pipeline initial (collecte + historique + prédictions)..."
    run_daily_pipeline
fi

# ── Scheduler de collecte quotidienne ─────────────────────────────────────────
# Lance run_daily_pipeline tous les jours à 05:00 UTC (06:00 WAT)
# dans un processus d'arrière-plan.
schedule_collector() {
    echo -e "${GREEN}[scheduler]${NC} Démarrage du scheduler de collecte quotidienne (05:00 UTC)..."
    while true; do
        # Calcule le nombre de secondes avant 05:00 UTC demain
        NOW=$(date -u +%s)
        TARGET=$(date -u -d "tomorrow 05:00" +%s 2>/dev/null || \
                 python3 -c "import time; from datetime import datetime, timezone, timedelta; \
 t = datetime.now(timezone.utc).replace(hour=5,minute=0,second=0,microsecond=0) + timedelta(days=1); \
 print(int(t.timestamp()))")
        WAIT=$((TARGET - NOW))
        if [ $WAIT -le 0 ]; then WAIT=86400; fi
        echo -e "${GREEN}[scheduler]${NC} Prochaine collecte dans $(($WAIT/3600))h $(( ($WAIT%3600)/60 ))min"
        sleep $WAIT
        echo -e "${YELLOW}[scheduler]${NC} Lancement pipeline quotidien — $(date -u)"
        run_daily_pipeline >> logs/collect.log 2>&1 || true
    done
}

# Lance le scheduler en arrière-plan
schedule_collector &
SCHEDULER_PID=$!
echo -e "${GREEN}[scheduler]${NC} PID $SCHEDULER_PID"

# ── Démarrage du serveur FastAPI ──────────────────────────────────────────────
if [[ "${1:-}" == "--dev" ]]; then
    echo -e "${GREEN}[server]${NC} Mode développement (hot-reload)..."
    exec uvicorn server.api:app --host 0.0.0.0 --port 8000 --reload
else
    echo -e "${GREEN}[server]${NC} Mode production..."
    exec uvicorn server.api:app --host 0.0.0.0 --port 8000 --workers 2
fi
