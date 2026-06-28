# quote-to-cash — Quote to Cash

An RFQ-to-quote desk as a department of self-reliant agents. A request for
quote arrives, costs are pulled from your price book, a discount tier is
chosen, the right human approver signs off (rep → deal desk → finance →
CFO, by deal size × margin × discount), and a quote is drafted — every
terminal path landing in a hash-chained WORM audit. 13 agents, YAML-first:
the entire approval policy is declared as wire conditions on one agent.

## Story

A regional sales rep, **Priya**, gets an RFQ by email from an existing mid-
market customer: 40 seats of the Pro SKU, wants it closed this quarter.
The email hits the `rfq_email` entry point and lands on the **RFQ intake
specialist** (`rfq_ingester_agent`), which normalises it into a clean
record — customer_id, line_items (sku, qty, list_price_cents),
target_close — and hands it to the **cost analyst**
(`cost_calculator_agent`). The cost analyst calls the price-book lookup
tool on the company's CPQ MCP server and returns total COGS, total list,
and gross margin.

The **pricing strategist** (`discount_policy_agent`) reads that, weighs
customer history and any competitive signal, and picks a 12% discount
(tier_2). Its own outbound wires *are* the approval matrix: at 12% discount
on a sub-$100K, healthy-margin deal, exactly one edge fires — the **deal
desk approver** (`deal_desk_human`). Before the gate, a small Python stash
writer saves the full deal context keyed by session, because the SDK
resumes a chain after a human gate with only the human's response.

The deal desk approver sees a 2-3 sentence briefing in their inbox and
replies `approve`. That routes to the **quote writer**
(`quote_drafter_agent`), which recovers the stashed deal context and drafts
the quote body (pricing table, terms, validity, next steps). The writer
hands off to the **quote issuer** (`quote_issuer_agent`), the
artifact-producing executor that *finishes the job*: it renders the
approved quote to a real document at `./out/<quote_id>.pdf` (ReportLab; or
a deterministic `.md` when ReportLab isn't installed) and pushes it to your
CPQ (`CPQ_WEBHOOK_URL`, inert until set; a dev store records the issued
quote otherwise) — but only after a **fail-closed floor** re-derives the
required approver from the financials and confirms the deal was approved by
the right tier; an unapproved or under-approved quote is never written. The
issuer then calls the **compliance archivist** (`qtc_audit_logger_agent`),
which appends a hash-chained WORM entry. If the deal desk had stayed silent
past its timeout, the gate fails *toward* finance, not into silence.

## Why it works in an organization

Quote-to-cash is where revenue leaks: discounts approved out of policy,
deals stuck waiting on the wrong approver, quotes sent with margins below
floor, contracts signed with clauses nobody flagged. This desk encodes the
discount-approval matrix *as enforceable wires* — a sales controller can
read the whole policy in one config block, and no deal can skip its tier.
Reps self-serve small healthy deals in seconds; only the deals that
genuinely need deal desk / finance / CFO judgment reach a human, and those
arrive with a briefing already written. Side flows add cross-sell
suggestions (more revenue per quote) and a deal-compliance analyst that
hard-gates unacceptable contract clauses and routes ASC 606 ambiguity to
the CFO (less restatement risk). Every approval and every quote is in a
tamper-evident audit trail for the auditor and the regulator.

## Configuration

Three tiers — see `env` for the full annotated list.

### Tier 1 · Boot (required)
| Var | Purpose |
|---|---|
| `LEAFMESH_LICENSE_KEY` | starts the SDK (required) |
| `LEAFMESH_ENV_TOKEN` | per-environment telemetry token |
| `OPENAI_API_KEY` | all `gpt-4o-mini` agents + the manager |
| `ANTHROPIC_API_KEY` | `deal_compliance_agent` (claude-sonnet-4-6) |

### Tier 2 · State store (defaults work locally)
`REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` — default to local Redis
(`docker compose up redis -d`). Approval thresholds are **not** env vars;
they are wire conditions on `discount_policy_agent` in
`configs/config.yaml`.

### Tier 3 · Connectors (optional — inert until set)
System-of-record agents point at YOUR stack:
| Var | Powers |
|---|---|
| `CPQ_MCP_URL` / `CPQ_MCP_TOKEN` | `cost_calculator_agent` — your CPQ/ERP price book (**not auto-consumed**; wire into `load_price_book` — the seeded dev store works day-0) |
| `CPQ_WEBHOOK_URL` / `CPQ_WEBHOOK_TOKEN` | `quote_issuer_agent` — your CPQ create-quote webhook (Salesforce CPQ / DealHub / Conga); inert until set, the issuer still renders `./out/<quote>.pdf` and records a dev-store fallback |
| `CLM_MCP_URL` / `CLM_MCP_TOKEN` | `contract_redline_tracker_agent` — redline ledger in your CLM |
| `N8N_COMPETITOR_WATCH_WEBHOOK_URL` / `N8N_AUTH_TOKEN` | `competitor_watch_agent` — price-intelligence sweep (cron stays commented out until wired) |
| `PAGER_WEBHOOK` | manager PagerDuty escalation target |
| `SLACK_PRICING_CHANNEL` / `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` | manager Slack escalation — **not auto-consumed**; wire a Slack sender in code/connector |

## Agents

| Agent | Role | Responsibilities | Can perform |
|---|---|---|---|
| `rfq_ingester_agent` | RFQ intake specialist | Normalises inbound RFQs (email / CPQ event / rep-initiated / manual) into a clean record (customer_id, line_items, target_close) | LLM extraction; routes to the cost analyst |
| `cost_calculator_agent` | Cost analyst | Costs the RFQ's line items; a **code floor recomputes COGS / list / gross margin** from the price book of record (the model can't fake a margin) and flags regulated SKUs | LLM + `@pre_compose` (price book) + `@chain` cost floor; seeded dev store day-0, CPQ/ERP MCP in prod; routes to the pricing strategist |
| `discount_policy_agent` | Pricing strategist | Picks the discount from customer history + competitive signals; a **code floor derives the tier and the post-discount margin the approval matrix routes on**; **its outbound wires are the approval matrix** | LLM + `@pre_compose` (deal history, competitor pricing, policy table) + `@chain` discount floor + `@compose` (approver brief vs full deal); fans out to exactly one of rep / deal desk / finance / CFO; pre-gate context stash |
| `quote_drafter_agent` | Quote writer | Assembles the quote body (pricing table, terms, validity, next steps) after the human gate; never auto-sends | LLM + Python recovery of stashed deal context; fail-soft fallback body; routes to the quote issuer |
| `quote_issuer_agent` | Quote issuer | **Artifact-producing executor that finishes the job** — renders the approved quote to `./out/<quote_id>.pdf` (ReportLab; deterministic `.md` fallback) and pushes to your CPQ; a **fail-closed floor never issues an unapproved or under-approved quote** (re-derives the required approver from the financials) | Programmatic actuator + `@chain` issuance floor; CPQ push via `CPQ_WEBHOOK_URL` (inert until set) with a dev-store fallback; routes to the compliance archivist |
| `competitor_watch_agent` | Competitive-intelligence watcher | Surfaces competitor price changes from your price-intelligence stack | n8n webhook; standalone (cron disabled until wired) |
| `bundle_recommender_agent` | Cross-sell strategist | Suggests adjacent SKUs from purchase history, similar accounts, product affinity, and use-case completeness; suppresses anything previously declined | LLM (knowledge: `product_affinity`); routes to the rep when there are candidates, else to audit |
| `contract_redline_tracker_agent` | Contract redline registrar | Tracks who changed what across contract versions (open / update / report); flags redlines stalled past lead time | MCP tool `redline_ledger` on your CLM; routes the morning brief to the deal desk |
| `deal_compliance_agent` | Deal-compliance analyst | Mode `contract_review`: clause-by-clause playbook check (unacceptable = hard gate). Mode `rev_rec`: ASC 606 classification (POs, SSP allocation, recognition pattern) | LLM (claude-sonnet-4-6, knowledge: `rev_rec_policy`); hard-gates unacceptable clauses to the finance approver for legal sign-off, negotiable to deal desk, rev-rec ambiguity to the CFO |
| `sales_rep_human` | Sales representative | Self-approves small, healthy-margin, low-discount deals (≤ $25K, ≥ 20% margin, ≤ 10% discount) | Human gate; approve → quote writer, escalate → deal desk, reject → audit; default-deny to deal desk on timeout |
| `deal_desk_human` | Deal desk approver | Approves discounted / mid-size deals (≤ $100K, ≤ 20% discount) | Human gate; approve → quote writer, escalate → finance, reject → audit; default-deny to finance on timeout |
| `finance_approver_human` | Finance approver | Approves large / lower-margin deals (≤ $1M) and signs off legally-flagged contracts | Human gate; approve → quote writer, escalate → CFO, reject → audit; default-deny to CFO on timeout |
| `cfo_human` | Chief Financial Officer | Top-tier authority — margin below floor, discount > 30%, list > $1M, or rev-rec ambiguity | Human gate; approve → quote writer, else → audit; default-deny holds for review on timeout |
| `qtc_audit_logger_agent` | Compliance archivist | Appends every terminal outcome to a tamper-evident, hash-chained WORM ledger | Custom external sink (registered in `main.py`); terminal |

