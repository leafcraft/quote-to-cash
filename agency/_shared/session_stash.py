"""Per-session deal stash — bridges the HITL gap.

When a human approves in the Studio inbox, the SDK resumes the chain
with ONLY the human-response meta fields (human_message, human_decision,
…) — the deal payload that was flowing through the chain is not
re-delivered to the next agent. discount_policy_agent stashes the full
RFQ + cost + discount context here, keyed by session_id, so
quote_drafter (and the audit sink) can recover it after the human gate.

In-process only — survives the human wait because the mesh is one
process. A multi-replica deployment swaps this for the Redis session
store; the get/put interface stays the same.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

_LOCK = threading.Lock()
_MAX_SESSIONS = 500
_STASH: OrderedDict[str, dict[str, Any]] = OrderedDict()


def stash_put(session_id: str, payload: dict[str, Any]) -> None:
    if not session_id:
        return
    with _LOCK:
        _STASH[session_id] = dict(payload)
        _STASH.move_to_end(session_id)
        while len(_STASH) > _MAX_SESSIONS:
            _STASH.popitem(last=False)


def stash_get(session_id: str) -> dict[str, Any]:
    if not session_id:
        return {}
    with _LOCK:
        return dict(_STASH.get(session_id) or {})


def resolve_session_id(input_data: dict[str, Any], context: dict[str, Any]) -> str:
    for src in (input_data, context):
        if not isinstance(src, dict):
            continue
        for key in ("session_id", "sessionId"):
            sid = src.get(key)
            if sid:
                return str(sid)
        owd = src.get("original_webhook_data")
        if isinstance(owd, dict) and owd.get("session_id"):
            return str(owd["session_id"])
    return ""
