# quote-to-cash — Quote-to-Cash Pod · PRD

The brief behind `configs/config.yaml` (the first-start seed — after the first
start the configuration lives in the store and is changed in Studio). This pod runs a deal from an inbound
RFQ all the way to **cash**, as a **team** of self-reliant agents — a
coordinator, specialists, a finisher, first-class human gates, and a WORM
sink — supervised by the LeafMesh Manager. Not a pipeline.

Design doctrine: `.claude/skills/leafmesh/building-agents-thoroughly.md`.
SDK baseline: **2.4.131**.

---

## 1. The pod shape

```
                 ┌────────────────────────── Manager (supervisor) ──────────────────────────┐
                 │   escalates errors (non-retryable / 5 failed agents) to the RevOps Lead    │
                 └───────────────────────────────────────────────────────────────────────────┘

  rfq_email ─┐
  cpq_event ─┼─▶ Quinn ──(open_case)──▶ Cass ──┬── APPROVAL MATRIX (wires) ──▶ [rep|deal-desk|finance|CFO]
  rep_init  ─┘   (coordinator)        (shaper,  │   amount × margin × discount        │ (human decides)
  deal_status ─▶ Quinn (status)        super-   │                                     │ approve
                                       agent)   ├── incomplete ──▶ rep (rework, BOUNDED)
                                                └── rework exhausted ──▶ RevOps Lead (terminal)
                                                                                       ▼
                          audit ◀── issuer ◀──(drafted)── drafter ◀────────────────────┘
                        (WORM)   (FINISHER: re-check approval, re-derive required
                                  approver, render ./out/<quote>.pdf, DELETE-ON-BLOCK)

  quote_accepted ─▶ billing (invoice) ─┐
  dunning_sweep ──▶ billing (dun, ×copies, atomic claim) ─┴─▶ RevOps Lead (severe) + audit
```

**One human, one agent, one system per stage.** The agent produces, the human
decides, the system records — no stage advances on an agent's own authority.

---

## 2. Entry points (one per real trigger)

| Entry point | Target | Trigger |
|---|---|---|
| `rfq_email` | Quinn | RFQ arrives by email |
| `cpq_event` | Quinn | CPQ/CRM system event |
| `rep_initiated` | Quinn | Rep starts an RFQ by hand |
| `deal_status` | Quinn | "Where is my quote?" |
| `quote_accepted` | billing | Customer accepted → raise invoice |
| `dunning_sweep` | billing | Overdue sweep (also a `wake_up` cron) |
| `rep_reply` / `deal_desk_reply` / `finance_reply` / `cfo_reply` / `revops_reply` | the matching human | HITL resume — a human answers in Studio's Inbox |

---

## 3. Agents

### 3.1 Quinn — Deal Coordinator (LLM, pure YAML)
Owns the case end to end: opens it, echoes the RFQ, hands to Cass, keeps live
status, routes exceptions to the RevOps Lead. **Never prices or approves.**
Wires: `open_case → cass`, `escalate → revops_lead`.

### 3.2 Cass — Costing & Deal Shaper (LLM · super_agent · playbook · tools)
Turns a raw RFQ into a priced, policy-compliant deal. The **super_agent** (dict
form: `cost_ceiling`, `wall_clock`) plans/executes/verifies across the SKUs and
competitive signals. Two **playbook** intents fetched on demand — `quote` (the
read-before-price craft) and `approve` (how to read the tier / write the brief).
Day-0 **tools** read the seeded price book / deal history / competitor store and
**announce themselves**; a commented `mcp:` block wires the real CPQ/ERP.

**`@chain` floors (fail closed):**
- **Completeness** — an RFQ with no customer or line-items is forced incomplete
  and routed back to the rep. The back-edge is **bounded**: a per-session rework
  counter escalates to the RevOps Lead once `_MAX_REWORK_ROUNDS` is exceeded, so
  it can never ping-pong forever.
- **Pricing** — COGS / list / margin are **recomputed** from the price book ×
  line items, the discount is clamped to 0..1, the tier is **derived** from the
  policy bands, and `gross_margin_pct` is recomputed as the **post-discount**
  margin. These three keys drive the approval matrix.

Cass **stashes the full deal pre-gate** (session_stash) so the drafter and
issuer recover it after the human gate drops the chain payload.

**The approval matrix lives on Cass's wires** (amount × margin × discount):

| Tier | Fires when (and `is_complete == true`) |
|---|---|
| `cfo_human` | margin < 20% **or** discount > 30% **or** list > $1M |
| `finance_approver_human` | (discount > 20% **or** list > $100K) and not CFO-bound |
| `deal_desk_human` | (discount > 10% **or** list > $25K) and not finance/CFO-bound |
| `sales_rep_human` | small, healthy-margin, ≤10% discount, ≤ $25K |

The four are mutually exclusive + exhaustive — **exactly one fires per deal.**
Edit the policy by editing these conditions; the finisher re-derives the same
matrix in code as an independent second check.

### 3.3 drafter — Quote Drafter (LLM)
Runs **after** a human tier approves. Assembles the quote body and renders a
draft to `./out`. **`@chain` validity floor** caps shelf life by tier (deeper
discount → shorter validity), recovered from the stash so the cap stands on the
real tier. Never auto-sends. Wire: `drafted → quote_issuer`.

