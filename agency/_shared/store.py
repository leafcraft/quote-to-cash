"""Dev-mode store for the Quote-to-Cash desk.

Lets the FULL chain (intake → cost → discount → approval → quote → audit,
plus the compliance and cross-sell side flows) run end-to-end BEFORE any
connector is wired. Everything here stands in for a real system of record:

  * RFQs                     → your CPQ / CRM (Salesforce CPQ, HubSpot)
  * per-SKU cost + list      → your CPQ/ERP price book (NetSuite, SAP)
  * discount policy table    → your deal-desk / pricing-ops policy
  * deal history             → your CRM (won/lost, last discount given)
  * competitor pricing       → your price-intelligence stack (Klue/Crayon)

In production you replace the read calls with the matching MCP / n8n
connectors; the SHAPE the rest of the mesh reads stays the same — these
function signatures are the contract. Setting the env vars (CPQ_MCP_URL,
CLM_MCP_URL, N8N_*) alone does nothing until you wire the calls here.

Single-process JSON files under ./data/, lazily seeded on first read so
the demo works out of the box. Swap for Redis/Postgres at multi-replica.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_DIR = Path("./data")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(kind: str) -> Path:
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / f"{kind}.json"


def _load(kind: str) -> dict[str, Any]:
    p = _path(kind)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _save(kind: str, data: dict[str, Any]) -> None:
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
        data = {item[key]: item for item in seed}
    else:
        data = {"items": list(seed)}
    _save(kind, data)
    return data


# ── Seed data ────────────────────────────────────────────────────────
# A realistic mid-market RFQ + price book + discount policy + deal
# history + competitor pricing so the chain has real material on day 0.

# The sample RFQ — 40 Pro seats + onboarding, the README's "Priya" deal.
_RFQ_SEED: list[dict[str, Any]] = [
    {
        "rfq_id": "RFQ-2026-0042",
        "customer_id": "ACME-4471",
        "received_at_utc": "2026-06-20T09:14:00Z",
        "target_close": "2026-06-30",
        "segment": "mid_market",
        "line_items": [
            {"sku": "PRO-SEAT", "qty": 40, "list_price_cents": 120000},
            {"sku": "ONBOARD-STD", "qty": 1, "list_price_cents": 500000},
        ],
    }
]

# Price book — per-SKU UNIT cost + UNIT list, in cents. The cost floor
# recomputes COGS / list / margin from these; the LLM cannot invent a
# cheaper cost basis to manufacture a healthier margin.
#   unit_cost_cents = our cost to deliver one unit
#   unit_list_cents = rack/list price for one unit
_PRICE_BOOK_SEED: dict[str, Any] = {
    "PRO-SEAT":    {"unit_cost_cents": 42000,  "unit_list_cents": 120000, "regulated": False},
    "ENT-SEAT":    {"unit_cost_cents": 70000,  "unit_list_cents": 220000, "regulated": False},
    "ONBOARD-STD": {"unit_cost_cents": 180000, "unit_list_cents": 500000, "regulated": False},
    "ONBOARD-PRE": {"unit_cost_cents": 420000, "unit_list_cents": 1200000, "regulated": False},
    "ADDON-SSO":   {"unit_cost_cents": 15000,  "unit_list_cents": 60000,  "regulated": False},
    "ADDON-HIPAA": {"unit_cost_cents": 90000,  "unit_list_cents": 300000, "regulated": True},
    "_default":    {"unit_cost_cents": 0,      "unit_list_cents": 0,      "regulated": False},
}

# Discount policy table — the deal-desk policy a sales controller owns.
# The discount floor reads these bands to derive the tier deterministically
# and clamps to the segment's max self-serve discount.
_DISCOUNT_POLICY_SEED: dict[str, Any] = {
    "margin_floor_pct": 0.20,            # below → CFO (matches the wire matrix)
    "tier_bands": [                       # upper bound (inclusive) → tier name
        {"max_discount_pct": 0.10, "tier": "tier_1"},
        {"max_discount_pct": 0.20, "tier": "tier_2"},
        {"max_discount_pct": 0.30, "tier": "tier_3"},
        {"max_discount_pct": 1.00, "tier": "tier_4"},   # > 30% → CFO
    ],
    # Soft guidance the strategist sees; the floor still clamps to 0..1.
    "segment_guidance": {
        "mid_market":   {"typical_discount_pct": 0.12, "max_unreviewed_pct": 0.20},
        "enterprise":   {"typical_discount_pct": 0.18, "max_unreviewed_pct": 0.30},
        "smb":          {"typical_discount_pct": 0.08, "max_unreviewed_pct": 0.10},
        "_default":     {"typical_discount_pct": 0.10, "max_unreviewed_pct": 0.15},
    },
}

# Deal history — what the pricing strategist reasons over (CRM).
_DEAL_HISTORY_SEED: list[dict[str, Any]] = [
    {"customer_id": "ACME-4471", "rfq_id": "RFQ-2025-0188", "outcome": "won",
     "discount_pct": 0.10, "deal_size_cents": 5_200_000, "closed_at": "2025-07-02"},
    {"customer_id": "ACME-4471", "rfq_id": "RFQ-2024-0911", "outcome": "won",
     "discount_pct": 0.08, "deal_size_cents": 3_100_000, "closed_at": "2024-06-19"},
    {"customer_id": "GLOBEX-2210", "rfq_id": "RFQ-2025-0440", "outcome": "lost",
     "discount_pct": 0.25, "deal_size_cents": 18_000_000, "closed_at": "2025-09-30",
     "lost_to": "Northstar"},
]

# Competitor pricing signals — from your price-intelligence stack.
_COMPETITOR_SEED: list[dict[str, Any]] = [
    {"sku": "PRO-SEAT", "competitor": "Northstar", "their_unit_cents": 99000,
     "observed_at": "2026-06-15", "note": "aggressive seat pricing in mid-market"},
    {"sku": "ENT-SEAT", "competitor": "Vertex", "their_unit_cents": 240000,
     "observed_at": "2026-06-10", "note": "premium positioning"},
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
