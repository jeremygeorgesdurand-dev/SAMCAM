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
│  Collecte  →  Prétraitement  →  Phi-3 mini  →  API REST    │
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
3. Le modèle Phi-3 mini (via Ollama) calcule un niveau de risque et génère un rapport en langage naturel
4. Les résultats sont stockés puis exposés à l'application mobile via une API REST légère
5. L'application affiche les alertes simplement et notifie l'utilisateur lorsqu'un seuil critique est dépassé

En cas de connexion limitée, l'application continue d'afficher les dernières informations synchronisées localement (**offline-first**), puis se met à jour dès que le réseau redevient disponible.

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
│   ├── analyser_kribi.py                   ← Analyse Phi-3 mini via Ollama
│   ├── pipeline_complet.py                 ← Orchestration collecte → analyse → JSON
│   └── README.md
│
├── server/                                 ← [V3] Serveur API REST
│   ├── api.py                              ← FastAPI : endpoints /risk /meteo /report /history
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

## 🚀 Démarrage rapide — V3

### 1. Prérequis

```bash
# Dépendances collecte + analyse
pip install -r data_collection/requirements.txt

# Dépendances serveur
pip install -r server/requirements.txt

# Ollama + Phi-3 mini (pour la génération des rapports)
ollama pull phi3:mini
```

### 2. Lancer le pipeline une première fois

```bash
python3 inference/pipeline_complet.py
# → Collecte, analyse, génère dashboard/latest_report.json
```

### 3. Démarrer le serveur API

```bash
bash server/start.sh
# Serveur disponible sur http://localhost:8000
# Dashboard : http://localhost:8000/dashboard/samcam-v4-dashboard.html
# API docs  : http://localhost:8000/docs
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
| `GET` | `/health` | Statut + date du dernier rapport |
| `GET` | `/api/risk` | Niveau d'alerte + indicateurs (léger) |
| `GET` | `/api/meteo` | Météo actuelle + prévisions 7j |
| `GET` | `/api/report` | Rapport complet avec texte Phi-3 |
| `GET` | `/api/history?limit=30` | Historique des N derniers rapports |
| `GET` | `/dashboard/*` | Dashboard HTML (fichiers statiques) |
| `GET` | `/docs` | Documentation Swagger interactive |

### Exemple de réponse `/api/risk`

```json
{
  "date": "2026-06-16",
  "zone": "Kribi",
  "niveau_alerte": "JAUNE",
  "indicateurs": {
    "pluie_cumulee_7j_mm": 142.5,
    "pluie_prevue_7j_mm": 98.2,
    "ndvi_moyen": 0.712,
    "risque_inondation_observe": "modéré",
    "risque_secheresse": "faible"
  },
  "capteur": "Sentinel-2"
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
- [ ] **V4** — Modèle de classification de risque formalisé (scikit-learn, données historiques)
- [ ] **V5** — Application mobile Flutter (offline-first, notifications, historique)
- [ ] **V6** — Diffusion multi-canaux (push notifications, SMS / WhatsApp)

---

## 🔧 Technologies

| Couche | Technologie |
|---|---|
| Collecte météo | Open-Meteo API, NASA POWER |
| Satellite | Google Earth Engine (Sentinel-2, MODIS, SMAP) |
| Analyse IA | Phi-3 mini via Ollama |
| Serveur API | FastAPI + uvicorn |
| Dashboard | HTML/CSS/JS, Leaflet.js, Chart.js |
| Automatisation | cron, bash |

---

## 📄 Licence

Projet de stage — ENIB / Cameroun 2026
