"""Entry point: exposes the agent to Supervaize Studio (Supervaizer v2 contract, SDK 1.11).

Start it with one of these commands (both register the agent with Studio):
    supervaizer start --env-file .env --public-url https://your-public-address
    python supervaizer_control.py
Do NOT start it with `uvicorn` alone: the agent would answer but never appear in Studio.

Configuration: see .env.example. `supervaizer login` writes the Studio variables for you.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Load .env first: the SDK reads its variables when the server is created.
_env = Path(__file__).resolve().parent / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from supervaizer import Account, Agent, Parameter, ParametersSetup, Server  # noqa: E402
from supervaizer.contracts import build_v2_agent_registration  # noqa: E402

import agent as my_agent  # noqa: E402
from controller import ACTION_REVIEW, SURFACE_REVIEW, SURFACE_START, Controller  # noqa: E402

VERSION = "0.1.0"
AGENT_NAME = "My Agent"          # change it; the slug below must stay its slugified form
AGENT_SLUG = "my-agent"
CATALOG = "my-agent-ui.1"        # bump (…ui.2, …ui.3) every time a form changes

agent = Agent(
    name=AGENT_NAME,
    version=VERSION,
    author="Your name",
    description="Describe what your agent does in one sentence.",
    tags=["template"],
    introduction={
        "tagline": "One line that says what the agent does",
        "summary": "What the agent does, in one or two sentences.",
        "example_goals": ["Process these items", "Summarize this list"],
    },
    full_description={"format": "markdown",
                      "content": "## What it does\n\nDescribe inputs, outputs, costs and what needs human approval."},
    # The agent's own settings: filled in once by a workspace admin in Studio, never in the start form.
    # is_environment=True puts the value in os.environ, so code that reads os.environ keeps working.
    parameters_setup=ParametersSetup.from_list([
        Parameter(name="AI_API_KEY", description="Your AI provider key (optional for the demo)",
                  is_secret=True, is_required=False, is_environment=True),
    ]),
    supervaizer_v2_registration=build_v2_agent_registration(
        agent_slug=AGENT_SLUG,
        display_name=AGENT_NAME,
        a2ui_catalog_version=CATALOG,
        surfaces=[SURFACE_START, SURFACE_REVIEW],
        actions=["job.start", "job.sync", "job.stop", ACTION_REVIEW],
        case_lanes=[{"id": "run", "label": "Run", "default": True}, {"id": "items", "label": "Items"}],
        job_policy={"sync": {"action": "job.sync",
                             "supported_statuses": ["active", "awaiting", "completed", "failed"]}},
    ),
)

account = Account(
    workspace_id=os.getenv("SUPERVAIZE_WORKSPACE_ID") or "dummy_workspace_id",
    api_key=os.getenv("SUPERVAIZE_API_KEY") or "dummy_api_key",
    api_url=os.getenv("SUPERVAIZE_API_URL") or "https://app.supervaize.com",
)
server = Server(agents=[agent], a2a_endpoints=True, supervisor_account=account)
controller = Controller(AGENT_SLUG, CATALOG, my_agent.list_items, my_agent.process_item)


def _as_dict(request: Any) -> dict:
    return request if isinstance(request, dict) else request.model_dump(mode="python", by_alias=True)


def surface(request: Any) -> dict:
    return controller.surface(_as_dict(request))


def action(request: Any) -> dict:
    return controller.action(_as_dict(request))


for _s in (SURFACE_START, SURFACE_REVIEW):
    server.register_v2_surface(_s, surface, agent_slug=agent.slug)
for _a in ("job.start", "job.sync", "job.stop", ACTION_REVIEW):
    server.register_v2_action(_a, action, agent_slug=agent.slug)

assert agent.slug == AGENT_SLUG, f"unexpected slug: {agent.slug} (update AGENT_SLUG)"

app = server.app

if __name__ == "__main__":
    server.launch(log_level="INFO")
