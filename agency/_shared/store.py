"""Dev store — a working stand-in for the systems of record, so the
Quote-to-Cash pod runs day-0 with NO connector wired.

This is a DEV STAND-IN, not a system of record. In production every read
here comes from a real system:

  * price book (per-SKU cost + list)  -> your CPQ / ERP (Salesforce CPQ,
    NetSuite, SAP) via the commented `mcp:` block on cass_shaper_agent
  * deal history (won / lost, prior discounts) -> your CRM
  * competitor pricing signals         -> your price-intelligence stack
                                          (Klue / Crayon / a scraper)
  * open invoices + payment status     -> your billing / AR system
                                          (Stripe, NetSuite, Chargebee)

**The function signatures are the contract you swap real systems into** —
the mesh does not change. Nothing here is a system of record: it holds
seed data (so the pod has something real to read) and appends the pod's
own outbox + append-only ledger under ./data. Per the doctrine
(where-data-lives): a real store enforces its own invariants — this file
is dev only. A read with genuinely nothing to return announces itself
(`available: false`), never a synthetic-but-confident empty success.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_DIR = Path("./data")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(kind: str) -> Path:
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / f"{kind}.json"


def _load(kind: str) -> Any:
    p = _path(kind)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _save(kind: str, data: Any) -> None:
    p = _path(kind)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)


def _seeded(kind: str, seed: Any, key: str | None = None) -> Any:
    """Load a store kind, lazily writing the seed on first access."""
    data = _load(kind)
    if data:
        return data
    if isinstance(seed, dict):
        data = dict(seed)
    elif key:
        data = {item[key]: dict(item) for item in seed}
    else:
        data = {"items": list(seed)}
    _save(kind, data)
    return data


# ── Seed data ────────────────────────────────────────────────────────
# A realistic mid-market RFQ + price book + discount policy + deal history
# + competitor pricing + open invoices, so the whole quote-to-CASH chain
# (shape -> approve -> draft -> issue -> invoice -> dun) has real material
# on day 0.

# The sample RFQ — 40 Pro seats + onboarding, the README's "ACME" deal.
_RFQ_SEED: list[dict[str, Any]] = [
    {
        "rfq_id": "RFQ-2026-0042",
        "customer_id": "ACME-4471",
        "received_at_utc": "2026-10-28T09:14:00Z",
        "target_close": "2026-11-20",
        "segment": "mid_market",
        "line_items": [
            {"sku": "PRO-SEAT", "qty": 40, "list_price_cents": 120000},
            {"sku": "ONBOARD-STD", "qty": 1, "list_price_cents": 500000},
        ],
    }
]

# Price book — per-SKU UNIT cost + UNIT list, in cents. The pricing floor
# recomputes COGS / list / margin from these; the LLM cannot invent a
# cheaper cost basis to manufacture a healthier margin.
_PRICE_BOOK_SEED: dict[str, Any] = {
    "PRO-SEAT":    {"unit_cost_cents": 42000,  "unit_list_cents": 120000,  "regulated": False},
    "ENT-SEAT":    {"unit_cost_cents": 70000,  "unit_list_cents": 220000,  "regulated": False},
    "ONBOARD-STD": {"unit_cost_cents": 180000, "unit_list_cents": 500000,  "regulated": False},
    "ONBOARD-PRE": {"unit_cost_cents": 420000, "unit_list_cents": 1200000, "regulated": False},
    "ADDON-SSO":   {"unit_cost_cents": 15000,  "unit_list_cents": 60000,   "regulated": False},
    "ADDON-HIPAA": {"unit_cost_cents": 90000,  "unit_list_cents": 300000,  "regulated": True},
    "_default":    {"unit_cost_cents": 0,      "unit_list_cents": 0,       "regulated": False},
}

# Discount policy table — the deal-desk policy a sales controller owns.
# The pricing floor reads these bands to derive the tier deterministically.
_DISCOUNT_POLICY_SEED: dict[str, Any] = {
    "margin_floor_pct": 0.20,             # below -> CFO (matches the wire matrix)
    "tier_bands": [                        # upper bound (inclusive) -> tier name
        {"max_discount_pct": 0.10, "tier": "tier_1"},
        {"max_discount_pct": 0.20, "tier": "tier_2"},
        {"max_discount_pct": 0.30, "tier": "tier_3"},
        {"max_discount_pct": 1.00, "tier": "tier_4"},   # > 30% -> CFO
    ],
    "segment_guidance": {
        "mid_market": {"typical_discount_pct": 0.12, "max_unreviewed_pct": 0.20},
        "enterprise": {"typical_discount_pct": 0.18, "max_unreviewed_pct": 0.30},
        "smb":        {"typical_discount_pct": 0.08, "max_unreviewed_pct": 0.10},
        "_default":   {"typical_discount_pct": 0.10, "max_unreviewed_pct": 0.15},
    },
}

# Deal history — what the deal shaper reasons over (CRM). Customers and
# competitors are fictional. Every invoice below traces to a WON deal here:
# invoice amount = deal_size_cents x (1 - discount_pct).
_DEAL_HISTORY_SEED: list[dict[str, Any]] = [
    {"customer_id": "ACME-4471", "rfq_id": "RFQ-2025-0188", "outcome": "won",
     "discount_pct": 0.10, "deal_size_cents": 5_200_000, "closed_at": "2025-07-02"},
    {"customer_id": "ACME-4471", "rfq_id": "RFQ-2024-0911", "outcome": "won",
     "discount_pct": 0.08, "deal_size_cents": 3_100_000, "closed_at": "2024-06-19"},
    {"customer_id": "GLOBEX-2210", "rfq_id": "RFQ-2025-0372", "outcome": "won",
     "discount_pct": 0.10, "deal_size_cents": 15_000_000, "closed_at": "2025-06-18"},
    {"customer_id": "GLOBEX-2210", "rfq_id": "RFQ-2025-0440", "outcome": "lost",
     "discount_pct": 0.25, "deal_size_cents": 18_000_000, "closed_at": "2025-09-30",
     "lost_to": "Quillon"},
    {"customer_id": "INITECH-9001", "rfq_id": "RFQ-2026-0011", "outcome": "won",
     "discount_pct": 0.125, "deal_size_cents": 2_400_000, "closed_at": "2026-10-16"},
    {"customer_id": "HOOLI-5567", "rfq_id": "RFQ-2025-0090", "outcome": "won",
     "discount_pct": 0.025, "deal_size_cents": 8_000_000, "closed_at": "2025-04-28"},
]

# Competitor pricing signals — from your price-intelligence stack.
_COMPETITOR_SEED: list[dict[str, Any]] = [
    {"sku": "PRO-SEAT", "competitor": "Quillon", "their_unit_cents": 99000,
     "observed_at": "2026-08-15", "note": "aggressive seat pricing in mid-market"},
    {"sku": "ENT-SEAT", "competitor": "Corvane", "their_unit_cents": 240000,
     "observed_at": "2026-08-10", "note": "premium positioning"},
]

# Open invoices — the CASH side (Net 30 from issue). Two are already overdue
# so the dunning sweep has real work to fan out across billing copies on
# day 0; one is open (not yet due); one is paid (must never be dunned).
_INVOICE_SEED: list[dict[str, Any]] = [
    {"invoice_id": "INV-2026-0301", "quote_id": "Q-RFQ-2025-0188",
     "customer_id": "ACME-4471", "amount_cents": 4_680_000,
     "issued_at": "2026-07-05", "due_date": "2026-08-04",
     "status": "overdue", "dunning_stage": 1, "claimed_by": ""},
    {"invoice_id": "INV-2026-0288", "quote_id": "Q-RFQ-2025-0372",
     "customer_id": "GLOBEX-2210", "amount_cents": 13_500_000,
     "issued_at": "2026-06-20", "due_date": "2026-07-20",
     "status": "overdue", "dunning_stage": 2, "claimed_by": ""},
    {"invoice_id": "INV-2026-0312", "quote_id": "Q-RFQ-2026-0011",
     "customer_id": "INITECH-9001", "amount_cents": 2_100_000,
     "issued_at": "2026-10-20", "due_date": "2026-11-19",
     "status": "open", "dunning_stage": 0, "claimed_by": ""},
    {"invoice_id": "INV-2026-0260", "quote_id": "Q-RFQ-2025-0090",
     "customer_id": "HOOLI-5567", "amount_cents": 7_800_000,
     "issued_at": "2026-05-01", "due_date": "2026-05-31",
     "status": "paid", "dunning_stage": 0, "claimed_by": ""},
]


# ── RFQs ──────────────────────────────────────────────────────────────
def get_rfq(rfq_id: str) -> dict[str, Any]:
    """Captured RFQ record ({} if unknown). PROD: CPQ/CRM lookup."""
    if not rfq_id:
        return {}
    return _seeded("rfqs", _RFQ_SEED, key="rfq_id").get(rfq_id, {})


def sample_rfq() -> dict[str, Any]:
    """The seeded demo RFQ — the README's copy-paste entry payload."""
    return dict(_RFQ_SEED[0])


