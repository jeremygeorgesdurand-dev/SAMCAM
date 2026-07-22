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

# Collecte immédiate si aucune prédiction n'existe, OU si la dernière date
# d'au moins un jour avant aujourd'hui.
#
# Bug corrigé le 2026-07-22 : l'ancienne condition ne vérifiait que
# l'EXISTENCE de latest.json, pas sa fraîcheur. Comme ce fichier survit aux
# redémarrages du conteneur (volume monté), chaque `docker compose up`/
# `restart` pendant la journée réinitialisait juste le minuteur "prochaine
# collecte à 05h00 UTC" sans jamais l'atteindre — si le conteneur redémarre
# plus d'une fois par jour (courant en maintenance/déploiement), la collecte
# quotidienne pouvait ne JAMAIS se déclencher, plusieurs jours de suite,
# sans aucune erreur : data/*.json (l'aperçu du jour) restait à jour car
# généré par un autre mécanisme, mais data/historical/*.csv (utilisé par
# /api/history) n'était plus jamais fusionné.
LAST_RUN_DATE=""
if [ -f data/predictions/latest.json ]; then
    LAST_RUN_DATE=$(date -u -r data/predictions/latest.json +%Y-%m-%d 2>/dev/null || echo "")
fi
TODAY=$(date -u +%Y-%m-%d)
if [ "$LAST_RUN_DATE" != "$TODAY" ]; then
    echo "[collector] Dernière collecte : ${LAST_RUN_DATE:-jamais} — pas celle d'aujourd'hui ($TODAY) — collecte immédiate"
    run_pipeline
else
    echo "[collector] Collecte déjà faite aujourd'hui ($TODAY) — pas de collecte immédiate"
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
