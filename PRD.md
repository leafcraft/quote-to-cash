# PRD — quote-to-cash — Quote to Cash

## Overview / Story

A quote-to-cash desk built as a LeafMesh agency: a department of self-
reliant agents that takes a request for quote from intake to a signed-off,
audited quote. The defining design choice is that the **discount-approval
matrix is declared as wire conditions** on a single agent
(`discount_policy_agent`) — not buried in a Python router — so a sales
controller can read the entire policy (amount × margin × discount → rep /
deal desk / finance / CFO) in one config block.

A regional sales rep, Priya, emails an RFQ for 40 Pro seats. It enters at
`rfq_email`, is normalised by the RFQ intake specialist, costed by the cost
analyst against the CPQ price book, and priced by the pricing strategist at
12% (tier_2). The pricing strategist's wires fire exactly one approver —
the deal desk — who approves; the quote writer recovers the deal context
and drafts the quote body, the quote issuer renders it to a real document
(`./out/<quote_id>.pdf`) and pushes it to the CPQ — but only after a
fail-closed floor confirms the right approver cleared the deal — and the
compliance archivist writes a hash-chained WORM entry.

## Why it works in an organization

Quote-to-cash leaks revenue through out-of-policy discounts, mis-routed
approvals, sub-floor margins, and unflagged contract clauses. Encoding the
approval matrix as enforceable wires means no deal can skip its tier, reps
self-serve small healthy deals instantly, and only judgment-grade deals
reach a human — pre-briefed. Side flows add cross-sell (revenue per quote)
and deal-compliance (clause hard-gates + ASC 606), and every terminal path
is tamper-evident for audit and regulator.

## Flow diagram

```
 rfq_email ─┐
 cpq_event ─┤
rep_initiated┤──> rfq_ingester ──> cost_calculator ──> discount_policy
 manual_action┘   (intake)          (COGS via CPQ MCP)   (tier + briefing)
                                                              │
                          ══ APPROVAL MATRIX (one edge fires) ══
                          │            │            │            │
                   ≤$25K,≥20%,  >10% disc or   >20% disc or  margin<20% or
                   ≤10% disc    >$25K          >$100K        disc>30% or
                          │     (≤$100K)       (≤$1M)        list>$1M
                          ▼            ▼            ▼            ▼
                   sales_rep ──> deal_desk ──> finance ──> cfo   (HITL,
                          │  esc.       │  esc.    │  esc.    │    default-
                          │  approve    │ approve  │ approve  │    deny on
                          └─────────────┴──────────┴──────────┘    timeout)
                                         │ approve
                                         ▼
                  quote_drafter ──> quote_issuer ──> qtc_audit_logger (WORM)
                  (recover stash)   (render ./out/        ▲
                                     <quote>.pdf + CPQ;   │
                                     fail-closed floor)   │
   reject ───────────────────────────────────────────────┘

 SIDE FLOWS
 bundle_suggestion / renewal_uplift_bundle / expansion_cross_sell
        └─> bundle_recommender ──(candidates)──> sales_rep
                                └──(none)──────> qtc_audit_logger

 rev_rec_classify / direct_call_deal_compliance
        └─> deal_compliance ──(unacceptable clause)──> finance_approver (legal sign-off)
                            ──(negotiable)───────────> deal_desk
                            ──(clean contract_review)─> finance_approver
                            ──(rev-rec ambiguity)─────> cfo

 redline_open / redline_update / redline_morning_brief
        └─> contract_redline_tracker ──(stalled)──> deal_desk   [CLM MCP]

 competitor_price_change ──> discount_policy   |   direct_call_competitor_watch ──> competitor_watch [n8n]
```

The only cycles are the human escalation back-edges (rep→deal_desk→finance
→cfo), each a forward escalation with a default-deny timeout fallback — no
conductor hub, work flows forward, every branch terminates in audit.

## Actor inventory

