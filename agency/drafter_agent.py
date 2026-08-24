"""Drafter — Quote Drafter.

auto_discover matches `drafter_agent`. The drafter runs AFTER a human tier
approves the deal: it assembles the quote body (pricing table, terms,
validity, next steps) and renders a DRAFT to ./out, then hands the deal to
the quote_issuer (the finisher) which produces the ISSUED artifact. It is
deliberately SEPARATE from the issuer (the writer is not the actuator).

@chain enforce_validity_floor — the deterministic floor a prompt can't
waive: validity is CAPPED by the deal's discount tier (a deeper discount
gets a shorter shelf life), recovered from the per-session stash so the cap
stands on the real tier even though the human gate dropped the chain
payload. The drafter never auto-sends — it assembles; the issuer issues.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from leafmesh import LeafMeshLogger, chain

try:
    from ._shared import store
    from ._shared.session_stash import resolve_session_id, stash_get
except ImportError:  # pragma: no cover
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _shared import store  # type: ignore
    from _shared.session_stash import resolve_session_id, stash_get  # type: ignore

logger = LeafMeshLogger(__name__)

_OUT_DIR = Path("./out")

# Validity cap (days) by tier — deeper discount, shorter shelf life.
_VALIDITY_CAP = {"tier_1": 45, "tier_2": 30, "tier_3": 21, "tier_4": 14}
_DEFAULT_CAP = 30


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _fmt(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _render_draft(result: dict, deal: dict) -> str:
    """Render the draft quote to ./out (Markdown). Returns the path."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    ident = str(result.get("rfq_id") or deal.get("rfq_id") or "quote")
    path = _OUT_DIR / f"{ident}_quote_draft.md"
    lines = [f"# Quote draft — {ident}", "",
             f"- **Customer:** {result.get('customer_id') or deal.get('customer_id') or '—'}",
             f"- **Discount tier:** {result.get('tier') or deal.get('tier') or '—'}",
             f"- **Validity:** {result.get('validity_days')} days",
             "", "## Line items", "",
             "| SKU | Qty | Unit list |", "|-----|-----|-----------|"]
    for li in deal.get("line_items") or []:
        if not isinstance(li, dict):
            continue
        lines.append(f"| {li.get('sku','?')} | {_as_int(li.get('qty'))} | "
                     f"{_fmt(_as_int(li.get('list_price_cents')))} |")
    lines += ["", "## Terms", "", "Net 30. System-drafted from approved pricing.",
              "", "_Draft — awaiting issuance by the quote issuer._"]
    if result.get("quote_body"):
        lines += ["", "## Narrative", "", str(result["quote_body"])]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def enforce_validity_floor(result: Any, context: dict) -> dict:
    """Fail closed: cap validity by the deal's tier and render the draft."""
    result = result if isinstance(result, dict) else {}
    context = context if isinstance(context, dict) else {}

    sid = resolve_session_id(result, context)
    deal = stash_get(sid)
    tier = str(result.get("tier") or deal.get("tier") or "").strip()
    result.setdefault("rfq_id", deal.get("rfq_id", ""))
    result.setdefault("customer_id", deal.get("customer_id", ""))
    result["tier"] = tier

    cap = _VALIDITY_CAP.get(tier, _DEFAULT_CAP)
    requested = _as_int(result.get("validity_days"), cap) or cap
    capped = min(requested, cap)
    result["validity_days"] = capped
    result["validity_floor_applied"] = capped < requested

    result["artifact_path"] = _render_draft(result, deal)
    result["drafted"] = True
    logger.info(f"[drafter] drafted {result.get('rfq_id','?')} tier={tier or '?'} "
                f"validity={capped}d -> {result['artifact_path']}")
    return result


@chain(enforce_validity_floor)
async def drafter_agent(llm_response: Any, input_data: dict, context: dict) -> dict:
    out = llm_response if isinstance(llm_response, dict) else {}
    out.setdefault("quote_body", "")
    out.setdefault("validity_days", 0)
    out.setdefault("tier", "")
    out.setdefault("rfq_id", "")
    out.setdefault("customer_id", "")
    out.setdefault("drafted", False)
    out.setdefault("artifact_path", "")
    out.setdefault("validity_floor_applied", False)
    return out