# ── Price book (cost basis) ───────────────────────────────────────────
def sku_cost(sku: str) -> dict[str, Any]:
    """Per-SKU unit cost + unit list ({} fields default to 0 / unknown)."""
    book = _seeded("price_book", _PRICE_BOOK_SEED)
    return book.get(sku) or book.get("_default", {})


def price_book() -> dict[str, Any]:
    return _seeded("price_book", _PRICE_BOOK_SEED)


def is_regulated(sku: str) -> bool:
    return bool(sku_cost(sku).get("regulated"))


# ── Discount policy table ─────────────────────────────────────────────
def discount_policy() -> dict[str, Any]:
    return _seeded("discount_policy", _DISCOUNT_POLICY_SEED)


def margin_floor_pct() -> float:
    return float(discount_policy().get("margin_floor_pct", 0.20))


def tier_for_discount(discount_pct: float) -> str:
    """Deterministic tier from the policy bands (the floor uses this)."""
    try:
        d = max(0.0, min(1.0, float(discount_pct)))
    except (TypeError, ValueError):
        d = 0.0
    for band in discount_policy().get("tier_bands", []):
        if d <= float(band.get("max_discount_pct", 1.0)):
            return str(band.get("tier", "tier_4"))
    return "tier_4"


def segment_guidance(segment: str) -> dict[str, Any]:
    g = discount_policy().get("segment_guidance", {})
    return g.get((segment or "").strip().lower()) or g.get("_default", {})


