# Guide de réentraînement du modèle ML — Multi-zones Cameroun

## Pourquoi réentraîner ?

Le modèle actuel a été entraîné principalement sur les données de **Kribi**.
Pour qu'il soit précis sur l'ensemble du Cameroun (8 zones, 3 grandes régions
climatiques), il doit voir des données de **chaque zone** sur au moins
**6 à 12 mois** de collecte quotidienne.

---

## Les 3 régions climatiques à couvrir

| Région | Zones | Particularités |
|---|---|---|
| **Guinéen / Équatorial** | Kribi, Ebolowa, Kumba | 2 saisons des pluies, humidité élevée, risque inondation fort |
| **Tropical de transition** | Yaounde_peri, Bafoussam, Ngaoundere | 1 saison sèche marquée, risque sécheresse modéré |
| **Sahélien / Semi-aride** | Garoua, Maroua | Longue saison sèche, risque chaleur et sécheresse élevés |

---

## Étape 1 — Accumuler les données multi-zones

Le scheduler lance automatiquement la collecte chaque jour à 06h00 WAT :

```bash
bash server/start.sh
```

Pour lancer une collecte manuelle sur toutes les zones :

```bash
python3 data_collection/collect_all_zones.py
```

Pour une zone spécifique :

```bash
python3 data_collection/collect_all_zones.py --zones Garoua Maroua
```

Vérifier les données disponibles :

```bash
ls data/ | sort
# Attendu : kribi_2026-07-03.json, garoua_2026-07-03.json, etc.
```

---

## Étape 2 — Préparer le dataset d'entraînement

Après au moins **30 jours** de collecte multi-zones (idéalement 90+), lancer :

```bash
python3 inference/prepare_dataset.py \
    --zones Kribi Ebolowa Kumba Yaounde_peri Bafoussam Ngaoundere Garoua Maroua \
    --output data/training_dataset_multizone.csv
```

Ce script :
- Fusionne les fichiers `data/<zone>_*.json` de toutes les zones
- Ajoute une colonne `zone` et `region_climatique` comme features
- Normalise les indicateurs (pluie, NDVI, humidité sol) par région
- Génère les labels `risque_inondation`, `risque_secheresse`, `risque_chaleur`

---

## Étape 3 — Réentraîner le modèle

```bash
python3 inference/train_model.py \
    --dataset data/training_dataset_multizone.csv \
    --output models/ \
    --zones-aware          # active les features région climatique
```

Options importantes :
- `--zones-aware` : ajoute `zone_encoded` et `region_encoded` comme features
- `--cross-validate` : validation croisée par zone (recommandé)
- `--min-samples 50` : exclut les zones avec moins de 50 jours de données

### Métriques cibles par type de risque

| Risque | AUC-ROC cible | Notes |
|---|---|---|
| Inondation | > 0.82 | Surtout Kribi, Kumba, Yaounde_peri |
| Sécheresse | > 0.80 | Surtout Garoua, Maroua, Ngaoundere |
| Chaleur | > 0.78 | Toutes zones Nord |

---

## Étape 4 — Valider et déployer

```bash
# Test sur les données récentes (les 7 derniers jours de chaque zone)
python3 inference/evaluate_model.py \
    --model models/ \
    --zones Garoua Maroua Ngaoundere  # zones les plus éloignées de Kribi

# Si métriques OK → remplacer les modèles en production
cp models/risk_model_multizone_*.pkl models/risk_model.pkl

# Redémarrer le serveur pour charger le nouveau modèle
bash server/start.sh
```

---

## Stratégie de réentraînement continu

Une fois le scheduler actif, ajouter ce cron **mensuel** :

```cron
# Réentraînement automatique le 1er de chaque mois à 03:00 UTC
0 3 1 * * cd /chemin/vers/SAMCAM && python3 inference/train_model.py \
    --dataset data/training_dataset_multizone.csv \
    --output models/ --zones-aware >> logs/retrain.log 2>&1
```

### Priorité des zones pour les premières semaines

Les zones les plus différentes de Kribi (zone d'entraînement initial) doivent
être collectées en priorité :

1. **Maroua** — Sahel, risques très différents
2. **Garoua** — Semi-aride, coton/mil
3. **Ngaoundere** — Altitude, élevage bovin
4. Les autres zones progressivement

---

## Résumé du flux complet

```
[06:00 WAT chaque jour]
  └── collect_all_zones.py
        └── data/kribi_YYYY-MM-DD.json
        └── data/garoua_YYYY-MM-DD.json
        └── ... (8 zones)

[Appli Flutter]
  └── GET /api/nearest?lat=X&lon=Y    (< 50 ms)
        └── trouve zone la plus proche
        └── charge JSON du jour
        └── calcule scores ML
        └── retourne au téléphone

[1er du mois à 03:00 UTC]
  └── train_model.py --zones-aware
        └── dataset fusionné 8 zones
        └── nouveau modèle → models/
        └── server rechargé
```