| Agent | Role | Responsibilities | Can perform |
|---|---|---|---|
| `rfq_ingester_agent` | RFQ intake specialist | Normalises inbound RFQs into a clean record | LLM; → cost analyst |
| `cost_calculator_agent` | Cost analyst | COGS / list / margin recomputed from the price book (code floor); flags regulated SKUs | LLM + @pre_compose price book + @chain cost floor; → pricing strategist |
| `discount_policy_agent` | Pricing strategist | Discount + approver briefing; code floor derives tier + post-discount margin; wires = approval matrix | LLM + @pre_compose deal intel + @chain discount floor + @compose; → one of rep/deal_desk/finance/cfo; pre-gate stash |
| `quote_drafter_agent` | Quote writer | Assembles quote body post-gate; never auto-sends | LLM + Python stash recovery; → quote issuer |
| `quote_issuer_agent` | Quote issuer | Artifact-producing executor — renders the approved quote to `./out/<quote>.pdf` (ReportLab; `.md` fallback) + CPQ push; fail-closed floor blocks unapproved / under-approved quotes | programmatic actuator + @chain issuance floor (re-derives required approver from financials); → compliance archivist |
| `competitor_watch_agent` | Competitive-intelligence watcher | Competitor price changes | n8n; standalone (cron disabled until wired) |
| `bundle_recommender_agent` | Cross-sell strategist | Adjacent-SKU suggestions; suppresses declined items | LLM (knowledge: product_affinity); → rep or audit |
| `contract_redline_tracker_agent` | Contract redline registrar | Tracks redlines across versions; flags stalled | MCP `redline_ledger`; → deal desk |
| `deal_compliance_agent` | Deal-compliance analyst | Playbook clause review + ASC 606 rev-rec | LLM (sonnet, knowledge: rev_rec_policy); → finance (legal)/deal_desk/cfo |
| `sales_rep_human` | Sales representative | Self-approves small healthy deals | Human gate; default-deny → deal desk |
| `deal_desk_human` | Deal desk approver | Discounted / mid-size deals | Human gate; default-deny → finance |
| `finance_approver_human` | Finance approver | Large / lower-margin deals + legal sign-off | Human gate; default-deny → CFO |
| `cfo_human` | Chief Financial Officer | Top-tier authority | Human gate; default-deny holds for review |
| `qtc_audit_logger_agent` | Compliance archivist | Hash-chained WORM ledger | Custom external sink; terminal |

## Data artifacts

- **RFQ** (declared `data_structures.RFQ`): rfq_id, customer_id,
  line_items (sku, qty, list_price_cents), target_close, received_at_utc.
- **Cost yields**: total_cogs_cents, total_list_cents, gross_margin_pct,
  has_regulated_sku, line_items (recomputed by the cost floor from the
  price book — seeded dev store day-0, CPQ MCP in prod).
- **Discount decision**: discount_pct, tier, rationale,
  deal_desk_briefing, plus echoed total_list_cents / gross_margin_pct /
  rfq_id that drive the matrix wires.
- **Quote**: quote_body, validity_days (+ identity/degraded flag).
- **Compliance**: clause review (severity-classified) + ASC 606
  performance obligations, recognition pattern, risk_score.
- **Audit entry**: audit_event_id, written_at_utc, hash_chain_prev,
  hash_chain_current — append-only.
- **Session stash** (in-process): the deal context bridged across the HITL
  gate (the SDK resumes a chain after a human gate with only the human's
  response meta fields).

## Per-agent spec

- **rfq_ingester_agent** (llm) — temp 0.1, enforce_yields. Generates an
  rfq_id when absent. Sole successor: cost_calculator.
- **cost_calculator_agent** (llm + floor) — backed by
  `agency/cost_calculator_agent.py`: `@pre_compose load_price_book` pulls
  per-SKU cost+list from the seeded price book (CPQ/ERP MCP in prod);
  `@chain enforce_cost_floor` **recomputes** total_cogs / total_list /
  gross_margin from line_items × the price book and sets has_regulated_sku
  — the LLM's numbers are advisory, the floor owns the cost basis.
  Successor: discount_policy.
- **discount_policy_agent** (llm + floor) — temp 0.0, knowledge
  discount_policy. Backed by `agency/discount_policy_agent.py`:
  `@pre_compose load_deal_intel` pulls deal history + competitor pricing +
  the policy table; `@chain enforce_discount_floor` **clamps** discount,
  **derives** tier from the policy bands, and **recomputes**
  gross_margin_pct as the post-discount margin — the three matrix-driving
  keys are COMPUTED, not echoed. `@compose` gives the approver a focused
  brief vs the quote writer the full deal. The body also stashes the deal
  pre-gate. Four mutually-exclusive, exhaustive can_call conditions
  implement the matrix (thresholds in cents: rep ≤$25K, deal_desk ≤$100K,
  finance ≤$1M, else CFO; margin floor 0.20; discount bands 0.10/0.20/0.30).
