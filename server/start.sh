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

# ── Environnement virtuel (accepte venv/ et .venv/) ──────────────────────────
if [ -f "venv/bin/activate" ]; then
    echo -e "${GREEN}[venv]${NC} Activation de l'environnement virtuel (venv)..."
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    echo -e "${GREEN}[venv]${NC} Activation de l'environnement virtuel (.venv)..."
    source .venv/bin/activate
else
    echo -e "${YELLOW}[venv]${NC} Pas de venv trouvé — utilisation du Python système"
fi

PYTHON="$(which python3)"
echo -e "${GREEN}[python]${NC} $PYTHON"

# ── Secrets locaux (WhatsApp, etc.) — jamais commités, voir .gitignore ───────
if [ -f "server/.env.local" ]; then
    echo -e "${GREEN}[env]${NC} Chargement de server/.env.local..."
    source server/.env.local
fi

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

# ── Garde-fou : un seul scheduler à la fois ───────────────────────────────────
# Chaque lancement de start.sh créait un scheduler d'arrière-plan qui
# SURVIVAIT à l'arrêt du serveur (aucun trap) : les instances s'accumulaient
# et le pipeline quotidien s'exécutait N fois en parallèle. On tue donc les
# schedulers résiduels des lancements précédents, et un trap lie la vie du
# nouveau scheduler à celle du serveur.
for pid in $(pgrep -f "server/start.sh" 2>/dev/null || true); do
    [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ] && kill "$pid" 2>/dev/null || true
done

schedule_collector &
SCHEDULER_PID=$!
trap 'kill $SCHEDULER_PID 2>/dev/null || true' EXIT INT TERM
echo -e "${GREEN}[scheduler]${NC} PID $SCHEDULER_PID (arrêté automatiquement avec le serveur)"

# ── Accès distant : publication automatique via Tailscale Funnel ─────────────
# Si Tailscale est installé et connecté, l'API est publiée sur Internet
# (https://<machine>.<tailnet>.ts.net) sans aucune manipulation supplémentaire.
# La publication est persistante (--bg) : elle survit aux redémarrages tant
# que tailscaled tourne. Sans Tailscale, le serveur reste accessible en local.
#
# Résolution du binaire : sur Linux (Raspberry Pi), le paquet officiel
# installe `tailscale` dans le PATH. Sur macOS (version Mac App Store), le
# CLI n'est PAS dans le PATH — il faut appeler le binaire de l'app bundle
# directement (jamais via un lien symbolique : le binaire vérifie son
# identifiant de bundle et plante si on le symlinke ailleurs).
resolve_tailscale_bin() {
    if command -v tailscale >/dev/null 2>&1; then
        echo "tailscale"
    elif [ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ]; then
        echo "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    fi
}

enable_funnel() {
    local TS
    TS="$(resolve_tailscale_bin)"
    if [ -z "$TS" ]; then
        echo -e "${YELLOW}[funnel]${NC} Tailscale non installé — accès local uniquement."
        echo -e "${YELLOW}[funnel]${NC} Pour l'accès Internet : curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --hostname=cameroun"
        return 0
    fi
    if ! "$TS" status >/dev/null 2>&1; then
        echo -e "${YELLOW}[funnel]${NC} Tailscale installé mais non connecté — lancez : sudo $TS up --hostname=cameroun"
        return 0
    fi
    if "$TS" funnel --bg 8000 >/dev/null 2>&1 || sudo -n "$TS" funnel --bg 8000 >/dev/null 2>&1; then
        FUNNEL_URL=$("$TS" funnel status 2>/dev/null | grep -o 'https://[^ ]*\.ts\.net[^ ]*' | head -1)
        echo -e "${GREEN}[funnel]${NC} API publiée sur Internet : ${FUNNEL_URL:-voir « $TS funnel status »}"
    else
        echo -e "${YELLOW}[funnel]${NC} Publication impossible (droits ?) — lancez une fois : sudo $TS funnel --bg 8000"
    fi
}
enable_funnel

# ── Démarrage du serveur FastAPI ──────────────────────────────────────────────
# uvicorn tourne en processus ENFANT (pas exec) pour que le trap EXIT
# s'exécute à l'arrêt et tue le scheduler avec le serveur.
if [[ "${1:-}" == "--dev" ]]; then
    echo -e "${GREEN}[server]${NC} Mode développement (hot-reload)..."
    uvicorn server.api:app --host 0.0.0.0 --port 8000 --reload &
else
    echo -e "${GREEN}[server]${NC} Mode production..."
    uvicorn server.api:app --host 0.0.0.0 --port 8000 --workers 2 &
fi
SERVER_PID=$!
trap 'kill $SERVER_PID $SCHEDULER_PID 2>/dev/null || true' EXIT INT TERM
wait $SERVER_PID
