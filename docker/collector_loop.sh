#!/usr/bin/env bash
# Boucle de planification du pipeline quotidien SAMCAM (collecte → historique → prédictions).
# Reste endormi (quasi 0 RAM/CPU) le reste du temps — même logique que
# schedule_collector() dans server/start.sh, extraite ici pour le conteneur collecteur.
set -uo pipefail
cd /app

run_pipeline() {
    echo "[collector] $(date -u) — lancement du pipeline quotidien"
    python3 data_collection/collect_all_zones.py || true
    python3 data_collection/append_daily_to_historical.py || true
    python3 inference/compute_daily_predictions.py || true
    echo "[collector] $(date -u) — pipeline terminé"
}

# Collecte immédiate au premier démarrage si aucune prédiction n'existe encore
if [ ! -f data/predictions/latest.json ]; then
    echo "[collector] Aucune prédiction existante — collecte initiale"
    run_pipeline
fi

while true; do
    NOW=$(date -u +%s)
    TARGET=$(python3 -c "
from datetime import datetime, timezone, timedelta
t = datetime.now(timezone.utc).replace(hour=5, minute=0, second=0, microsecond=0) + timedelta(days=1)
print(int(t.timestamp()))
")
    WAIT=$((TARGET - NOW))
    if [ "$WAIT" -le 0 ]; then WAIT=86400; fi
    echo "[collector] Prochaine collecte dans $((WAIT/3600))h $(((WAIT%3600)/60))min"
    sleep "$WAIT"
    run_pipeline
done
