# Developing an Agency — Theory & Method

A **theory of how to build a LeafMesh agency** (a template: one complete
multi-agent operation). Read this *before* writing any config. It is the
repeatable method — follow it and every agency comes out consistent,
correct, and legible. SKILL.md tells you *which field does what*; this tells
you *how to think and in what order*.

> **An agency is a department of self-reliant agents.** Each agent is a
> *job role*, not a node. The config IS the department. Your job is to cast
> the roles, draw how they hand work to each other, and put Python only
> where a role genuinely needs hands.

---

## The depth bar — what "deep AND usable" means (objective)

A template is **shippable-flagship** only when it clears BOTH bars. This is
the acceptance test, not a vibe.

**DEEP — the SDK's power is used where it earns its place (no decorator theater):**
- [ ] Key agents are **self-reliant**: they pull their own context with
      `@pre_compose` (a queue, account history, a diff, records) — not
      spoon-fed by a conductor.
- [ ] **Safety/compliance/completeness is enforced in `@chain`** as a
      deterministic floor the LLM can't waive — not merely asked for in a
      prompt.
- [ ] Connector results are **shaped** (intelligence/shaper); where
      downstreams need different payloads, `@compose` is used.
- [ ] **Real Python only where it MUST be** — domain math, actuators,
      idempotency, bounded loops — and genuinely present, not stubbed away.
- [ ] **Event-driven where natural** (`brokers` + `listen_events`), and an
      **external/`claude_agent`** agent where the work is truly external
      (autonomous coding/execution), not an LLM pretending.
- [ ] Every agent is a real job role (Rule 2); the cast is consolidated.

**USABLE — it runs and does something real on day 0:**
- [ ] A **dev store / stubs** make the full chain run end-to-end with **no
      connectors set** (the demo works out of the box).
- [ ] Connectors are wired inert (3-tier config), with a copy-paste
      **example entry-point call** in the README that actually produces output.
- [ ] **Tests + `validate_config` + real-SDK `from_yaml` load** all green,
      verified by ME independently — and the runtime mechanics that can't be
      introspected are flagged for a live smoke test.

If a template only has docs + clean YAML but no `@pre_compose`/`@chain`
where the domain calls for it, it is **swept, not deep** — it has not
cleared this bar.

## 0. The seven first principles (non-negotiable)

1. **One role, multiple responsibilities (Rule 2).** Every agent reads like
   a job title a human would recognise — "Records registrar", "Quality &
   compliance reviewer" — never a thin function. Merge thin agents until
   each is a real role. Supporting/connector agents are roles too.
2. **Self-reliant agents.** A role pulls its *own* context
   (`@pre_compose`), enforces its *own* controls (`@chain`), and shapes its
   *own* outputs (`@compose`/intelligence). It does not depend on a
   conductor to spoon-feed it.
3. **YAML-first.** The config is the department. Add Python *only where it
   MUST be* (§4). Most agencies are 90% YAML.
4. **The mesh boundary is sacred.** An external party (a customer) is
   **never** a mesh member and **no mesh agent talks to them directly**.
   Ingress = a mesh call; egress = a connector actor; all external contact
   is owned by external systems (§5).
5. **Forward-flow DAG, no conductor hubs.** Work flows forward and the
   originator steps out. Hub agents that re-dispatch create loops. The only
   cycles allowed are **bounded back-edges** (rework), counted and capped.
6. **Trust by construction.** Human gates are default-deny on timeout;
   safety rules are enforced in `@chain` (not hoped for in a prompt); every
   terminal path lands in a WORM audit; controls fail closed.
7. **State lives in the customer's systems**, not template storage. Jira,
   Zendesk, Salesforce, ServiceNow, the telephony/CRM — reached via
   connectors. Template SQLite/ledgers are a smell; a dev stub is fine.

---

## 1. The method — nine phases, in order

### Phase 1 — Frame the operation (write the story first)
Before any agent, write two paragraphs: **the story** (a real request enters,
flows through roles, produces an outcome — name a persona) and **why it works
in an organization** (what it deflects/automates, the ROI). If you can't tell
the story, you don't understand the operation yet. This becomes the PRD/README
opener.

### Phase 2 — Cast the roles (agents as job titles)
List every role the operation needs as a **job title**. Then *consolidate*:
if two roles share one responsibility-set, merge them (Rule 2). Assign each a
type (§3). Aim for the smallest cast that still reads as a real department.

### Phase 3 — Draw the flow (DAG + gates)
- **Ingress:** one entry point per channel/trigger; add `brokers` +
  `listen_events` for event/async triggers; `wake_up` cron for sweeps.
