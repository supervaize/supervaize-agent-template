# Supervaize-ready agent template / Modèle d'agent prêt pour Supervaize

**EN** — A working agent that already meets the eight Supervaize requirements: one entry point, a simple start form, one case per item with a cost per step, no secret in the code or the form (agent parameters), an idempotent start, background work with `job.sync` and `job.stop`, human review before completion, and isolation between Studio workspaces. Replace the demo logic in `agent.py` with yours; you should not need to touch `controller.py`.

**FR** — Un agent qui fonctionne et respecte déjà les huit exigences de Supervaize : un point d'entrée unique, un formulaire de lancement simple, un case par élément avec un coût par étape, aucun secret dans le code ni dans le formulaire (paramètres de l'agent), un lancement idempotent, le travail en arrière-plan avec `job.sync` et `job.stop`, une validation humaine avant la fin, et l'isolation entre espaces Studio. Remplacez la logique de démonstration dans `agent.py` par la vôtre ; vous ne devriez pas avoir à toucher `controller.py`.

| File / Fichier | What it is / Ce que c'est |
|---|---|
| `agent.py` | **Your logic / Votre logique** : `list_items()` and `process_item()` |
| `controller.py` | Generic controller, no SDK needed, tested / Contrôleur générique, sans SDK, testé |
| `supervaizer_control.py` | SDK wiring: name, form, parameters, registration / Branchement au SDK |
| `verify_agent.py` | Readiness check, never prints secrets / Vérification avant branchement, n'affiche jamais de secret |
| `tests/` | `python -m pytest -q` |
| `.env.example` | Variables to set / Variables à renseigner |
| `requirements.txt` | Packages installed by the host (Render: `pip install -r requirements.txt`) / Paquets installés par l'hébergeur |

## Quick start / Démarrage

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install supervaizer pytest
python -m pytest -q                    # 13 tests
supervaizer start --local              # try it without Studio
supervaizer login                      # writes the Studio variables to .env
python verify_agent.py                 # tells you what is missing
```

Then follow the guide "I already have an agent", from step 5 / Puis suivez le guide « J'ai déjà un agent », à partir de l'étape 5.

## Customize / Personnaliser

1. `supervaizer_control.py`: `AGENT_NAME`, `AGENT_SLUG` (slugified name / nom en minuscules avec tirets), `CATALOG` (bump at every form change / à augmenter à chaque changement de formulaire), `introduction`, `full_description`, parameters.
2. `controller.py` → `start_fields()` / `read_inputs()`: your start form and its server-side validation / votre formulaire et sa vérification côté serveur.
3. `agent.py`: your logic / votre logique.

Hosting on Render / Héberger sur Render: Web Service, Python 3, start command `SUPERVAIZER_PORT=$PORT python supervaizer_control.py`, variables from `.env` plus `SUPERVAIZER_PUBLIC_URL`, paid instance (the free one sleeps).

Built against Supervaizer 1.11.1 (November 2026). / Écrit pour Supervaizer 1.11.1 (novembre 2026).
