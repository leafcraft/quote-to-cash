"""LLM Agent — cost analyst (deterministic cost/margin floor).

Costs the RFQ's line items, then enforces the firm's cost basis as a
FLOOR the LLM cannot waive:

  * total_cogs_cents and total_list_cents are RECOMPUTED in code from the
    line items × the price book of record (sum of unit_cost × qty and
    unit_list × qty) — the model cannot invent a cheaper cost to
    manufacture a healthier margin (and so dodge a sign-off tier later).
  * gross_margin_pct is RECOMPUTED from those two computed totals.
  * has_regulated_sku is set from the price book — a bundled regulated
    SKU is flagged so the discount strategist (and the compliance gate)
    can route accordingly.

DEV: the cost basis comes from agency/_shared/store.py (a seeded price
book) so the chain runs end-to-end with NO connector wired. PROD: point
the CPQ/ERP MCP server at your price book and have load_price_book read
it (the function signature is the contract); the recompute floor still
applies on top so an upstream typo can't waive a margin floor.

Decorators (bottom-up execution):
  @pre_compose load_price_book — pull per-SKU unit cost + unit list for
      the RFQ's SKUs from the price book of record.
  @chain enforce_cost_floor — recompute COGS / list / margin in code.

auto_discover matches function name 'cost_calculator_agent' to YAML.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, chain, pre_compose

from agency._shared import store

logger = LeafMeshLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "total_cogs_cents": 0,
    "total_list_cents": 0,
    "gross_margin_pct": 0.0,
    "has_regulated_sku": False,
    "cost_floor_applied": False,
    "line_items": [],
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


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _line_items(data: Any) -> list[dict[str, Any]]:
    """Pull line_items from input_data (flat or one level deep)."""
    if isinstance(data, dict):
        li = data.get("line_items")
        if isinstance(li, list):
            return [x for x in li if isinstance(x, dict)]
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("line_items"), list):
                return [x for x in v["line_items"] if isinstance(x, dict)]
    return []


# ── @pre_compose processor ───────────────────────────────────────────
def load_price_book(data: Any, ctx: dict) -> dict[str, Any]:
    """Pull per-SKU unit cost + unit list for the RFQ's SKUs.

    PROD: replace the store.sku_cost lookups with a single call to the
    CPQ/ERP price-book MCP tool (${CPQ_MCP_URL})."""
    items = _line_items(data)
    skus = sorted({str(li.get("sku", "")) for li in items if li.get("sku")})
    book = {sku: store.sku_cost(sku) for sku in skus}
    return {"line_items": items, "price_book": book, "skus": skus}


# ── @chain step (the deterministic cost/margin floor) ────────────────
async def enforce_cost_floor(result: dict, ctx: dict) -> dict[str, Any]:
    """Recompute COGS / list / margin from the line items × price book.

    Floor — runs regardless of what the LLM returned; the cost basis
    gates a downstream human sign-off, so it is never the model's
    arithmetic."""
    if not isinstance(result, dict):
        result = {}
    pctx = _prepared(ctx)
    book = pctx.get("price_book") or {}
    items = pctx.get("line_items") or result.get("line_items") or []

    total_cogs = 0
    total_list = 0
    regulated = False
    for li in items:
        if not isinstance(li, dict):
            continue
        sku = str(li.get("sku", ""))
        qty = _as_int(li.get("qty", li.get("quantity", 0)))
        ref = book.get(sku) or store.sku_cost(sku)
        unit_cost = _as_int(ref.get("unit_cost_cents", 0))
        # Prefer the price book's list; fall back to the RFQ's stated list.
        unit_list = _as_int(ref.get("unit_list_cents", 0)) or \
            _as_int(li.get("list_price_cents", 0))
        total_cogs += unit_cost * qty
        total_list += unit_list * qty
        if ref.get("regulated"):
            regulated = True

    result["total_cogs_cents"] = total_cogs
    result["total_list_cents"] = total_list
    result["gross_margin_pct"] = (
        round((total_list - total_cogs) / total_list, 4) if total_list > 0 else 0.0
    )
    result["has_regulated_sku"] = bool(regulated)
    result["cost_floor_applied"] = True
    result["line_items"] = items

    logger.info(
        f"enforce_cost_floor — cogs={total_cogs} list={total_list} "
        f"margin={result['gross_margin_pct']} regulated={regulated}"
    )
    return result


@pre_compose(context_processor=load_price_book)
@chain(enforce_cost_floor)
async def cost_calculator_agent(llm_response, input_data: dict,
                                context: dict) -> dict[str, Any]:
    """Surface a costing pass; the chain enforces the deterministic floor.

    The LLM's numbers are advisory only — enforce_cost_floor recomputes
    everything from the price book, so a bad parse still yields a correct
    cost basis."""
    parsed = _parse_json(llm_response)
    pctx = _prepared(context)
    out = {**_DEFAULTS}
    out["line_items"] = pctx.get("line_items") or _line_items(input_data)
    # Carry the LLM's draft numbers through; the floor overwrites them.
    out["total_cogs_cents"] = _as_int(parsed.get("total_cogs_cents", 0))
    out["total_list_cents"] = _as_int(parsed.get("total_list_cents", 0))
    return out
