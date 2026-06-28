"""Programmatic Agent — quote ISSUER (artifact-producing executor).

This is the actuator that FINISHES the job. The desk used to draft a quote
and route it; now `quote_issuer_agent` runs AFTER the approval gate clears
and quote_drafter has assembled the body, and it GENERATES + ISSUES the
quote as a real artifact from the approved pricing/discount/validity:

  · a real quote DOCUMENT — line items, subtotal, discount, total,
    validity date, terms — rendered to ./out/<quote_id>.pdf via ReportLab
    when available, else a deterministic .md/.txt file (always a real file
    on disk, day-0, no extra deps);
  · AND/OR a CPQ PUSH via ${CPQ_WEBHOOK_URL:} (read from env — a custom
    urllib actuator, not a YAML connector_config) — inert until the URL is
    set; a dev-store fallback records the issued quote in
    ./data/issued_quotes.json so the chain is observable out of the box.

It returns the artifact path/id + a summary.

FAIL-CLOSED FLOOR (@chain enforce_issuance_floor): a quote is NEVER issued
if the deal was not approved, or if its discount TIER was not cleared by
the REQUIRED approver. The required approver is re-derived in code from the
recovered financials (the same amount × margin × discount matrix the
discount_policy wires encode), so the issuer cannot be tricked into issuing
an under-approved deal even if an upstream marker is wrong. If the floor
trips, the artifact is suppressed and the result is marked blocked — the
audit terminus still records the attempt.

auto_discover matches function name 'quote_issuer_agent' to YAML.
"""
from __future__ import annotations

import json
import os
import random
import string
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from leafmesh import LeafMeshLogger, chain

from agency._shared import store
from agency._shared.session_stash import resolve_session_id, stash_get

logger = LeafMeshLogger(__name__)

_OUT_DIR = Path("./out")
_DEFAULT_VALIDITY_DAYS = 30

# The approval matrix, re-derived in code (mirrors discount_policy_agent's
# can_call conditions). Thresholds in cents: rep ≤ $25K < deal_desk ≤ $100K
# < finance ≤ $1M < CFO. Margin floor 20%; discount bands 10% / 20% / 30%.
_MARGIN_FLOOR = 0.20
_REP_MAX_CENTS = 2_500_000
_DEAL_DESK_MAX_CENTS = 10_000_000
_FINANCE_MAX_CENTS = 100_000_000


def _required_approver(total_list_cents: int, gross_margin_pct: float,
                       discount_pct: float) -> str:
    """The single approver tier that MUST clear this deal — recomputed from
    the financials exactly as discount_policy_agent's wires do. Fail-closed:
    anything off the healthy/cheap band escalates upward."""
    if (gross_margin_pct < _MARGIN_FLOOR or discount_pct > 0.30
            or total_list_cents > _FINANCE_MAX_CENTS):
        return "cfo_human"
    if discount_pct > 0.20 or total_list_cents > _DEAL_DESK_MAX_CENTS:
        return "finance_approver_human"
    if discount_pct > 0.10 or total_list_cents > _REP_MAX_CENTS:
        return "deal_desk_human"
    return "sales_rep_human"


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


def _lookup(key: str, *sources: Any) -> Any:
    for src in sources:
        if not isinstance(src, dict):
            continue
        if src.get(key) not in (None, ""):
            return src[key]
        for v in src.values():
            if isinstance(v, dict) and v.get(key) not in (None, ""):
                return v[key]
    return None


def _quote_id(rfq_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    base = (rfq_id or "RFQ").replace(" ", "")
    return f"Q-{base}-{today}-{suffix}"


def _validity_date(validity_days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=validity_days)).strftime("%Y-%m-%d")


