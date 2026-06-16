# SAMCAM V3 — Serveur FastAPI REST

Serveur HTTP léger qui expose les rapports de risque climatique de SAMCAM via une API JSON.
Permet à l'application mobile (V5) et au dashboard HTML de consommer les données sans lire directement les fichiers locaux.

---

## Installation

```bash
# Depuis la racine du projet
pip install -r server/requirements.txt
```

---

## Démarrage

```bash
# Lancement simple (port 8000)
bash server/start.sh

# Mode développement (rechargement auto)
bash server/start.sh --dev

# Port personnalisé
PORT=9000 bash server/start.sh

# Directement avec uvicorn
uvicorn server.api:app --host 0.0.0.0 --port 8000
```

---

## Endpoints

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/health` | Statut du serveur + date du dernier rapport |
| `GET` | `/api/risk` | Dernier niveau d'alerte + indicateurs (réponse légère) |
| `GET` | `/api/meteo` | Météo actuelle + prévisions 7j (Open-Meteo) |
| `GET` | `/api/report` | Rapport complet : texte Phi-3, données brutes |
| `GET` | `/api/history?limit=30` | Historique des N derniers rapports |
| `GET` | `/dashboard/*` | Dashboard HTML servi statiquement |
| `GET` | `/docs` | Documentation Swagger auto-générée |
| `GET` | `/redoc` | Documentation ReDoc |

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

## Automatisation — Cron

Pour lancer la collecte + analyse toutes les 6h automatiquement :

```bash
# Installer le crontab
bash data_collection/scheduler_cron.sh

# Vérifier que le cron est actif
crontab -l

# Logs
tail -f logs/samcam_cron.log
```

---

## Accès réseau local

Le serveur écoute sur `0.0.0.0` → accessible depuis tous les appareils du réseau local :

```
Serveur   : http://[IP_DU_SERVEUR]:8000
Dashboard : http://[IP_DU_SERVEUR]:8000/dashboard/samcam-v4-dashboard.html
API risk  : http://[IP_DU_SERVEUR]:8000/api/risk
```

Trouver l'IP locale du serveur :
```bash
hostname -I | awk '{print $1}'
# ou
ip route get 1.1.1.1 | awk '{print $7; exit}'
```

---

## Prérequis

- Python 3.10+
- `fastapi`, `uvicorn` (voir `requirements.txt`)
- Un rapport `dashboard/latest_report.json` généré par le pipeline (`inference/pipeline_complet.py`)
- Ollama en fonctionnement avec le modèle `phi3:mini` pour la génération des rapports
