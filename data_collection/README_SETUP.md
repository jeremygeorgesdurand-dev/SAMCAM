# SAMCAM v2 — Setup de la collecte de données

## Prérequis

```bash
pip3 install -r data_collection/requirements.txt
```

## Configuration de la clé GEE

⚠️ **Ne JAMAIS committer la clé JSON sur GitHub.**

```bash
mkdir -p ~/.config/gee
mv ~/Downloads/samcam-499511-*.json ~/.config/gee/kribi-key.json
chmod 600 ~/.config/gee/kribi-key.json
```

Rends la variable permanente (Mac/zsh) :

```bash
echo 'export EE_PRIVATE_KEY_PATH="$HOME/.config/gee/kribi-key.json"' >> ~/.zshrc
source ~/.zshrc
```

## Lancer la collecte manuellement

```bash
python3 data_collection/collect_kribi.py
# avec 30 jours d'historique :
python3 data_collection/collect_kribi.py --days 30
```

## Résultat attendu

```
============================================================
SAMCAM v2 — Collecte automatique Kribi
============================================================
[1/3] Open-Meteo...
[Open-Meteo] ✅ Historique 7j + prévisions 16j récupérés
[2/3] NASA POWER...
[NASA POWER] ✅ Données 7j récupérées
[3/3] Google Earth Engine...
[GEE Sentinel-2] 🛰️  X image(s) trouvée(s) (filtre nuages 80%)
[GEE SMAP] ✅ Humidité du sol récupérée
✅ Collecte terminée
📄 Fichier : data/kribi_2026-06-15.json
```

Si Sentinel-2 retourne 0 image (couverture nuageuse totale) :
```
[GEE Sentinel-2] ⚠️  Aucune image → passage au fallback MODIS
[GEE MODIS] ✅ NDVI et EVI MODIS récupérés (fallback)
```

## Automatisation cron (Mac/Linux)

```bash
crontab -e
```

Ajoute ces deux lignes :

```
# Collecte complète 1x/jour à 1h du matin
0 1 * * * /Users/jeremy/Documents/Cameroun/SAMCAM/data_collection/scheduler.sh

# Collecte météo rapide toutes les 6h (6h, 12h, 18h)
0 6,12,18 * * * /Users/jeremy/Documents/Cameroun/SAMCAM/data_collection/scheduler_meteo_only.sh
```

## Sources de données

| Source | Données | Fréquence recommandée | Clé API |
|--------|---------|----------------------|--------|
| Open-Meteo | Météo historique + prévisions 16j | Toutes les 6h | ❌ Aucune |
| NASA POWER | Rayonnement solaire, humidité, précip | 1x/jour | ❌ Aucune |
| Sentinel-2 (GEE) | NDVI, NDWI, NBR, NDRE (10-20m) | 1x/jour | ✅ Service account |
| MODIS (GEE fallback) | NDVI, EVI (500m, 16j) | 1x/jour | ✅ Service account |
| SMAP (GEE) | Humidité du sol (10km) | 1x/jour | ✅ Service account |

## Fichiers générés

```
data/
  kribi_2026-06-15.json        # Collecte complète (GEE + météo + NASA)
  meteo_only_2026-06-15.json   # Collecte météo rapide (Open-Meteo seul)
logs/
  collecte.log                 # Logs collecte complète
  meteo_only.log               # Logs collecte rapide
```
