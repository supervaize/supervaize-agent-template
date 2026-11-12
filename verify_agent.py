"""Check that an agent is ready to connect to Supervaize Studio. Prints what is missing, never a secret.

Usage (from the agent's folder, Mac / Linux / Windows):
    python verify_agent.py                      # reads .env in the current folder
    python verify_agent.py --env-file other.env
    python verify_agent.py --url https://my-agent.example.com   # also tests a public address

Exit code 0 when everything required is OK, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"
results: list[tuple[str, str, str]] = []


def report(level: str, what: str, detail: str = "") -> None:
    results.append((level, what, detail))


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(url: str, timeout: int = 15) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "supervaize-verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
            return r.status, r.read(200_000)
    except urllib.error.HTTPError as e:
        return e.code, b""


def check_python() -> None:
    v = sys.version_info
    if v >= (3, 12):
        report(OK, "Python", f"{v.major}.{v.minor}")
    else:
        report(FAIL, "Python", f"{v.major}.{v.minor} found, 3.12 or later required")


def check_sdk() -> None:
    try:
        from supervaizer.__version__ import VERSION  # type: ignore
        report(OK, "Supervaizer installed", VERSION)
    except Exception:
        report(FAIL, "Supervaizer installed", "not found: activate your virtual environment, then pip install supervaizer")


def check_files(folder: Path) -> None:
    ctrl = folder / "supervaizer_control.py"
    if ctrl.exists():
        text = ctrl.read_text(encoding="utf-8", errors="ignore")
        report(OK, "supervaizer_control.py", "found")
        if "launch(" not in text:
            report(WARN, "Start command", "no server.launch(): start with `supervaizer start`, not `uvicorn` alone")
    else:
        report(FAIL, "supervaizer_control.py", "not found in this folder (run `supervaizer scaffold`)")
    pyproject = folder / "pyproject.toml"
    if pyproject.exists():
        has_dep = "supervaizer" in pyproject.read_text(encoding="utf-8", errors="ignore")
        report(OK if has_dep else WARN, "pyproject.toml",
               "lists supervaizer" if has_dep else "does not list supervaizer in its dependencies")
    else:
        report(WARN, "pyproject.toml", "missing: needed by `supervaizer deploy`")
    gitignore = folder / ".gitignore"
    if (folder / ".git").exists() and (not gitignore.exists() or ".env" not in gitignore.read_text(encoding="utf-8")):
        report(FAIL, ".gitignore", ".env is not ignored by git: add a line `.env`")


def check_env(env: dict[str, str]) -> None:
    required = ["SUPERVAIZE_API_KEY", "SUPERVAIZE_WORKSPACE_ID", "SUPERVAIZE_API_URL"]
    for k in required:
        if env.get(k):
            report(OK, k, "set")
        else:
            report(FAIL, k, "missing: run `supervaizer login`")
    for k in ("SUPERVAIZE_API_URL", "SUPERVAIZER_PUBLIC_URL", "SUPERVAIZER_WORKSPACE_AUTH_JWKS_URL",
              "SUPERVAIZER_WORKSPACE_AUTH_ISSUER"):
        v = env.get(k, "")
        if v and (re.search(r"\s", v) or not v.startswith("https://")):
            report(FAIL, k, "must be a full https:// address without spaces or line breaks")
    auth = env.get("SUPERVAIZER_WORKSPACE_AUTH_REQUIRED", "").lower() in ("1", "true", "yes")
    if auth:
        for k in ("SUPERVAIZER_WORKSPACE_AUTH_ISSUER", "SUPERVAIZER_WORKSPACE_AUTH_JWKS_URL"):
            report(OK if env.get(k) else FAIL, k, "set" if env.get(k) else "missing: run `supervaizer login`")
    else:
        report(WARN, "Workspace authorization", "SUPERVAIZER_WORKSPACE_AUTH_REQUIRED is not true: run `supervaizer login`")
    sid = env.get("SUPERVAIZER_SERVER_ID", "")
    if len(sid) > 5:
        report(OK, "SUPERVAIZER_SERVER_ID", "set")
    else:
        report(WARN, "SUPERVAIZER_SERVER_ID", "not set: a new agent identity at every restart")
    if not env.get("SUPERVAIZER_PUBLIC_URL"):
        report(WARN, "SUPERVAIZER_PUBLIC_URL", "not in .env: pass --public-url at startup, or set it in production")


def check_jwks(env: dict[str, str]) -> None:
    url = env.get("SUPERVAIZER_WORKSPACE_AUTH_JWKS_URL", "")
    if not url:
        return
    try:
        status, body = fetch(url)
        keys = json.loads(body or b"{}").get("keys") if status == 200 else None
        if keys:
            report(OK, "JWKS address", "answers with keys")
        else:
            report(FAIL, "JWKS address", f"HTTP {status}, no keys: see Troubleshooting (JWKS URL returns 404)")
    except Exception as e:
        report(FAIL, "JWKS address", f"unreachable ({type(e).__name__}): check the address and your network")


def check_public(url: str) -> None:
    url = url.rstrip("/")
    try:
        status, _ = fetch(url + "/.well-known/health")
        if status == 200:
            report(OK, "Public address", f"{url} answers on /.well-known/health")
        else:
            report(FAIL, "Public address", f"HTTP {status} on /.well-known/health: is the agent started with A2A on?")
    except Exception as e:
        report(FAIL, "Public address", f"unreachable ({type(e).__name__}): is the agent or the tunnel running?")


def main() -> int:
    p = argparse.ArgumentParser(description="Check that an agent is ready for Supervaize Studio.")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--url", help="public address to test (defaults to SUPERVAIZER_PUBLIC_URL)")
    p.add_argument("--offline", action="store_true", help="skip network checks")
    a = p.parse_args()
    folder = Path.cwd()
    env_path = Path(a.env_file)
    env = {**{k: v for k, v in os.environ.items() if k.startswith("SUPERVAIZ")}, **load_env(env_path)}
    if not env_path.exists():
        report(WARN, a.env_file, "not found: variables are read from your shell only")
    check_python()
    check_sdk()
    check_files(folder)
    check_env(env)
    if not a.offline:
        check_jwks(env)
        url = a.url or env.get("SUPERVAIZER_PUBLIC_URL")
        if url:
            check_public(url)
    width = max(len(w) for _, w, _ in results)
    for level, what, detail in results:
        print(f"[{level}] {what.ljust(width)}  {detail}")
    failed = sum(1 for level, _, _ in results if level == FAIL)
    print(f"\n{'Ready' if not failed else str(failed) + ' problem(s) to fix'}. "
          "Details: https://docs.runwaize.com/docs/supervaizer-controller/troubleshooting")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
