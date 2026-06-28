"""Hash-chained WORM audit sink.

The audit_logger_agent in configs/config.yaml is `agent_type: external`
with `framework: custom`. SDK 2.4+ executes custom external agents via
an *intelligence function* registered on the LeafMesh instance:

    from agency._shared import audit_logger
    leafmesh = LeafMesh.from_yaml("configs/config.yaml")
    audit_logger.register(leafmesh)          # ← main.py does this

(Older SDKs used a `leafmesh.external.registry` connector registry —
that path is kept below for backwards compatibility and no-ops when
the module is absent.)

Dev mode writes hash-chained JSON lines to ./logs/audit.jsonl.
Production swaps `_dispatch_local` for S3 Object Lock / Datadog Audit
Trail / Splunk HEC.

Hash-chain invariant: each entry includes the SHA-256 of the prior
entry's serialized body, making any insertion / deletion detectable
post-hoc.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from leafmesh import LeafMeshLogger

logger = LeafMeshLogger(__name__)
_CHAIN_LOCK = threading.Lock()
_LAST_HASH = "GENESIS"

# Default sink — overridden by connector_config in config.yaml when the
# SDK passes it through; kept as module default so the intelligence
# path (which receives no connector_config) still lands in the same file.
DEFAULT_AUDIT_PATH = "./logs/audit.jsonl"

# Human/meta keys that are transport plumbing, not audit payload.
_META_KEYS = frozenset({
    "session_id", "sessionId", "payload",
    "human_initiated", "original_webhook_data",
})


def _sha256_hex(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(body).hexdigest()


def _dispatch_local(path_str: str, entry: dict[str, Any]) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")


def write_audit_entry(input_data: dict[str, Any],
                      config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append one hash-chained entry. Returns the audit_logger yields."""
    global _LAST_HASH
    input_data = input_data if isinstance(input_data, dict) else {}
    cfg = config or {}
    sink_type = cfg.get("sink_type", "local_file")
    path_str = cfg.get("local_file_path", DEFAULT_AUDIT_PATH)

    # Prefer an explicit `payload` key; otherwise audit the entire
    # input minus transport meta — upstream agents deliver their
    # yields flat, and an audit sink must never drop them on a
    # shape mismatch.
    payload = input_data.get("payload")
    if not isinstance(payload, dict) or not payload:
        payload = {k: v for k, v in input_data.items() if k not in _META_KEYS}

    with _CHAIN_LOCK:
        prev_hash = _LAST_HASH
        entry = {
            "audit_event_id": f"audit-{uuid.uuid4().hex[:12]}",
            "written_at_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": str(input_data.get("session_id", "")),
            "payload": payload,
            "hash_chain_prev": prev_hash,
        }
        entry["hash_chain_current"] = _sha256_hex(
            {k: v for k, v in entry.items() if k != "hash_chain_current"}
        )
        _LAST_HASH = entry["hash_chain_current"]

        if sink_type == "local_file":
            _dispatch_local(path_str, entry)
        else:
            logger.warning(
                f"[audit] sink_type={sink_type!r} not implemented — "
                "falling back to local_file"
            )
            _dispatch_local(path_str, entry)

    logger.info(f"[audit] {entry['audit_event_id']} chain={entry['hash_chain_current'][:8]}…")
    return entry


def register(mesh: Any, agent_name: str = "audit_logger_agent") -> bool:
    """Register the audit intelligence function on a LeafMesh instance.

    SDK 2.4+: custom external agents execute through
    `@mesh.intelligence("<agent_name>")`. Call this AFTER
    `LeafMesh.from_yaml(...)` and before `mesh.start()`.
    """
    if not callable(getattr(mesh, "intelligence", None)):
        logger.warning("[audit] mesh has no .intelligence() — audit sink NOT registered")
        return False

    async def audit_logger_agent(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # Signature-tolerant: the SDK may pass (input_data),
        # (llm_response, input_data, context), or kwargs. The audit
        # payload is the first dict that isn't obviously a context.
        input_data: dict[str, Any] = {}
        if isinstance(kwargs.get("input_data"), dict):
            input_data = kwargs["input_data"]
        elif len(args) >= 2 and isinstance(args[1], dict):
            input_data = args[1]
        else:
            input_data = next((a for a in args if isinstance(a, dict)), {})
        return write_audit_entry(input_data)

    mesh.intelligence(agent_name)(audit_logger_agent)
    logger.info("[audit] hash-chained WORM sink registered via mesh.intelligence()")
    return True


# ── Legacy path (SDK < 2.4): connector registry ──────────────────────
try:  # pragma: no cover — exercised only on old SDKs
    from leafmesh.external.base import ExternalConnector
    from leafmesh.external.registry import register_connector

    @register_connector("custom")
    class FinanceAuditLoggerConnector(ExternalConnector):  # type: ignore[misc]
        """Append-only hash-chained audit sink (legacy connector API)."""

        async def execute(self, input_data: dict[str, Any],
                          config: dict[str, Any]) -> dict[str, Any]:
            return write_audit_entry(input_data, config)
except ImportError:
    pass
