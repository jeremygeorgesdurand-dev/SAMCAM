#!/bin/bash
# SAMCAM — Collecte météo seule (Open-Meteo uniquement, sans GEE)
# Utilisé pour les runs intermédiaires toutes les 6h
# GEE n'est lancé qu'une fois par jour (scheduler.sh)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/.."
LOG_FILE="$PROJECT_DIR/logs/meteo_only.log"

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/data"

echo "" >> "$LOG_FILE"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') — Collecte météo rapide ====" >> "$LOG_FILE"

cd "$PROJECT_DIR"

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Script allégé : Open-Meteo uniquement
python3 - <<'EOF' >> "$LOG_FILE" 2>&1
import requests, json, datetime, os

LAT, LON = 2.9391, 9.9098
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath("data_collection/collect_kribi.py")), "data")
os.makedirs(OUT_DIR, exist_ok=True)

today = datetime.date.today()
end = today - datetime.timedelta(days=1)

fcast = requests.get("https://api.open-meteo.com/v1/forecast", params={
    "latitude": LAT, "longitude": LON,
    "daily": ["precipitation_sum", "temperature_2m_max", "windspeed_10m_max", "weathercode",
              "precipitation_probability_max"],
    "hourly": ["precipitation", "relative_humidity_2m"],
    "forecast_days": 16, "timezone": "Africa/Douala"
}, timeout=30).json()

filename = os.path.join(OUT_DIR, f"meteo_only_{today.isoformat()}.json")
with open(filename, "w") as f:
    json.dump({"date": today.isoformat(), "source": "open-meteo-only", "previsions": fcast.get("daily", {})}, f, ensure_ascii=False, indent=2)

print(f"[Open-Meteo] ✅ Prévisions sauvegardées : {filename}")
EOF

echo "===== Fin météo rapide ====" >> "$LOG_FILE"
