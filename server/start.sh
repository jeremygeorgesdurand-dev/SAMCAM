#!/usr/bin/env bash
# SAMCAM V3 — Lancement du serveur FastAPI
#
# Usage :
#   bash server/start.sh            # production (port 8000)
#   bash server/start.sh --dev      # rechargement auto (développement)
#   bash server/start.sh --port 9000
#
# Prérequis :
#   pip install -r server/requirements.txt

set -e

PORT=${PORT:-8000}
HOST=${HOST:-0.0.0.0}
MODE="production"

for arg in "$@"; do
  case $arg in
    --dev)   MODE="dev" ;;
    --port=*) PORT="${arg#*=}" ;;
  esac
done

cd "$(dirname "$0")/.."

echo "================================================"
echo " SAMCAM V3 — Serveur API REST"
echo " Mode    : $MODE"
echo " Adresse : http://$HOST:$PORT"
echo " Docs    : http://localhost:$PORT/docs"
echo " Dashboard : http://localhost:$PORT/dashboard/samcam-v4-dashboard.html"
echo "================================================"
echo ""

if [ "$MODE" = "dev" ]; then
  uvicorn server.api:app --host "$HOST" --port "$PORT" --reload
else
  uvicorn server.api:app --host "$HOST" --port "$PORT"
fi