- **quote_drafter_agent** (llm + floor) — temp 0.1. Backed by
  `agency/quote_drafter_agent.py`: recovers stash, fail-soft fallback body,
  logs degraded drafts; `@chain enforce_quote_validity_floor` **caps**
  validity_days by the deal's discount tier (tier_1 60d → tier_4 14d) so a
  steep discount can't sit open indefinitely. Successor: quote_issuer.
- **quote_issuer_agent** (programmatic actuator + floor) — the
  artifact-producing executor that finishes the job. Backed by
  `agency/quote_issuer_agent.py`: recovers the deal (line items, totals,
  discount, tier) from the per-session stash + drafter yields, builds the
  priced quote, and **renders a real artifact** to `./out/<quote_id>.pdf`
  (ReportLab) or a deterministic `./out/<quote_id>.md` when ReportLab is
  absent (always a real file, day-0, no extra deps). It also **pushes to
  the CPQ** via `CPQ_WEBHOOK_URL` (read from env — a custom urllib actuator;
  inert until set) with a `./data/issued_quotes.json` dev-store fallback.
  `@chain enforce_issuance_floor` is **fail-closed**: it re-derives the
  required approver from the financials (the same amount × margin × discount
  matrix the discount_policy wires encode) and **never issues** a quote that
  wasn't approved or whose tier wasn't cleared by the required approver — on
  a trip the artifact is deleted and the result marked `issuance_blocked`.
  Successor: qtc_audit_logger.
- **competitor_watch_agent** (programmatic, n8n) — wake_up cron commented
  out until the connector is wired.
- **bundle_recommender_agent** (llm) — knowledge product_affinity; hard
  rule that a suppression reason forces empty candidates.
- **contract_redline_tracker_agent** (programmatic, mcp) — `redline_ledger`
  over HTTP at `${CLM_MCP_URL}`; auto_store_response/yields.
