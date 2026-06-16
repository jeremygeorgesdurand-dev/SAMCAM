#!/usr/bin/env bash
# SAMCAM V3 — Lancement du serveur FastAPI
#
# Usage :
#   bash server/start.sh            # production (port 8000)
#   bash server/start.sh --dev      # rechargement auto (développement)
#   PORT=9000 bash server/start.sh  # port personnalisé
#
# Prérequis :
#   python3 -m pip install -r server/requirements.txt
#   # ou avec venv : source .venv/bin/activate && pip install -r server/requirements.txt

set -e

PORT=${PORT:-8000}
HOST=${HOST:-0.0.0.0}
MODE="production"

for arg in "$@"; do
  case $arg in
    --dev)    MODE="dev" ;;
    --port=*) PORT="${arg#*=}" ;;
  esac
done

# Aller à la racine du projet
cd "$(dirname "$0")/.."

# Auto-détection du venv (.venv ou venv dans la racine du projet)
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
  echo "[venv] Environnement virtuel .venv activé"
elif [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
  echo "[venv] Environnement virtuel venv activé"
fi

# Utilise python3 -m uvicorn pour éviter le problème "command not found"
PYTHON="$(which python3)"
UVICORN_CMD="$PYTHON -m uvicorn"

echo "================================================"
echo " SAMCAM V3 — Serveur API REST"
echo " Mode    : $MODE"
echo " Python  : $PYTHON"
echo " Adresse : http://localhost:$PORT"
echo " Docs    : http://localhost:$PORT/docs"
echo " Dashboard : http://localhost:$PORT/dashboard/samcam-v4-dashboard.html"
echo "================================================"
echo ""

if [ "$MODE" = "dev" ]; then
  $UVICORN_CMD server.api:app --host "$HOST" --port "$PORT" --reload
else
  $UVICORN_CMD server.api:app --host "$HOST" --port "$PORT"
fi