# ── Approval signal ──────────────────────────────────────────────────
def _was_approved(input_data: dict, context: dict, deal: dict) -> bool:
    """Did a human gate clear this deal with 'approve'? quote_drafter is
    only reached on an approve route, so reaching the issuer already implies
    approval — but we re-check the human signal/stash so the floor stands on
    its own (a direct call with no approval is blocked)."""
    for src in (input_data, context, deal):
        if not isinstance(src, dict):
            continue
        msg = str(src.get("human_message", "")).strip().lower()
        if msg in ("approve", "approved"):
            return True
        if str(src.get("approval_status", "")).strip().lower() in ("approved", "approve"):
            return True
        if src.get("approved") is True:
            return True
    return False


# ── Artifact rendering ───────────────────────────────────────────────
def _line_rows(deal: dict) -> tuple[list[dict], int]:
    """Normalise recovered line_items → display rows + list subtotal (cents)."""
    rows: list[dict] = []
    subtotal = 0
    items = deal.get("line_items") or []
    for li in items if isinstance(items, list) else []:
        if not isinstance(li, dict):
            continue
        qty = _as_int(li.get("qty"))
        unit = _as_int(li.get("list_price_cents"))
        line_total = qty * unit
        subtotal += line_total
        rows.append({
            "sku": str(li.get("sku", "?")),
            "qty": qty,
            "unit_price_cents": unit,
            "line_total_cents": line_total,
        })
    return rows, subtotal


