"""The SDK wiring loads and its answers fit the SDK contract. Fails when an SDK release breaks the template."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()  # before the import: the Store is created at import time
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supervaizer.contracts import V2ActionResult, V2SurfaceResult  # noqa: E402

import supervaizer_control as sc  # noqa: E402


def test_registration_matches_the_agent():
    assert sc.agent.slug == sc.AGENT_SLUG
    assert sc.app is not None


def test_surfaces_fit_the_sdk_contract():
    for name in (sc.SURFACE_START, sc.SURFACE_REVIEW):
        assert V2SurfaceResult.model_validate(sc.surface({"surface": name})).surface == name


def test_job_start_and_sync_fit_the_sdk_contract():
    req = {"job_id": "wiring-1", "mission_id": "m-1", "workspace": {"id": "ws-1"}}
    started = V2ActionResult.model_validate(sc.action({**req, "action": "job.start", "input": {"items": "one"}}))
    assert started.status == "ok" and started.job_state.job.agent_slug == sc.AGENT_SLUG
    synced = V2ActionResult.model_validate(sc.action({**req, "action": "job.sync"}))
    assert synced.status == "ok" and synced.job_state.cases
