# Building agents & meshes thoroughly — the direction

> This is the direction, not the API reference. **Every rule here has a failure
> behind it, and most of those failures were silent.** Silence is the theme: an
> agent that is wrong *loudly* gets fixed in an hour; an agent that is wrong
> *quietly* ships to a person who believes it. Read this before you add an agent,
> a tool, or a store — and again before you call one finished.
>
> Affirmed from field experience ("Designing an agent with us") and from building
> the LeafMesh pods (expense-reimbursement, BA-practice). Where the source used
> generic words, this file maps them to the exact LeafMesh construct:
> **playbook = [Skills](SKILL.md#skills-system)**, **the four stages = the
> [decorators](SKILL.md#decorators--making-an-agent-self-reliant)**,
> **flow = the prompt's sequence-with-reasons + `context_parts.flows`**,
> **stores = `session_stash` / Redis / the domain store / the customer's system of record.**
>
> **Calibrate to your risk surface.** This doctrine was hardened by a user-facing
> assistant that touches a person's phone — so it is unusually paranoid about
> fabrication and about actuating. Take the *reasoning*, not the rules verbatim: a
> batch pipeline with no human reading the output has different economics, and some
> of §A5 (truth protocols) is overkill there. The reasoning is what transfers; the
> stricter the thing an agent can reach (money, health, calendar, a send), the more
> of this applies literally.

---

## PART A — The agent, built thoroughly

### A1. An agent is a role you would hire

**One job per agent.** Model agents as people you would put on a team. **If you
cannot say what an agent does in one sentence with no "and", it is two jobs** —
split it. (This is [Rule 2](SKILL.md#rule-2--one-role-multiple-responsibilities-the-hiring-test),
made sharper: the "and" test is the tripwire.)

What follows from it:

- **Wires are the policy.** Routing lives in `can_call` conditions in YAML, where
  anyone can read who reaches whom. **If you find yourself writing
  `if template == "...": call_other_agent()` in Python, the wire belongs in the
  config.** Routing hidden in a function is a policy nobody can review.
- **The config is the department.** Topology, routing, prompts, contracts — all
  declared in `configs/config.yaml`. **Python is only for:** actuators with side
  effects, domain math that must not be hallucinated, and controls like the audit
  sink. Nothing else.
- **Don't split one job across two agents.** Auditing is *not* a role — "write
  down what happened" is a *step inside* other roles. In LeafMesh it is a function
  call (`sdk.intelligence(name)(fn)` → the WORM sink) invoked from every agent
  that does something, **not** a standalone agent per writer. Conversely, never
  merge a control (approval gate, reviewer, actuator, audit) into a role — see
  [Rule 2's "never merged" list](SKILL.md#rule-2--one-role-multiple-responsibilities-the-hiring-test).

### A2. The four stages — and what belongs in each

```
@pre_compose  →  inference (the model + its tools)  →  @chain  →  @compose
```

| Stage | Whose job | What it is for — and ONLY this |
|---|---|---|
| `@pre_compose` | **code** | Establish **identity** (whose turn is this). Select a **flow**. Nothing else. |
| inference | **the model** | **Decide. Pull. Act. Report.** |
| `@chain` | **code** | **Verify** what came back. **Fail closed.** Audit. |
| `@compose` | **code** | Shape the handoff to the next agent (per-downstream payloads). |

**The rule underneath it: code prepares and verifies; the model decides and acts.**
Every time a decision is moved into `@pre_compose` "to make it reliable", it gets
worse — because the code has to guess, and it guesses from a keyword match on a
sentence. Two consequences that cost real days:

- **Don't pull facts in `@pre_compose` that the turn may not want.** Pulling the
  user on every turn *decides* the turn is about that person before the model has
  read the request. A fact the model *may* need is a **tool call** (model-chosen,
  in the inference). A fact it **always** needs is `@pre_compose`. Confusing the
  two is the most common modelling error (see the skill's decorator note).
- **A raising `@pre_compose` does not stop the turn.** The SDK logs the error and
  **runs the agent anyway — with no flow, no prepared context.** The agent then
  works *badly*, without the instructions it was built around, and nothing
  surfaces. **If a stage can fail, it must fail into a defined state, not into
  absence.** Wrap `@pre_compose` bodies so a failure yields a known-empty,
  known-flagged context — never an exception that the runtime swallows.
- **`@chain` is where you fail closed.** Anything the model could invent that
  reaches a person's money, health, calendar, or an outbound send gets **checked
  in `@chain` after the model has spoken and before anyone sees it** — a
  `numeric_guard` that rejects a fabricated id or amount, a floor that rejects an
  unapproved artifact. Not trusted because the prompt said not to. This is the
  [finisher floor](#b4-the-finisher-pattern) in Part B.

### A3. Three layers of instruction — and why they MUST stay separate

This is the part people get wrong, and it is why a well-written playbook can sit
unread for weeks.

| Layer | Contains | Cost | Answers | LeafMesh home |
|---|---|---|---|---|
| **prompt** | persona, output contract | **every turn** | Who am I, and what shape is my answer? | agent `prompt:` + `yields:` |
| **flow** | what to call, when, and **why** | **every turn** | What is the sequence? | prompt's ordered steps + `context_parts.flows:` |
| **playbook** | how each job is actually done | **on demand, per job** | How do I do THIS job well? | **Skills** (`skills:` — loaded via `load_skill_reference`) |

- **Prompt is identity, not instruction.** Keep it small — who the agent is and
  the exact JSON (`yields`) it must return. **No how-to.**
- **Flow is sequence *with reasons*.** Not a catalogue — the *reason* each call
  comes where it does. "A model that knows *why* `get_user` comes first will not
  skip it under pressure." Example: *"`get_user` FIRST, before any other tool — it
  decides WHAT you go and fetch, so fetching before you pull it means fetching for
  a stranger."*
- **Playbook (Skills) is the craft.** One skill per job, fetched when the model
  recognises the job. This is where domain knowledge lives: which reads precede
  which writes, what a specific failure means, what to say instead of guessing.

**The pairing rule (this is why the split is not stylistic):** if the prompt
carries the job description, the model has **no reason** to call the playbook.
They compete, and whatever is resident wins (it is already there; the tool call
is not free). **Duplicating a playbook line into the prompt does not reinforce it
— it kills the playbook.** In LeafMesh terms: do not restate a Skill's body in the
agent `prompt`.

**The exception that costs the most:** anything needed on **every** turn stays
**resident** (in the prompt), never behind a Skill. Moving the closed action
vocabulary (`send_sms`, `set_alarm`, …) behind a Skill made a planner *invent*
action names — rejected before dispatch, and **the person got nothing, with no
error anywhere.** The test: **if forgetting it breaks the turn, it is prompt, not
a playbook section.**

*What it looks like when it works* — same request, before and after the playbook
became reachable:
```
before: fetch_latest_news(topic="top") → get_user → send_card         # generic feed, wrong
after:  playbook("news") → get_user → fetch_latest_news ×4 → send_card # 4 topics from the user's setup
```
The card looked correct either way — **which is the whole problem. Nothing in the
result told the user which briefing they got.**

### A4. Tools — the model acts; code does not act afterwards

- **Dispatch happens *inside* the turn, through tool calls.** Do **not** have the
  model return `action / target / parameters` and let code dispatch after it
  stops. An agent with more than one thing to do cannot know whether its work is
  finished if the doing happens after it ends — it finishes *believing* everything
  is handled, having sent nothing.
- **Identity comes from code, never the model.** The turn's user is set in
  `@pre_compose` and read by the tools themselves. Never ask the model who it is
  serving — asked once, it passed `user_id="2115"`, a number it lifted out of the
  request text. The turn's user always wins:
  ```python
  def _who(user_id: str = "") -> str:
      turn = _CURRENT_USER.get("user_id", "")
      return turn if turn else str(user_id or "").strip()   # turn wins; arg is only a fallback
  ```
  This is not distrust of the model; a misrouted card is unrecoverable and the
  model has no way to know it guessed.
- **A stub must announce itself.** A connector/dev-store fallback that returns
  `{"status": "placed", "eta_minutes": 35}` for an order that never happened is a
  **synthetic success indistinguishable from a real one** — to everything
  downstream, the user included. **If there is no real path, return
  `available: false` and say why.** (This is exactly why the shipped finishers set
  `sent=False` / `artifact_produced=False` on a dev-store fallback and never fake
  an ack — see [B4](#b4-the-finisher-pattern).)
- **Fake data is tidiness until it can reach a real person.** A contact stub full
  of plausible mobile numbers feeding a real `send_sms` is a live incident waiting
  to happen. Seed data is fine *only* when it cannot actuate.
- **One way to do one thing.** If two paths can do the same job, the **weaker one
  silently owns whatever traffic reaches it first**. A triage agent with its own
  `do_on_phone` tool AND a planner that dispatches device actions properly meant
  four scenarios failed on the weak path while the planner's was untouched. Delete
  the duplicate; the failure was never the fields, it was **ambiguity** — two ways
  to do one job. (The same fields that failed as a dispatch tool work fine as a
  todo list handed to the one agent that executes.)
- **Fewer doors.** One `read_phone(kinds=[…])` that reads several sources in one
  session beats four readers each opening its own — not for tidiness: an agent that
  wanted a day AND notifications from two readers paid twice and, on a background
  pass, got **two answers from two different moments with nothing saying so**.
  Collapse N ways to read one thing into one.

### A5. Truth protocols — never say something about a person's life that isn't so

These guard one specific failure: the system asserting something about a person in
a way that person **cannot detect**.

- **Never collapse three outcomes into one.** Every read has three distinct
  answers and they must stay distinct:

  | Outcome | Means |
  |---|---|
  | `count: 0` | We looked. There is nothing. (A free day. No transactions.) |
  | `unreachable` | The source never answered. **We do not know.** |
  | `skipped` | We declined to look (asleep, opportunistic read). |

  A flat battery reading as "no transactions" is a *fabrication about someone's
  money*. A skipped calendar read that renders "11 AM Sales review" invents
  meetings they will plan around. In LeafMesh: an unwired connector returns
  `unreachable`/`available:false`, **never** an empty-but-confident `count:0`.
- **Real source or no card.** Build the artifact `None` when no real provider is
  connected. A `demo: true` badge does not fix a fabricated figure — it protects
  *you*, not the person reading it.
- **Provenance is not existence.** Provenance proves where a number *came from*,
  not that the world *contains* it. A grounding gate will happily pass a test
  notification injected during development. **Ask both questions.**
- **Never claim what you did not confirm.** An action is "done" when the device
  **acked** it — not when it was dispatched. "Sent" and "queued" are different
  facts about the world. An agent told `queued` must not tell the user it happened.
- **Window boundaries are a correctness surface.** A calendar window starting at
  "now" returned zero for a fully booked day. Off-by-one on a boundary is a
  truth bug, not a cosmetic one.

### A6. Where data lives — find the fact's home before you add a store

| Kind of fact | Home | Why |
|---|---|---|
| Who someone is, their devices, their **traits** | identity store | Small, stable, one current value per `(domain, key)`, meaningful to any agent |
| Domain **working state** — observations, rules, schedules | the domain store | Append-heavy, shaped by one agent's needs, unreadable without its logic |
| A **ledger** | the domain store | Has invariants only the domain can enforce |

**The test:** *could another agent, in another domain, act correctly on this
without understanding your domain?* "Banks with HDFC" → yes, that's a **trait**.
"Observation #4412, systolic 128, pending rule 9" → no, that's **domain state**.

- **A store that cannot enforce its own invariants will hold corrupt data
  politely** — that is why a ledger never moves to an identity store, however
  user-shaped it looks.
- **Don't build a queue/cache for a fact that is already safe.** A retry queue for
  writes to a cache — while the fact was already durable upstream — protected the
  copy that didn't matter, leaked collections, and hit a cluster cap that took the
  test suite down.
- **Nothing writes to local files as a system of record.** The shipped `./data`
  dev store is a **dev stand-in only** (see [B/C](#part-c--from-heres-what-i-have-to-a-running-mesh-intake--provisioning)).
  A `reminders.jsonl` that accumulated 96 test rows was read by a wake as the
  user's real commitments. Real store or device — never a file in the repo.
- **One vocabulary.** If two services name the same concept differently, they
  agree in review and disagree in production (`SignalDomain=[…, today]` vs
  `MemoryDomain=[…, admin]` matched *nobody*, silently). **Fold synonyms at the
  boundary, normalise unknowns to empty, and never let a typo become a new
  category nobody sweeps for.**

### A7. Verification — know which layer you are standing on

Four different facts, each a different layer. Confusing them cost the most:

```
registered   the boot log says the tool loaded            ← true, and useless
permitted    the registry says this agent may call it
offered      the schemas in the request the provider gets  ← THIS one decides
called       what the model actually did
```

A playbook can be *registered* and never *offered* (e.g. every agent registering
under one shared name, overwriting the last — only the last-booted agent could
call it). Three probes "confirmed" three wrong answers, each correct about the
layer it looked at, each one layer below the bug.

- **Registration is not exposure. Permission is not exposure. Availability is not
  use.**
- **Probe the path that decides the user's experience.** For "what can the model
  see", drive the real executor with a mock provider and read the tools out of the
  request it *receives*.
- **Build the control, not just the measurement.** When something is missing, rerun
  the same probe with one variable changed — that turns "it doesn't work" into a
  two-line reproducer.
- **A green test on a simplified setup proves the simplified setup.** A fix that
  passed end-to-end with one agent needed *two*. **Reproduce at the real
  cardinality.** (In LeafMesh: `validate_config.py` proves structure, not runtime;
  a day-0 dev-store run proves the chain, not the connectors. State which layer you
  verified — see the [verification doctrine](agency-development.md).)

### A8. Shipping across a boundary you do not control

Most of what you build lands next to something a different team ships.

- **Omitted must mean the call is unchanged** — not the *value*, the *call*.
  Adding an always-present parameter (even `""`) changes every signature it
  touches and every service that validates strictly. **Send a field only when it
  is set.** (LeafMesh: this is why connector configs use `${VAR:}` empty-defaults
  and stay inert until set.)
- **Inert by default when the other side hasn't shipped.** A filter that scopes a
  batch to "people a domain is live for" is correct, indexed, tested — and until
  the other side reports activity it claims **zero users on every sweep**, so all
  scheduled work stops **with no error anywhere.** Wire it through, pass it from
  nowhere, and pin the reason in a test that names itself when a sweep mysteriously
  stops finding work. **Beware anyone (including yourself) calling a change "inert"
  and "returns zero" in the same breath — only one of those decides whether work
  happens.**
- **A lease is a slot.** When a batch claims work, every row it will discard on
  sight pushes out someone who genuinely needed help. "Nothing to do for this
  user" is too ordinary an outcome for anyone to notice it happened.
- **Instrument both ends before blaming either.** Two independent implementations
  of the same dropped field, each certain it was the other.
- **Don't wake a device just to read.** Background reads pass `opportunistic=True`
  and accept `skipped` as an answer (ties back to [A5](#a5-truth-protocols--never-say-something-about-a-persons-life-that-isnt-so)).
- **Say "live after the next restart", never "done".** A merged endpoint that
  404s is indistinguishable from one that was never built.

### A9. Before you call an agent finished — the checklist

- [ ] Can you say its job in **one sentence with no "and"**?
- [ ] Is routing in `can_call`, **not** in Python?
- [ ] Does `@pre_compose` establish **identity** and select a **flow** — and nothing else? Does it fail into a *defined* state, never into absence?
- [ ] Does the `prompt` hold only **persona + output contract** (`yields`)?
- [ ] Does the **flow** give the sequence **and the reason** for it?
- [ ] Is every how-to in a **Skill**, and **nowhere else** (not duplicated into the prompt)?
- [ ] Is everything needed on **every turn** resident?
- [ ] Does every tool that can fail distinguish **nothing / could-not-tell / declined**?
- [ ] Does every **stub announce itself** (`available:false`, never a synthetic success)?
- [ ] Does **identity come from code**, not the model?
- [ ] Does `@chain` **fail closed** on anything that reaches money / health / calendar / an outbound send?
- [ ] Did you verify at the **offered** layer and at **real cardinality** — not just "registered"?

---

## PART B — The mesh, designed thoroughly (lessons from the expense-reimbursement pod)

The expense-reimbursement pod (Remi · Odo · Fern · Sol + human members) is the
reference implementation of the house style. What building it taught, distilled:

### B1. The pod shape

A pod is **a coordinator + specialists + a finisher + human gates + a supervisor**:
- **Coordinator** (Remi) — owns the case end-to-end, orchestrates, keeps live
  status, is the single point of contact. **Never does specialist work** (never
  reads a receipt, never approves).
- **Specialists** (Odo reads/extracts; Fern builds; Sol routes approval→finance) —
  each a role with responsibilities, each self-reliant ([Part A](#part-a--the-agent-built-thoroughly)).
- **Finisher** — the agent *after* the human gate that produces the real artifact
  ([B4](#b4-the-finisher-pattern)).
- **Human members** — Finance-Ops Lead (accountable owner), Employee, Approver,
  Finance Officer — reached in their own channels, first-class, never endpoints.
- **Supervisor = the LeafMesh Manager** — reads every hand-off; stalls, contract
  violations, repeated errors escalate to the accountable human automatically.

### B2. One human, one agent, one system per stage

Held at *every* stage: **the agent produces, the human decides, the system
records. No stage advances on an agent's own authority.** If a stage has an agent
acting *and* deciding, you've collapsed a control — split it.

### B3. Membership, entries, wires, loops

- **Members are people and agents; systems are tools.** A system earns a seat only
  if it can act on an *intent given context* (decide, ask, negotiate, hold a
  responsibility). Outlook/Box/SAP/Teams/SharePoint/Jira cannot → they are
  **tool-chips inside agents**, never nodes, and **data never leaves them.**
- **Multiple entry points** — one per real trigger (receipts, a status ask, a
  daily cron sweep). Don't force everything through one intake.
- **Every wire is conditional** on the producer's declared output. A bare
  unconditional edge is a smell that two roles should be one.
- **HITL gates default-deny.** `fallback_on_timeout: true` + a `fallback_response`
  that resolves to a **non-approving** verdict (`held_for_review`) routed to the
  audit sink. **Silence never advances anything.**
- **Bounded back-edges.** Re-extract / rejection loops count their rounds *in the
  mesh* (exhaustion counter → terminal route — [Rule 3](SKILL.md#rule-3--bound-every-retry-back-edge)).
  Back-edges *through a human* are the worst offenders — bound them first.
- **WORM ledger terminus.** Hash-chained, append-only, registered via
  `sdk.intelligence(name)(fn)`; every approval, send, and reversal recorded, never
  edited.

### B4. The finisher pattern

The **artifact-producing executor** — the single most load-bearing pattern, and
the concrete form of "[`@chain` fails
closed](#a2-the-four-stages--and-what-belongs-in-each)". An agent wired **after**
the human gate that:

1. **Re-checks approval** — never trusts that *reaching* the agent means approved.
   An **allow-token allowlist + block-token denylist**, so an unknown/ambiguous
   verdict **fails closed**.
2. **Enforces deterministic invariants a human can't waive** — PII/policy
   concerns empty; approver authority re-derived *in code* from the matrix; no
   double-issue; frequency caps.
3. **Renders the real artifact** to `./out` (PDF via ReportLab, else Markdown) —
   or an outbox/booking record.
4. **Fails closed on trip — deletes the partial artifact**, marks
   `artifact_produced=false` + `block_reasons`, records nothing downstream.
5. **Two-layer defense** — the body short-circuits before writing; the `@chain`
   floor re-checks independently.
6. **Dev-store fallback that announces itself** — runs day-0 with no connector by
   writing a *verifiable* dev-store record, and **never fakes a real ack** ([A4](#a4-tools--the-model-acts-code-does-not-act-afterwards)).

Reference modules: `procurement-ops/agency/purchase_order_agent.py`,
`bd-proposals/agency/proposal_assembler_agent.py`,
`quote-to-cash/agency/quote_issuer_agent.py`.

---

## PART C — From "here's what I have" to a running mesh (intake + provisioning)

When a user describes their systems, build in this order. This is the
client-intake method — how you turn "we use Outlook and Box and no real backend"
into a running LeafMesh pod.

### C1. Inventory — write down three lists

1. **Triggers** (what starts work): an email arrives, a webhook fires, a form is
   submitted, a schedule ticks, a chat message lands. → these become **entry
   points**.
2. **People** (who decides / owns / claims): approvers, an accountable owner, the
   end user. → these become **human members**.
3. **Systems** (where truth lives / work is recorded): mailbox, file store, ERP,
   CRM, DB, spreadsheet. → candidates for **tools/connectors**.

### C2. Apply the membership bar to every system

For each system ask: *can it, today, act on an intent given context — decide, ask,
negotiate, hold a responsibility?* **Almost always no** → it is a **tool inside an
agent**, wired as a connector, never a member. (An agentic ITSM that can genuinely
accept and negotiate an intent is the rare exception that joins as a member.)

### C3. Cast the mesh

- **Agents = roles** (one job, no "and" — [A1](#a1-an-agent-is-a-role-you-would-hire)):
  coordinator + specialists + finisher.
- **Humans = members** reached in their channel (inbox / Teams / Slack / Box).
- **Systems = tool-chips** inside the agents that operate them.
- **Controls stay separate**: approval gates, the finisher, the WORM sink.

### C4. Pick a connector per system

| The user has… | Wire it as |
|---|---|
| Outlook / Gmail / mailbox | native email channel (SMTP/IMAP) or Graph/MCP connector |
| Slack / Teams / WhatsApp / Telegram | native `channels:` adapter on the human agent |
| A SaaS with an API (CRM/ERP/WMS, Box, Jira, SharePoint) | `integration: mcp` / `n8n` connector agent, shaped by `@sdk.intelligence` |
| A webhook-only system | `programmatic` agent + `connector_config.webhook_url` (n8n), or `/callback/{agent}` |
| Nothing yet for this step | ship the **dev-store stub** (`./data`) that **announces itself** ([A4](#a4-tools--the-model-acts-code-does-not-act-afterwards)), inert until the real URL is set ([A8](#a8-shipping-across-a-boundary-you-do-not-control)) |

Every connector uses `${VAR:}` empty-defaults and is **inert until wired** —
never a synthetic success in the meantime.

### C5. "I don't have any backend" → provision one (Supabase, or the right fit)

A LeafMesh mesh needs two kinds of persistence. Map the user's answer:

1. **Session / working state** — `session_stash` (in-process) and **Redis** ship
   with the SDK. **Always present**, no provisioning needed. This is where retry
   counters, per-session state, and the HITL-recovery ladder live.
2. **System of record** — durable relational data + files + (optionally) auth.
   **If the user has none, provision it.** Default recommendation: **Supabase**
   (hosted Postgres + Storage + Auth + PostgREST + Realtime), because it gives all
   three in one, with an auto REST API you can wire without writing a backend.

**Supabase → LeafMesh mapping** (respecting [A6 "where data lives"](#a6-where-data-lives--find-the-facts-home-before-you-add-a-store)):

| LeafMesh need | Supabase | Notes |
|---|---|---|
| Identity / traits | a `profiles` / `entities` table (one row per `(domain,key)`) | small, stable, readable by any agent |
| Domain working state | domain tables (append-heavy) | shaped by one agent's needs |
| **WORM ledger** | an **insert-only** table — RLS/triggers block `update`/`delete` | this is what `sdk.intelligence(name)(fn)` writes to; enforces its own invariant, so it stays in the domain store, never the identity store |
| Files / documents (receipts, rendered artifacts) | **Supabase Storage** bucket | replaces a Box/`./out` dev path in production |
| Human auth / a review UI | Supabase Auth | only if the pod needs a hosted human surface |

**How to wire it:** the shipped templates read/write a JSON **dev store**
(`agency/_shared/store.py`, under `./data`) day-0 — *dev only, never a system of
record* ([A6](#a6-where-data-lives--find-the-facts-home-before-you-add-a-store)).
Going live = **swap `store.py`'s function bodies for Supabase calls** (the
`supabase-py` client, or PostgREST over HTTP via a `programmatic`/`mcp` connector
agent). The function signatures are the contract; the mesh does not change. Point
`.env` at `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` (kept in the vault, never in
code — [A8](#a8-shipping-across-a-boundary-you-do-not-control)).

**Other fits** (pick by need, don't over-build — [A6](#a6-where-data-lives--find-the-facts-home-before-you-add-a-store)):
- **Redis only** — if all they need is ephemeral/session state and a simple KV
  ledger, the SDK's Redis is already enough; don't provision Supabase for nothing.
- **Airtable / Google Sheets** — lightweight, human-editable, good for a pilot;
  wire via n8n/MCP.
- **Their existing ERP/WMS/CRM** — if they *do* have one, that IS the system of
  record; connect to it (MCP), don't build a parallel store beside it (the
  don't-build-a-queue-for-a-safe-fact rule).

### C6. Controls + verification before you call it done

- Default-deny gates, bounded loops, WORM sink ([B3](#b3-membership-entries-wires-loops)).
- `validate_config.py` clean (structure), a day-0 dev-store run (the chain), then
  each connector wired and verified at the **offered** layer and **real
  cardinality** ([A7](#a7-verification--know-which-layer-you-are-standing-on)).
- Walk the [finished-agent checklist](#a9-before-you-call-an-agent-finished--the-checklist)
  for every agent, and confirm the pod's discipline in one sentence: **agents
  produce, humans decide, systems record — and silence never advances anything.**
