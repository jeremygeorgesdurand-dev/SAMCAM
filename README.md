# 🌦️ SAMCAM — Système d'Alerte Météorologique du Cameroun

> Système d'alerte climatique précoce (inondation, sécheresse, vague de chaleur) pour 18 zones du Cameroun, appuyé par un serveur local (Raspberry Pi) hébergeant 54 modèles d'apprentissage automatique. Application mobile Flutter offline-first, bilingue français/anglais.

**Rapport de projet complet** (architecture, choix techniques, guide d'installation détaillé, évaluation de fiabilité) : [`docs/RAPPORT_SAMCAM.md`](docs/RAPPORT_SAMCAM.md)

---

## 🎯 Contexte et problématique

Le Cameroun est exposé à plusieurs aléas climatiques majeurs : inondations en saison de fortes pluies, sécheresses affectant l'agriculture, et vagues de chaleur. Ces phénomènes ont des conséquences directes sur les populations, les exploitations agricoles, les infrastructures locales et l'organisation des services publics.

**Problématique** : comment concevoir un système d'alerte météorologique léger, accessible sur smartphone, capable d'exploiter des données météorologiques et satellitaires pour estimer des risques climatiques localisés, tout en restant utilisable dans un contexte de connectivité intermittente et de ressources matérielles limitées ?

---

## 🏗️ Architecture

Traitement centralisé sur un serveur (Raspberry Pi ou machine de développement) qui collecte les données, exécute les modèles et expose une API REST légère ; l'application mobile ne fait qu'interroger cette API et conserve un cache local pour fonctionner hors-ligne.

```
┌──────────────────────────────────────────────────────────────┐
│                      SOURCES DE DONNÉES                       │
│   Open-Meteo · NASA POWER · Google Earth Engine (Sentinel-2,  │
│   MODIS, SMAP, CHIRPS, IMERG, ERA5)                            │
└────────────────────────────┬───────────────────────────────────┘
                              │ Collecte quotidienne (cron, 05h00 UTC)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                 SERVEUR (Raspberry Pi ou dev)                  │
│  Collecte → Prétraitement → 54 modèles zonaux (RandomForest/   │
│  GradientBoosting) → Cache prédictions → API FastAPI :8000      │
│  + Assistant IA (Ollama, RAG léger) + Bot WhatsApp (prêt)       │
└────────────────────────────┬───────────────────────────────────┘
                              │ API JSON légère (Tailscale Funnel
                              │ pour l'accès distant gratuit)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                  APPLICATION MOBILE (Flutter)                  │
│  Alertes multi-horizon · Carte · Historique · Signalement      │
│  communautaire · Mode offline-first · Français/Anglais         │
└──────────────────────────────────────────────────────────────┘
```

---

## 🗺️ Les 18 zones surveillées

**8 zones climatiques initiales** : Kribi, Ebolowa, Kumba, Bafoussam, Yaoundé (périphérie), Ngaoundéré, Garoua, Maroua.

**10 zones agricoles ajoutées** (couvrant riz, coton, cacao, café, palmier à huile, élevage) : Ndop, Foumbot, Kaélé, Guider, Meiganga, Mbalmayo, Bafia, Bertoua, Nkongsamba, Buea.

Détail complet (région, filière, climat) : `docs/RAPPORT_SAMCAM.md` §2.3.

---

## 📁 Structure du projet

```
SAMCAM/
├── docs/
│   ├── RAPPORT_SAMCAM.md            ← Rapport de projet complet
│   ├── DEPLOIEMENT_RASPBERRY_PI.md  ← Guide déploiement Docker sur Pi
│   └── NOTIFICATIONS_PUSH_FCM.md    ← Guide notifications push (Firebase)
│
├── config/zones/            ← Climatologie de chaque zone (18 fichiers .json)
│
├── data_collection/         ← Collecte (Open-Meteo, NASA POWER, Google Earth Engine)
│   ├── collect_all_zones.py         (orchestrateur, 18 zones)
│   ├── collect_historical.py        (backfill historique 20-36 ans)
│   └── append_daily_to_historical.py
│
├── training/                 ← Génération des labels + entraînement
│   ├── build_labels.py              (labels par règles climatologiques + événements réels)
│   ├── generate_zone_config.py      (calibration climatique depuis l'historique réel)
│   ├── calibrate_zone_thresholds.py (ré-étalonnage statistique des seuils)
│   ├── train_zonal_models.py        (54 modèles : 18 zones × 3 risques)
│   ├── onboard_new_zones.sh         (pipeline complet pour une nouvelle zone)
│   └── evaluate_real_events.py      (validation contre catastrophes documentées)
│
├── inference/                ← Moteur de prédiction
│   ├── infer_zonal.py               (inférence multi-horizon J0 → J+14)
│   └── compute_daily_predictions.py (pré-calcul quotidien → cache)
│
├── models/zonal/             ← 54 modèles entraînés (.pkl) + métriques
│
├── server/
│   ├── api.py                       (API REST FastAPI)
│   ├── whatsapp_bot.py              (bot WhatsApp)
│   ├── send_push_alerts.py          (notifications push)
│   └── start.sh                     (démarrage natif + Tailscale Funnel)
│
├── docker/                   ← Images Docker (API + collecteur) pour Raspberry Pi
├── docker-compose.yml
├── install_pi.sh             ← Installation automatique sur Raspberry Pi
│
├── dashboard/                 ← Tableau de bord HTML (écran local)
└── samcam_app/                ← Application mobile Flutter (FR/EN)
```

---

## 🚀 Démarrage rapide

### Sur une machine de développement (Mac/Linux/PC)

```bash
git clone <url-du-depot> SAMCAM && cd SAMCAM
python3 -m venv venv && source venv/bin/activate

pip install -r data_collection/requirements.txt
pip install -r inference/requirements_v4.txt
pip install -r server/requirements.txt

python3 data_collection/collect_all_zones.py
python3 data_collection/append_daily_to_historical.py
python3 inference/compute_daily_predictions.py

bash server/start.sh
# API      : http://localhost:8000
# Docs     : http://localhost:8000/docs
# Dashboard: http://localhost:8000/dashboard/samcam-v4-dashboard.html
```

### Sur Raspberry Pi 4 (recommandé si RAM limitée, ex. 2 Go)

```bash
git clone <url-du-depot> SAMCAM && cd SAMCAM
bash install_pi.sh
```

Installation Docker automatisée (swap, Docker Engine, vérification Ollama, Tailscale
Funnel). Détail complet : [`docs/DEPLOIEMENT_RASPBERRY_PI.md`](docs/DEPLOIEMENT_RASPBERRY_PI.md).

### Application mobile

```bash
cd samcam_app
flutter pub get
flutter build apk --release --split-per-abi
adb install build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
```

L'app détecte automatiquement le serveur au premier lancement — aucune configuration
manuelle requise dans le cas normal. Guide complet : `docs/RAPPORT_SAMCAM.md` §9.6-9.7.

---

## 🌐 API REST — Principaux endpoints

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/health` | Statut du serveur, modèles chargés, zones disponibles |
| `GET` | `/api/zones` | Liste des 18 zones |
| `GET` | `/api/risk?zone=X` | Bulletin de risque complet (J0 → J+14) |
| `GET` | `/api/nearest?lat=&lon=` | Bulletin de la zone la plus proche d'une position GPS |
| `GET` | `/api/overview` | Niveau d'alerte des 18 zones en une requête |
| `GET` | `/api/history?zone=&days=` | Évolution jour par jour des scores |
| `POST` | `/api/assistant` | Résumé/question en langage naturel (Ollama, ancré sur les données réelles) |
| `POST` | `/api/signalement` | Dépôt d'un signalement terrain par un utilisateur |
| `GET` | `/docs` | Documentation Swagger interactive |

---

## 🗺️ Roadmap

- [x] **V1-V3** — Dashboard météo multi-zones, intégration satellite, serveur FastAPI + collecte automatisée
- [x] **V4** — Modèle de classification de risque (GradientBoosting), historique réel
- [x] **V5** — Architecture zonale (un modèle par zone et par risque), application mobile Flutter offline-first
- [x] **Zones agricoles** — Extension de 8 à 18 zones, méthode de calibration reproductible
- [x] **Assistant IA** — Résumés/questions en langage naturel via Ollama, ancrés sur les données réelles
- [x] **Bilingue** — Interface français/anglais
- [x] **Déploiement Raspberry Pi** — Installation Docker en une commande, budget mémoire 2 Go
- [x] **Bot WhatsApp** — Code prêt, activation bloquée par une vérification anti-fraude côté Meta (indépendante du projet)
- [ ] **Notifications push** — Scaffolding prêt (Firebase), activation à finaliser
- [ ] **Publication Play Store**

Détail complet des perspectives : `docs/RAPPORT_SAMCAM.md` §10.

---

## 🔧 Technologies

| Couche | Technologie |
|---|---|
| Collecte | Open-Meteo, NASA POWER, Google Earth Engine (Sentinel-2, MODIS, SMAP, CHIRPS, IMERG, ERA5) |
| Modèles ML | scikit-learn (RandomForest, GradientBoosting), TimeSeriesSplit, 54 modèles zonaux |
| Assistant IA | Ollama (Phi-3 mini en dev, Qwen 3 0.6B partagé sur Pi) |
| Serveur API | FastAPI, uvicorn |
| Déploiement Pi | Docker Engine, Docker Compose, Tailscale Funnel |
| Application | Flutter/Dart, offline-first, français/anglais |
| Bot WhatsApp | Meta WhatsApp Business Cloud API |

---

## 📄 Licence

Projet de stage — ENIB / Cameroun 2026
