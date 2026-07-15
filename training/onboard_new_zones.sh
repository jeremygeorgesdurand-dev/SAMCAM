#!/usr/bin/env bash
# Pipeline complet d'intégration des nouvelles zones agricoles SAMCAM :
# backfill historique → calibration config zone → labellisation → entraînement.
# Traite les zones une par une (une zone qui échoue n'interrompt pas les suivantes).
set -uo pipefail
cd "$(dirname "$0")/.."

ZONES=(Ndop Foumbot Kaele Guider Meiganga Mbalmayo Bafia Bertoua Nkongsamba Buea)

source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null

LOG="logs/onboard_new_zones.log"
mkdir -p logs
echo "=== Démarrage onboarding $(date -u) ===" >> "$LOG"

for Z in "${ZONES[@]}"; do
    echo "" >> "$LOG"
    echo "########## $Z ##########" >> "$LOG"

    CSV="data/historical/${Z}_historical.csv"
    if [ ! -f "$CSV" ] || [ "$(wc -l < "$CSV")" -lt 1000 ]; then
        echo "[$Z] Backfill historique..." >> "$LOG"
        python3 -m data_collection.collect_historical --zone "$Z" >> "$LOG" 2>&1
    else
        echo "[$Z] Historique déjà présent ($(wc -l < "$CSV") lignes) — skip backfill." >> "$LOG"
    fi

    if [ ! -f "$CSV" ]; then
        echo "[$Z] ✗ Échec backfill — zone ignorée." >> "$LOG"
        continue
    fi

    Z_SLUG=$(echo "$Z" | tr '[:upper:]' '[:lower:]')
    echo "[$Z] Calibration config/zones/${Z_SLUG}.json..." >> "$LOG"
    python3 training/generate_zone_config.py --zone "$Z" --force >> "$LOG" 2>&1

    echo "[$Z] Labellisation..." >> "$LOG"
    python3 training/build_labels.py --zone "$Z" >> "$LOG" 2>&1

    echo "[$Z] Entraînement modèles (3 risques)..." >> "$LOG"
    python3 training/train_zonal_models.py --zone "$Z" --force >> "$LOG" 2>&1

    echo "[$Z] ✓ Terminé." >> "$LOG"
done

echo "" >> "$LOG"
echo "=== Onboarding terminé $(date -u) ===" >> "$LOG"