# ── Deal history ──────────────────────────────────────────────────────
def deal_history(customer_id: str) -> list[dict[str, Any]]:
    rows = _seeded("deal_history", _DEAL_HISTORY_SEED, key="rfq_id").values()
    cid = (customer_id or "").strip()
    return [r for r in rows if not cid or r.get("customer_id") == cid]


def record_deal(row: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        data = _seeded("deal_history", _DEAL_HISTORY_SEED, key="rfq_id")
        rid = row.get("rfq_id") or f"RFQ-{_now()}"
        row["rfq_id"] = rid
        row["recorded_at"] = _now()
        data[rid] = {**data.get(rid, {}), **row}
        _save("deal_history", data)
        return data[rid]


# ── Competitor pricing ────────────────────────────────────────────────
def competitor_pricing(skus: list[str] | None = None) -> list[dict[str, Any]]:
    rows = list(_seeded("competitor_pricing", _COMPETITOR_SEED, key="sku").values())
    if not skus:
        return rows
    want = {str(s) for s in skus}
    return [r for r in rows if r.get("sku") in want]


# ── Invoices (the CASH side) ──────────────────────────────────────────
def _days_overdue(due_date: str) -> int:
    try:
        due = datetime.fromisoformat(str(due_date)).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 0
    return max(0, (datetime.now(timezone.utc) - due).days)


def open_invoices(customer_id: str | None = None) -> list[dict[str, Any]]:
    """Every non-paid invoice (open + overdue), annotated with days_overdue.
    PROD: your billing/AR system."""
    rows = list(_seeded("invoices", _INVOICE_SEED, key="invoice_id").values())
    out = []
    for r in rows:
        if str(r.get("status")) == "paid":
            continue
        if customer_id and r.get("customer_id") != customer_id:
            continue
        r = dict(r)
        r["days_overdue"] = _days_overdue(r.get("due_date", ""))
        out.append(r)
    return out


def invoice_status(invoice_id: str) -> str:
    """Current status of an invoice ('paid' | 'overdue' | 'open' | 'unknown').
    The billing floor calls this to refuse to dun a paid invoice."""
    row = _seeded("invoices", _INVOICE_SEED, key="invoice_id").get(str(invoice_id))
    return str(row.get("status")) if row else "unknown"


def mark_invoice(invoice_id: str, **fields: Any) -> dict[str, Any]:
    """Update an invoice's fields (status, dunning_stage, claimed_by).
    PROD: a write to your billing system."""
    with _LOCK:
        data = _seeded("invoices", _INVOICE_SEED, key="invoice_id")
        row = data.get(str(invoice_id))
        if not row:
            return {}
        row.update(fields)
        row["updated_at"] = _now()
        data[str(invoice_id)] = row
        _save("invoices", data)
        return dict(row)


def claim_billing_work(kind: str, count: int, claim_token: str) -> list[dict[str, Any]]:
    """Atomically claim up to `count` disjoint billing items for one worker.

    Fan-out primitive for `scaling.copies.count: N` on billing_agent: each parallel
    copy calls this under the shared lock and receives a DISJOINT slice, so
    N copies split a backlog instead of all dunning the same invoices. For
    a single-item trigger (one accepted quote to invoice) exactly one copy
    wins the item and the rest get [] — the claim is what makes fan-out
    idempotent in BOTH modes.

    kind='dun'     -> overdue invoices not yet claimed
    kind='invoice' -> open invoices past due-soon that need an invoice pass
    """
    kind = (kind or "dun").strip().lower()
    try:
        count = max(1, min(50, int(count)))
    except (TypeError, ValueError):
        count = 1
    with _LOCK:
        data = _seeded("invoices", _INVOICE_SEED, key="invoice_id")
        claimed: list[dict[str, Any]] = []
        for inv_id, row in data.items():
            if len(claimed) >= count:
                break
            if row.get("claimed_by"):
                continue
            status = str(row.get("status"))
            if kind == "dun" and status != "overdue":
                continue
            if kind == "invoice" and status != "open":
                continue
            row["claimed_by"] = claim_token
            row["claimed_at"] = _now()
            data[inv_id] = row
            r = dict(row)
            r["days_overdue"] = _days_overdue(r.get("due_date", ""))
            claimed.append(r)
        if claimed:
            _save("invoices", data)
        return claimed


# ── Outbox (the pod's sends) + append-only ledger ─────────────────────
def record_outbox(entry: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        outbox = _load("outbox") or []
        rec = {"recorded_at": _now(), **entry}
        outbox.append(rec)
        _save("outbox", outbox)
    return rec


def append_ledger(entry: dict[str, Any]) -> dict[str, Any]:
    """Append-only deal/cash ledger (dev mirror of the WORM sink)."""
    with _LOCK:
        ledger = _load("qtc_ledger") or []
        rec = {"recorded_at": _now(), **entry}
        ledger.append(rec)
        _save("qtc_ledger", ledger)
    return rec


# ── Finisher dev-store fallback (post-issue record) ───────────────────
def record_issued_quote(quote: dict[str, Any]) -> dict[str, Any]:
    """Record an issued quote so the chain is observable with NO CPQ wired.
    PROD: your CPQ is the record; this becomes a no-op fallback."""
    with _LOCK:
        data = _load("issued_quotes") or {}
        qid = str(quote.get("quote_id") or f"Q-{_now()}")
        data[qid] = {
            "quote_id": qid,
            "rfq_id": quote.get("rfq_id", ""),
            "customer_id": quote.get("customer_id", ""),
            "tier": quote.get("tier", ""),
            "approved_by": quote.get("approved_by", ""),
            "total_cents": quote.get("total_cents", 0),
            "valid_until": quote.get("valid_until", ""),
            "issued_at": quote.get("issued_at", ""),
            "artifact_path": quote.get("artifact_path", ""),
        }
        _save("issued_quotes", data)
        return data[qid]
