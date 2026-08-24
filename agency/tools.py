"""Global tools for the Quote-to-Cash pod.

These are the day-0 tool surface the specialists call, in the turn, to PULL
what they need from the systems of record. Each reads the dev store (seed
data) so the pod runs with no connector wired, and **each announces
itself**: when there is no real source and no seed, it returns
`available: false` and says why — never a synthetic success that looks like
a real read. To go live, wire the CPQ/ERP/billing `mcp:` block on the
agent (each named action becomes its own tool); these dev tools are the
fallback contract.

Registered by import (`import agency.tools` in main.py) BEFORE `from_yaml`,
so the @global_tool decorators run before the mesh binds tool categories.
"""
from __future__ import annotations

import os

from leafmesh import global_tool, LeafMeshLogger

try:
    from ._shared import store
except ImportError:  # pragma: no cover — direct-run fallback
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _shared import store  # type: ignore

logger = LeafMeshLogger(__name__)


def _cpq_wired() -> bool:
    """True if a real CPQ/ERP price-book connector is configured."""
    return bool(os.getenv("CPQ_MCP_URL"))


def _billing_wired() -> bool:
    """True if a real billing/AR connector is configured."""
    return bool(os.getenv("BILLING_MCP_URL"))


# ── Deal-shaping tools (cass_shaper_agent, category: shaping) ─────────
@global_tool(category="shaping")
def read_price_book(skus: str = "") -> dict:
    """Read per-SKU unit cost + unit list price (cents) from the price book.

    Returns the cost basis the deal shaper prices against. Reads the seed
    price book when no real CPQ/ERP is wired; announces `available: false`
    only if there is genuinely nothing to read.

    Args:
        skus: Comma-separated SKU codes to price (empty = the whole book).
    """
    book = store.price_book()
    if not book:
        return {"available": False, "reason": "no price book seeded; wire CPQ_MCP_URL"}
    wanted = [s.strip() for s in str(skus).split(",") if s.strip()]
    if wanted:
        rows = {s: store.sku_cost(s) for s in wanted}
        missing = [s for s in wanted if not (store.price_book().get(s))]
        if missing and _cpq_wired():
            return {"available": False,
                    "reason": f"CPQ wired but returned no price for {missing}"}
        return {"available": True, "skus": rows}
    logger.info("read_price_book full-book")
    return {"available": True, "skus": {k: v for k, v in book.items() if k != "_default"}}


@global_tool(category="shaping")
def read_deal_history(customer_id: str) -> dict:
    """Read this customer's prior deals (won/lost, discounts given) so the
    shaper prices against the relationship, not a cold inbound.

    Args:
        customer_id: The account to read deal history for (e.g. "ACME-4471").
    """
    rows = store.deal_history(str(customer_id).strip())
    return {"available": True, "customer_id": customer_id, "deals": rows}


@global_tool(category="shaping")
def read_competitor_prices(skus: str = "") -> dict:
    """Read competitor pricing signals for the requested SKUs, so a discount
    can answer a real competitive threat rather than a guess.

    Args:
        skus: Comma-separated SKU codes (empty = all tracked SKUs).
    """
    wanted = [s.strip() for s in str(skus).split(",") if s.strip()]
    rows = store.competitor_pricing(wanted or None)
    if not rows and _cpq_wired():
        return {"available": False, "reason": "price-intelligence wired but returned nothing"}
    return {"available": True, "signals": rows}


# ── Billing / collections tools (billing_agent, category: billing) ───
@global_tool(category="billing")
def read_open_invoices(customer_id: str = "") -> dict:
    """Read open + overdue invoices (with days_overdue) for the CASH side.

    Args:
        customer_id: Scope to one account, or empty for every open invoice.
    """
    rows = store.open_invoices(str(customer_id).strip() or None)
    if not rows and _billing_wired():
        return {"available": False, "reason": "billing system wired but returned nothing"}
    return {"available": True, "invoices": rows, "count": len(rows)}


@global_tool(category="billing")
def claim_billing_work(kind: str, count: int = 5, claim_token: str = "") -> dict:
    """Atomically claim a DISJOINT batch of billing work for this worker copy.

    The fan-out primitive for `instances: N` on billing_agent — each parallel
    copy claims its own slice so copies never dun the same invoice twice.
    For a single accepted quote, exactly one copy wins it and the rest get [].

    Args:
        kind: "dun" (overdue invoices) or "invoice" (open invoices to bill).
        count: Max items this copy should claim (1-50).
        claim_token: A per-copy id so the claim is attributable and idempotent.
    """
    token = str(claim_token).strip() or f"worker-{os.getpid()}-{id(kind)}"
    batch = store.claim_billing_work(str(kind), int(count or 5), token)
    logger.info(f"claim_billing_work kind={kind} claimed={len(batch)} token={token}")
    return {"available": True, "claimed": batch, "count": len(batch), "claim_token": token}