### 3.4 quote_issuer — Quote Issuer / FINISHER (programmatic)
The artifact-producing executor — the load-bearing control ([doctrine B4]):
1. **Re-checks approval** — only an explicit approve counts; an
   unknown/ambiguous verdict **fails closed**.
2. **Re-derives the required approver in code** from the recovered financials
   (the same matrix Cass's wires encode) and requires the seat that actually
   approved (the drafter records the reply's `source_agent`) to match or
   out-rank it — no under-approved issue; no seat on record = not cleared.
3. **Renders the real artifact** to `./out/<quote>.pdf` (ReportLab if present,
   else a deterministic `.md`) and pushes it to the CPQ through the vault record
   `cpq_webhook` ('Outbound webhook', read with `connection_rows`) — only after
   checks 1–2 pass.
4. **Fails closed on a tripped floor — deletes the partial artifact**, marks
   `status: issuance_blocked` + `block_reasons`.
5. **Dev-store fallback that announces itself** — records the issued quote +
   ledger with no CPQ wired; never fakes a real ack.

Wire: `always → qtc_audit_logger_agent`.

### 3.5 billing — AR & Collections Clerk (LLM · playbook · scaling.copies · atomic claim)
The **cash** side. One role, two **playbook** crafts: `invoice` (raise an
invoice from an accepted quote) and `dun` (chase an overdue invoice on cadence).
**`scaling.copies.count: 3`** fans a sweep across parallel copies; each calls the atomic
`claim_billing_work` tool and gets a **disjoint** slice, so copies split the
backlog instead of double-chasing (and a single accepted quote is won by exactly
one copy — the claim makes fan-out idempotent in both modes). A daily
**`wake_up` cron with `timezone`** drives the dunning sweep in the company's
zone, not UTC. **`@chain` billing floor** re-checks each claimed invoice and
**never duns a paid one**; escalations are a list so the `scaling.copies.handoff:
last` merge concatenates them. Wires: `escalations != [] → revops_lead`,
`worked != [] → audit`.

### 3.6 Human members (Studio Inbox · dual · nothing moves on silence)
Rep / Deal Desk / Finance / CFO decide their tier; the **RevOps Lead** is the
accountable owner (the Manager's escalation target for errors). A reject or
hold goes to the audit sink. If nobody answers within the reply window (rep 4 h,
deal desk 4 h, finance 8 h, CFO 24 h, RevOps Lead 24 h), the Inbox card closes
and the ticket records that no reply came — **nothing is approved or issued on
silence**, and nobody is chased automatically. `fallback_on_timeout` +
`fallback_response → held_for_review` stay in the config as the declared intent;
on leafmesh 2.4.486 a dual seat's timeout does not route it yet. `dual` is on the human
boundary only; every downstream peer is `chain` (no dual→dual ping-pong).

### 3.7 qtc_audit_logger_agent — WORM sink (external, custom)
Hash-chained, append-only, the terminus of every path. Registered in `main.py`
via `sdk.intelligence("qtc_audit_logger_agent")` after `from_yaml`, before
`start()`.

---

## 4. Controls (before you call it done)

- **Every wire is conditional** on the producer's declared yields.
- **Nothing moves on silence** — reject / hold → audit; no reply → the card
  closes and nothing is approved or issued.
- **Bounded back-edge** — the rep⇄shaper rework loop counts rounds and goes
  terminal (RevOps Lead) on exhaustion.
- **Two-layer finisher defense** — the issuer body short-circuits before writing;
  the `@chain` floor re-checks independently and deletes the partial.
- **WORM ledger terminus** — every approval, issuance, held gate, and dunning
  action recorded, never edited.
- **Stubs announce themselves** — every dev-store read returns `available:false`
  when it has no real source, never a synthetic success.

---

## 5. Day-0 vs production

| Concern | Day-0 (dev) | Production |
|---|---|---|
| Price book / deal history / competitor | seeded `agency/_shared/store.py` | CPQ/ERP via the `mcp:` block on Cass |
| Billing / invoices | seeded store + atomic claim | billing/AR via the `mcp:` block on billing |
| Quote artifact | `./out/<quote>.pdf` (ReportLab) or `.md` + dev-store record | CPQ push through the vault record `cpq_webhook` |
| Session / working state | `session_stash` (in-process) | Redis session store |
| WORM audit | `./logs/qtc_audit.jsonl` | S3 Object Lock / Splunk HEC / Datadog |

Going live = swap the function bodies in `store.py` for real system calls; the
signatures are the contract, and the mesh does not change.

---

## 6. Modern capabilities in this pod (SDK 2.4.131)

| Capability | Where | Why here |
|---|---|---|
| `super_agent` (dict form) | Cass | autonomous deal shaping across many SKUs + signals |
| `playbook` (per-intent) | Cass (`quote`,`approve`), billing (`invoice`,`dun`) | the craft, loaded on demand; only `description` rides in the prompt |
| `scaling.copies` + atomic claim | billing | fan out the overdue backlog without double-chasing |
| `wake_up` + `timezone` | billing | the dunning sweep fires in the company's zone, not UTC |
| commented `mcp:` block | Cass, billing | declare the real-connector shape; ships commented (each picks a vault connection — `cpq_mcp`, `billing_mcp` — that day 0 does not have) |
| `@chain` fail-closed floors | Cass, drafter, billing, issuer | the controls a prompt cannot waive |
