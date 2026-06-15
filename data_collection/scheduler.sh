#!/bin/bash
# SAMCAM — Planificateur de collecte automatique
# Lance la collecte chaque semaine via cron
#
# Pour ajouter au cron (chaque lundi à 6h du matin) :
#   crontab -e
#   0 6 * * 1 /chemin/vers/SAMCAM/data_collection/scheduler.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/.."
LOG_FILE="$PROJECT_DIR/logs/collecte.log"

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/data"

export EE_PRIVATE_KEY_PATH="$HOME/.config/gee/kribi-key.json"

echo "" >> "$LOG_FILE"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') - Collecte SAMCAM démarrée =====" >> "$LOG_FILE"

cd "$PROJECT_DIR"

# Activation de l'environnement virtuel si présent
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

python data_collection/collect_kribi.py --days 7 >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Collecte réussie" >> "$LOG_FILE"
else
    echo "❌ Collecte échouée (code $EXIT_CODE)" >> "$LOG_FILE"
fi

echo "===== Fin collecte =====" >> "$LOG_FILE"
