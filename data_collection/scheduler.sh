#!/bin/bash
# SAMCAM v2 — Collecte multi-fréquence
#
# Fréquences recommandées :
#   Open-Meteo  : toutes les 6h (données météo courte échéance)
#   NASA POWER  : 1x/jour (latence ~7 jours côté NASA)
#   GEE         : 1x/jour (Sentinel-2 revisite ~5 jours + MODIS fallback)
#
# Configuration cron (crontab -e) :
#
#   # Collecte complète toutes les 6h
#   0 0,6,12,18 * * * /chemin/vers/SAMCAM/data_collection/scheduler.sh >> /chemin/vers/SAMCAM/logs/collecte.log 2>&1
#
#   # Ou collecte légère toutes les 6h (météo seulement) + complète 1x/jour
#   0 6,12,18 * * * /chemin/vers/SAMCAM/data_collection/scheduler_meteo_only.sh
#   0 1 * * *       /chemin/vers/SAMCAM/data_collection/scheduler.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/.."
LOG_FILE="$PROJECT_DIR/logs/collecte.log"

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/data"

export EE_PRIVATE_KEY_PATH="$HOME/.config/gee/kribi-key.json"

echo "" >> "$LOG_FILE"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') — Collecte SAMCAM démarrée ====" >> "$LOG_FILE"

cd "$PROJECT_DIR"

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

python3 data_collection/collect_kribi.py --days 7 >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Collecte réussie" >> "$LOG_FILE"
else
    echo "❌ Collecte échouée (code $EXIT_CODE)" >> "$LOG_FILE"
fi

echo "===== Fin ====" >> "$LOG_FILE"
