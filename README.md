# quote-to-cash — Quote-to-Cash Pod

Five digital employees + five human roles that run a deal from an **RFQ all
the way to cash** — **RFQ → shape a priced, policy-compliant deal
(super-agent) → approval matrix (rep / deal-desk / finance / CFO) → draft →
ISSUE the quote artifact (finisher, fail-closed) → invoice → dun the overdue
backlog** — with a human on every approval gate and the systems (CPQ / ERP /
CLM / billing) as tools inside the agents, never members.

**Read `PRD.md`** for the full agent-by-agent spec. This is a **pod-standard**
template (SDK 2.4.131): a team of self-reliant agents, not a pipeline.

## Story

A mid-market RFQ lands from **ACME** — 40 Pro seats plus onboarding, close by
month-end. Today a rep would key the line items, look up costs in the price
book, guess a discount that beats the competitor, chase the right approver,
draft the quote, and — weeks later — remember to invoice and then chase the
payment. This pod runs that whole chain. **Quinn** opens the case and hands it
to **Cass**, who pulls the price book, this account's deal history, and
competitor pricing, then shapes a defensible discount. A deterministic floor
recomputes the margin and tier, so the **approval matrix routes to exactly one
human** — a healthy small deal to the rep, a deep discount straight to the CFO,
no gaming it. On approval the **drafter** assembles the quote and the
**issuer** renders the real artifact and pushes it to the CPQ — and *deletes it*
if the deal turns out under-approved. When the customer accepts, **billing**
raises the invoice; every morning it fans out across parallel copies to dun the
overdue backlog, each copy claiming a disjoint batch so nobody is chased twice.

## Why it works in an organization

Quote-to-cash leaks at the seams: a discount that quietly dips below margin
floor, a quote approved by the wrong tier, an invoice that never goes out, an
overdue account nobody swept. This pod closes each seam the only honest way.
**Cass never invents a cost basis** — a code floor recomputes COGS, margin, and
the discount tier from the price book, so the gate fires on *computed* numbers,
not the model's. **The approval matrix is wires, not code** — the whole
amount × margin × discount policy is readable in one block, and exactly one tier
fires per deal. **The issuer re-checks that the *required* approver actually
cleared the deal** (re-derived in code from the financials) before it issues
anything, and **deletes a half-issued quote** if its floor trips. **Silence
never advances a deal** — every gate default-denies to `held_for_review` and
records it. **Billing never duns a paid invoice**, and its atomic claim means
parallel workers split the backlog instead of double-chasing. Every decision,
approval, issuance, held gate, and dunning action lands in a hash-chained WORM
ledger. ROI: faster quotes, real margin control, no missed invoices, and a live
"where is my quote?" answer.

## The team (11 members)

| Agent | Role (human job title) | Responsibilities | Can perform |
|---|---|---|---|
| `quinn_coordinator_agent` | Deal Coordinator | Owns the deal end to end; opens the case, keeps live status, is the single point of contact | LLM; orchestrates Cass→drafter→issuer→billing; routes exceptions to the RevOps Lead; **never prices or approves** |
| `cass_shaper_agent` | Costing & Deal Shaper | Costs the RFQ, shapes a policy-compliant discount against history + competitive signals | LLM + **super_agent** (autonomous deal shaping) + **playbook** (quote / approve) + price/history/competitor tools; `@chain` **pricing + completeness floors** (fail closed); its wires **are** the approval matrix |
| `drafter_agent` | Quote Drafter | Assembles the approved quote body + validity and renders a draft | LLM; `@chain` **validity floor** (caps shelf life by tier); renders the draft to `./out` |
| `quote_issuer_agent` | Quote Issuer | Renders + issues the approved quote artifact and pushes it to the CPQ | Programmatic **finisher**; approve re-check + required-approver re-derivation → invariants → render `./out/<quote>.pdf` → **delete-on-block** → dev-store fallback → WORM |
| `billing_agent` | AR & Collections Clerk | Invoices accepted quotes and duns the overdue backlog | LLM + **playbook** (invoice / dun) + **instances** (backlog fan-out) + **atomic claim** tool + `wake_up`/`timezone`; `@chain` **never duns a paid invoice** |
| `sales_rep_human` | Sales Rep (Human) | Self-approves small healthy deals; reworks incomplete RFQs | Human gate |
| `deal_desk_human` | Deal Desk (Human) | Approves discounted + competitive deals | Human gate |
| `finance_approver_human` | Finance Approver (Human) | Approves margin + large deals | Human gate |
| `cfo_human` | CFO (Human) | Top-tier authority (below-floor margin, deep discount, > $1M) | Human gate |
| `revops_lead_human` | RevOps Lead (Human) | Accountable owner — resolves escalations, owns policy calls | Human gate — everything that leaves the pod |
| `qtc_audit_logger_agent` | WORM audit | Hash-chains every decision, approval, issuance, held gate, dunning action | External (custom sink); terminus |

