# SAMCAM — Pipeline d'entraînement zonal

Ce dossier contient les scripts pour entraîner des modèles ML spécifiques à chaque zone SAMCAM (18 zones : 8 zones climatiques initiales + 10 zones agricoles) sur des données historiques réelles (1990/2000-2026 selon la zone).

## Workflow complet (zone déjà connue du système)

```
Étape 1 : Collecte historique
  python data_collection/collect_historical.py
  → data/historical/<zone>_historical.csv (18 fichiers, ~9 500 à 13 200 lignes chacun)

Étape 2 : Construction des labels
  python training/build_labels.py
  → data/historical/<zone>_labeled.csv (avec colonnes label_inondation, label_secheresse, label_chaleur)

Étape 3 : Entraînement zonal
  python training/train_zonal_models.py
  → models/zonal/model_{risque}_{zone}.pkl (54 fichiers)
  → models/zonal/metrics/metrics_{risque}_{zone}.json (métriques par modèle)
```

## Ajouter une TOUTE NOUVELLE zone

Pour une zone qui n'a pas encore de config climatique (`config/zones/<slug>.json`), deux étapes supplémentaires précèdent la Étape 2 ci-dessus — voir `docs/RAPPORT_SAMCAM.md` §6.6 pour la méthode complète :

```bash
# a. Calibrer les normales climatiques depuis l'historique réel (pas de valeurs génériques)
python training/generate_zone_config.py --zone <Nom> --climate <equatorial|tropical_highland|sahelian>

# b. Ré-étalonner statistiquement les seuils d'alerte (aligne le taux d'alerte sur les zones
#    déjà calibrées de la même classe climatique — les seuils génériques sont souvent trop sensibles)
python training/calibrate_zone_thresholds.py --zone <Nom>
```

Ou en une commande : `bash training/onboard_new_zones.sh` (éditer le script pour y ajouter le nom de la zone) enchaîne backfill → calibration → labellisation → entraînement.

## Options utiles

```bash
# Zone spécifique
python data_collection/collect_historical.py --zone Maroua
python training/build_labels.py --zone Maroua
python training/train_zonal_models.py --zone Maroua --risk secheresse

# Historique plus long (depuis 2010)
python data_collection/collect_historical.py --start 2010-01-01

# Forcer le ré-entraînement
python training/train_zonal_models.py --force
```

## Sources de données

| Source | Type | Période | Variables |
|---|---|---|---|
| Open-Meteo Historical | Météo journalière | 1940–J-5 | Précip, Tmax/min, humidité, vent, ETP |
| NASA POWER | Rayonnement, sol | 1981–J-2 | SW, T2M, RH, précip, humidité sol |

## Stratégie de labellisation

Approche hybride :
1. **Seuils physiques calibrés** par type climatique (équatorial, tropical highland, sahélien)
2. **Événements EM-DAT/OCHA** avérés au Cameroun (2012-2024) utilisés pour surcharger les labels (liste `KNOWN_EVENTS` dans `build_labels.py`)

## Modèles produits

54 modèles zonaux : **18 zones × 3 risques** (inondation, sécheresse, chaleur)

Chaque `.pkl` contient :
- Le modèle entraîné (RandomForest ou GradientBoosting, selon meilleur AUC)
- La liste des features utilisées
- Le seuil de décision optimisé par F1
- Les métriques d'évaluation

## Métriques attendues (objectifs)

| Zone/Risque | AUC cible | F1 cible |
|---|---|---|
| Inondation (zones côtières) | > 0.80 | > 0.65 |
| Sécheresse (zones sahéliennes) | > 0.75 | > 0.60 |
| Chaleur (Maroua, Garoua) | > 0.85 | > 0.70 |
