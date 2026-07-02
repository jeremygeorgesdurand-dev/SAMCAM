# 🌦️ SAMCAM — Système d'Alerte Météorologique du Cameroun

> Prototype de système d'alerte climatique précoce pour smartphone, appuyé par un serveur local hébergeant le modèle d'analyse. Le système exploite des données météorologiques et satellitaires open source pour estimer des risques de sécheresse, d'inondation et de vague de chaleur, afin d'aider les autorités locales, les habitants et les agriculteurs au Cameroun.

---

## 📄 Document de projet

Le document de présentation complet du projet est disponible ici : [`SAMCAM.pdf`](./SAMCAM.pdf)

---

## 🎯 Contexte et problématique

Le Cameroun est exposé à plusieurs aléas climatiques majeurs : inondations en saison de fortes pluies, sécheresses affectant l'agriculture, et vagues de chaleur. Ces phénomènes ont des conséquences directes sur les populations, les exploitations agricoles, les infrastructures locales et l'organisation des services publics.

La problématique adressée : **comment concevoir un système d'alerte météorologique léger, accessible sur smartphone, capable d'exploiter des données météorologiques et satellitaires pour estimer des risques climatiques, tout en restant utilisable dans un contexte de connectivité limitée ?**

---

## 🏗️ Architecture du système

La solution repose sur une **architecture hybride** : le traitement principal n'est pas effectué sur le téléphone, mais sur un serveur local qui collecte les données, exécute le modèle d'analyse et expose une API REST à l'application mobile.

