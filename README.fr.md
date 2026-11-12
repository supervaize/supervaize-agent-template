# Modèle d'agent prêt pour Supervaize

[English version](README.md) · [Supervaize Studio](https://studio.supervaize.com) · [Documentation](https://docs.runwaize.com)

Un agent qui fonctionne et respecte déjà les huit exigences de Supervaize : un point d'entrée unique, un formulaire de lancement simple, un case par élément avec un coût par étape, aucun secret dans le code ni dans le formulaire (paramètres de l'agent), un lancement idempotent, le travail en arrière-plan avec `job.sync` et `job.stop`, une validation humaine avant la fin, et l'isolation entre espaces Studio. Remplacez la logique de démonstration dans `agent.py` par la vôtre ; vous ne devriez pas avoir à toucher `controller.py`.

| Fichier | Ce que c'est |
|---|---|
| `agent.py` | **Votre logique** : `list_items()` et `process_item()` |
| `controller.py` | Contrôleur générique, sans SDK, testé |
| `supervaizer_control.py` | Branchement au SDK : nom, formulaire, paramètres, enregistrement |
| `verify_agent.py` | Vérification avant branchement, n'affiche jamais de secret |
| `tests/` | `python -m pytest -q` |
| `.env.example` | Variables à renseigner |
| `requirements.txt` | Paquets installés par l'hébergeur (Render : `pip install -r requirements.txt`) |

## Démarrage

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell : .\.venv\Scripts\Activate.ps1
pip install supervaizer pytest
python -m pytest -q                    # 17 tests
supervaizer start --local              # essai sans Studio
supervaizer login                      # écrit les variables Studio dans .env
python verify_agent.py                 # indique ce qui manque
```

Puis suivez le guide « J'ai déjà un agent », à partir de l'étape 5.

## Personnaliser

1. `supervaizer_control.py` : `AGENT_NAME`, `AGENT_SLUG` (nom en minuscules avec tirets), `CATALOG` (à augmenter à chaque changement de formulaire), `introduction`, `full_description`, paramètres.
2. `controller.py` → `start_fields()` / `read_inputs()` : votre formulaire de lancement et sa vérification côté serveur.
3. `agent.py` : votre logique.

Héberger sur Render : Web Service, Python 3, commande de démarrage `SUPERVAIZER_PORT=$PORT python supervaizer_control.py`, variables de `.env` plus `SUPERVAIZER_PUBLIC_URL`, instance payante (la gratuite se met en veille).

Écrit pour Supervaizer 1.11.1 (novembre 2026).

## Licence

[Mozilla Public License 2.0](LICENSE.md), la même licence que le SDK Supervaizer.
