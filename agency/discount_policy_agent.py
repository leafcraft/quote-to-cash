"""LLM Agent — pricing strategist (deterministic discount floor + stash).

Picks a discount tier from customer history + competitive signals, then
enforces the firm's discount policy as a FLOOR the LLM cannot waive:

  * discount_pct is CLAMPED to 0..1 in code.
  * tier is DERIVED in code from discount_pct against the policy table's
    bands (tier_1..tier_4) — the model cannot mislabel a 35% discount as
    tier_2 to dodge the CFO gate.
  * gross_margin_pct is RECOMPUTED as the post-discount margin from the
    upstream cost basis (margin AFTER the discount eats into list) — this
    is the number the approval matrix wires route on, so a deep discount
    that pushes margin below the floor forces the CFO tier deterministically.
  * total_list_cents is echoed from the recomputed cost basis (never the
    LLM's arithmetic).
  These three keys drive discount_policy_agent's can_call matrix, so the
  rep / deal-desk / finance / CFO gate fires on COMPUTED numbers.

It also STASHES the full deal context pre-gate (the SDK resumes a chain
after a human gate with only the human's response), and @compose gives
the human approver a focused approval brief vs the quote writer the full
deal.

DEV: deal history + competitor pricing + the policy table come from
agency/_shared/store.py so the chain runs day-0. PROD: wire your CRM /
price-intelligence connectors into load_deal_intel.

Decorators (bottom-up execution):
  @pre_compose load_deal_intel — pull deal history, competitor pricing,
      and the discount policy table for this customer/SKUs.
  @compose per-peer payloads — approver gets the approval brief; quote
      writer gets the full deal package.
  @chain enforce_discount_floor — clamp discount, derive tier, recompute
      post-discount margin, stash the deal (the floor).

auto_discover matches function name 'discount_policy_agent' to YAML.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, chain, compose, pre_compose

from agency._shared import store
from agency._shared.session_stash import resolve_session_id, stash_put

logger = LeafMeshLogger(__name__)

_STASH_KEYS = ("rfq_id", "customer_id", "line_items", "target_close",
               "total_list_cents", "total_cogs_cents", "gross_margin_pct",
               "discount_pct", "tier", "rationale")

_DEFAULTS: dict[str, Any] = {
    "discount_pct": 0.0,
    "tier": "tier_1",
    "rationale": "",
    "deal_desk_briefing": "",
    "total_list_cents": 0,
    "gross_margin_pct": 0.0,
    "rfq_id": "",
    "discount_floor_applied": False,
}


def _prepared(context: Any) -> dict[str, Any]:
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


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


# ── @pre_compose processor ───────────────────────────────────────────
def load_deal_intel(data: Any, ctx: dict) -> dict[str, Any]:
    """Pull deal history, competitor pricing, and the policy table.

    PROD: wire your CRM (deal history) + price-intelligence stack
    (competitor pricing) connectors here; the SHAPE stays the same."""
    input_data = data if isinstance(data, dict) else {}
    customer_id = str(_lookup("customer_id", input_data,
                              input_data.get("upstream_yields")) or "")
    segment = str(_lookup("segment", input_data,
                          input_data.get("upstream_yields")) or "")
    line_items = _lookup("line_items", input_data,
                         input_data.get("upstream_yields")) or []
    skus = [str(li.get("sku", "")) for li in line_items
            if isinstance(li, dict) and li.get("sku")]
    return {
        "customer_id": customer_id,
        "deal_history": store.deal_history(customer_id),
        "competitor_pricing": store.competitor_pricing(skus),
        "policy": store.discount_policy(),
        "segment_guidance": store.segment_guidance(segment),
    }


def _apply_floor(result: dict, pctx: dict) -> dict[str, Any]:
    """Pure derivation — clamp discount, derive tier, recompute the
    post-discount margin from the cost basis. Shared by the @chain floor
    and the agent body so the stashed numbers match the routed numbers."""
    # 1. clamp discount to 0..1.
    discount = max(0.0, min(1.0, _as_float(result.get("discount_pct", 0.0))))
    result["discount_pct"] = discount

    # 2. tier DERIVED in code from the policy bands (LLM can't mislabel).
    result["tier"] = store.tier_for_discount(discount)

    # 3. recompute the POST-DISCOUNT margin from the upstream cost basis.
    #    The matrix wires route on gross_margin_pct, so the floor owns it:
    #    a deep discount that eats into list pushes margin below the floor
    #    and forces the CFO tier deterministically.
    total_list = _as_int(result.get("total_list_cents", 0)) or \
        _as_int(_lookup("total_list_cents", result, pctx))
    total_cogs = _as_int(result.get("total_cogs_cents", 0)) or \
        _as_int(_lookup("total_cogs_cents", result, pctx))
    discounted_list = total_list * (1.0 - discount)
    if discounted_list > 0:
        post_margin = round((discounted_list - total_cogs) / discounted_list, 4)
    else:
        post_margin = 0.0
    result["total_cogs_cents"] = total_cogs
    result["total_list_cents"] = total_list
    result["gross_margin_pct"] = post_margin
    result["discount_floor_applied"] = True
    return result


# ── @chain step (the deterministic discount floor) ───────────────────
async def enforce_discount_floor(result: dict, ctx: dict) -> dict[str, Any]:
    """Clamp discount, derive tier, recompute post-discount margin. Floor —
    runs after the agent body; re-asserts the routing keys deterministically
    so the can_call matrix fires on COMPUTED numbers no matter what."""
    if not isinstance(result, dict):
        result = {}
    out = _apply_floor(result, _prepared(ctx))
    logger.info(
        f"enforce_discount_floor — rfq={out.get('rfq_id','')} "
        f"discount={out['discount_pct']} tier={out['tier']} "
        f"post_margin={out['gross_margin_pct']} list={out['total_list_cents']} "
        f"(matrix routes on these)"
    )
    return out


# ── @compose per-peer payloads ───────────────────────────────────────
def _to_approver(result: dict, ctx: dict) -> dict[str, Any]:
    """Focused approval brief for the rep / deal-desk / finance / CFO gate."""
    return {
        "rfq_id": result.get("rfq_id", ""),
        "tier": result.get("tier", ""),
        "discount_pct": result.get("discount_pct", 0),
        "gross_margin_pct": result.get("gross_margin_pct", 0),
        "total_list_cents": result.get("total_list_cents", 0),
        "deal_desk_briefing": result.get("deal_desk_briefing", ""),
    }


def _to_quote(result: dict, ctx: dict) -> dict[str, Any]:
    """Full deal package for the quote writer."""
    return result


@pre_compose(context_processor=load_deal_intel)
@compose(
    sales_rep_human=_to_approver,
    deal_desk_human=_to_approver,
    finance_approver_human=_to_approver,
    cfo_human=_to_approver,
    quote_drafter_agent=_to_quote,
)
@chain(enforce_discount_floor)
async def discount_policy_agent(llm_response, input_data: dict,
                                context: dict) -> dict[str, Any]:
    """Surface the discount pick, apply the floor, then STASH the deal.

    The stash happens here (not in the @chain) because input_data +
    context are real params here — the SDK resumes the post-gate chain
    with only the human's response, so the deal must be persisted now."""
    if not isinstance(input_data, dict):
        input_data = {}
    parsed = _parse_json(llm_response)
    pctx = _prepared(context)
    uy = input_data.get("upstream_yields")
    out = {**_DEFAULTS}
    out["discount_pct"] = _as_float(parsed.get("discount_pct", 0.0))
    out["rationale"] = str(parsed.get("rationale", ""))
    out["deal_desk_briefing"] = str(parsed.get("deal_desk_briefing", ""))
    out["rfq_id"] = str(parsed.get("rfq_id", "")) or \
        str(_lookup("rfq_id", input_data, uy, pctx) or "")
    out["total_list_cents"] = _as_int(parsed.get("total_list_cents", 0)) or \
        _as_int(_lookup("total_list_cents", input_data, uy))
    out["total_cogs_cents"] = _as_int(parsed.get("total_cogs_cents", 0)) or \
        _as_int(_lookup("total_cogs_cents", input_data, uy))

    # Apply the floor here too so the STASHED numbers match the routed
    # ones (the @chain re-asserts the same derivation as the guarantee).
    out = _apply_floor(out, pctx)

    # Stash the full deal context pre-gate for quote_drafter recovery.
    sources = (out, input_data, uy, pctx,
               context.get("upstream") if isinstance(context, dict) else None)
    deal = {k: _lookup(k, *sources) for k in _STASH_KEYS}
    deal.update({
        "total_cogs_cents": out["total_cogs_cents"],
        "total_list_cents": out["total_list_cents"],
        "gross_margin_pct": out["gross_margin_pct"],
        "discount_pct": out["discount_pct"],
        "tier": out["tier"],
    })
    stash_put(resolve_session_id(input_data, context), deal)
    return out
