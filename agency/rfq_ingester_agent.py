"""LLM Agent — RFQ intake registrar (self-reliant, deterministic floor).

The desk's front door. On top of the LLM's RFQ normalisation, this role:

  * pulls its OWN context (@pre_compose load_customer_intel) — this
    customer's deal history and any prior RFQs from the system of record,
    so the registrar ingests against what we already know about the
    account (returning customer, last discount, prior open RFQ) instead
    of treating every RFQ as a cold inbound.
  * enforces a COMPLETENESS FLOOR (@chain enforce_completeness_floor) the
    LLM cannot waive: an RFQ missing line_items OR a customer is FORCED
    incomplete in code. is_complete drives the can_call edge, so an
    underspecified RFQ is routed BACK to the sales rep for rework and is
    NEVER passed downstream to costing/pricing on bad data.

The model can normalise sloppy input, but it cannot declare a headless
RFQ "ready to cost" — the floor recomputes is_complete from the actual
presence of a customer and at least one line item, every time.

DEV: deal history + prior RFQs come from agency/_shared/store.py so the
chain runs end-to-end with NO connector wired. PROD: wire your CPQ/CRM
(deal history) connector into load_customer_intel; the SHAPE the rest of
the mesh reads stays the same.

Decorators (bottom-up execution):
  @pre_compose load_customer_intel — pull this customer's deal history +
      prior RFQs from the system of record.
  @chain enforce_completeness_floor — FORCE is_complete in code from the
      presence of customer + line_items (the floor that gates routing).

auto_discover matches function name 'rfq_ingester_agent' to YAML.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, chain, pre_compose

from agency._shared import store

logger = LeafMeshLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "rfq_id": "",
    "customer_id": "",
    "line_items": [],
    "target_close": "",
    "is_complete": False,
    "missing_fields": [],
    "intake_status": "incomplete",
    "completeness_floor_applied": False,
}


def _prepared(context: Any) -> dict[str, Any]:
    """Read the @pre_compose output, tolerant of SDK wrapping depth."""
    if not isinstance(context, dict):
        return {}
    prep = context.get("prepared_data", {})
    if isinstance(prep, dict):
        inner = prep.get("context")
        if isinstance(inner, dict):
            return inner
        return prep
    return {}


def _parse_json(text: Any) -> dict[str, Any]:
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return {}
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            return {}
    return {}


def _lookup(key: str, *sources: Any) -> Any:
    """First non-empty value for key across dict sources (flat or one
    level deep, e.g. payload nested under the entry-point envelope)."""
    for src in sources:
        if not isinstance(src, dict):
            continue
        if src.get(key) not in (None, ""):
            return src[key]
        for v in src.values():
            if isinstance(v, dict) and v.get(key) not in (None, ""):
                return v[key]
    return None


def _line_items(data: Any) -> list[dict[str, Any]]:
    """Pull line_items from the input (flat or one level deep)."""
    if isinstance(data, dict):
        li = data.get("line_items")
        if isinstance(li, list):
            return [x for x in li if isinstance(x, dict)]
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("line_items"), list):
                return [x for x in v["line_items"] if isinstance(x, dict)]
    return []


# ── @pre_compose processor ───────────────────────────────────────────
def load_customer_intel(data: Any, ctx: dict) -> dict[str, Any]:
    """Pull this customer's deal history + any prior RFQs from the store.

    Lets the registrar ingest against what we already know about the
    account — a returning customer, their last discount, an existing open
    RFQ — rather than treating every inbound as cold.

    PROD: wire your CPQ/CRM (deal history + prior RFQs) connector here;
    the SHAPE stays the same."""
    input_data = data if isinstance(data, dict) else {}
    payload = input_data.get("payload")
    customer_id = str(_lookup("customer_id", input_data, payload) or "")
    rfq_id = str(_lookup("rfq_id", input_data, payload) or "")

    history = store.deal_history(customer_id) if customer_id else []
    # Prior RFQs for this customer (this same RFQ id excluded).
    prior_rfqs = [
        r for r in history
        if r.get("rfq_id") and r.get("rfq_id") != rfq_id
    ]
    # If this exact RFQ id was seen before, surface it as a duplicate.
    existing = store.get_rfq(rfq_id) if rfq_id else {}

    return {
        "customer_id": customer_id,
        "is_returning_customer": bool(history),
        "deal_history": history,
        "prior_rfqs": prior_rfqs,
        "prior_rfq_count": len(prior_rfqs),
        "is_duplicate_rfq": bool(existing),
        "existing_rfq": existing,
    }


# ── @chain step (the deterministic completeness floor) ────────────────
async def enforce_completeness_floor(result: dict, ctx: dict) -> dict[str, Any]:
    """FORCE is_complete from the presence of customer + line_items.

    Floor — runs after the agent body and recomputes completeness in
    code. is_complete gates the can_call edge: a missing customer OR
    missing line_items routes the RFQ BACK to the sales rep for rework
    rather than downstream to costing. The LLM cannot declare a headless
    RFQ ready to cost."""
    if not isinstance(result, dict):
        result = {}

    customer_id = str(result.get("customer_id", "") or "").strip()
    line_items = result.get("line_items")
    if not isinstance(line_items, list):
        line_items = []
    line_items = [li for li in line_items if isinstance(li, dict)]

    missing: list[str] = []
    if not customer_id:
        missing.append("customer_id")
    if not line_items:
        missing.append("line_items")

    is_complete = not missing
    result["line_items"] = line_items
    result["is_complete"] = is_complete
    result["missing_fields"] = missing
    result["intake_status"] = "complete" if is_complete else "incomplete"
    result["completeness_floor_applied"] = True

    logger.info(
        f"enforce_completeness_floor — rfq={result.get('rfq_id','')} "
        f"customer={customer_id or '?'} items={len(line_items)} "
        f"complete={is_complete} missing={missing} "
        f"(is_complete gates routing — incomplete → sales rep, not costing)"
    )
    return result


@pre_compose(context_processor=load_customer_intel)
@chain(enforce_completeness_floor)
async def rfq_ingester_agent(llm_response, input_data: dict,
                             context: dict) -> dict[str, Any]:
    """Surface the normalised RFQ; the chain enforces the completeness floor.

    The LLM's is_complete (if any) is advisory — enforce_completeness_floor
    recomputes it from the actual presence of a customer + line items, so a
    sloppy parse still routes correctly."""
    if not isinstance(input_data, dict):
        input_data = {}
    parsed = _parse_json(llm_response)
    payload = input_data.get("payload")
    out = {**_DEFAULTS}

    out["rfq_id"] = str(parsed.get("rfq_id", "")) or \
        str(_lookup("rfq_id", input_data, payload) or "")
    out["customer_id"] = str(parsed.get("customer_id", "")) or \
        str(_lookup("customer_id", input_data, payload) or "")
    items = parsed.get("line_items")
    out["line_items"] = items if isinstance(items, list) else \
        _line_items(input_data) or _line_items(payload)
    out["target_close"] = str(parsed.get("target_close", "")) or \
        str(_lookup("target_close", input_data, payload) or "")
    return out