- **deal_compliance_agent** (llm + floor, claude-sonnet-4-6) — two modes,
  one role; knowledge rev_rec_policy; auto_store_response/yields. Mode
  dispatch via explicit `mode` input then inference. Backed by
  `agency/deal_compliance_agent.py`: `@chain enforce_compliance_floor`
  **recomputes** risk_score from the severity counts and **forces**
  requires_legal_review true on ANY unacceptable clause (the legal hard
  gate routes on the computed flag — the model can't soften it); rev_rec
  mode forces requires_cfo_review on the restatement-risk conditions.
- **Human gates** (4) — dual communication, default-deny fallbacks
  escalating up the chain (cfo holds for review). `operator_ids` left unset
  → shared inbox.
- **qtc_audit_logger_agent** (external, custom) — intelligence function
  registered in `main.py`; hash-chained WORM lines to `./logs/`.

## Entry points

- Pricing flow: `rfq_email`, `cpq_event`, `rep_initiated`, `manual_action`
  → rfq_ingester.
- `competitor_price_change` → discount_policy (tier refresh).
- Redline: `redline_open` / `redline_update` / `redline_morning_brief` →
  contract_redline_tracker.
- Compliance: `rev_rec_classify`, `direct_call_deal_compliance` →
  deal_compliance.
- Cross-sell: `bundle_suggestion`, `renewal_uplift_bundle`,
  `expansion_cross_sell` → bundle_recommender.
- Direct/debug: `direct_call_cost_calculator`, `direct_call_quote_drafter`,
  `direct_call_quote_issuer`, `direct_call_competitor_watch`.

## Controls / trust

- **Approval matrix as wires** — mutually exclusive, exhaustive; exactly
  one human tier fires per deal (asserted in `tests/test_config_shape.py`),
  routed on floor-computed numbers.
- **Deterministic floors** — cost / discount-tier / compliance-legal-gate /
  quote-validity recomputed in `@chain` (asserted in `tests/test_floors.py`);
  the LLM cannot waive a margin, mislabel a tier, soften an unacceptable
  clause, or over-extend a steep quote.
- **Default-deny HITL** — every gate has `fallback_on_timeout: true`
  escalating up; the CFO holds for review. No placeholder `operator_ids`.
- **Hard gate** — `deal_compliance_agent` routes any unacceptable contract
  clause to the finance approver for legal sign-off (the senior contract
  authority below the CFO — there is no standalone legal role in this
  cast); the prompt forbids softening `requires_legal_review`.
- **WORM audit terminus** — every branch (approve / reject / clean
  compliance / no-bundle) lands in the hash-chained sink.
- **yields ↔ prompt contract** — every llm agent carries an OUTPUT
  CONTRACT block (validated by `validate_config.py`).
- **Manager escalation** — human_agent (finance), PagerDuty webhook, and
  Slack channel targets; auto-escalate on retries/errors/timeout.

## Configuration

See `env` (three tiers) and `README.md`. Boot: license + env token +
OpenAI + Anthropic. State: Redis (local defaults). Day-0 data: the seeded
`agency/_shared/store.py` (RFQ, price book, discount policy, deal history,
competitor pricing) so the chain runs with no connectors. Connectors:
CPQ price book (wire into `load_price_book`), CLM MCP, n8n
price-intelligence, PagerDuty, Slack — all inert until set. Approval
thresholds are wire conditions in `configs/config.yaml`, not env vars.

## Reflection / decisions

- **Approval policy as wires, not Python.** The former
  `approval_router_agent` module was deleted; its elif chain is now four
  wire conditions on `discount_policy_agent`. Readable by non-engineers and
  test-verified to reproduce the original routing exactly. The wires now
  route on **floor-computed** keys (derived tier, post-discount margin), so
  a deal cannot skip its tier even if the LLM mislabels the numbers.
- **Deterministic floors the LLM can't waive.** Four `@chain` floors moved
  rules out of prompts and into code: the **cost floor** recomputes
  COGS/list/margin from the price book (no faked margin); the **discount
  floor** clamps discount, derives the tier, and recomputes the
  post-discount margin the matrix routes on; the **compliance floor**
  forces requires_legal_review on any unacceptable clause and recomputes
  risk_score; the **quote-validity floor** caps validity_days by tier. Each
  is unit-tested in `tests/test_floors.py`.
- **Self-reliant context via `@pre_compose` + a seeded dev store.** The
  cost analyst pulls the price book; the pricing strategist pulls deal
  history + competitor pricing + the policy table — all from
  `agency/_shared/store.py`, seeded so the full chain runs day-0 with no
  connectors. Prod swaps each read for the matching CPQ/CRM/price-intel
  connector; the function signatures are the contract.
- **`@compose` where downstreams differ.** The pricing strategist emits a
  focused approval brief to the human gate vs the full deal package to the
  quote writer.
- **HITL stash bridge.** The SDK resumes a chain after a human gate with
  only the human's response, so the deal context is stashed pre-gate
  (`discount_policy_agent.py` body, after the floor so stashed == routed)
  and recovered post-gate (`quote_drafter_agent.py`). In-process for
  single-replica; swap for the Redis session store at multi-replica.
- **Role-merge: deal-compliance analyst.** The former contract-review and
  rev-rec-classifier agents merged into one two-mode role — one job title,
  two responsibilities (Rule 2), pure-YAML.
- **Legal sign-off routes to finance, not a separate legal role.** This
  cast has no standalone legal counsel; the finance approver is the senior
  contract authority below the CFO and owns legally-flagged contracts. The
  narration was reconciled to match the enforced route.
- **Slack escalation is not plug-and-play.** The manager's Slack channel
  target names `SLACK_PRICING_CHANNEL`, but the SDK does not auto-send to
  Slack from `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET`; those are
  documented as "wire it in code/connector" rather than implied as
  plug-and-play.
- **competitor_watch cron stays disabled** until the n8n connector is
  wired — a cron sweeping an unwired connector just fills the logs.

### To verify in a live smoke test (not provable from config-load)

- Whether `@chain` (the stash recovery) receives the session id after a
  real human gate resume in the target deployment.
- The MCP / n8n connector round-trips against real CPQ / CLM / n8n
  endpoints.
- The manager Slack escalation once a sender is wired.
