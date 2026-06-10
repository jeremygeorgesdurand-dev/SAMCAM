# 🌦️ Système d'Alerte Météorologique du Cameroun

> Système d'alerte précoce basé sur l'IA pour les risques climatiques : outil utilisant des données météo et satellitaires pour prédire sécheresses, inondations ou vagues de chaleur, afin d'aider les autorités locales et les agriculteurs à anticiper les crises.

---

## 📁 Structure du projet

```
Cameroun-Systeme_alerte_meteorologique/
├── dashboard/
│   └── kribi-weather-dashboard.html   ← Dashboard météo multi-zones (V1)
├── README.md
```

---

## 🗺️ Dashboard météo multi-zones — V1

**Fichier :** `dashboard/kribi-weather-dashboard.html`

Interface web autonome (HTML/CSS/JS) pour la surveillance météo en temps réel de **8 zones** autour de Kribi.

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

### 📡 Variables météo affichées

- 🌡️ Température (°C)
- 💧 Humidité relative (%)
- 🌧️ Précipitations (mm)
- 💨 Vitesse et direction du vent (km/h, °)
- 📊 Pression atmosphérique (hPa)
- ☁️ Couverture nuageuse (%)

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
- [ ] **V3** — Historique des données et alertes automatiques
- [ ] **V4** — Modèle de prédiction IA (sécheresse, inondation, vague de chaleur)

---

## 📄 Licence

Projet de stage — ENIB / Cameroun 2026