- **Forward edges:** `can_call` with conditions on `calling_agent_response.*`.
- **Human gates** at every high-judgment or irreversible step (default-deny).
- **Bounded back-edges** for rework only (Rule 3 — counter + cap + escape).
- **Audit terminus** on every branch.
Sanity-check: is there any hub everything returns to? Remove it.

### Phase 4 — Decide YAML vs Python, per agent
Default to pure YAML. Add an `agency/<name>_agent.py` module **only** for:
- a **deterministic control floor** the LLM must not be able to waive
  (PII/secret sweep, security gate, completeness gate, hard-escalation
  keywords);
- a **side-effect / actuator** (place a call, push to a system, file a bug);
- **domain math** or shaping the LLM can't reliably do;
- **pre-pulling context** (a queue, a diff, account history) before the
  LLM/connector runs;
- **shaping an external connector's raw result** into yields.
If none apply, the agent is YAML-only. Be honest — adding a module is a
choice with a cost (tests, maintenance), not a default.

### Phase 5 — Wire the decorators (§6 catalog)
Map each module to `@pre_compose` / `@chain` / `@conditional_chain` /
`@compose` / intelligence-shaper. Keep each function small and pure.

### Phase 6 — Connectors & the boundary (§5)
Pick the connectors: channel adapters (whatsapp/telegram/slack/email…),
listeners (redis_streams/imap/kafka/sqs/mqtt), `mcp`/`n8n` for systems,
`claude_agent` for autonomous coding. Decide ingress adapters (outside the
mesh) vs egress connector actors (inside). For customer contact, route
through external comms systems — bulk-batch where possible.

### Phase 7 — Controls
Default-deny human fallbacks; bounded loops via `session_stash` counters;
WORM audit; **and the yields↔prompt contract**: every LLM agent's prompt must
carry an `OUTPUT CONTRACT` block listing *every* yield key — zero overlap and
the SDK refuses to boot.

### Phase 8 — Verify (§7 doctrine)
`validate_config` → real-SDK `from_yaml` **against the version that has the
connectors** → run the agency modules directly (smoke) → for runtime
mechanics that can't be introspected (streaming, side-effects, chain↔session),
a **live smoke test**. Then adversarially self-check (§8).

### Phase 9 — Document to the completion standard
Ship: **Story**, **Why it works in an organization**, **Requirements
(3-tier config)**, **Agent table** (`Agent | Role | Responsibilities | Can
perform`, Role = job title), and a **PRD** for the deeper architecture.

---

## 2. Agent-type decision

| Type | Use when | Boundary note |
|---|---|---|
| `llm` | judgment over text — classify, draft, decide, converse | grounds via `knowledge:` RAG; carries the OUTPUT CONTRACT |
| `programmatic` | deterministic logic or a pure connector push (`integration` + `connector_config`) | no Python needed if connector-only |
| `human` | high-judgment / irreversible sign-off; an operator on *your* side | default-deny fallback; routes on `human_message` |
| `external` (`framework:`) | hand work to another runtime — `claude_agent` (autonomous coding), `mcp`/`n8n` (systems), crewai/langgraph/… | `@pre_compose` runs before the connector; shaper after |

---

## 3. The decorator catalog (when to reach for each)

- **`@pre_compose(context_processor=…)`** — pull what the role needs *before*
  it runs: a work queue, a PR diff, account history, the request + dedupe
  signal. Runs **before** the LLM *and before an external connector*. May
  carry a side-effect (e.g. place an outbound call and inject context).
- **`@chain(fn, …)`** — run *after* the agent. Two jobs: (a) **enforce
  floors the LLM can't waive** (security → block, PII → no-send,
  form-incomplete → don't advance); (b) **post-process** (form-fill from a
  blob, lifecycle writes, persist a pick). **Bound back-edges here** with a
  `session_stash` counter → escalate at the cap.
- **`@conditional_chain(cond, …)`** — branch the post-processing.
- **`@compose(**target_shapers)`** — emit a *different* payload per
  downstream agent.
- **intelligence shaper** (the name-matched module fn for an `external`
  agent) — map the connector's raw result into the declared yields.
- **`@global_tool`** — runtime write tooling the LLM calls mid-run
  (`jira_update`, `jira_create_bug`). Pair with a `@chain` that *guarantees*
  the write even if the model forgets: **tool for the moment, chain for the
  guarantee.**

---

## 4. The mesh boundary (external parties)

