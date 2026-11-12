"""Your agent's logic. Replace the two functions below with your own code.

The controller (controller.py) calls them; it never needs to know what your agent does.

    list_items(inputs)  -> the items to process: one item = one case in Studio
    process_item(item)  -> (output, cost_usd) for one item; raise an exception if it fails

Rules (see the guide "I already have an agent"):
- nothing interactive: everything comes from `inputs`;
- read secrets from os.environ when the work runs, not at import time;
- processing the same item twice must not repeat an irreversible action.
"""
from __future__ import annotations

import os
from typing import Any


def list_items(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn the start form values into a list of items. Demo: one item per non-empty line."""
    lines = [line.strip() for line in str(inputs.get("items") or "").splitlines() if line.strip()]
    return [{"id": f"item-{i + 1}", "title": line[:80], "text": line} for i, line in enumerate(lines)]


def process_item(item: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Process one item and return (output, cost in USD). Demo: counts words, no external call.

    Replace with your agent: call your model or your tools here. Example of a secret read at run time:
        api_key = os.environ["AI_API_KEY"]
    """
    _ = os.environ.get("AI_API_KEY")  # read when the work runs, never at import time
    text = item["text"]
    if text.lower().startswith("fail"):
        raise ValueError("demo failure: lines starting with 'fail' are rejected")
    words = len(text.split())
    return {"words": words, "summary": text[:120]}, 0.0