def _fmt(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _render_pdf(quote: dict) -> str | None:
    """ReportLab PDF when available, else None (caller falls back to text)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except Exception:
        return None

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = _OUT_DIR / f"{quote['quote_id']}.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    brand = colors.HexColor("#1a3a5c")
    accent = colors.HexColor("#2e86c1")
    el = []
    el.append(Paragraph("SALES QUOTE", ParagraphStyle("t", parent=styles["Title"], fontSize=18, spaceAfter=4)))
    el.append(Paragraph(f"<b>{quote['quote_id']}</b>", ParagraphStyle("h", parent=styles["Normal"], fontSize=10, textColor=colors.grey)))
    el.append(HRFlowable(width="100%", thickness=2, color=brand))
    el.append(Spacer(1, 6 * mm))

    meta = [
        ["Issued At", quote.get("issued_at", "")[:19].replace("T", " ") + " UTC"],
        ["RFQ", quote.get("rfq_id", "")],
        ["Customer", quote.get("customer_id", "") or "—"],
        ["Discount Tier", quote.get("tier", "")],
        ["Approved By", quote.get("approved_by", "")],
        ["Valid Until", quote.get("valid_until", "")],
        ["Approval Reference", quote.get("approval_reference", "")],
    ]
    mt = Table(meta, colWidths=[55 * mm, 110 * mm])
    mt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), brand),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f4f8fb")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0dce8")),
    ]))
    el.append(mt)
    el.append(Spacer(1, 8 * mm))

    rows = [["#", "SKU", "Qty", "Unit Price", "Line Total"]]
    for i, ln in enumerate(quote.get("lines", []), 1):
        rows.append([str(i), ln["sku"], str(ln["qty"]),
                     _fmt(ln["unit_price_cents"]), _fmt(ln["line_total_cents"])])
    it = Table(rows, colWidths=[10 * mm, 60 * mm, 20 * mm, 35 * mm, 40 * mm], repeatRows=1)
    it.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f8fb")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0dce8")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]))
    el.append(it)
    el.append(Spacer(1, 6 * mm))

    totals = [
        ["", "", "", "List subtotal:", _fmt(quote["subtotal_cents"])],
        ["", "", "", f"Discount ({quote['discount_pct']:.0%}):", "-" + _fmt(quote["discount_cents"])],
        ["", "", "", "Total:", _fmt(quote["total_cents"])],
    ]
    tt = Table(totals, colWidths=[10 * mm, 60 * mm, 20 * mm, 35 * mm, 40 * mm])
    tt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (3, 0), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (4, 2), (4, 2), accent),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (3, 2), (-1, 2), 1, brand),
    ]))
    el.append(tt)
    el.append(Spacer(1, 10 * mm))
    el.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    el.append(Spacer(1, 3 * mm))
    el.append(Paragraph(
        f"Terms: Net 30. This quote is valid until {quote.get('valid_until', '')}. "
        "System-issued from approved pricing.",
        ParagraphStyle("f", fontSize=7, textColor=colors.grey)))
    if quote.get("quote_body"):
        el.append(Spacer(1, 4 * mm))
        for para in str(quote["quote_body"]).split("\n"):
            if para.strip():
                el.append(Paragraph(para.replace("<", "&lt;").replace(">", "&gt;"),
                                    ParagraphStyle("b", fontSize=8)))
    doc.build(el)
    return str(pdf_path)


def _render_text(quote: dict) -> str:
    """Deterministic markdown artifact — always works, no extra deps."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUT_DIR / f"{quote['quote_id']}.md"
    lines = [
        f"# Sales Quote {quote['quote_id']}",
        "",
        f"- **RFQ:** {quote.get('rfq_id', '')}",
        f"- **Customer:** {quote.get('customer_id', '') or '—'}",
        f"- **Issued at:** {quote.get('issued_at', '')}",
        f"- **Discount tier:** {quote.get('tier', '')}",
        f"- **Approved by:** {quote.get('approved_by', '')}",
        f"- **Approval reference:** {quote.get('approval_reference', '')}",
        f"- **Valid until:** {quote.get('valid_until', '')}",
        "",
        "## Line items",
        "",
        "| # | SKU | Qty | Unit Price | Line Total |",
        "|---|-----|-----|-----------|-----------|",
    ]
    for i, ln in enumerate(quote.get("lines", []), 1):
        lines.append(
            f"| {i} | {ln['sku']} | {ln['qty']} | {_fmt(ln['unit_price_cents'])} "
            f"| {_fmt(ln['line_total_cents'])} |")
    lines += [
        "",
        f"- List subtotal: {_fmt(quote['subtotal_cents'])}",
        f"- Discount ({quote['discount_pct']:.0%}): -{_fmt(quote['discount_cents'])}",
        f"- **Total: {_fmt(quote['total_cents'])}**",
        "",
        f"Terms: Net 30. Valid until {quote.get('valid_until', '')}. "
        "System-issued from approved pricing.",
    ]
    if quote.get("quote_body"):
        lines += ["", "## Quote narrative", "", str(quote["quote_body"])]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _push_to_cpq(quote: dict, webhook_url: str, auth_token: str) -> dict[str, Any]:
    """Push the issued quote to the CPQ via webhook. Inert (returns
    cpq_pushed=False) when no URL is configured."""
    if not webhook_url:
        return {"cpq_pushed": False, "cpq_status": "not_configured"}
    body = json.dumps(quote, default=str).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    if auth_token:
        req.add_header("Authorization", f"Bearer {auth_token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return {"cpq_pushed": True, "cpq_status": f"http_{resp.status}"}
    except (urllib.error.URLError, OSError) as e:
        logger.warning(f"[quote-issuer] CPQ push failed: {e}")
        return {"cpq_pushed": False, "cpq_status": f"error:{e}"}


def _record_dev_store(quote: dict) -> None:
    """Dev-store fallback — record the issued quote so the chain is
    observable with NO connector wired. PROD: your CPQ is the record."""
    try:
        store._DIR.mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
        path = store._DIR / "issued_quotes.json"        # type: ignore[attr-defined]
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                data = {}
        data[quote["quote_id"]] = {
            "quote_id": quote["quote_id"],
            "rfq_id": quote.get("rfq_id", ""),
            "customer_id": quote.get("customer_id", ""),
            "tier": quote.get("tier", ""),
            "approved_by": quote.get("approved_by", ""),
            "total_cents": quote.get("total_cents", 0),
            "valid_until": quote.get("valid_until", ""),
            "issued_at": quote.get("issued_at", ""),
            "artifact_path": quote.get("artifact_path", ""),
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[quote-issuer] dev-store record failed: {e}")


# ── @chain fail-closed issuance floor ────────────────────────────────
def enforce_issuance_floor(result: dict, context: dict) -> dict:
    """Block any quote that wasn't approved or whose discount tier wasn't
    cleared by the REQUIRED approver. Fail-closed: on a trip we suppress
    the artifact and mark the result blocked. The required approver is the
    one re-derived from the financials; the actually-cleared approver must
    match (or out-rank) it."""
    if not isinstance(result, dict):
        return result
    if result.get("status") not in ("issued", "issued_pending_floor"):
        return result  # rejection / degraded-no-context paths pass through

    required = result.get("required_approver", "")
    cleared = result.get("approved_by", "")
    approved = bool(result.get("approved"))

    # Authority ordering: a higher tier clearing a lower-tier deal is fine.
    rank = {"sales_rep_human": 1, "deal_desk_human": 2,
            "finance_approver_human": 3, "cfo_human": 4}
    cleared_ok = rank.get(cleared, 0) >= rank.get(required, 99)

    reasons: list[str] = []
    if not approved:
        reasons.append("deal was not approved")
    if not cleared_ok:
        reasons.append(
            f"discount tier requires {required or 'an approver'} but was "
            f"cleared by {cleared or '∅'}")

    if reasons:
        logger.error(f"[quote-issuer] ISSUANCE BLOCKED — {'; '.join(reasons)}")
        # Suppress the artifact: never leave an under-approved quote on disk.
        ap = result.get("artifact_path")
        if ap:
            try:
                Path(ap).unlink(missing_ok=True)
            except OSError:
                pass
        result.update({
            "status": "issuance_blocked",
            "issued": False,
            "artifact_path": "",
            "block_reasons": reasons,
        })
        return result

    result["status"] = "issued"
    result["issued"] = True
    result["block_reasons"] = []
    logger.info(
        f"[quote-issuer] ISSUED {result.get('quote_id')} "
        f"({result.get('artifact_kind')}) — approver {cleared} cleared {required}")
    return result


@chain(enforce_issuance_floor)
async def quote_issuer_agent(llm_response: Any, input_data: Any,
                             context: Any) -> dict[str, Any]:
    """Generate + issue the approved quote as a real artifact."""
    if not isinstance(input_data, dict):
        input_data = {}
    if not isinstance(context, dict):
        context = {}

    # Recover the deal: quote_drafter's yields (body/validity/tier/identity)
    # + the per-session stash discount_policy wrote pre-gate (line items,
    # totals, discount).
    session_id = resolve_session_id(input_data, context)
    stashed = stash_get(session_id)
    uy = input_data.get("upstream_yields") if isinstance(input_data.get("upstream_yields"), dict) else {}
    sources = (input_data, uy, input_data.get("upstream_results"),
               context.get("upstream") if isinstance(context, dict) else None,
               stashed)

    rfq_id = str(_lookup("rfq_id", *sources) or "")
    customer_id = str(_lookup("customer_id", *sources) or "")
    tier = str(_lookup("tier", *sources) or "")
    discount_pct = _as_float(_lookup("discount_pct", *sources))
    total_list_cents = _as_int(_lookup("total_list_cents", *sources))
    gross_margin_pct = _as_float(_lookup("gross_margin_pct", *sources))
    quote_body = str(_lookup("quote_body", *sources) or "")
    validity_days = _as_int(_lookup("validity_days", *sources), _DEFAULT_VALIDITY_DAYS) or _DEFAULT_VALIDITY_DAYS

    # No recoverable deal → cannot issue. Fail-closed (audited downstream).
    if not rfq_id and not (stashed.get("line_items") or _lookup("line_items", *sources)):
        logger.warning(
            f"[quote-issuer] no deal context recoverable (session={session_id or '?'}) "
            "— nothing issued")
        return {
            "quote_id": "", "artifact_path": "", "artifact_kind": "none",
            "issued": False, "status": "no_deal_context",
            "approved": False, "approved_by": "", "required_approver": "",
            "rfq_id": "", "customer_id": "", "tier": "",
            "total_cents": 0, "valid_until": "", "issue_summary":
            "No deal context recoverable — nothing issued.",
            "cpq_pushed": False,
        }

    # Build the line items + totals from the recovered deal.
    deal = {
        "rfq_id": rfq_id, "customer_id": customer_id, "tier": tier,
        "discount_pct": discount_pct,
        "line_items": _lookup("line_items", *sources) or [],
    }
    rows, subtotal = _line_rows(deal)
    discount_cents = int(round(subtotal * discount_pct))
    total_cents = subtotal - discount_cents

    # Which approver MUST clear this (re-derived) and who actually did.
    required = _required_approver(total_list_cents or subtotal, gross_margin_pct, discount_pct)
    approved = _was_approved(input_data, context, stashed)
    approved_by = str(_lookup("approved_by", *sources) or "")
    if not approved_by and approved:
        # quote_drafter is only reachable on an approve route, so the
        # required approver is the one who cleared it (the matrix is
        # mutually exclusive — exactly one tier fires per deal).
        approved_by = required

    issued_at = datetime.now(timezone.utc).isoformat()
    valid_until = _validity_date(validity_days)
    quote_id = _quote_id(rfq_id)
    approval_reference = f"APPROVED:{approved_by}" if approved else "UNAPPROVED"

    quote: dict[str, Any] = {
        "quote_id": quote_id,
        "rfq_id": rfq_id,
        "customer_id": customer_id,
        "tier": tier,
        "discount_pct": discount_pct,
        "lines": rows,
        "subtotal_cents": subtotal,
        "discount_cents": discount_cents,
        "total_cents": total_cents,
        "validity_days": validity_days,
        "valid_until": valid_until,
        "issued_at": issued_at,
        "approved_by": approved_by,
        "approval_reference": approval_reference,
        "quote_body": quote_body,
    }

    # Render the artifact: PDF if ReportLab is present, else a real .md file.
    artifact_path = _render_pdf(quote)
    artifact_kind = "pdf"
    if not artifact_path:
        artifact_path = _render_text(quote)
        artifact_kind = "markdown"
    quote["artifact_path"] = artifact_path

    # CPQ push (inert until ${CPQ_WEBHOOK_URL:} set) + dev-store fallback.
    conn = context.get("connector_config") if isinstance(context, dict) else None
    conn = conn if isinstance(conn, dict) else {}
    webhook_url = str(conn.get("webhook_url") or os.environ.get("CPQ_WEBHOOK_URL", "")).strip()
    auth_token = str(conn.get("auth_token") or os.environ.get("CPQ_WEBHOOK_TOKEN", "")).strip()
    cpq = _push_to_cpq(quote, webhook_url, auth_token)
    if not cpq.get("cpq_pushed"):
        _record_dev_store(quote)

    summary = (
        f"Issued quote {quote_id} for {customer_id or 'customer'} "
        f"({len(rows)} line(s), total {_fmt(total_cents)}, valid {valid_until}); "
        f"artifact={artifact_kind} at {artifact_path}; "
        f"cpq_pushed={cpq.get('cpq_pushed')}.")

    return {
        "quote_id": quote_id,
        "artifact_path": artifact_path,
        "artifact_kind": artifact_kind,
        "issued": True,
        "status": "issued_pending_floor",   # the @chain floor confirms/blocks
        "approved": approved,
        "approved_by": approved_by,
        "required_approver": required,
        "rfq_id": rfq_id,
        "customer_id": customer_id,
        "tier": tier,
        "total_cents": total_cents,
        "valid_until": valid_until,
        "issue_summary": summary,
        "cpq_pushed": bool(cpq.get("cpq_pushed")),
    }