The model that resolves "how does the customer talk to the mesh?":

- **The customer is never a member; no mesh agent talks to them.** Agents
  talk to *other agents* or *external systems* only.
- **Ingress = a mesh call.** A channel adapter / external system (LiveKit,
  a WhatsApp webhook, the chat platform) turns the external event into an
  `entry_point` invocation (or onto a `listen_events` stream).
- **Egress = a connector actor.** Live: an LLM agent streams its reply to
  the *external system* (it's responding to LiveKit/Twilio, not the person).
  Async: a **programmatic** agent uploads to a comms platform that
  **batch-sends** once a threshold is met. External party → CPaaS; internal
  recipient → a `human` channel.
- **Continuity = a `conversation_id` + the session store, never a held
  connection.** A reply hours later is a *fresh* mesh call resolved back to
  the open ticket. This is not "mesh-to-mesh."
- **Sessions are first-class:** `SessionData.conversation` holds the
  multi-turn transcript, `state` the running scratch; streaming is
  `StreamChunk(delta, finish_reason)` (use `finish_reason` to detect
  turn/conversation end).

---

## 5. Verification doctrine (earn the confidence)

1. **`validate_config`** — structure, targets, conditions, the yields↔prompt
   contract, module reconciliation (dead modules / unshaped externals).
2. **Real-SDK `from_yaml`** — but **against the version that actually
   contains the connectors you use.** A config parses fine on a version that
   *lacks* `claude_agent`; that load proves nothing. **Config-load ≠ runtime
   proof** — this is the single most common false-confidence trap.
3. **Module smoke tests** — run each `agency/*_agent.py` directly with stub
   inputs; assert the floors fire, the gate holds, the shaper maps.
4. **Live smoke test** — for mechanics you *cannot* introspect from compiled
   bytecode: streaming, `@pre_compose` side-effects, whether `@chain`
   receives the session transcript, outbound same-session. These need a
   running mesh in the target environment.
5. When a primitive's wiring is unproven, **design conservatively** (e.g.
   read `session.conversation` if present, else accumulate via
   `session_stash`) and **flag it for the live smoke test** — don't assert
   it works.

---

## 6. Adversarial self-check (the "are you sure?" pass)

Before declaring done, hunt for:
- **Phantom config** — env vars documented but consumed nowhere; connectors
  sold as "set the URL and it works" that actually need code. Check *both*
  directions (referenced→documented AND documented→used). Watch regex
  blind spots (digits like `N8N_`).
- **Unenforced narration** — distinguish two cases:
  - A route promised in an agent's **prompt / free-text comment** with **no
    mechanism** (no `can_call` edge, not in the `narration:` field) → a real
    bug; the LLM can't route. Add a `can_call` edge.
  - The **`narration:` field is a legitimate primitive** — additive,
    Manager/Summarizer-dispatched, may name *any* agent (only when the
    Manager is enabled; non-deterministic; ignored if Manager off).
    Conditions are the authority. So: a **must-happen route** (failure
    branch, legal/safety/escalation gate, anything default-deny) must be a
    deterministic **`can_call` condition** — never narration alone. A
    genuine **"maybe" route** ("if they sound frustrated, perhaps retention")
    is correctly left as `narration:`. Don't convert advisory additive
    narration into an exclusive edge (that changes semantics).
- **LLM-only safety** — PII/escalation/policy enforced only in a prompt; add
  the deterministic `@chain` floor.
- **Silent dead code** — a `*_agent.py` matching no agent; an external agent
  with no shaper.
- **Shallow verification** — claiming "loads under the real SDK" on the
  wrong version, or "tests pass" without running the runtime path.
- **Placeholder HITL** — dummy `operator_ids` make tasks invisible; leave
  unset to use the shared inbox.

---

## 7. Anti-patterns (lessons already paid for)

- **Conductor hub** → re-dispatch loops. Use forward-flow.
- **Customer as a mesh member** → unbounded membership. Keep them external.
- **Unbounded retry back-edge** → ChainCapExceeded. Counter + cap + escape.
- **yields↔prompt zero overlap** → SDK won't boot. OUTPUT CONTRACT.
- **Template SQLite as the system of record** → state belongs in the
  customer's systems; ship a dev stub at most.
- **One agent per channel for egress** → sprawl. One messenger, channel
  chosen at runtime; split out only genuinely different send semantics
  (voice dial vs text).

---

*The config is the department; the PRD is the brief; this doc is the method.
Cast roles, draw the hand-offs, add hands only where a role needs them,
verify against the real SDK, and document to the standard.*
