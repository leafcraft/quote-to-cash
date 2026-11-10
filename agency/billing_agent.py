"""Billing — AR & Collections Clerk (the CASH side of quote-to-cash).

auto_discover matches `billing_agent`. One role, two crafts loaded from the
playbook on demand: `invoice` (raise an invoice from an accepted quote) and
`dun` (chase an overdue invoice on cadence). It runs on two triggers:

  * quote_accepted  -> invoice mode, one accepted quote
  * dunning_sweep    -> dun mode, a wake_up cron sweep of the overdue backlog

`scaling.copies.count: N` fans the sweep across parallel copies; each copy calls the
atomic `claim_billing_work` tool and gets a DISJOINT slice, so copies split
the backlog instead of all chasing the same invoices (and a single accepted
quote is won by exactly one copy — the claim is what makes fan-out
idempotent in both modes).

@chain enforce_billing_floor — fail closed: NEVER dun an invoice that is
already paid (re-checked in code against the store, not trusted from the
model), records each verified action to the outbox + ledger, and raises an
escalation for anything severely overdue. Escalations are a LIST so the
`scaling.copies.handoff: last` merge concatenates them across copies rather than
dropping all but the last.
"""
from __future__ import annotations

from typing import Any

from leafmesh import LeafMeshLogger, chain

try:
    from ._shared import store
except ImportError:  # pragma: no cover
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _shared import store  # type: ignore

logger = LeafMeshLogger(__name__)

_ESCALATE_DAYS_OVERDUE = 45   # severely overdue -> RevOps lead
_MAX_DUNNING_STAGE = 3        # after this, stop auto-chasing and escalate


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def enforce_billing_floor(result: Any, context: dict) -> dict:
    """Fail closed: verify every claimed invoice against the store before
    acting; never dun a paid invoice; record verified actions; escalate the
    severely overdue."""
    result = result if isinstance(result, dict) else {}
    mode = str(result.get("mode") or "dun").strip().lower()
    worked = result.get("worked") if isinstance(result.get("worked"), list) else []

    escalations: list[str] = []
    dunned = 0
    invoiced = 0
    verified: list[str] = []

    for item in worked:
        inv_id = item.get("invoice_id") if isinstance(item, dict) else str(item)
        if not inv_id:
            continue
        status = store.invoice_status(inv_id)
        if status == "paid":
            logger.info(f"[billing] refusing to {mode} PAID invoice {inv_id} (fail closed)")
            continue
        if status == "unknown":
            logger.info(f"[billing] skipping unknown invoice {inv_id}")
            continue

        row = {r["invoice_id"]: r for r in store.open_invoices()}.get(inv_id, {})
        days = _as_int(row.get("days_overdue"))
        if mode == "invoice":
            store.record_outbox({"action": "raise_invoice", "invoice_id": inv_id,
                                 "customer_id": row.get("customer_id", "")})
            store.append_ledger({"event": "invoice_raised", "invoice_id": inv_id})
            invoiced += 1
            verified.append(inv_id)
            continue

        # dun mode
        stage = _as_int(row.get("dunning_stage")) + 1
        store.mark_invoice(inv_id, dunning_stage=stage)
        store.record_outbox({"action": "dunning_notice", "invoice_id": inv_id,
                             "dunning_stage": stage, "days_overdue": days})
        store.append_ledger({"event": "dunning_notice", "invoice_id": inv_id,
                             "dunning_stage": stage})
        dunned += 1
        verified.append(inv_id)
        if days >= _ESCALATE_DAYS_OVERDUE or stage > _MAX_DUNNING_STAGE:
            escalations.append(inv_id)

    result["worked"] = verified
    result["escalations"] = escalations
    result["dunned_count"] = dunned
    result["invoiced_count"] = invoiced
    result["available"] = bool(verified) or bool(result.get("available"))
    result["billing_floor_applied"] = True
    if not verified:
        result.setdefault("summary", "No billing work claimed for this worker copy.")
    logger.info(f"[billing] mode={mode} dunned={dunned} invoiced={invoiced} "
                f"escalate={escalations}")
    return result


@chain(enforce_billing_floor)
async def billing_agent(llm_response: Any, input_data: dict, context: dict) -> dict:
    out = llm_response if isinstance(llm_response, dict) else {}
    out.setdefault("mode", "dun")
    out.setdefault("worked", [])
    out.setdefault("escalations", [])
    out.setdefault("dunned_count", 0)
    out.setdefault("invoiced_count", 0)
    out.setdefault("available", False)
    out.setdefault("summary", "")
    out.setdefault("claim_token", "")
    return out