The **LeafMesh Manager** supervises — it reads every hand-off and escalates
stalls / policy calls / approval timeouts to the RevOps Lead automatically.

## Prerequisites — what to set, in three tiers

Everything is set in `.env` (`cp env .env`). The **whole LLM chain (shape →
approve → draft → issue → invoice → dun) runs on Tier 1 alone** against the
seeded stores (`./data`); price-book, billing, and CPQ reads use dev
stand-ins that **announce themselves** until you wire Tiers 2–3.

### Tier 1 — required to boot (dev mode)
| Setting | For | Notes |
|---|---|---|
| `LEAFMESH_LICENSE_KEY` | LeafMesh runtime | **Required.** |
| `ANTHROPIC_API_KEY` | Cass (deal shaping, Claude) | **Required.** |
| `OPENAI_API_KEY` | Quinn + drafter + billing + Manager (`gpt-4o-mini`) | **Required** unless you change the models. |
| `REDIS_HOST` / `PORT` / `PASSWORD` | State store | Defaults to `localhost:6379`. `docker run -d -p 6379:6379 redis:7-alpine`. |
| `HITL_OUTBOUND_URL` | Where human members are notified | Defaults to a local stub. |

### Tier 2 — real system-of-record connectors (set the URL, uncomment the `mcp` block)
| Setting | Enables |
|---|---|
| `CPQ_MCP_URL` / `_TOKEN` | Real CPQ/ERP price book + deal history (`cass_shaper_agent`) |
| `BILLING_MCP_URL` / `_TOKEN` | Real billing/AR reads + writes (`billing_agent`) |

> ⚠️ The SDK rejects an `mcp` block with an **empty** URL at load, so the blocks
> ship **commented** in `configs/config.yaml`. Fill the URL, then uncomment.

### Tier 3 — CPQ create-quote webhook (the finisher's push)
| Setting | Enables |
|---|---|
| `CPQ_WEBHOOK_URL` / `_TOKEN` | The issuer pushes the issued quote to your CPQ. Inert until set; the issuer renders `./out/<quote>.pdf` and records a dev-store fallback regardless. |

## Run it

```bash
pip install -r requirements.txt          # core LeafMesh runs the pod day-0
docker run -d -p 6379:6379 redis:7-alpine
cp env .env                              # fill at least Tier 1
python validate_config.py                # pre-flight: wiring, yields, dead-code
python main.py                           # API at http://127.0.0.1:18820/docs
```

Submit an RFQ (day-0, against the seed store — no connector needed):

```bash
curl -X POST http://127.0.0.1:18820/api/mesh/request \
  -H "Content-Type: application/json" \
  -d '{"entry_point":"rfq_email",
       "data":{"rfq_id":"RFQ-2026-0042","customer_id":"ACME-4471",
               "segment":"mid_market",
               "line_items":[{"sku":"PRO-SEAT","qty":40,"list_price_cents":120000},
                             {"sku":"ONBOARD-STD","qty":1,"list_price_cents":500000}]}}'
```

See `examples/` for the four scenarios (rep self-approval, a deep discount that
forces the CFO tier, an accepted quote → invoice, and the dunning sweep):

```bash
python examples/run_examples.py
```

On approval, the issuer renders the approved quote to `./out/` and appends the
hash-chained ledger at `./logs/qtc_audit.jsonl`.

> Packaging note: `pip install leafmesh` (core) includes all LLM providers and
> runs the pod. For real CPQ/ERP/billing connectors add `leafmesh[mcp]`. Avoid
> `leafmesh[all]` on Python 3.12+ (it pulls `cchardet`, which has no wheel) — add
> only the specific extras you need.

---

*Built with `create-leafmesh`. The config is the department; the PRD is the brief.*
*Design doctrine: `.claude/skills/leafmesh/building-agents-thoroughly.md`.*