## Day-0 dev store (no connectors)

`agency/_shared/store.py` seeds a realistic mid-market RFQ
(`RFQ-2026-0042` — 40 Pro seats + onboarding for `ACME-4471`), a per-SKU
**price book** (unit cost + unit list), the **discount policy table**
(tier bands + margin floor), **deal history**, and **competitor pricing**.
The `@pre_compose` pulls and `@chain` floors read from it, so the FULL
chain (cost → discount → approval routing → quote) runs end-to-end before
any connector is wired. Swap each read for the matching connector in prod;
the function signatures are the contract.

## Run

```bash
cp env .env && pip install -r requirements.txt && python main.py
```

### Try the seeded deal (copy-paste, no connectors)

```python
import asyncio
from agency._shared import store
from agency import cost_calculator_agent as cost, discount_policy_agent as disc

async def demo():
    rfq = store.sample_rfq()                       # the seeded RFQ-2026-0042
    items = rfq["line_items"]
    # cost analyst — the floor recomputes the cost basis from the price book
    cprep = cost.load_price_book({"line_items": items}, {})
    c = await cost.enforce_cost_floor({}, {"prepared_data": {"context": cprep}})
    print("cost:", c["total_cogs_cents"], c["total_list_cents"], c["gross_margin_pct"])
    # pricing strategist — the floor derives the tier + post-discount margin
    d = await disc.discount_policy_agent(
        {"discount_pct": 0.12, "rfq_id": rfq["rfq_id"], "rationale": "renewal"},
        {"session_id": "demo", "customer_id": rfq["customer_id"],
         "segment": rfq["segment"], "upstream_yields": {"cost_calculator_agent": c}}, {})
    print("discount:", d["tier"], d["gross_margin_pct"], "(12% on a sub-$100K, healthy-margin deal → deal desk)")

asyncio.run(demo())
# cost: 1860000 5300000 0.6491
# discount: tier_2 0.6012 (12% on a sub-$100K, healthy-margin deal → deal desk)
```

See `PRD.md` for the full architecture, flow diagram, and design decisions.