```
┌─────────────────────────────────────────────────────────────┐
│                      SOURCES DE DONNÉES                     │
│         API météo open source  ·  Données satellitaires     │
└────────────────────────────┬────────────────────────────────┘
                             │ Récupération automatique (cron toutes les 6h)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      SERVEUR LOCAL                          │
│  Collecte  →  Prétraitement  →  GradientBoosting  →  API   │
│  (sécheresse · inondation · vague de chaleur)               │
│  FastAPI · uvicorn · port 8000                              │
└────────────────────────────┬────────────────────────────────┘
                             │ API JSON légère
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  APPLICATION MOBILE (V5)                    │
│  Alertes · Niveau de risque · Carte · Historique local      │
│  Mode offline-first : cache local si réseau indisponible    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Objectifs du projet

- **Exploiter** des données météorologiques et satellitaires open source pertinentes pour le contexte camerounais
- **Concevoir** un modèle d'analyse léger capable d'attribuer un niveau de risque simple (faible / modéré / élevé) pour les inondations, sécheresses et vagues de chaleur
- **Héberger** ce modèle sur un serveur local afin de centraliser les traitements et de faciliter les mises à jour
- **Développer** une application mobile capable d'interroger ce serveur pour récupérer alertes, résumés et historique
- **Limiter** les échanges réseau au strict nécessaire pour un fonctionnement acceptable en cas de faible connectivité

---

## ⚙️ Fonctionnement du prototype

1. Le serveur local récupère à intervalles réguliers des données météorologiques et satellitaires open source
2. Ces données sont nettoyées et transformées en indicateurs exploitables
3. Le modèle **GradientBoosting** (scikit-learn, V4) calcule un niveau de risque J0/J+3/J+7 pour inondation, sécheresse et vague de chaleur
4. Les résultats sont exposés à l'application mobile via une API REST légère
5. L'application affiche les alertes simplement et notifie l'utilisateur lorsqu'un seuil critique est dépassé

En cas de connexion limitée, l'application continue d'afficher les dernières informations synchronisées localement (**offline-first**), puis se met à jour dès que le réseau redevient disponible.

> **Fallback** : si les modèles `.pkl` sont absents, le serveur revient automatiquement sur Phi-3 mini via Ollama (comportement V3).

---

## 📁 Structure du projet

```
SAMCAM/
├── SAMCAM.pdf                              ← Document de présentation
├── README.md
│
├── data_collection/
│   ├── collect_kribi.py                    ← Collecte Open-Meteo + GEE + NASA POWER
│   ├── scheduler.sh                        ← Scheduler shell (manuel)
│   ├── scheduler_cron.sh                   ← Installation du cron automatique (V3)
│   └── requirements.txt
│
├── inference/
│   ├── build_dataset.py                    ← Construction dataset historique (V4.6.1)
│   ├── train_model.py                      ← Entraînement GradientBoosting multi-horizon (V4.4)
│   ├── risk_model.py                       ← Inférence ML (chargement .pkl + prédiction)
│   ├── analyser_kribi.py                   ← Analyse Phi-3 mini via Ollama (fallback)
│   ├── pipeline_complet.py                 ← Orchestration collecte → analyse → JSON
│   └── requirements_v4.txt
│
├── models/                                 ← [V4] Modèles entraînés
│   ├── model_inondation.pkl                ← J0  (AUC=0.942, F1=0.804)
│   ├── model_inondation_j1.pkl             ← J+1 (AUC=0.884)
│   ├── model_inondation_j3.pkl             ← J+3 (AUC=0.887)
│   ├── model_inondation_j7.pkl             ← J+7 (AUC=0.862)
│   ├── model_secheresse.pkl                ← J0  (AUC=0.940, F1=0.732)
│   ├── model_secheresse_j1.pkl             ← J+1 (AUC=0.897)
│   ├── model_secheresse_j3.pkl             ← J+3 (AUC=0.898)
│   ├── model_secheresse_j7.pkl             ← J+7 (AUC=0.891)
│   ├── model_metadata.json                 ← Métadonnées entraînement (V4.4)
│   └── evaluate_model.py                   ← Script d'évaluation
│
├── server/                                 ← [V4] Serveur API REST
│   ├── api.py                              ← FastAPI V4 : ML branché sur /api/risk
│   ├── start.sh                            ← Script de lancement
│   ├── requirements.txt                    ← fastapi, uvicorn
│   └── README.md
│
├── dashboard/
│   ├── kribi-weather-dashboard.html        ← Dashboard météo multi-zones (V1)
│   ├── samcam-v4-dashboard.html            ← Dashboard risques + météo (V4)
│   └── latest_report.json                 ← Dernier rapport (généré par pipeline)
│
├── data/                                   ← Données collectées (kribi_YYYY-MM-DD.json)
├── reports/                                ← Rapports générés (rapport_kribi_*.json/txt)
└── logs/                                   ← Logs cron (samcam_cron.log)
```

---

## 🚀 Démarrage rapide — V4

### 1. Prérequis

```bash
# Dépendances collecte + analyse
pip install -r data_collection/requirements.txt

# Dépendances ML V4
pip install -r inference/requirements_v4.txt

# Dépendances serveur
pip install -r server/requirements.txt

# (Optionnel) Ollama + Phi-3 mini — fallback si modèles ML absents
ollama pull phi3:mini
```

### 2. Construire le dataset et entraîner les modèles

```bash
# Dataset historique 1984→2024 (vraies données Open-Meteo)
python3 inference/build_dataset.py --openmeteo

# Entraînement tous horizons (J0, J+1, J+3, J+7)
python3 inference/train_model.py --all-horizons

# Évaluation
python3 models/evaluate_model.py
```

### 3. Lancer le pipeline et le serveur

```bash
# Collecte + génération latest_report.json
python3 inference/pipeline_complet.py

# Démarrer le serveur
bash server/start.sh
# Serveur  : http://localhost:8000
# API risk : http://localhost:8000/api/risk   ← scores ML J0/J+3/J+7
# Dashboard: http://localhost:8000/dashboard/samcam-v4-dashboard.html
# API docs : http://localhost:8000/docs
```

### 4. Activer la collecte automatique (cron toutes les 6h)

```bash
bash data_collection/scheduler_cron.sh
# Logs : tail -f logs/samcam_cron.log
```

---

## 🌐 API REST — Endpoints

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/health` | Statut + modèle ML chargé + date du dernier rapport |
| `GET` | `/api/risk` | Scores ML J0/J+3/J+7 + niveau d'alerte global |
| `GET` | `/api/meteo` | Météo actuelle + prévisions 7j |
| `GET` | `/api/report` | Rapport complet |
| `GET` | `/api/history?limit=30` | Historique des N derniers rapports |
| `GET` | `/dashboard/*` | Dashboard HTML (fichiers statiques) |
| `GET` | `/docs` | Documentation Swagger interactive |

