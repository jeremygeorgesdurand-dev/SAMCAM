# Guide de réentraînement des modèles — SAMCAM

> Ce guide décrit l'architecture **actuelle** (un modèle par zone et par risque). Pour le
> détail complet de la méthode, voir `docs/RAPPORT_SAMCAM.md` §5.3, §6.6 et §9.8.

## Pourquoi réentraîner ?

Chaque zone SAMCAM a son propre modèle par risque (54 modèles = 18 zones × 3 risques :
inondation, sécheresse, chaleur), entraîné sur l'historique météo réel de sa zone. Un
réentraînement est nécessaire après :

- l'enrichissement de l'historique d'une zone (nouvelles années de données) ;
- la correction d'une configuration de zone (`config/zones/<slug>.json`) ;
- l'ajout d'un événement documenté (EM-DAT/OCHA) à `training/build_labels.py` ;
- ou périodiquement (trimestriel recommandé), pour intégrer les données collectées depuis.

## Les zones et leur classe climatique

| Classe climatique | Zones |
|---|---|
| **Équatorial** | Kribi, Ebolowa, Kumba, Yaounde_peri, Mbalmayo, Bafia, Bertoua, Nkongsamba, Buea |
| **Hauts plateaux** | Bafoussam, Ngaoundere, Ndop, Foumbot, Meiganga |
| **Sahélien** | Garoua, Maroua, Kaele, Guider |

## Réentraîner une zone existante

```bash
cd /chemin/SAMCAM && source venv/bin/activate   # ou .venv selon votre installation

python training/build_labels.py --zone <Nom>              # 1. Régénérer les labels
python training/train_zonal_models.py --zone <Nom> --force  # 2. Réentraîner (3 risques)
python inference/compute_daily_predictions.py             # 3. Rafraîchir le cache de prédictions
```

Réentraîner **toutes les zones** en une fois : omettre `--zone`. Limiter à un seul risque :
ajouter `--risk inondation|secheresse|chaleur` à `train_zonal_models.py`.

⚠️ **Sans `--force`, un modèle `.pkl` déjà existant est sauté** — indispensable pour un
vrai réentraînement.

## Valider après réentraînement

```bash
# Métriques détaillées (AUC, F1) par modèle
cat models/zonal/metrics/metrics_<risque>_<zone>.json

# Validation contre des événements réels documentés (zones initiales)
python training/evaluate_real_events.py
```

## Ajouter une toute nouvelle zone

Voir `training/README.md` (section « Ajouter une TOUTE NOUVELLE zone ») et
`docs/RAPPORT_SAMCAM.md` §6.6 pour la méthode complète (calibration climatique depuis
l'historique réel + ré-étalonnage statistique des seuils, pour éviter des labels trop
sensibles). En résumé :

```bash
python data_collection/collect_historical.py --zone <Nom> --start 2000-01-01
python training/generate_zone_config.py --zone <Nom> --climate <classe>
python training/calibrate_zone_thresholds.py --zone <Nom>
python training/build_labels.py --zone <Nom>
python training/train_zonal_models.py --zone <Nom> --force
```

Ou en une commande : `bash training/onboard_new_zones.sh` (après y avoir ajouté le nom
de la zone).

## Réentraînement continu (cron mensuel)

```cron
# 1er de chaque mois à 03:00 UTC — réentraîne toutes les zones
0 3 1 * * cd /chemin/vers/SAMCAM && venv/bin/python training/build_labels.py && venv/bin/python training/train_zonal_models.py --force >> logs/retrain.log 2>&1
```

Sur Raspberry Pi (installation Docker, voir `docs/DEPLOIEMENT_RASPBERRY_PI.md`), le
réentraînement n'est **pas** destiné à tourner sur la station elle-même (charge CPU trop
lourde pour 2 Go de RAM) — il se fait sur une machine de développement, puis les
`.pkl` mis à jour sont poussés via `git push` / `git pull`.
