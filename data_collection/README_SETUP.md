# SAMCAM — Setup de la collecte de données

## Prérequis

```bash
pip install -r data_collection/requirements.txt
```

## Configuration de la clé GEE

Ne JAMAIS committer la clé JSON sur GitHub.

```bash
mkdir -p ~/.config/gee
mv ~/Téléchargements/samcam-499511-*.json ~/.config/gee/kribi-key.json
chmod 600 ~/.config/gee/kribi-key.json
```

Exporte la variable d'environnement (ajoute dans `~/.bashrc` ou `~/.zshrc`) :

```bash
export EE_PRIVATE_KEY_PATH="$HOME/.config/gee/kribi-key.json"
```

## Test d'authentification GEE

```python
import ee
import os

credentials = ee.ServiceAccountCredentials(
    "gee-kribi-bot@samcam-499511.iam.gserviceaccount.com",
    os.environ["EE_PRIVATE_KEY_PATH"]
)
ee.Initialize(credentials, project="samcam-499511")
print("✅ GEE OK")
```

## Lancer la collecte manuellement

```bash
python data_collection/collect_kribi.py
# ou avec 30 jours d'historique :
python data_collection/collect_kribi.py --days 30
```

## Automatiser avec cron

```bash
crontab -e
```

Ajoute cette ligne pour lancer chaque lundi à 6h :

```
0 6 * * 1 /chemin/vers/SAMCAM/data_collection/scheduler.sh
```

## Sortie

Chaque collecte génère un fichier dans `data/` :

```
data/kribi_2026-06-16.json
```

Ce fichier JSON contient :
- `meteorologie` — données Open-Meteo (historique + prévisions)
- `nasa_power` — rayonnement solaire, précipitations NASA
- `satellitaire` — indices NDVI, NDWI, NBR depuis Sentinel-2 (GEE)
- `indicateurs_risque` — scores de risque (inondation, sécheresse, submersion)
- `contexte_phi3` — texte pré-formaté pour l'inférence Phi-3 mini

## Sources de données

| Source | Données | Clé API |
|--------|---------|--------|
| Open-Meteo | Météo historique 1940+ et prévisions 7j | ❌ Aucune |
| NASA POWER | Rayonnement solaire, humidité, précipitations | ❌ Aucune |
| Google Earth Engine | Sentinel-2 NDVI/NDWI/NBR, humidité sol SMAP | ✅ Service account |
