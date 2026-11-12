"""Tests of the generic controller, without the SDK and without Studio: python -m pytest -q"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent as demo  # noqa: E402
from controller import ACTION_REVIEW, Controller, Store  # noqa: E402


def make(tmp_path, process=demo.process_item):
    return Controller("my-agent", "my-agent-ui.1", demo.list_items, process, store=Store(tmp_path))


def start(c, items="first line\nsecond line", job="job-1", ws="ws-1", key=None):
    return c.action({"action": "job.start", "job_id": job, "mission_id": "m-1", "workspace": {"id": ws},
                     "idempotency_key": key, "input": {"items": items}})


def wait(c, job="job-1", ws="ws-1", until=("awaiting", "failed", "completed")):
    for _ in range(200):
        r = c.action({"action": "job.sync", "job_id": job, "workspace": {"id": ws}})
        if r["job_state"]["job"]["status"] in until:
            return r["job_state"]
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_start_form_has_no_secret_and_valid_fields(tmp_path):
    doc = make(tmp_path).surface({"surface": "job.start"})["document"]
    assert doc["type"] == "Form" and doc["submit"]["action"] == "job.start"
    assert all("key" not in f["id"].lower() for f in doc["fields"])


def test_job_runs_in_background_one_case_per_item_with_costs(tmp_path):
    c = make(tmp_path)
    r = start(c)
    assert r["status"] == "ok" and r["job_state"]["job"]["status"] in ("active", "awaiting")
    state = wait(c)
    items = [x for x in state["cases"] if x["lane"] == "items"]
    assert len(items) == 2 and all(x["status"] == "completed" for x in items)
    assert all("cost" in s for x in state["cases"] for s in x["steps"])
    assert "total_cost" in state["job"]["information"]["cost"]
    assert state["job"]["status"] == "awaiting"


def test_one_failing_item_does_not_stop_the_others(tmp_path):
    c = make(tmp_path)
    start(c, items="ok line\nfail here\nanother ok")
    state = wait(c)
    statuses = sorted(x["status"] for x in state["cases"] if x["lane"] == "items")
    assert statuses == ["completed", "completed", "failed"]


def test_start_is_idempotent_and_detects_conflicts(tmp_path):
    c = make(tmp_path)
    a = start(c, key="k1")
    b = start(c, key="k1")
    assert a is b
    conflict = start(c, items="something else", key="k1")
    assert conflict["status"] == "error" and conflict["errors"][0]["code"] == "idempotency_conflict"


def test_invalid_input_is_rejected_on_the_server(tmp_path):
    r = start(make(tmp_path), items="   ")
    assert r["status"] == "error"


def test_human_review_approve_and_double_click(tmp_path):
    c = make(tmp_path)
    start(c)
    wait(c)
    req = {"action": ACTION_REVIEW, "job_id": "job-1", "workspace": {"id": "ws-1"}, "input": {"decision": "approve"}}
    r = c.action(req)
    assert r["job_state"]["job"]["status"] == "completed"
    assert c.action(req)["job_state"]["job"]["status"] == "completed"


def test_human_review_reject(tmp_path):
    c = make(tmp_path)
    start(c)
    wait(c)
    r = c.action({"action": ACTION_REVIEW, "job_id": "job-1", "workspace": {"id": "ws-1"},
                  "input": {"decision": "reject"}})
    assert r["job_state"]["job"]["status"] == "failed"


def test_stop_interrupts_the_run(tmp_path):
    def slow(item):
        time.sleep(0.05)
        return {"ok": True}, 0.0
    c = make(tmp_path, process=slow)
    start(c, items="\n".join(f"line {i}" for i in range(40)))
    c.action({"action": "job.stop", "job_id": "job-1", "workspace": {"id": "ws-1"}})
    state = wait(c, until=("failed",))
    done = [x for x in state["cases"] if x["lane"] == "items" and x["status"] == "completed"]
    assert len(done) < 40


def test_a_workspace_only_sees_its_own_jobs(tmp_path):
    c = make(tmp_path)
    start(c)
    wait(c)
    r = c.action({"action": "job.sync", "job_id": "job-1", "workspace": {"id": "another-ws"}})
    assert r["status"] == "error"


def test_a_request_with_no_workspace_does_not_see_a_workspace_job(tmp_path):
    c = make(tmp_path)
    start(c)
    wait(c)
    assert c.action({"action": "job.sync", "job_id": "job-1"})["status"] == "error"


def test_a_retried_start_after_a_restart_does_not_run_twice(tmp_path):
    calls = []

    def count(item):
        calls.append(item["id"])
        return {}, 0.0
    first = make(tmp_path, process=count)
    a = start(first, key="k1")
    wait(first)
    done = len(calls)
    fresh = make(tmp_path, process=count)
    b = start(fresh, key="k1")
    assert b["effects"] == a["effects"] and len(calls) == done
    assert start(fresh, items="something else", key="k1")["errors"][0]["code"] == "idempotency_conflict"


def test_a_job_running_during_a_restart_is_closed_as_failed(tmp_path):
    release = threading.Event()

    def blocked(item):
        release.wait(5)
        return {}, 0.0
    start(make(tmp_path, process=blocked))  # the worker of this controller never reports before the "restart"
    try:
        fresh = make(tmp_path)
        state = fresh.action({"action": "job.sync", "job_id": "job-1", "workspace": {"id": "ws-1"}})["job_state"]
        assert state["job"]["status"] == "failed"
        assert "restart" in state["cases"][0]["steps"][-1]["title"]
    finally:
        release.set()


def test_finished_jobs_survive_a_restart(tmp_path):
    c = make(tmp_path)
    start(c)
    wait(c)
    fresh = make(tmp_path)
    r = fresh.action({"action": "job.sync", "job_id": "job-1", "workspace": {"id": "ws-1"}})
    assert r["job_state"]["job"]["status"] == "awaiting"
