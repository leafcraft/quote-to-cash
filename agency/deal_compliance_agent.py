"""LLM Agent — deal-compliance analyst (deterministic legal-gate floor).

Two responsibilities, one role (mode contract_review / rev_rec — see the
config prompt). On top of the LLM's clause review, a code floor enforces
the firm's compliance controls as a FLOOR the LLM cannot waive:

  * requires_legal_review is FORCED true whenever the review contains ANY
    unacceptable clause — recomputed in code from the clause list, NOT
    trusted from the model. The legal hard gate to the finance approver
    (the senior contract authority below the CFO) routes on this flag, so
    the LLM cannot soften an unacceptable clause into "fine to proceed".
  * requires_deal_desk_review is recomputed (>=1 negotiable OR >=3
    unmapped clauses).
  * risk_score is RECOMPUTED in code from the severity counts
    (0.5×unacceptable + 0.15×negotiable + 0.05×unmapped, capped at 1.0).
  * requires_cfo_review (rev_rec mode) is forced on low confidence,
    multi-year + variable consideration, or many performance obligations.

The unacceptable-clause count is taken from the model's own classified
review list, but the GATE DECISION is code — the model can misclassify a
single clause, but it cannot mark a clearly-unacceptable list "clean".

Decorators:
  @chain enforce_compliance_floor — recompute risk + force the gates.

auto_discover matches function name 'deal_compliance_agent' to YAML.
"""
from __future__ import annotations

import json
import re
from typing import Any

from leafmesh import LeafMeshLogger, chain

logger = LeafMeshLogger(__name__)

_SEVERITY_WEIGHT = {"unacceptable": 0.5, "negotiable": 0.15, "unmapped": 0.05}


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


def _severity_counts(review: Any) -> dict[str, int]:
    counts = {"acceptable": 0, "negotiable": 0, "unacceptable": 0, "unmapped": 0}
    if isinstance(review, list):
        for clause in review:
            if isinstance(clause, dict):
                sev = str(clause.get("severity", "")).strip().lower()
                if sev in counts:
                    counts[sev] += 1
    return counts


def _clause_types(review: Any, severity: str) -> list[str]:
    out: list[str] = []
    if isinstance(review, list):
        for clause in review:
            if isinstance(clause, dict) and \
                    str(clause.get("severity", "")).strip().lower() == severity:
                ct = clause.get("clause_type")
                if ct:
                    out.append(str(ct))
    return out


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


# ── @chain step (the deterministic compliance / legal gate floor) ─────
async def enforce_compliance_floor(result: dict, ctx: dict) -> dict[str, Any]:
    """Recompute risk + FORCE the legal / deal-desk / CFO gates in code."""
    if not isinstance(result, dict):
        result = _parse_json(result)
    if not isinstance(result, dict):
        result = {}

    mode = str(result.get("mode", "")).strip().lower()

    # ── contract_review: legal gate is computed from the clause list ──
    review = result.get("review")
    counts = _severity_counts(review)
    if isinstance(review, list) and review:
        result["severity_counts"] = counts
        result["clauses_reviewed"] = len(
            [c for c in review if isinstance(c, dict)])
        result["unacceptable_clauses"] = _clause_types(review, "unacceptable")
        result["negotiable_clauses"] = _clause_types(review, "negotiable")
        result["unmapped_clauses"] = _clause_types(review, "unmapped")
        result["risk_score"] = round(min(1.0,
            _SEVERITY_WEIGHT["unacceptable"] * counts["unacceptable"]
            + _SEVERITY_WEIGHT["negotiable"] * counts["negotiable"]
            + _SEVERITY_WEIGHT["unmapped"] * counts["unmapped"]), 2)
        # HARD GATE — any unacceptable clause forces legal review.
        result["requires_legal_review"] = counts["unacceptable"] > 0
        result["requires_deal_desk_review"] = (
            counts["negotiable"] >= 1 or counts["unmapped"] >= 3)
        result["compliance_floor_applied"] = True

    # ── rev_rec: CFO review forced on the restatement-risk conditions ──
    if mode == "rev_rec":
        confidence = _as_float(result.get("classification_confidence", 0.0))
        term = _as_int(result.get("contract_term_months", 0))
        var_consid = result.get("variable_consideration") or []
        pos = result.get("performance_obligations") or []
        multi = bool(result.get("is_multi_element"))
        forced_cfo = (
            confidence < 0.7
            or (term >= 24 and bool(var_consid))
            or (multi and isinstance(pos, list) and len(pos) > 3)
        )
        # Floor only TIGHTENS — never relaxes a model-set true.
        result["requires_cfo_review"] = bool(result.get("requires_cfo_review")) or forced_cfo
        if isinstance(pos, list):
            result["total_allocated_cents"] = sum(
                _as_int(p.get("allocated_cents", 0))
                for p in pos if isinstance(p, dict))
        result["compliance_floor_applied"] = True

    logger.info(
        f"enforce_compliance_floor — mode={mode or '?'} "
        f"unacceptable={counts['unacceptable']} "
        f"legal_review={result.get('requires_legal_review')} "
        f"risk={result.get('risk_score')} "
        f"cfo_review={result.get('requires_cfo_review')}"
    )
    return result


@chain(enforce_compliance_floor)
async def deal_compliance_agent(llm_response, input_data: dict,
                                context: dict) -> dict[str, Any]:
    """Surface the LLM's classification; the chain enforces the floor."""
    parsed = _parse_json(llm_response)
    return parsed if isinstance(parsed, dict) else {}
