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

La solution repose sur une **architecture hybride** : le traitement principal n'est pas effectué sur le téléphone, mais sur un serveur local qui collecte les données, exécute le modèle d'analyse et expose une API à l'application mobile.

```
┌─────────────────────────────────────────────────────────────┐
│                      SOURCES DE DONNÉES                     │
│         API météo open source  ·  Données satellitaires     │
└────────────────────────────┬────────────────────────────────┘
                             │ Récupération périodique
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      SERVEUR LOCAL                          │
│  Collecte  →  Prétraitement  →  Modèle de risque  →  API   │
│  (sécheresse · inondation · vague de chaleur)               │
└────────────────────────────┬────────────────────────────────┘
                             │ API légère (JSON)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  APPLICATION MOBILE                         │
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
3. Le modèle d'analyse calcule un score ou un niveau de risque pour chaque aléa ciblé
4. Les résultats sont stockés puis transmis à l'application mobile sur demande via API
5. L'application affiche les alertes simplement et notifie l'utilisateur lorsqu'un seuil critique est dépassé

En cas de connexion limitée, l'application continue d'afficher les dernières informations synchronisées localement (**offline-first**), puis se met à jour dès que le réseau redevient disponible.

---

## 📁 Structure du projet

```
SAMCAM/
├── SAMCAM.pdf                          ← Document de présentation du projet
├── dashboard/
│   └── kribi-weather-dashboard.html   ← Dashboard météo multi-zones (V1)
└── README.md
```

---

## 🗺️ Dashboard météo multi-zones — V1

**Fichier :** `dashboard/kribi-weather-dashboard.html`

Interface web autonome (HTML/CSS/JS) pour la surveillance météo en temps réel de **8 zones** autour de Kribi. Ce dashboard constitue la base de visualisation qui évoluera vers l'interface de l'application finale.

### ✅ Fonctionnalités V1

| Fonctionnalité | Description |
|---|---|
| **Multi-zones** | 8 points d'observation couvrant toute la région de Kribi |
| **Sélection de zone** | Via liste latérale, menu déroulant ou clic sur la carte |
| **Carte interactive** | Carte OpenStreetMap avec marqueurs par zone (Leaflet.js) |
| **KPI régionaux** | Température moyenne, humidité, pluie max, vent max |
| **Résumé par zone** | Fiche détaillée de la zone active |
| **Graphiques horaires** | Température et précipitations/humidité sur 24h |
| **Tableau comparatif** | Synthèse des 8 zones côte à côte |
| **Mode clair/sombre** | Bascule via bouton en haut à gauche |
| **100% gratuit** | Source : Open-Meteo (pas de clé API requise) |
| **Responsive** | Adapté mobile et desktop |

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

### 🚀 Utilisation

Aucune installation requise. Ouvrir directement dans un navigateur :

```bash
# Option 1 — Ouvrir directement
open dashboard/kribi-weather-dashboard.html

# Option 2 — Serveur local simple (Python)
python3 -m http.server 8000
# Puis naviguer vers http://localhost:8000/dashboard/kribi-weather-dashboard.html
```

### 🔧 Technologies utilisées

- **Open-Meteo API** — Données météo gratuites, temps réel, sans clé API
- **Leaflet.js** — Carte interactive OpenStreetMap
- **Chart.js** — Graphiques horaires
- **Lucide Icons** — Icônes SVG
- **Satoshi (Fontshare)** — Typographie

---

## 🗺️ Roadmap

- [x] **V1** — Dashboard météo multi-zones (Open-Meteo)
- [ ] **V2** — Intégration images satellites (couverture nuageuse, pluie estimée, NDVI)
- [ ] **V3** — Serveur local : collecte automatisée, prétraitement, API REST
- [ ] **V4** — Modèle de classification de risque (sécheresse, inondation, vague de chaleur)
- [ ] **V5** — Application mobile (offline-first, notifications, historique)
- [ ] **V6** — Diffusion multi-canaux (push notifications, SMS / WhatsApp)

---

## 📄 Licence

Projet de stage — ENIB / Cameroun 2026
