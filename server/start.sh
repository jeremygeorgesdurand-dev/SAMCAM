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

# ── Collecte immédiate si demandée ou si aucune donnée ────────────────────────
if [[ "${1:-}" == "--collect" ]] || [ -z "$(ls data/*.json 2>/dev/null)" ]; then
    echo -e "${YELLOW}[collect]${NC} Lancement de la collecte initiale (toutes zones)..."
    $PYTHON data_collection/collect_all_zones.py || true
fi

# ── Scheduler de collecte quotidienne ─────────────────────────────────────────
# Lance collect_all_zones.py tous les jours à 05:00 UTC (06:00 WAT)
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
        echo -e "${YELLOW}[scheduler]${NC} Lancement collecte quotidienne — $(date -u)"
        $PYTHON data_collection/collect_all_zones.py >> logs/collect.log 2>&1 || true
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
