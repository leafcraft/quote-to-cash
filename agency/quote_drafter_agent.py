"""quote_drafter_agent — post-HITL recovery actuator: assembles the quote.

Usually invoked by a HUMAN approval (rep / deal_desk / finance / cfo).
The SDK resumes the chain with only the human-response meta fields, so
the RFQ + cost + discount context is recovered from the per-session
stash that discount_policy_agent wrote before the gate. FAIL-SOFT:
draft with whatever is recoverable; if the deal context is lost we
still emit a body but log a degraded-draft warning so the rep knows to
verify before sending.
"""
from __future__ import annotations

from typing import Any

from leafmesh import LeafMeshLogger, chain

from agency._shared.session_stash import resolve_session_id, stash_get

logger = LeafMeshLogger(__name__)

# Quote validity floor — deeper discounts get a SHORTER shelf life so a
# steep price can't sit open indefinitely. Per-tier max validity in days;
# the floor caps validity_days at the deal's tier (the LLM can't extend a
# tier_4 quote to 90 days). Standard floor is 30.
_TIER_MAX_VALIDITY_DAYS = {
    "tier_1": 60, "tier_2": 45, "tier_3": 30, "tier_4": 14,
}
_DEFAULT_MAX_VALIDITY_DAYS = 30

_CONTEXT_FIELDS = ("rfq_id", "customer_id", "line_items", "target_close",
                   "total_list_cents", "total_cogs_cents", "gross_margin_pct",
                   "discount_pct", "tier", "rationale")
# tier is already in _CONTEXT_FIELDS above — recovered from the stash so
# the validity floor can cap by it.


def _lookup(key: str, *sources: Any) -> Any:
    """First non-empty value for key across dict sources (flat or one
    level deep, e.g. upstream_yields keyed by agent name)."""
    for src in sources:
        if not isinstance(src, dict):
            continue
        if src.get(key) not in (None, ""):
            return src[key]
        for v in src.values():
            if isinstance(v, dict) and v.get(key) not in (None, ""):
                return v[key]
    return None


def _fallback_body(deal: dict[str, Any]) -> str:
    """Deterministic minimal quote when the LLM returned no body —
    pricing table from recovered line items + standard terms."""
    lines = [f"QUOTE — RFQ {deal.get('rfq_id') or 'UNKNOWN'}",
             f"Customer: {deal.get('customer_id') or 'UNKNOWN'}", "", "Pricing:"]
    items = deal.get("line_items") or []
    for li in items if isinstance(items, list) else []:
        if isinstance(li, dict):
            lines.append(
                f"  - {li.get('sku', '?')} x{li.get('qty', '?')} "
                f"@ ${int(li.get('list_price_cents') or 0)/100:,.2f}"
            )
    try:
        discount = float(deal.get("discount_pct") or 0.0)
    except (TypeError, ValueError):
        discount = 0.0
    lines += ["", f"Discount applied: {discount:.0%}",
              "Terms: Net 30. Quote subject to final review.",
              "Next steps: your sales rep will confirm and send."]
    return "\n".join(lines)


async def enforce_quote_validity_floor(result: dict, ctx: dict) -> dict[str, Any]:
    """Cap validity_days by the deal's discount tier — the LLM cannot give
    a steeply-discounted quote a long shelf life. Floor; runs after the
    body. The tier is read from the recovered deal (set in the body)."""
    if not isinstance(result, dict):
        result = {}
    tier = str(result.get("tier", "")).strip().lower()
    cap = _TIER_MAX_VALIDITY_DAYS.get(tier, _DEFAULT_MAX_VALIDITY_DAYS)
    try:
        validity = max(1, int(result.get("validity_days") or _DEFAULT_MAX_VALIDITY_DAYS))
    except (TypeError, ValueError):
        validity = _DEFAULT_MAX_VALIDITY_DAYS
    capped = min(validity, cap)
    if capped != validity:
        logger.info(
            f"[quote-drafter] validity capped {validity}d→{capped}d "
            f"(tier={tier or '?'} max={cap}d)")
    result["validity_days"] = capped
    result["validity_floor_applied"] = True
    return result


@chain(enforce_quote_validity_floor)
async def quote_drafter_agent(llm_response, input_data, context):
    if isinstance(llm_response, str):
        try:
            import json
            llm_response = json.loads(llm_response)
        except (ValueError, TypeError):
            llm_response = {}
    if not isinstance(llm_response, dict):
        llm_response = {}

    # Recover the deal context: live chain shapes first, then the
    # session stash written by discount_policy before the human gate.
    session_id = resolve_session_id(input_data, context)
    stashed = stash_get(session_id)
    sources = (
        input_data,
        input_data.get("upstream_yields"),
        input_data.get("upstream_results"),
        input_data.get("human_data"),
        context.get("upstream") if isinstance(context, dict) else None,
        stashed,
    )
    deal = {k: _lookup(k, *sources) for k in _CONTEXT_FIELDS}

    degraded = not deal.get("rfq_id")
    if degraded:
        # Fail-soft: still draft, but flag it — extra key, allowed by SDK
        logger.warning(
            f"[quote-drafter] DEGRADED draft — no RFQ context recoverable "
            f"(session={session_id or '?'}); rep must verify before sending"
        )

    body = str(llm_response.get("quote_body") or "").strip()
    if not body:
        body = _fallback_body(deal)
    try:
        validity = max(1, int(llm_response.get("validity_days") or 30))
    except (TypeError, ValueError):
        validity = 30

    logger.info(
        f"[quote-drafter] rfq={deal.get('rfq_id') or '?'} "
        f"validity={validity}d degraded={degraded}"
    )
    return {
        "quote_body": body,
        "validity_days": validity,
        # Extra keys (allowed): identity + degraded flag for the audit line.
        # tier is carried so the @chain validity floor can cap by tier.
        "rfq_id": str(deal.get("rfq_id") or ""),
        "customer_id": str(deal.get("customer_id") or ""),
        "tier": str(deal.get("tier") or ""),
        "degraded": degraded,
    }
