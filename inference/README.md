# SAMCAM — Module d'inférence Phi-3 mini

## Prérequis

1. **Ollama installé** : https://ollama.com
2. **Phi-3 mini téléchargé** :
   ```bash
   ollama pull phi3:mini
   ollama serve   # si pas déjà en cours
   ```
3. **Un fichier JSON collecté** dans `data/` :
   ```bash
   python3 data_collection/collect_kribi.py
   ```

## Analyser les données du jour

```bash
# Analyse simple (affichage temps réel)
python3 inference/analyser_kribi.py

# Analyser un fichier spécifique
python3 inference/analyser_kribi.py --fichier data/kribi_2026-06-15.json

# Mode silencieux (pipeline automatisé)
python3 inference/analyser_kribi.py --json-only
```

## Pipeline complet en une commande

```bash
python3 inference/pipeline_complet.py
```

Exécute automatiquement :
1. `collect_kribi.py` — collecte les données
2. `analyser_kribi.py` — analyse avec Phi-3 mini

## Fichiers générés

```
reports/
  rapport_kribi_2026-06-15.txt   — rapport texte lisible
  rapport_kribi_2026-06-15.json  — rapport structuré (pour dashboard)
```

## Exemple de sortie attendue

```
════════════════════════════════════════════════════════════
RAPPORT SAMCAM — Phi-3 mini
════════════════════════════════════════════════════════════

1. RÉSUMÉ EXÉCUTIF
La zone de Kribi se trouve actuellement en saison des pluies...

2. ANALYSE DES RISQUES
- Inondation : risque élevé en raison de...
...

5. NIVEAU D'ALERTE GÉNÉRAL : 🟡 JAUNE
```

## Paramètres Phi-3 (dans analyser_kribi.py)

| Paramètre | Valeur | Rôle |
|-----------|--------|------|
| `temperature` | 0.3 | Réponses factuelles (0=déterministe, 1=créatif) |
| `top_p` | 0.9 | Diversité du vocabulaire |
| `num_predict` | 1024 | Longueur maximale du rapport |