### Exemple de réponse `/api/risk` (V4)

```json
{
  "date": "2026-07-02",
  "zone": "Kribi",
  "niveau_alerte": "JAUNE",
  "methode_risque": "ml_gradient_boosting",
  "risque_actuel": {
    "scores": { "inondation": 0.38, "secheresse": 0.12, "chaleur": 0.05 },
    "niveau_alerte": "JAUNE"
  },
  "risque_prevu_3j": {
    "scores": { "inondation": 0.45, "secheresse": 0.10, "chaleur": 0.04 },
    "niveau_alerte": "ORANGE"
  },
  "risque_prevu_7j": {
    "scores": { "inondation": 0.52, "secheresse": 0.09, "chaleur": 0.04 },
    "niveau_alerte": "ORANGE"
  },
  "indicateurs": {
    "pluie_cumulee_7j_mm": 142.5,
    "pluie_prevue_7j_mm": 98.2,
    "ndvi_moyen": 0.712
  },
  "capteur": "Open-Meteo"
}
```

---

## 🗺️ Dashboard météo multi-zones — V1

**Fichier :** `dashboard/kribi-weather-dashboard.html`

Interface web autonome (HTML/CSS/JS) pour la surveillance météo en temps réel de **8 zones** autour de Kribi.

### 🗺️ Zones couvertes

| Zone | Latitude | Longitude |
|---|---|---|
| Kribi Centre | 2.9397 | 9.9132 |
| Kribi Port | 2.9500 | 9.9200 |
| Campo | 2.3667 | 9.8167 |
| Bipindi | 3.0833 | 10.4167 |
| Lokoundjé | 3.1167 | 10.3000 |
| Akom II | 3.0000 | 10.5833 |
| Lolodorf | 3.2333 | 10.7333 |
| Ebolowa | 2.9000 | 11.1500 |

---

## 🗺️ Roadmap

- [x] **V1** — Dashboard météo multi-zones (Open-Meteo)
- [x] **V2** — Intégration images satellites (Sentinel-2, MODIS, SMAP) + indicateurs de risque
- [x] **V3** — Serveur local FastAPI : collecte automatisée (cron), API REST, dashboard servi
- [x] **V4** — Modèle de classification de risque (GradientBoosting, scikit-learn, 40 ans de données)
  - Dataset historique 1984→2024 (2139 semaines, vraies données Open-Meteo + 47 événements catalogués)
  - 8 modèles entraînés : inondation + sécheresse × J0/J+1/J+3/J+7
  - AUC > 0.86 sur tous les horizons, split temporel strict (train<2020, test≥2020)
  - Branchement ML dans `server/api.py` avec fallback Phi-3 mini
  - Fix `label_chaleur` : anomalie thermique relative (V4.6.1)
- [ ] **V5** — Application mobile Flutter (offline-first, notifications, historique)
- [ ] **V6** — Diffusion multi-canaux (push notifications, SMS / WhatsApp)

---

## 🔧 Technologies

| Couche | Technologie |
|---|---|
| Collecte météo | Open-Meteo API, NASA POWER |
| Satellite | Google Earth Engine (Sentinel-2, MODIS, SMAP) |
| Modèle ML | GradientBoostingClassifier (scikit-learn), multi-horizon J0/J+1/J+3/J+7 |
| Analyse LLM (fallback) | Phi-3 mini via Ollama |
| Serveur API | FastAPI + uvicorn |
| Dashboard | HTML/CSS/JS, Leaflet.js, Chart.js |
| Automatisation | cron, bash |

---

## 📄 Licence

Projet de stage — ENIB / Cameroun 2026
