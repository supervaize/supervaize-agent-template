"""Generic Supervaizer v2 controller, independent of the SDK (testable on its own).

Mapping (change it to match your agent, see "Missions, Jobs, Cases, Steps" in the docs):
  Job              = one run started from the Studio form
  Case "Run" (lane "run")     = the run itself: preparation, processing, then human approval
  Cases "Items" (lane "items") = one per processed item, with its own step, status and cost

What it already handles, so you don't have to:
  - job.start is idempotent (same idempotency_key = same result; same key with other input = conflict)
  - the work runs in the background; job.sync returns the latest state; job.stop stops the run
  - one failing item does not stop the others
  - a human approves (or rejects) the run before it is marked completed
  - a Studio workspace only sees its own jobs
  - state is written to DATA_DIR/<job>/state.json so a restart does not lose finished jobs;
    a job that was running during the restart is closed as failed, and a retried start is not run twice
Wire it to the SDK in supervaizer_control.py.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("agent")

SURFACE_START = "job.start"
SURFACE_REVIEW = "case.step.awaiting"
ACTION_REVIEW = "step.awaiting.submit"
MAX_ITEMS = 200

ListItems = Callable[[dict], list[dict]]
ProcessItem = Callable[[dict], tuple[dict, float]]


def start_fields() -> list[dict]:
    """The Studio start form. Same field types as in "Build Your Controller". No secrets here."""
    return [
        {"id": "items", "label": "Items to process (one per line)", "type": "text", "multiline": True,
         "min_rows": 3, "required": True,
         "description": "Each line becomes one case in Studio.",
         "validation": {"min_length": 1, "max_length": 20000, "message": "At least one line"}},
    ]


def read_inputs(raw: dict) -> dict:
    """Validate again on the server: Studio validates for the operator, the action must validate too."""
    items = str(raw.get("items") or "")
    lines = [line for line in items.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Items: at least one non-empty line")
    if len(lines) > MAX_ITEMS:
        raise ValueError(f"Items: {MAX_ITEMS} lines at most")
    return {"items": items}


def review_fields() -> list[dict]:
    return [
        {"id": "decision", "label": "Decision", "type": "select", "required": True, "default": "approve",
         "options": [{"value": "approve", "label": "Approve"}, {"value": "reject", "label": "Reject"}]},
        {"id": "comment", "label": "Comment", "type": "text", "multiline": True},
    ]


class Store:
    """Job states in memory, copied to DATA_DIR/<job>/state.json (use a persistent disk in production)."""

    def __init__(self, folder: str | Path | None = None):
        self.folder = Path(folder or os.environ.get("DATA_DIR") or Path(__file__).resolve().parent / "data")
        self.folder.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, dict] = {}
        self.starts_file = self.folder / "starts.json"
        # idempotency key -> [input fingerprint, first result]; on disk, so a retry after a restart starts nothing
        self.starts: dict[str, list] = (
            json.loads(self.starts_file.read_text(encoding="utf-8")) if self.starts_file.exists() else {})
        self.stopped: set[str] = set()
        self.lock = threading.RLock()

    def remember_start(self, key: str, fingerprint: str, result: dict) -> None:
        with self.lock:
            self.starts[key] = [fingerprint, result]
            self.starts_file.write_text(json.dumps(self.starts, ensure_ascii=False, default=str), encoding="utf-8")

    def read(self, job_id: str) -> dict | None:
        with self.lock:
            f = self.folder / job_id / "state.json"
            if job_id not in self.jobs and f.exists():
                state = json.loads(f.read_text(encoding="utf-8"))
                # Read from disk = started by an earlier process. If it is still "active", its worker is gone.
                # ponytail: assumes one process per DATA_DIR; with several, keep the work in a shared queue instead.
                if state["job"]["status"] == "active":
                    self.write(job_id, _interrupted(state))
                else:
                    self.jobs[job_id] = state
            return self.jobs.get(job_id)

    def write(self, job_id: str, state: dict) -> None:
        with self.lock:
            self.jobs[job_id] = state
            d = self.folder / job_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "state.json").write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")


def snapshot(job_id: str, mission_id: str, agent_slug: str, cases: list[dict], status: str, info: dict) -> dict:
    total = round(sum(s.get("cost", 0) for c in cases for s in c.get("steps", [])), 6)
    return {"job": {"id": job_id, "agent_slug": agent_slug, "mission_id": mission_id, "status": status,
                    "source": {"type": "fresh_start"},
                    "information": {"cost": {"total_cost": total}, **info}},
            "cases": cases}


def _interrupted(state: dict) -> dict:
    """Close a job whose worker was lost in a restart, so the operator does not wait for it forever."""
    run = next(c for c in state["cases"] if c["lane"] == "run")
    for step in run["steps"]:
        if step["status"] == "active":
            step["status"] = "failed"
    run["steps"].append({"id": f"{state['job']['id']}-run-interrupted", "activity": "operation",
                         "status": "completed", "title": "Interrupted by a restart — start a new run", "cost": 0.0})
    run["status"] = state["job"]["status"] = "failed"
    return state


class Controller:
    def __init__(self, agent_slug: str, catalog_version: str, list_items: ListItems, process_item: ProcessItem,
                 store: Store | None = None, workers: int = 2):
        self.slug = agent_slug
        self.catalog = catalog_version
        self.list_items = list_items
        self.process_item = process_item
        self.store = store or Store()
        self.pool = ThreadPoolExecutor(max_workers=workers)

    # ------------------------------------------------------------ surfaces
    def surface(self, req: dict) -> dict:
        name = req.get("surface") or SURFACE_START
        if name == SURFACE_REVIEW:
            doc = {"type": "Form", "title": "Review the run", "fields": review_fields(),
                   "submit": {"action": ACTION_REVIEW, "label": "Save my decision"},
                   "state": {"case_id": req.get("case_id"), "step_id": req.get("step_id")}}
        else:
            doc = {"type": "Form", "title": "Start a run", "fields": start_fields(),
                   "submit": {"action": "job.start", "label": "Start"}}
        return {"surface": name, "a2ui_catalog_version": self.catalog, "document": doc}

    # ------------------------------------------------------------ actions
    def action(self, req: dict) -> dict:
        name = req.get("action") or ""
        try:
            if name == "job.start":
                return self._start(req)
            if name == "job.sync":
                state = self._allowed(_job_id(req), req)
                return _ok("job.synced", job_state=state) if state else _error("job.sync.failed", message="unknown job")
            if name == "job.stop":
                return self._stop(req)
            if name == ACTION_REVIEW:
                return self._review(req)
        except ValueError as e:
            return _error(f"{name}.failed", message=str(e))
        return _error("action.unsupported", action=name)

    def _start(self, req: dict) -> dict:
        raw = req.get("input") or {}
        key = req.get("idempotency_key")
        fingerprint = json.dumps(raw, sort_keys=True, default=str)
        if key and key in self.store.starts:
            previous_fp, previous = self.store.starts[key]
            if previous_fp != fingerprint:
                return {"status": "error", "errors": [{"code": "idempotency_conflict",
                                                       "message": "same idempotency key, different input"}]}
            return previous
        inputs = read_inputs(raw)
        job_id, mission = _job_id(req), str(req.get("mission_id") or "mission")
        items = self.list_items(inputs)
        if not items:
            raise ValueError("Nothing to process")
        info = {"workspace": _ws(req), "items": len(items)}
        run = {"id": f"{job_id}-run", "lane": "run", "title": f"Run — {len(items)} item(s)", "status": "active",
               "steps": [{"id": f"{job_id}-run-prepare", "activity": "operation", "status": "completed",
                          "title": f"Prepare — {len(items)} item(s) found", "cost": 0.0}]}
        pending = [_item_case(job_id, it, "pending") for it in items]
        self.store.write(job_id, snapshot(job_id, mission, self.slug, [run] + pending, "active", info))
        self.pool.submit(self._work, job_id, mission, items, info)
        result = _ok("job.started", job_id=job_id, status="active", job_state=copy.deepcopy(self.store.read(job_id)))
        if key:
            self.store.remember_start(key, fingerprint, result)
        return result

    def _work(self, job_id: str, mission: str, items: list[dict], info: dict) -> None:
        done: list[dict] = []
        for it in items:
            if job_id in self.store.stopped:
                break
            started = time.time()
            try:
                output, cost = self.process_item(it)
                case = _item_case(job_id, it, "completed", cost=float(cost or 0), output=output,
                                  seconds=round(time.time() - started, 2))
            except Exception as e:  # one failing item never stops the others
                log.warning("item %s failed: %s", it.get("id"), e)
                case = _item_case(job_id, it, "failed", error=f"{type(e).__name__}: {e}")
            done.append(case)
            self._update(job_id, mission, items, done, info, final=False)
        self._update(job_id, mission, items, done, info, final=True)

    def _update(self, job_id: str, mission: str, items: list[dict], done: list[dict], info: dict, final: bool) -> None:
        with self.store.lock:
            state = copy.deepcopy(self.store.read(job_id))
            run = next(c for c in state["cases"] if c["lane"] == "run")
            ids = {c["id"] for c in done}
            rest = [_item_case(job_id, it, "pending") for it in items if _case_id(job_id, it) not in ids]
            ok = sum(c["status"] == "completed" for c in done)
            failed = sum(c["status"] == "failed" for c in done)
            run["steps"] = run["steps"][:1] + [{
                "id": f"{job_id}-run-process", "activity": "operation", "status": "completed" if final else "active",
                "title": f"Process — {ok} done, {failed} failed, {len(rest)} left",
                "cost": round(sum(s["cost"] for c in done for s in c["steps"]), 6)}]
            status = "active"
            if final and job_id in self.store.stopped:
                run["status"], status = "failed", "failed"
                run["steps"].append({"id": f"{job_id}-run-stopped", "activity": "operation", "status": "completed",
                                     "title": "Stopped by an operator", "cost": 0.0})
            elif final:
                run["status"], status = "awaiting", "awaiting"
                run["steps"].append({"id": f"{job_id}-run-review", "activity": "operation", "status": "awaiting",
                                     "title": f"Human review — {ok}/{len(items)} item(s) done", "cost": 0.0,
                                     "awaiting": {"reason": "human_input", "surface": SURFACE_REVIEW,
                                                  "action": ACTION_REVIEW, "fields": review_fields()}})
            self.store.write(job_id, snapshot(job_id, mission, self.slug, [run] + done + rest, status, info))

    def _stop(self, req: dict) -> dict:
        job_id = _job_id(req)
        state = self._allowed(job_id, req)
        if state and state["job"]["status"] == "active":
            self.store.stopped.add(job_id)
        return _ok("job.stopped", job_id=job_id, job_state=self.store.read(job_id) if state else None)

    def _review(self, req: dict) -> dict:
        job_id = _job_id(req)
        state = copy.deepcopy(self._allowed(job_id, req))
        if not state:
            raise ValueError("unknown job")
        run = next(c for c in state["cases"] if c["lane"] == "run")
        if run["status"] != "awaiting":  # double click: nothing to redo
            return _ok("step.awaiting.submitted", job_id=job_id, job_state=state)
        decision = (req.get("input") or {}).get("decision") or "approve"
        if decision not in ("approve", "reject"):
            raise ValueError("Unknown decision")
        with self.store.lock:
            run["steps"] = [s for s in run["steps"] if s["status"] != "awaiting"] + [{
                "id": f"{job_id}-run-review", "activity": "operation", "status": "completed", "cost": 0.0,
                "title": "Approved" if decision == "approve" else "Rejected"}]
            run["status"] = "completed" if decision == "approve" else "failed"
            run["metadata"] = {"decision": decision, "by": (req.get("actor") or {}).get("user_id"),
                               "comment": str((req.get("input") or {}).get("comment") or "")[:2000]}
            info = {k: v for k, v in state["job"]["information"].items() if k != "cost"}
            state = snapshot(job_id, state["job"]["mission_id"], self.slug, state["cases"], run["status"], info)
            self.store.write(job_id, state)
        return _ok("step.awaiting.submitted", job_id=job_id, case_id=run["id"], step_id=req.get("step_id"),
                   job_state=state)

    def _allowed(self, job_id: str, req: dict) -> dict | None:
        """A Studio workspace only sees its own jobs. A request with no workspace sees only jobs with no owner."""
        state = self.store.read(job_id)
        if not state:
            return None
        owner = state["job"]["information"].get("workspace")
        if owner and owner != _ws(req):
            return None
        return state


def _case_id(job_id: str, item: dict) -> str:
    return f"{job_id}-{re.sub(r'[^A-Za-z0-9_-]+', '_', str(item['id']))[:60]}"


def _item_case(job_id: str, item: dict, status: str, cost: float = 0.0, output: dict | None = None,
               error: str | None = None, seconds: float | None = None) -> dict:
    meta: dict[str, Any] = {}
    if output is not None:
        meta["output"] = output
    if error:
        meta["error"] = error
    if seconds is not None:
        meta["seconds"] = seconds
    step_status = {"pending": "pending", "completed": "completed", "failed": "failed"}[status]
    return {"id": _case_id(job_id, item), "lane": "items", "title": str(item.get("title") or item["id"])[:90],
            "status": status, "metadata": meta,
            "steps": [{"id": f"{_case_id(job_id, item)}-process", "activity": "operation", "status": step_status,
                       "title": "Process", "cost": round(cost, 6)}]}


def _ws(req: dict) -> str | None:
    return (req.get("workspace") or {}).get("id")


def _job_id(req: dict) -> str:
    j = str(req.get("job_id") or f"job-{req.get('request_id') or uuid.uuid4().hex[:12]}")
    # The id is a folder name under DATA_DIR. No dot allowed: ".." would leave the folder, "starts.json" would
    # collide with the idempotency file.
    return re.sub(r"[^A-Za-z0-9_\-]+", "-", j)[:120]


def _ok(effect: str, *, job_state: dict | None = None, **data: Any) -> dict:
    r: dict[str, Any] = {"status": "ok", "effects": [{"type": effect, **data}]}
    if job_state is not None:
        r["job_state"] = job_state
    return r


def _error(effect: str, **data: Any) -> dict:
    return {"status": "error", "effects": [{"type": effect, **data}]}
