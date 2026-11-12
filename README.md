# Supervaize-ready agent template

[Version française](README.fr.md) · [Supervaize Studio](https://studio.supervaize.com) · [Documentation](https://docs.runwaize.com)

A working agent that already meets the eight Supervaize requirements: one entry point, a simple start form, one case per item with a cost per step, no secret in the code or the form (agent parameters), an idempotent start, background work with `job.sync` and `job.stop`, human review before completion, and isolation between Studio workspaces. Replace the demo logic in `agent.py` with yours; you should not need to touch `controller.py`.

| File | What it is |
|---|---|
| `agent.py` | **Your logic**: `list_items()` and `process_item()` |
| `controller.py` | Generic controller, no SDK needed, tested |
| `supervaizer_control.py` | SDK wiring: name, form, parameters, registration |
| `verify_agent.py` | Readiness check, never prints secrets |
| `tests/` | `python -m pytest -q` |
| `.env.example` | Variables to set |
| `requirements.txt` | Packages installed by the host (Render: `pip install -r requirements.txt`) |

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install supervaizer pytest
python -m pytest -q                    # 17 tests
supervaizer start --local              # try it without Studio
supervaizer login                      # writes the Studio variables to .env
python verify_agent.py                 # tells you what is missing
```

Then follow the guide "I already have an agent", from step 5.

## Customize

1. `supervaizer_control.py`: `AGENT_NAME`, `AGENT_SLUG` (slugified name), `CATALOG` (bump at every form change), `introduction`, `full_description`, parameters.
2. `controller.py` → `start_fields()` / `read_inputs()`: your start form and its server-side validation.
3. `agent.py`: your logic.

Hosting on Render: Web Service, Python 3, start command `SUPERVAIZER_PORT=$PORT python supervaizer_control.py`, variables from `.env` plus `SUPERVAIZER_PUBLIC_URL`, paid instance (the free one sleeps).

Built against Supervaizer 1.11.1 (November 2026).

## License

[Mozilla Public License 2.0](LICENSE.md), the same license as the Supervaizer SDK.
