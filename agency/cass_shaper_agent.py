"""Cass — Costing & Deal Shaper (the deal-shaping SUPER-AGENT).

auto_discover matches `cass_shaper_agent` to the YAML agent. Cass turns a
raw RFQ into a priced, policy-compliant deal: it plans the pricing across
the SKUs, pulls the price book / deal history / competitor signals through
its tools, and shapes a discount within policy given the competitive
picture. The MODEL decides and pulls; this CODE fails closed.

Two deterministic floors a prompt can't waive live in `@chain`:

  1. COMPLETENESS — an RFQ with no customer or no line-items can never be
     declared ready to price; it is forced incomplete and routed BACK to
     the sales rep for rework. The back-edge is BOUNDED: a rework counter
     (persisted per session) escalates to the RevOps lead once exhausted,
     so a deal can never ping-pong rep<->shaper forever.
  2. PRICING — COGS / list / margin are RECOMPUTED from line_items x the
     price book, the discount is clamped to 0..1, the tier is DERIVED from
     the policy bands, and `gross_margin_pct` is recomputed as the
     POST-DISCOUNT margin. These three keys drive the approval matrix on
     this agent's wires, so the gate fires on COMPUTED numbers — a deep
     discount that pushes margin below floor forces the CFO tier
     deterministically, whatever the model wrote.

Cass also STASHES the full deal pre-gate: the SDK resumes a chain after a
human gate with only the human's reply, so the drafter and issuer recover
the deal from the per-session stash.
"""
from __future__ import annotations

from typing import Any

from leafmesh import LeafMeshLogger, chain

try:
    from ._shared import store
    from ._shared.session_stash import resolve_session_id, stash_get, stash_put
except ImportError:  # pragma: no cover
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _shared import store  # type: ignore
    from _shared.session_stash import resolve_session_id, stash_get, stash_put  # type: ignore

logger = LeafMeshLogger(__name__)

_MAX_REWORK_ROUNDS = 2   # rep <-> shaper back-edge bound; then escalate (terminal)


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _recompute_costs(line_items: list[dict]) -> tuple[int, int, bool]:
    """Recompute (total_cogs_cents, total_list_cents, has_regulated) from the
    price book x line items — the model cannot invent a cheaper cost basis."""
    total_cogs = 0
    total_list = 0
    regulated = False
    for li in line_items if isinstance(line_items, list) else []:
        if not isinstance(li, dict):
            continue
        sku = str(li.get("sku", ""))
        qty = _as_int(li.get("qty"))
        book = store.sku_cost(sku)
        unit_cost = _as_int(book.get("unit_cost_cents"))
        unit_list = _as_int(book.get("unit_list_cents")) or _as_int(li.get("list_price_cents"))
        total_cogs += unit_cost * qty
        total_list += unit_list * qty
        if store.is_regulated(sku):
            regulated = True
        li["unit_cost_cents"] = unit_cost
        li["list_price_cents"] = unit_list
    return total_cogs, total_list, regulated


def enforce_pricing_floor(result: Any, context: dict) -> dict:
    """Fail closed: recompute the cost basis + derive the tier, and force an
    incomplete RFQ back to the rep (bounded)."""
    result = result if isinstance(result, dict) else {}
    context = context if isinstance(context, dict) else {}

    line_items = result.get("line_items") or []
    customer_id = str(result.get("customer_id") or "").strip()

    # ── Completeness floor + bounded rework counter ──
    is_complete = bool(customer_id) and bool(line_items)
    sid = resolve_session_id(result, context)
    prior = stash_get(sid)
    rework_round = _as_int(prior.get("rework_round"))
    rework_exhausted = False
    if not is_complete:
        rework_round += 1
        missing = []
        if not customer_id:
            missing.append("customer_id")
        if not line_items:
            missing.append("line_items")
        result["missing_fields"] = missing
        result["intake_status"] = "incomplete"
        if rework_round > _MAX_REWORK_ROUNDS:
            rework_exhausted = True   # terminal route -> RevOps lead
    else:
        result["missing_fields"] = []
        result["intake_status"] = "complete"

    result["is_complete"] = is_complete
    result["rework_round"] = rework_round
    result["rework_exhausted"] = rework_exhausted

    # ── Pricing floor (only meaningful for a complete deal) ──
    total_cogs, total_list, regulated = _recompute_costs(line_items)
    discount_pct = max(0.0, min(1.0, _as_float(result.get("discount_pct"))))
    discounted_list = total_list * (1.0 - discount_pct)
    post_margin = ((discounted_list - total_cogs) / discounted_list) if discounted_list > 0 else 0.0

    result["line_items"] = line_items
    result["total_cogs_cents"] = total_cogs
    result["total_list_cents"] = total_list
    result["discount_pct"] = round(discount_pct, 4)
    result["gross_margin_pct"] = round(post_margin, 4)   # POST-discount — drives the matrix
    result["tier"] = store.tier_for_discount(discount_pct)
    result["has_regulated_sku"] = regulated
    result["pricing_floor_applied"] = True

    # Stash the full deal pre-gate so the drafter/issuer recover it after the
    # human approval boundary drops the chain payload.
    if sid:
        stash_put(sid, {
            "rfq_id": result.get("rfq_id", ""),
            "customer_id": customer_id,
            "segment": result.get("segment", ""),
            "line_items": line_items,
            "total_cogs_cents": total_cogs,
            "total_list_cents": total_list,
            "discount_pct": result["discount_pct"],
            "gross_margin_pct": result["gross_margin_pct"],
            "tier": result["tier"],
            "rework_round": rework_round,
        })

    if not is_complete:
        logger.info(f"[cass] completeness floor: incomplete "
                    f"(round {rework_round}, exhausted={rework_exhausted}) missing={result['missing_fields']}")
    else:
        logger.info(f"[cass] priced {result.get('rfq_id','?')}: list={total_list} "
                    f"discount={discount_pct:.0%} margin={post_margin:.0%} tier={result['tier']}")
    return result


@chain(enforce_pricing_floor)
async def cass_shaper_agent(llm_response: Any, input_data: dict, context: dict) -> dict:
    """Return the model's shaped deal; the floor recomputes + fails closed."""
    out = llm_response if isinstance(llm_response, dict) else {}
    # Normalise to the yields contract so downstream conditions never read a
    # missing field (conditions fail closed on absence — nuance #14).
    out.setdefault("rfq_id", "")
    out.setdefault("customer_id", "")
    out.setdefault("segment", "")
    out.setdefault("line_items", (input_data or {}).get("line_items", []) if isinstance(input_data, dict) else [])
    out.setdefault("discount_pct", 0)
    out.setdefault("rationale", "")
    out.setdefault("deal_desk_briefing", "")
    out.setdefault("total_cogs_cents", 0)
    out.setdefault("total_list_cents", 0)
    out.setdefault("gross_margin_pct", 0)
    out.setdefault("tier", "")
    out.setdefault("has_regulated_sku", False)
    out.setdefault("is_complete", False)
    out.setdefault("missing_fields", [])
    out.setdefault("intake_status", "incomplete")
    out.setdefault("rework_round", 0)
    out.setdefault("rework_exhausted", False)
    out.setdefault("pricing_floor_applied", False)
    return out
