# LeafMesh — Nuances & Gotchas (READ FIRST)

**SDK baseline: 2.4.509** (templates pin `leafmesh>=2.4.509`). This file captures the non-obvious rules that cause
real, hard-to-debug failures. Most "my agent silently does nothing" or "the
handoff looks empty" or "Gemini behaves differently from GPT" reports trace to
exactly one item below. Read this before wiring agents.

Each rule states: **the trap → why → what to do.**

---

## 1. An `llm` agent's function MUST take exactly three parameters

**Trap:** you write `async def my_agent(input_data, context):` and the function
— including any `@chain` / `@compose` / `@pre_compose` on it — is **never
called**. The raw LLM output is routed instead, and nothing errors.

**Why:** the LLM path only invokes the 3-parameter form
`(llm_response, input_data, context)`. Any other arity falls into a
backward-compat branch that returns the raw LLM envelope and skips your
function entirely.

**Do this:** every `llm` agent function is
```python
async def my_agent(llm_response, input_data, context):
    ...
```
`llm_response` is the model's output (parsed dict when `yields` is declared),
`input_data` is the trigger/handoff, `context` is session/routing.

Since 2.4.100 the SDK **warns loudly at start()** when it sees a 2-param llm
function (`… will NEVER be called …`). If your decorators "do nothing," grep the
startup log for `NEVER be called`.

> Programmatic / human / external agents use other signatures — this rule is
> `agent_type: llm` only.

---


## Two meshes on one machine share the dated log file

`logs/leafmesh_<date>.log` is keyed by DATE, not by project or port. Run a
second mesh on the same box — a replica, a test pod, a colleague's env — and
both append to the same file. A report that greps that file for errors will
attribute one mesh's failures to the other, and it looks exactly like your
mesh broke.

Found twice in one day: a verify run picked up a deliberately-broken test
mesh's boot errors, and separately a probe's output landed in a different
project's log entirely.

- Give each mesh its own ports (`LEAFMESH_API_PORT` **and** the evolution port
  — set `evolution_api: {port}` in YAML, or `LEAFMESH_EVOLUTION_API_PORT`;
  note the `LEAFMESH_` prefix, the unprefixed name is read by nothing).
- When reading the log, filter by the run's own timestamp window before
  concluding anything about errors.


## 2. How a downstream agent SEES an upstream agent's output (handoffs)

**Trap:** agent B seems to ignore everything agent A produced except one text
field. You conclude the handoff is "empty" or "provider-specific."

**Why:** when A hands off to B, B's `input_data` is A's full output (a dict) —
nothing is lost at the transport layer. But **the prompt builder is
provider-agnostic** (byte-identical prompt for Gemini and OpenAI — there is no
"Google drops upstream" behaviour). What varies is *rendering*:

- If B's `input_data` has a `user_message` / `message` key, that string becomes
  B's user turn.
- **Since 2.4.104 the SDK ALSO renders A's other structured fields** as a
  labelled `UPSTREAM HANDOFF CONTEXT` system block — so B sees BOTH the user
  message and A's yields (intent_brief, prepared actions, ids). This is the
  "read both" behaviour.
- Before 2.4.104, only `user_message` rendered and A's other fields were
  silently dropped from the prompt (present in `input_data`, invisible to the
  model). Teams worked around it with `@compose` shapers that crammed everything
  into `user_message` text — which *itself* triggered the short-circuit. On
  2.4.104+ those shapers are redundant; you can delete them.

**Do this:**
- On 2.4.104+, DON'T hand-embed upstream fields into `user_message`. Let the
  SDK render them. If you have legacy shapers doing this, remove them (verify
  with the acceptance test below).
- Use `@compose` only when a target genuinely needs a *different shape* than
  the raw output — not to make fields "visible."
- Transport/plumbing fields (`tenant_id`, `device_id`, `session_id`, …) are
  rendered as a compact `(routing metadata — do not echo …)` line, not as
  content, so the model won't copy them into its yields.

**Acceptance test (prove it end-to-end):** chain two agents, plant a sentinel
string in a NON-`user_message` yield of the upstream agent, and grep the
downstream agent's built prompt (its `LLM Input` in the trace) for the
sentinel. Present = working.

---

## 3. `yields` shapes — declare item/field types or the model guesses

**Trap A — bare array:** you declare `tasks: "array"` and the model returns
`["find_doc", "upload"]` (bare strings) instead of task objects.

**Why:** schema-consuming providers reject an array with no element type, so the
SDK fills in `items: {type: string}` — which *tells the model to return
strings*. Since **2.4.486** start (and `/api/yaml/validate`) **warns** for
every list with no item type on an LLM agent, at any depth — "'researcher': yields
'report.recommendations' is a list with no item type, so the model is told to
write text items". (The 2.4.102 check looked only at top-level keys and was
never called.) It is a warning, not a refusal.

**Do this — declare the shape:**
```yaml
yields:
  tasks:
    type: "array"
    items:
      type: "object"
      fields:
        step: "number"
        action: "string"
        target: "string"
```

Write `type: "array"`. Since **2.4.487** `{type: list, items: …}` is read as
an array everywhere too (before, the model was told it was an object), and the
model's example shows every nested field — an object's declared fields and
one item of a list of objects.

**Trap B — dict-shaped yields were unvalidated (pre-2.4.101):** an
array-of-objects contract used to silently accept an array of strings. Since
2.4.101 dict-shaped `yields` are validated recursively (item types, nested
fields, presence). `enforce_yields: true` + `enforce_yields_retry: N` makes it
a hard contract with self-correction.

**Flat/scalar yields** (`is_multistep: boolean`, `summary: string`) always
worked and are the safe default.

---

**Nullable fields:** any yields declaration may add `nullable: true` (2.4.104)
to accept an explicit null. If a field is legitimately null sometimes, DECLARE
it nullable — do not leave it undeclared, and do not let the prompt mandate
null for a non-nullable field (the SDK detects that conflict and skips the
doomed reflection retry, telling you which to fix).

---

## 4. Structured output is IDENTICAL across providers (2.4.103)

**Trap:** you assume Gemini/Anthropic/Bedrock enforce a hard native schema while
OpenAI is "looser," and design around that difference.

**Why/what changed:** as of 2.4.103 EVERY provider uses the same enforcement
path — basic JSON mode (no native schema), the `yields` keys in the prompt, and
the SDK's own validation + reflection retry. An agent behaves the same whichever
model runs it. Don't rely on provider-specific structured-output behaviour; there
isn't any on the `yields` path.

---

## 5. Gemini: thinking is ON by default and eats your token budget

**Trap:** a Gemini agent (esp. the Manager) returns empty or mid-sentence
truncated JSON intermittently.

**Why:** Gemini 2.5/3.x think by default and thought tokens count against
`max_tokens`. A small budget (e.g. an agent left at its default 800) can be
consumed entirely by thinking → empty or truncated output. Since 2.4.101 the SDK reserves
headroom and fails MAX_TOKENS truncation loudly, but tight budgets still hurt.

**Do this:** give Gemini agents generous `max_tokens` (4000–8000). The
Manager's own default is 4000, and since 2.4.485 it really reads its own
`manager.max_tokens` / `manager.temperature` (a hardcoded 800 and 0.1 are gone)
— raise it under the `manager:` block if the Manager runs on Gemini and still
truncates.
**Gemini 2.5 Pro cannot turn thinking off** and thinks past the small budget
the SDK sets: with `max_tokens: 1000` it spent 1,125 tokens thinking and wrote
nothing. Since 2.4.443 such a reply is asked again with twice the room, but
that is a paid extra call — give 2.5 Pro agents at least 2000–4000.

---

## 6. Image generation (2.4.104) — native `llm`, all image-capable providers

**What:** an agent whose model is an image model (`gemini-3-pro-image`,
`gemini-2.5-flash-image`, `gpt-image-1`, `dall-e-3`, `imagen-*`, Titan/SDXL on
Bedrock) — or which sets `output_modality: image` — generates images natively,
with real token/cost tracking. Images arrive on the response's `media` list
(`{mime_type, data (base64) | url, creative_id}`) and surface to your agent as
`llm_response["media"]`; a `media.generated` audit event fires.

**Supported:** Google, Vertex (Imagen), OpenAI (/images endpoint), Bedrock
(Titan/SDXL). **Not supported:** Anthropic (no image API — the SDK rejects it at
start() rather than silently make a text call).

**Do this:** point the agent at an image model; no other config needed. Live-
verified on Google; validate other providers in your own environment first.

---

## 7. `discover()` binding is by NAME — a mismatch is silent dead code

**Trap:** you create `agency/foo_agent.py` but the function inside doesn't match
a declared agent name, so nothing binds and the agent runs as pure-YAML (raw
LLM output, no Python).

**Why:** `discover()` maps a file's function to an agent by name. No match =
nothing bound.

**Do this:** name the function to match the YAML agent (`foo` or `foo_agent`).
Since 2.4.100 `discover()` warns when a `*_agent.py` binds nothing (grep for
`none matched a declared agent`).

---

## 8. `schedule_followup` re-wakes an agent to finish ITS OWN work

**Trap:** an agent asked to "set an alarm for 7am" schedules *itself* to wake at
7am instead of calling its alarm tool now.

**Why/rule:** `schedule_followup` is a pre-injected built-in that re-wakes the
agent later to finish its own unfinished work — it is NOT a way to fulfil a
user's timed request. If the user wants a timed action and the agent has a tool
for it, the agent calls that tool NOW. (Description hardened in 2.4.96; it's not
gated behind a flag by design.)

---

## 9. Per-agent monthly budgets (opt-in)

`monthly_token_budget: N` / `monthly_cost_budget: N.NN` cap an agent's spend per
calendar month. `budget_on_exhaust: graceful` (default) makes the agent stop
cleanly with a `budget_exhausted` marker; `escalate` routes to the Manager.

- **A budget is paced, not a wall you hit on day two.** On every model call the
  agent is told where it stands: what it has used, how much of the month has
  gone, whether it is ahead of an even pace, and about how much a day is left.
  It is also told that each tool round resends the whole request. The agent
  manages its own spend from that; the hard stop still applies when the month's
  budget is spent.
- **Lean mode, and a learned per-task ceiling (2.4.457).** An agent ahead of an
  even monthly pace keeps taking every task, but each gets one normal task's
  share; the owner gets a daily Inbox notice, and it is back to normal once on
  pace. Every LLM task, budget or not, also has a ceiling learned from the
  agent's normal tasks (about 4× a typical one, once 10 are known). At the
  ceiling no more tools run and the task answers from what it has. Neither has
  a field. Never tell the user to "raise the budget" for this, and do not add
  tool-count or token caps to protect cost — tune `max_tool_calls_per_message`
  only for behaviour.
- **External agents count too.** Each external-agent call's self-reported spend
  is metered into the same month. A connector that reports no spend
  (`framework: custom`, `n8n`, `zapier`, `mcp`, `a2a`, …) is metered by
  estimate: each call reserves the agent's last call's spend, and tokens are
  estimated from what the mesh sends and receives. `monthly_cost_budget` needs
  `price_per_1k_tokens` on the agent; without it only a token budget bites.
- Inert on human and programmatic agents.

---

## 10. Multi-tenancy is pass-through

`X-Tenant-ID` on a request scopes that request's data + events to a tenant. The
SDK never mints tenant ids — you pass them. `env_token` and other secrets are
stripped from API/UI responses; never surface them.

- **A tenant can bring its own credentials (2.4.488).** It fills the
  organisation's records (`GET /api/infra/tenant-credentials`: same name,
  provider and rows). On a listed provider's record the organisation offers
  `tenant_models`; the tenant picks one as `model` on its own record. Its runs
  sign in with its key and that model. With `tenant_credentials_only: true` on
  the agent, a tenant with no record of its own is stopped ("this tenant has
  not connected <record>"), never given the organisation's. The Manager always
  uses the organisation's key. A tenant's own key failing is one quiet warning
  and never marks the model down for everyone.
- **The tenant id never reaches a model**, nor the input sent to an outside
  agent (it travels in code). The outbound call's `X-Tenant-ID` header still
  carries it, so a multi-customer outside service can keep data apart.
- **Cost by tenant comes from telemetry (2.4.489).** `GET /api/budgets/tenants`
  is gone. Agent and model-call spans carry `leafmesh.tenant_id`, and each
  model call `leafmesh.paid_by` (`tenant_key` / `organisation_key`) — filter
  dashboards on those.
- **Forget a tenant:** `DELETE /api/infra/tenants/{tenant}` (organisation
  only; refused while the tenant still holds vault records of its own). Only
  the tenants list changes; a later request carrying it adds it back.
- **A tenant joining an untenanted session mid-flow pays from then on**
  (2.4.491): its credentials and spans apply; the session's data stays where
  it started. Another tenant on the same session is refused.
- **A Slack thread reply runs in its session's tenant** (2.4.491) — the
  person replying never sends it.

---

## 11. `context` is a shared, per-turn pool — and a side channel

Within ONE agent turn, the SAME `context` dict is threaded through the
in-process stages: `@pre_compose` → your agent function → each `@chain` step.
Whatever a stage writes, later stages read. Use it to carry data *within* a
turn. (To carry data to the NEXT agent, use yields → `upstream_yields`, see #2.
`context` is rebuilt every turn; it does NOT travel between agents.)

**`@compose` is the exception (guaranteed-by-test since 2.4.107):** handoff
shapers run at PUBLISH time in the mesh and receive a fresh minimal ctx
(`session_id`, `tenant_id`, `from_agent`) — NOT the turn's context. A shaper
that needs pool-derived data must read it from the RESULT — put it there in
your function or a `@chain` step.

**The useful pattern — pull a full set, send the LLM a subset, rejoin after:**
the prompt is built from `input_data` + messages, NOT from arbitrary `context`
keys. So data parked in `context` under YOUR OWN key never reaches the model:

```python
from leafmesh import pre_compose, chain

def stage(input_data, context):
    context["records"] = fetch_records(input_data["query"])   # full set → pool (not sent)
    return {"items": [{"id": r["id"], "label": r["label"]} for r in context["records"]]}  # slim → LLM

def rejoin(result, context):                                   # after the LLM answered
    by_id = {r["id"]: r for r in context["records"]}
    result["ranked"] = [by_id[i] for i in result.get("ranked_ids", []) if i in by_id]
    return result

@chain(rejoin)
@pre_compose(input_processor=stage)
async def enrichment_agent(llm_response, input_data, context):
    return {"ranked_ids": llm_response.get("ranked_ids", []), "status": "ranked"}
```

The merge is YOUR code in a `@chain` step — the pool holds the data and threads
it; the SDK does not auto-merge.

**Trap — reserved `context` keys DO reach the prompt.** A fixed set is rendered
into the prompt on purpose: `prepared_data`, `agent_memory`, `agent_knowledge`,
`conversation_summary`, `conversation_history`, `previous_input`,
`previous_output`, `agent_data`. Note `prepared_data` especially — `@pre_compose`
processors write there by default, and it IS shown to the model. To keep
something OUT of the prompt, stash it under a key of your own (`context["records"]`
above), never one of these.

---

## 12. MCP tools do NOT go in `tools:` — and there are two different MCPs

Declare the server on the agent and its tools join that agent's tool list:

```yaml
  - name: research_agent
    agent_type: llm
    model: gpt-4o-mini
    mcp:
      - transport: http
        connection: mcp-search    # vault record: url + token (inline url/token fail to load, 2.4.481)
        use: [search_docs]        # omit for every tool the server publishes
```

Three ways people get this wrong:

1. **Re-listing the tools under `tools:`.** `tools:` is a positive allowlist for
   *locally registered* tools. MCP tools are merged in automatically. Naming
   them there does nothing — and if that is the only entry, you have written an
   allowlist that hides your local tools for no gain.
2. **Expecting the bare tool name.** Tools arrive namespaced as
   `<server>_<tool>` — `inventory_search`, not `search` — so two servers can
   publish the same name safely. Conditions and metric filters must use the
   namespaced name.
3. **Confusing it with `framework: "mcp"`.** That is the *connector* form, where
   the whole agent is one call to one remote tool named by `tool_name`. It still
   exists and is occasionally right, but it is not how you give an agent a set
   of tools. If you find yourself creating an agent per remote tool, you want
   the `mcp:` block instead.

A remote tool otherwise behaves exactly like a local one — same permission
scoping, timeout, output guardrail and execution record, and it can run in the
same turn as local tools, in parallel or in sequence.

---

## 13. `wake_up` crons run in UTC unless you declare a `timezone` (2.4.124+)

A cron with no timezone is pinned to **UTC** — deliberately, so a laptop
and a server never drift apart. The classic failure: an agent written
with `"0 9 * * *"` expecting a 9 AM local pass actually fires at 14:30
IST, and the operator concludes "wake-ups don't work".

```yaml
agents:
  coordinator:
    name: "coordinator"
    timezone: "Asia/Kolkata"        # governs ALL of this agent's crons
    wake_up:
      - cron: "0 9 * * *"
        input: { run: "assign" }
      - cron: "0 19 * * *"
        timezone: "Europe/London"   # per-entry override beats agent-level
        input: { run: "digest" }
```

- Validated at config load: a non-IANA name (`Asia/Bangalore` is the
  classic trap — the real zone is `Asia/Kolkata`) fails boot with a
  clear error, not silently at fire time.
- `GET /api/registry?category=timezones` (2.4.125+) returns the exact
  pickable zone list ({common, all, count}) — Studio's timezone inputs
  are fed by it.
- **Missed fires are skipped, not replayed**: if the process (or the
  laptop) is asleep when a cron comes due, the fire is skipped once it
  is more than the misfire grace (default 1 hour) late — you'll see
  "Run time of job … was missed by H:MM:SS" warnings on wake. That is
  by design: a 9 AM "assign the day's tasks" run firing at 5 PM is
  worse than not firing. If you WANT one catch-up run on wake, set
  ``scheduler.misfire_grace_s`=none` (ops env knob; coalesce
  guarantees at most ONE catch-up per schedule).
- **Day-of-week is standard cron** (since 2.4.382): `0` = Sunday … `6` =
  Saturday, or `SUN`–`SAT`, so `1-5` is Monday–Friday and `@weekly` is Sunday
  midnight. When both day-of-month and day-of-week are restricted, it fires
  when **either** matches (`0 9 1 * 1` = the 1st AND every Monday).
- **Anything the scheduler cannot run is refused at load**, with the
  expression in the message — hour `25`, day `8`, a backwards range like
  `sat-sun` (list the days instead), `#6`. Before 2.4.382 such a wake-up loaded
  and silently never armed.
- **`7`, `6-7`, `5#3` and `5L` load from SDK 2.4.385.** `7` is Sunday, `5#3`
  the 3rd Friday, `5L` the last Friday. SDK 2.4.384 and earlier refused them at
  load (the scheduler ran them; the loader's check did not); there, write `0`
  (or `SUN`) for Sunday and `fri#3` for the 3rd Friday.

## 14. Conditions FAIL CLOSED on missing fields — and `not` does NOT rescue them

A `can_call` condition that references a field **absent** from the
producing agent's output evaluates to **false**, whatever the rest of
the expression says. This is deliberate (a typo'd field must never
open a route), but it has a counterintuitive corollary:

```yaml
condition: "not calling_agent_response.from_agent"
```

reads as "when there is no caller" — but if `from_agent` is MISSING
(not empty — missing), the whole condition is false. `not x.field`
only matches when the field is **present and falsy** (`""`, `false`,
`0`).

Rules of thumb:
- Only reference fields the producing agent ALWAYS emits. Human agents
  always emit the uniform reply shape (`human_message`,
  `human_decision`, `from_agent` — possibly `""`) since 2.4.71; your
  own LLM agents always emit their declared `yields` keys.
- When two conditional branches target the SAME agent anyway, use one
  unconditional edge and gate on the DOWNSTREAM agent's conditions.
- The SDK logs `Condition ... could not be evaluated — route will NOT
  be taken` naming the missing field, and (2.4.127+) explains the
  `not` case inline. If a route "mysteriously never fires", search the
  logs for that line first.

## 15. Tool exposure follows REGISTRATION, and playbook/MCP registries are now per-agent (2.4.129 / 2.4.130)

`tools:` is only for tools **you** wrote. (The generic `zapier_action`,
`mcp_call`, `composio_action` and `n8n_workflow` tools were removed in 2.4.485 —
listing one, or `tool_categories: [integration]`, refuses the config.)
`playbook:` / `mcp:` / `zapier` / `composio` / `n8n`, `memory: true` (→ `recall_memory`), `knowledge:` (→
`query_knowledge`), `super_agent:` (→ planner tools) **all attach from their own
config block** — you do NOT list them in `tools:`.
- **≤2.4.128:** those merges were gated by the explicit `tools:` allowlist, so a
  declared block registered and was **never offered** if the agent also set
  `tools:`. Field case: 33 playbook sections across 6 agents, model saw none.
  Fixed in 2.4.129 — exposure now follows registration, not a request-time key.
- **≤2.4.129:** every agent's `playbook` registered a tool literally named
  `playbook`, all fighting for **one registry slot** — **the last agent to boot
  won**, so which agent had a working playbook depended on boot order (proven by
  flipping the order). **2.4.130 scopes the registry per agent.** A multi-agent
  template with per-agent playbooks **REQUIRES `leafmesh>=2.4.130`** — no config
  workaround exists.
- Related **2.4.128:** one logical event could reach local subscribers multiple
  times (pubsub self-echo / PEL redelivery); a Slack reply once fired a downstream
  agent 3×. Now de-duplicated per `event_id`.

## 16. `max_tool_calls_per_message` defaults to 5 — reaching it is a WARNING, not a failure

A chain that needs 7 tool calls stops calling tools at 5. The run is **not
failed**: the model gets one last call with tools off and answers with what it
has, the response carries `finish_reason: "tool_cap"`, and the agent's output
carries the warning on as `_warnings` ("Reached max_tool_calls_per_message (5)
— the agent stopped calling tools and answered with what it had"). So the
answer is plausible and the remaining work never happened. Every call the model
makes counts; the SDK's own memory / board / playbook calls are free. Check
`finish_reason` / `_warnings`, and raise the cap on any agent with a long
read/act chain; **20 is the hard ceiling** (the SDK rejects higher).
At the cap the model is offered no tools at all and sees its earlier tool work
as notes, so every provider — Gemini included — answers instead of reaching for
one more call (2.4.439 / 2.4.440). Signing the board ticket after the answer
never counts against the cap (2.4.442).

## 17. `dual` → `dual` `can_call` is unbounded ping-pong (2.4.126, now warned)

A `dual` agent calling **another** `dual` agent bounces replies back and forth
**independent of `can_call` conditions** — field case: 13 LLM calls from one
inbound message. The SDK warns at load as of 2.4.126. **`dual` belongs on the
human/webhook boundary agent only; downstream peers must be `chain`.** If a
template uses `dual`, put this rule in the comment right above it.

## 18. `enforce_yields` makes EVERY declared yield required — no conditional marker

There is no "this yield only applies to lane X" marker. A yield that only some
turns produce fails the contract on **every** unrelated turn and escalates twice
per turn. **Workaround: declare the lane-specific yield with a default** in the
output contract so the contract is always satisfiable.

## 19. 2.4.131 migration + packaging — silent reverts and uninstallable extras

- **Env → config silent revert (2.4.131):** ~49 runtime knobs moved from
  `LEAFMESH_*` env vars into the `timeouts`/`scheduler`/`runtime`/`limits`/
  `connectors` YAML blocks (see agent-config-fields.md). The SDK does **not** warn
  — a still-set env var is simply ignored and the default applies. Notably
  ``timeouts.llm_hard_timeout_s`` → `timeouts.llm_hard_timeout_s`, and the default
  dropped **300s → 90s**. The `timeouts` block is **rejected by ≤2.4.130**, so it
  must land *with* the 2.4.131 floor, never before.
- **`pip install leafmesh` is core + LLM providers only.** Channels, listeners,
  knowledge backends, storage, and MCP are **extras** — a bare install runs with
  those features silently dead. Use **`leafmesh[all]>=2.4.131`** (19 pkgs). ⚠️
  **`[all]` does NOT install on Python 3.12+** — it pulls `cchardet`, which has no
  wheel and fails to build. On 3.12+ install core + the specific extras you need
  instead of `[all]`. The seven AI-framework connectors (crewai, langgraph,
  autogen, a2a, composio, claude_agent, openai_agents) are excluded from `[all]`
  (unsatisfiable pins) — add exactly the one a template bridges: `leafmesh[crewai]`.
- **`_pre_compose_error`:** a raising `@pre_compose` does NOT stop the turn — the
  try wraps the whole processor loop, so the first raise skips **all** remaining
  processors and the agent runs with **no flows at all**. The failure is recorded
  as `_pre_compose_error` in `context` — **read it and refuse**, rather than
  answering for nobody.
- **2.4.131 boot-time capability check:** declared-but-uninstalled features are now
  reported at startup with the exact pip command — loud instead of silent, but only
  if the operator reads it.

## 20. Approval is routing — there is no approval switch (2.4.382)

`require_human_confirmation`, `confirmation_seat`, `human_escalation_triggers`
(on any agent) and `external_policy.skills` / `unknown_skill_risk` are
**removed**. One that was ON — a confirmation flag set true, a trigger list,
a skill marked `send` / `spend` / `delete` — **refuses the config at load**,
because dropping it silently would let calls go out that the author expected a
person to see first. One that was off or empty is dropped (and warned as an
unknown key). A tool's `requires_confirmation=True` is accepted but **does
nothing** — the tool runs and the SDK logs a warning once.

The replacement is the mesh itself: send the work to a **human agent** with a
`can_call` condition on the agent before it, and give that seat `can_call` to
the agent that acts. See [SKILL.md — Approval is routing](SKILL.md#approval-is-routing).

## 21. Vault references fail CLOSED, and a missing connection switches an agent off

- `${vault:<connection>}` (its primary secret) and `${vault:<connection>.<field>}`
  are resolved where the value is used, so a rotated secret applies on the next
  request with no restart. A reference that cannot be resolved **raises — it
  never becomes `""`**. (`pre-${vault:gone}` used to become `pre-`, a token
  anyone could send.)
- Connection names may contain dots: `${vault:ops.webhook}` first means the
  connection named `ops.webhook`; only when none exists is the last dot read
  as `<connection>.<field>`.
- **A config that names a missing connection still STARTS.** Each agent (or
  human seat, or broker consumer) that needs it is switched off, loudly, and its runs fail at once with the reason.
  Add the connection later and the agent switches back on with no restart. A
  vault that cannot be read is only a warning — nobody is switched off for it.
- **A connector with no address is not set up (2.4.490).** The record exists
  but holds no address (n8n `webhook_url`, A2A `url`, CrewAI `endpoint`, …):
  the agent is switched off at start with "not set up", never called, never
  counted toward quarantine. Put the address in the vault record and it
  switches back on with no restart. `framework: custom` is exempt.
- SDK 2.4.384 and earlier logged `Environment variable not set: vault` for a
  `${vault:...}` value. It was cosmetic (vault references are never treated as
  env vars) and is gone from 2.4.385.
- **In `request_form` a `${vault:}` reference is resolved on every call**, in
  the request's tenant (2.4.385). One that cannot be resolved refuses the call.
  In `connector_config` the account is vault-only since 2.4.482 — a
  `${vault:}` in a key/address field fails to load; pick the record with
  `connection` (see [Vault-only values](#vault-only-values-24481)).

## 22. Devices — the device comes from the conversation

- **Which device is never config.** The `device:` block names how to reach
  devices; the device itself arrives with the request
  (`{"message": "...", "device": {"id": "phone-7", "push_token": "..."}}`, or
  `devices: [...]`, up to 16). The push token is kept in the session's storage
  and stripped from the payload, so no prompt, history row or log holds it;
  the `id` (and `name` / `platform`) stay so the agent knows which device it
  may ask. A request with no device gets `refused`.
- **`device.connection` must be a notifier** (`fcm`, `mqtt`, `apns`, …). Naming
  a room service or any other connection there fails the action; a room goes in
  `device.room`.
- **Pusher as the room needs the mesh on a public https address.**
- **LiveKit as the room needs the extra**: `pip install 'leafmesh[livekit]'`.
- Every device connection is **Tested on save** on the Infrastructure page.
- `not_joined` means the device was rung but did not join in time (the owner
  did not allow it under `approval: ask`, or it is offline). A connection lost
  after the task was sent is `failed` — the device **may have done it**; never
  report it as not done.

## 23. External agents — what surprises people (2.4.385 / 2.4.386)

- **`request_form` is refused on some frameworks.** `writer`, `watsonx`,
  `autogen`, `hermes`, `relevance`, `claude_agent`, `openai_agents`,
  `custom_api` (2.4.486) and `custom` have no place in their request for it, so the config refuses to
  load. Other limits: ≤ 50 keys, 16 KB, key names `[A-Za-z0-9_.-]` up to 64
  characters, no leading `_`, no secret inline.
- **A `request_form` key the SDK already sets is ignored** (the message,
  session or conversation id) — warned once at load; the SDK's value is sent.
- **`send_fields` is strict.** Set it and the conversation history goes out
  only if you list `_conversation_history` (likewise `_chain_history`,
  `_rerun_context`).
- **A business `status: "failed"` in a reply is data, not a failed call.** Only
  `success: false` with an `error` fails the call — so a workflow that means
  "this call failed" must say it that way.
- **Ending a session cancels the external call**, and a cancelled call does not
  count toward `quarantine_after`. A connector's own timeout also cancels the
  job on the other side.
- **Changes apply live.** `framework`, `connection:`, a rotation on the Infrastructure page,
  `can_call`, `request_form`, `external_policy` — no restart. `PATCH` merges a
  nested block one level (`null` removes a key); `PUT` replaces the agent.
- **Claude Agent's host rights** (`connector_config.cwd`, `allowed_tools`,
  `permission_mode`, and from 2.4.486 `setting_sources`, `disallowed_tools`,
  `sandbox`) are refused by every API write, Studio included. **Change them
  from the host** (2.4.485): `leafmesh agent host-rights <agent> [--cwd DIR]
  [--allowed-tools a,b] [--permission-mode default|acceptEdits|plan|bypassPermissions]
  [--clear FIELD] [--yes]` (2.4.486 adds `--setting-sources`,
  `--disallowed-tools`, `--sandbox`). It reads the store from `.env`, prints
  the change, saves only after `--yes` or a typed `apply`, and the save is a
  new store version every pod applies. The agent must carry `framework:
  claude_agent` in the stored configuration.
- **`setting_sources` defaults to none (2.4.486)** — a `claude_agent` no longer
  picks up the host's CLAUDE.md or Claude Code settings unless the host grants
  it. Per-call tool rules go in `external_policy.allowed_tools` /
  `denied_tools`; they only narrow what the host allows.
- **External agents' addresses, keys and ids come only from the vault
  (2.4.485).** 58 connector env fallbacks (`CREWAI_ENDPOINT`, `A2A_AGENT_URL`,
  `N8N_WEBHOOK_URL`, `ZAPIER_MCP_KEY`, …) are no longer read; boot names each
  one still set and the record to use. Model keys and the host's cloud identity
  stay in `.env`.
- **The `n8n()` / `zapier()` / `composio()` helpers take `connection=`
  (2.4.485)** and refuse an address or key written in code (`n8n("https://…")`,
  `zapier(..., api_key=…)`) when the helper is created. They read the record at
  the first call, inside a started mesh.
- **Pick an external agent from the External agents page (2.4.486):**
  `external_agent: <entry>`. A `framework` / `connector_config` beside it that
  differs from the entry is refused. The old `framework:` + `connector_config:
  {connection: …}` shape still loads and runs.
- **The entry's kind comes from its vault record (2.4.491).** Don't name a
  framework on the page entry: a CrewAI record is CrewAI. Only a custom record
  needs `a2a` (Custom: A2A) or `custom_api` (Custom: API); a framework that
  contradicts the record is refused. A Custom API agent can start from a
  swagger file: `POST /api/external-agents/from-spec`.
- **Avoid SDK 2.4.385** (the 2.4.509 baseline is well clear of it): 2.4.385
  fails `import leafmesh` on Python 3.10–3.13 — fixed in 2.4.386 — and with
  mcp 2 an MCP stdio server could keep the program from exiting.

## 24. 2.4.482 — the store is in `.env`, and no setting lives in two places

- **The datastore is set only in `.env`.** A `persistence:` or top-level
  `redis:` block in config.yaml is **ignored** on 2.4.482–2.4.485 (boot warns
  "the persistence block is no longer read"). From **2.4.486
  `LeafMesh.from_yaml` raises `ConfigError`** when its values differ from
  `.env`, naming each `.env` line to add (a matching block still loads, with
  the warning). The trap it
  closes: an old file with `persistence.redis.db: 3` and no `REDIS_DB` in `.env`
  silently opened db 0, with an empty vault and board. Remove the block. Use `LEAFMESH_STORE` (`redis` default | `postgres`)
  with `REDIS_*` or `POSTGRES_*` (full list in reference.md → Environment
  Variables). Studio → Infrastructure → Datastores shows whether it is
  reachable, never the address or password.
- **The Manager rule sets go directly under `manager:`** —
  `human_input_rules`, `workflow_pause_rules`, `human_response_rules`
  (`timeout_rules` was removed in 2.4.486). Never under `manager.coordination_rules:` (a file
  that still nests them is moved at load, with a warning). `coordination_rules`
  stays for its other keys (`max_call_depth`, `agent_rules`, `reflection_budget`, …).
- **`mesh.call_timeout` is gone** → `timeouts.mesh_call_default_timeout_s`,
  default **300** s (it has been 300 since 2.4.382; text saying 30 is wrong).
  An old `mesh.call_timeout` is moved at load, with a warning. Unrelated to the
  agent field `tool_call_timeout`.
- **A new agency's YAML writes every setting with its default**, including
  `timeouts`, `scheduler`, `self_healing`, `runtime`, `limits`, `connectors`
  (defaults: agent-config-fields.md → Runtime Config Blocks). Defaults older
  text gets wrong: `scheduler.followup_tick_s` **2** (not 5);
  `security.telemetry_redact_pii` **true** (since 2.4.480 — customer text is
  hidden in traces by default); `manager.max_tokens` **4000**;
  `manager.chain_completion_timeout` **1800** s; `manager.domain` **"generic"**;
  `mesh.reply_stream` **false**. Left out on purpose (no fixed default):
  `runtime.lease_heartbeat_s` (= `lease_seconds / 3`), `api.public_base_url`
  (learned from the first authenticated request), `api.cors_origins` (empty
  until you list origins).
- **A setting sent as `null` goes back to its default** — including in a block
  never written; resetting never creates a block nobody asked for.
- **`runtime.live_model_discovery`** — "Set false for offline installs".

## 25. 2.4.481–2.4.484 — the configuration lives in the store; `config.yaml` is a first-boot seed

**Trap:** you edit a `config.yaml` of an agency that has already booted,
restart it, and nothing changes. (A project made by create-leafmesh ships no
configuration file at all: `create-leafmesh --start` loads the team into the
empty store with `leafmesh config import --if-empty`, and `main.py` uses
`from_store()`.)

**Why:** since 2.4.481 the configuration is one document **in the agency's
store** (Redis / Postgres); every Studio or config-API save is the next
version, and every pod runs the latest. `from_yaml` and `from_store` behave the
same at `start()`: an **empty** store imports the file once, as version 1;
after that the store's version runs and the file is never read for the
configuration again — never re-imported, never a new version, and a restart
does not apply an edit to it. Boot says so, at WARNING:

```
<path> was edited after it was imported into the store — that edit was NOT
applied. The configuration lives in the store now (version N); make changes in
Studio. Only the agency's name and where its store is are still read from this
file — …
```

The line goes on to advise moving the agency name and the datastore settings
(`REDIS_*` or `POSTGRES_*`) to `.env` and deleting the file (the SDK rewords
that part next release).

(An unedited file logs "`<path>` is no longer read for the configuration — it
lives in the store (version N); edit it in Studio. …"; a file that fails its
checks logs "`<path>` does not pass the checks any more; it is not read for the
configuration (the store's version N runs)".)

**Do this:** for a running agency, change the configuration in Studio
(settings, or the raw YAML editor), or with `PUT /api/yaml/raw`
(`{"yaml_content": "<whole YAML>", "save_to_disk": true}`, header `X-API-Key`)
/ `PATCH /api/yaml/config` (`{"updates": {...}, "save_to_disk": true}`). Read
what runs with `GET /api/yaml/raw`. Without `save_to_disk: true` the change
lives only in that process's memory. Or use the CLI: `leafmesh config
export` → edit → `leafmesh config import` (checked before it is saved). There
is no env flag or re-import-on-start — don't invent one.

- **Saved changes apply live (2.4.484).** Another pod picks a save up within
  ~15 s (`runtime.config_sync_poll_s`) and applies it in place. A change that
  still needs a reload — `brokers`, `self_healing.enabled`, `api.cors_origins`,
  `runtime.lease_seconds` / `lease_heartbeat_s`, `architecture`,
  `auto_discover`, `limits.consumer_inflight_max`, `manager.enabled` — makes the
  agency **reload itself in place** within seconds. Only `evolution_api`
  `enabled` / `host` / `port` need a process restart. Python code in
  `agency/` is loaded when the process starts.
- **`LeafMesh.from_store()`** needs `LEAFMESH_AGENCY_NAME` (and the store) in
  `.env`; an empty store starts a **blank agency** — quietly (2.4.482: no
  warnings about a Manager model or agents it does not have yet).
- **Every save is kept as a version**; an earlier one can be made the default
  again — in Studio, or `PUT /api/versions/mesh_yaml/config.yaml/default`
  `{"version": n}` (list: `GET /api/versions/mesh_yaml/config.yaml`; one
  version's text: `GET /api/versions/mesh_yaml/config.yaml/{n}`). It is saved
  as a new store version and applies live on every pod. `n` is the version
  number shown in the versions list — not the store's internal counter.

## Vault-only values (2.4.481+)

**The rule (owner, 2026-10-27; enforced at load from SDK 2.4.481).** API keys,
tokens, passwords, client ids, server addresses (base URLs, endpoints, hosts)
and header rows live **only** in a vault connection created on Studio's
Infrastructure page. A config block only **picks** the record by name
— `connection: <name>` (`vault_connection:` on `zapier` / `composio` / `n8n`
rows, whose own `connection` is a Zapier app slug). The one exception is the
mesh's own Redis / Postgres in `.env` (the vault is stored there).

**Written inline, the config fails to load** — a literal, a `${ENV}` or
`"${ENV:default}"` string, or a `${vault:…}` reference in one of these fields
alike. The message names the field and the record to create (the SDK's own
2.4.484 wording, quoted; 2.4.481–2.4.482 said "On Infrastructure → Connections
create …" — Studio never had that page, the record is made on the
Infrastructure page):

```
webhook_config: outbound_url is no longer read from the config — keys, tokens,
passwords, client ids, addresses and header rows are entered only in the vault.
On the Infrastructure page create an "Add custom" record on the Infrastructure
page with service type 'Outbound webhook': the address as its base URL, each
header as a header row, query values as query rows, and the inbound token as a
secret row named 'inbound_token'; put this value there, remove it from this
block, and pick the record here with `connection: <its name>`.
```

(2.4.486 still prints "query values as query rows" — that part is out of date:
an Outbound webhook record now refuses a query row. See the next section.)

### The vault keeps sign-in only (2.4.486)

A vault record holds **the address and the sign-in** — base URL, keys,
tokens, header rows. **What is sent** (a plain query value, a body field) is
set on the page that uses the record:

| Record (service type) | Rows it may carry | Plain query values / body fields go… |
|---|---|---|
| Outbound webhook | header rows (+ the secret `inbound_token`) | on **Tools → Webhooks** (the webhook's body fields and fixed query) |
| API tools | header rows; a key the API wants in the address as a **secret** query row; an OAuth app's client id / secret or a username / password as body rows (sign-in, never sent as they are) | on the API's Tools-page entry: `query` — fixed values, sent on every call, never overridden |
| Model | header rows | on the added model's Models-page entry: `query` (e.g. an `api-version`) |
| External agent | header rows; for Custom API, a key the API wants in the address as a **secret** query row (2.4.497) | on the External agents page entry (Custom API: `method`, `path`, `query`, `answer_path`) |
| Tools, Knowledge store, Your own code | header rows | the page that uses the record |

- **Saving** a record with a query or body row is **refused** (API tools
  excepted: its body rows and a secret query key), naming the row and where it
  goes instead.
- **A row saved before 2.4.486 is no longer sent.** Start logs one line per
  row: "vault record 'X': the query row 'Y' is no longer sent — the vault
  keeps sign-in only. Set it on the page that uses this record (Tools, Models
  or External agents) and remove the row." Move each one, or the call goes out
  without it.
- **Every picker shows each sign-in, not each provider (2.4.486).** `GET
  /api/infra/choices` gives Studio one list per picker — `models`,
  `external_agents`, `tool_platforms`, `human_seat` (the Inbox first),
  `notify` — each choice labelled "Provider · record" (two OpenAI keys are two
  choices) with exactly what picking it writes.
- **An LLM agent picks its model's sign-in with `model_connection: <record>`**
  when there is more than one for its provider. A wrong one fails the call
  naming the record; it never signs in with another key.
- **No secret reaches a log or a trace (2.4.485).** Every `leafmesh.*` logger
  scrubs its own lines, also when they reach your application's own root
  handlers, and an agent's returned failure reason is scrubbed on the trace
  like a raised one.

Which section each record lives in: SKILL.md → [Studio's Infrastructure
page](SKILL.md#studios-infrastructure-page--where-each-record-is-made).

**Day 0 — a missing record never blocks boot.** A `connection:` naming a record
that doesn't exist yet: the mesh starts and logs "connection 'X' does not exist
in this mesh's vault…"; the agent, human seat or broker consumer that needs it
is **switched off** until the record is created, then works with no restart.
An agent whose `listen_events` uses a broker with a missing record is switched
off even for its entry points.

| Block | Allowed shape | Record (on the Infrastructure page) | Refused inline |
|---|---|---|---|
| Human seat — Inbox | `human_interface: "default"`, no `webhook_config` | none — works out of the box, hosted or self-hosted | — |
| Human seat — webhook (never both with Inbox) | `webhook_config: {connection, inbound_endpoint?, outbound_timeout?, max_retries?, retry_delay?, response_mapping?, operators?}` | "Add custom" record, service type 'Outbound webhook': base URL = address, header rows = headers, secret row `inbound_token` (no query / body rows since 2.4.486) | `outbound_url`, `outbound_headers`, `inbound_auth_token`; an address in `operators` (each value is a record name) |
| `manager.escalation.targets` webhook | `{type: webhook, connection, method?, payload_template?}` | same "Outbound webhook" record | `url`, `headers` |
| `channels.<provider>` | `connection` + seat behaviour (`post_channel`, `listen_channels`, `operators`, `from_address`, threading, …) | the provider's connection (email: an email, Google or Microsoft one) | tokens/secrets, `app_id`/`client_id`/`tenant_id`, `service_url`, `base_url`, `smtp_host`/`smtp_port`/`smtp_username`, `attachments.storage_url`, … |
| `mcp:` rows | `{transport, connection, use?, name?, timeout?}` or `{server}`; stdio `env` secrets as `${vault:<field>}` | the MCP server's connection, or an "Add custom" record, service type 'Tools' (base URL = address) | `url`, `token`, a literal secret/address in `env` |
| `zapier` / `composio` / `n8n` rows | `vault_connection` (or `account:` from the Tools page) | the provider's connection, or an "Add custom" record, service type 'Tools' | `api_key`, `base_url` |
| `notify` (2.4.485) | `{webhook: <Tools → Webhooks name>, when}` | the Outbound webhook record the webhook picks | an address (`://`, `www.`) |
| `n8n()` / `zapier()` / `composio()` helpers in your code (2.4.485), `mcp()` (2.4.497) | `connection="<record>"` (`mcp("tool", connection=…)`; stdio: `command`/`args` in code, keys as the record's rows) | Infrastructure → Integrations → `<platform>`, or an "Add custom" record, service type 'Tools' | `n8n("https://…")`, `mcp("https://…", …)`, `webhook_url=`, `auth_token=`, `api_key=`, `mcp_key=` — refused when the helper is created |
| `brokers` kafka / sqs / imap | `type`, `connection` + behaviour (sasl_mechanism, region, auth, …) | a kafka / sqs / imap connection | addresses, usernames, passwords, keys, PEMs |
| `brokers` mqtt | `type, connection, use_tls, ssl_cafile, ssl_certfile, ssl_keyfile, client_id, keepalive_s` | mqtt connection, `url` = `mqtt://host:port` or `mqtts://…` | `host`, `port`, `username`, `password`, PEMs |
| `brokers` redis_streams | `type, connection, db` | redis_streams connection (`url`) | `url` |
| `connector_config` (external agents; programmatic `integration`) — 2.4.482 | `connection` (zapier: `vault_connection`) + behaviour: `after_handoff` (2.4.508, was `mode`), timeouts, graph / agent / assistant ids, prompts | Infrastructure → External agents → `<framework>`, or an "Add custom" record, service type 'External agent' (base URL = address); zapier / composio / n8n / mcp: Infrastructure → Integrations, or an "Add custom" record, service type 'Tools' | `url`, `endpoint`, `base_url`, `api_base`, `webhook_url`, `mcp_endpoint`, `headers`, `api_key`, `token`, `auth_token`, `bearer_token`, `mcp_key`, `secret`, `password`, `client_id`/`client_secret`, `tenant_id`, `aws_*`, `service_account_json`, `credential_config_json`, `auth_scheme`, `auth_mode`, … (full list: agent-config-fields.md → Common connector_config fields); an `mcp` connector's credential-named `env` entry (use secret body rows on the connection) |
| `mesh.bedrock` / `vertex` / `foundry` / `local` | `connection` + behaviour (`profile`, `api_version`, `auth_mode`, `server_type`, `timeout`) | AWS Bedrock / Google Vertex / Azure Foundry / Self-hosted model (or an "Add custom" record, service type 'Model') | bedrock `region`, `endpoint_url`; vertex `project`, `location`; foundry `endpoint`; local `endpoint`, `headers` (`LOCAL_MODEL_ENDPOINT` / `LOCAL_MODEL_SERVER_TYPE` in `.env` still work: `.env` wins, else a Local model connection on Infrastructure → Models fills them at boot) |

`connection:` is required for kafka, mqtt, redis_streams and imap brokers, and
for an http MCP row. Field-level detail: agent-config-fields.md (WebhookConfig,
ChannelConfig, EscalationTarget, brokers, MCP, provider configs).

## Scaling (`scaling:`, 2.4.484) — the rules that surprise people

How an agent runs in parallel is **one block**. `parallel`, `max_concurrent`,
`instances` and `instances_handoff` are **refused at load** with the lines to
write (an old field left at its old default — `parallel: false`,
`instances: 1`, `instances_handoff: last` — is dropped quietly):

```yaml
finance_agent:
  inputs: {invoices: array}
  scaling:
    runs: {max: 2}          # at most 2 jobs of this agent at once, across ALL pods
    copies:
      mode: auto            # the mesh hands out `invoices` item by item
      max: 8                # never more than 8 copies on one job
      work: invoices        # or claim_tool: <the agent's own tool> — exactly one of the two
      handoff: last         # last (default) = COMBINE and hand on once; each = every copy hands on
```

| Was | Write |
|---|---|
| `instances: N` (+ `instances_handoff: H`) | `scaling: {copies: {mode: fixed, count: N, handoff: H}}` |
| `max_concurrent: N` | `scaling: {runs: {max: N}}` |
| `parallel: true` | drop it — every agent already takes several jobs at once |

What to know before using it:

- **`runs.max` counts across every pod** (`max_concurrent` counted per pod,
  though it said mesh-wide). Extra jobs wait their turn. Unset = no cap.
- **`fixed` copies all get the whole job** (`_instance: {id, of}`); without a
  claim they duplicate the work — and the merge honestly shows it (two
  identical items, count 2). Prefer `auto`.
- **`auto` never starts an idle copy.** A copy starts only when there is an
  item for it — 6 items with `max: 10` → 6 copies. Each copy gets its item
  (`_instance: {id, of: "auto"}`, `_work: {item, field, tool}`; with `work:`
  the field holds just that item), takes the next with the built-in
  `next_work_item` tool (`{item}` or `{done: true}`), and stops when none is
  left. An empty list → one run on the job as it came. With `claim_tool`, the
  mesh calls your tool — no model run — before starting a copy and when a copy
  asks for more.
- **`auto` needs exactly one of `work` / `claim_tool`; `fixed` takes neither**
  — both mistakes are refused at load. `count` and `max` are 1–50.
- **`last` merges deterministically**: lists concatenate in copy order, numbers
  SUM, other fields take the final copy's value, and no field any copy
  produced is dropped. The per-copy detail rides on
  `_instances = {count, results: {"1": {...}, ...}, failed: [...]}`, and
  `upstream_yields` carries the same combined payload downstream.
- **The number-sum rule cuts both ways.** `item_count` summing is right;
  `confidence: 0.9` from two copies becomes `1.8` — wrong. Reshape scores and
  ratios with `@chain` / `@compose` (they receive the combined result + the
  `_instances` pool).
- **Don't multiply triggers**: a 3-entry `wake_up` list × `count: 3` = 9 runs.
- **Conversation/chain history keeps every copy's entry** (by design). If the
  doubling bothers a prompt, reshape via `@compose`.
- Failures stay visible: a dead copy is reported per copy AND named in
  `_instances.failed`; the chain still continues once if any copy succeeded.
- **A human seat is never copied (2.4.485).** `copies` (`mode: auto`, or
  `count` > 1) on a human agent is refused at load; `runs.max` still caps how
  many of the seat's requests are open at once.

## A seat waits its time and stops (2.4.486)

**Trap:** you expect an unanswered question to escalate, or the Manager to
nudge the asking agent again. Since 2.4.486 neither happens.

- When `human_timeout_seconds` is up the seat **stops waiting**: its Inbox
  request closes (`request_timeout`) and `HUMAN_INPUT_TIMEOUT` is published.
  No "timed out and escalated" note goes to the person, nothing escalates to
  the Manager, and no check-back re-runs the asking agent (a final answer
  nobody replied to used to loop advisor → client every 15 minutes). A late
  reply still lands, marked `answered_late`. A seat nobody answered is not
  judged, and nobody is coached for it.
- **Removed**, dropped at load with one warning: `manager.timeout_rules`,
  `manager.escalation.auto_escalate.timeout_threshold`,
  `manager.human_response_rules.timeout` (also under `coordination_rules`).
- **Still works:** `fallback_on_timeout: true` + `fallback_response` — the
  fallback is the seat's output (`human_decision: "timeout"`, `timeout: true`)
  and the chain carries on down `can_call`.
- On an `api` seat whose own handler times out, with no fallback, the run fails
  with a timeout error.

**An approval nobody answers:**

<!-- TODO(bb): 2.4.486 escalation pattern for unanswered approvals -->

## A person's reply — what reads it and where it goes (2.4.486)

- **`reply_reader` replaces `intent_model` / `intent_prompt`** (moved into it
  at load; both forms disagreeing are refused). The load may still print
  "'intent_model' is not an agent setting this SDK reads" — the value *is*
  moved; write `reply_reader`. Block: `{model, prompt, memory, knowledge,
  skills, experience, model_connection, temperature, max_tokens}`; `model` is
  required; nothing else (no tools). Field table: agent-config-fields.md →
  reply_reader.
- **The reader never picks a route.** It fills the fields the seat's
  `can_call` conditions read; `can_call` or the Manager decides. The SDK's old
  fallbacks — asking the operator which agent was meant, the only target, the
  first declared target — are gone: **a reply no route takes goes nowhere**,
  and a person's answer that no route takes **ends the conversation and closes
  the ticket** ("thank you" is not a new request). So give every seat a route
  for each thing a person may mean, including "done".
- **An answer to an agent's question is read too**, before it routes (before,
  only replies that arrived on their own were read — a Slack answer reached
  intent conditions with no intent and stopped).
- **One lean model call per reading** (~500 tokens, was ~22,600 as a full
  agent run); it is a step of the seat's own run in the trace.
- **Shared threads:** every open question in a thread is kept; a reply answers
  one; the same asker asking again replaces its earlier question (closed as
  `superseded`); with different askers open, the reader picks which question
  the reply answers, else the newest. A seat owns only the questions it asked —
  another seat's timeout sweep leaves them alone.
- **A seat declared with nothing else is answered in the Inbox** (it used to
  fail on its first question: `human_interface` defaults to `api`, and no
  handler was registered). `api` is only for a seat your code answers.
- **A seat picks one service** — Inbox, an Outbound webhook record, or one
  messaging / email sign-in; a channel picked in Studio writes
  `human_interface: webhook` with the `channels:` block.
- **A seat is never copied** (2.4.485) — see Scaling above.
- **A late failure never reopens a closed ticket** — it is added as a line on
  it (research still running fails after the customer ended the conversation:
  the ticket stays closed).
- **Agents write in the conversation's language** — the person's, or, when an
  agent works only from other agents' output, the language that work is in
  (an agent with a `mother_tongue` used to fall back to it there).

## Fan-in runs now, and again as late work arrives (2.4.486)

`wait_for: "processor AND (fallback OR researcher)"` — once processor and
fallback have answered, the target runs **now**; it no longer waits for a
researcher still running (2.4.462–2.4.485 did). When the researcher answers,
the target runs **again** on everything gathered, as an update. Design the
target for that:

- Its input carries `still_running: [names]` when more is coming, and
  `update_from: <name>` on the re-run. Make the second run correct and
  idempotent (update, don't re-send).
- A contributor that **fails** after the target ran runs nothing.
- A **second request in the same session** is a new round (its results used to
  be dropped as "late").
- Optional `?` contributors are still waited for.

## Memory, experience and the response cache (2.4.486)

- **Agent memory is filed by index** (per agent, by session, kind of work,
  entity, day and word; per tenant). `recall_memory` and the prompt read the
  index; the prompt carries a short table of contents (~1,500 characters)
  instead of earlier runs' work logs — the agent calls `recall_memory` for
  detail. Old posts are filed in the background; until then the request reads
  the feed as before.
- **Experience is stored by id** with indexes. The old single set is **copied,
  not moved**, in the background, so rolling back to an older SDK still finds
  every agent's experience.
- **Model calls that run no tools go through the response cache** — the reply
  reader, the Manager's analysis, the board designer. The cache keys on the
  request and serves an answer whose background (recalled memory, knowledge,
  prefetched lookups) is at least 85% similar.
- **Since 2.4.487 only lookup-only turns are stored.** A cached answer is
  replayed **without running the turn's tools**, so every tool the turn used
  must change nothing: the built-in reads (`recall_memory`,
  `recall_experience`, `view_board`, `query_knowledge`,
  `load_skill_reference`, `calculator`, `time_difference`, the text / JSON
  formatters, `playbook`, `api_find`, …), an MCP tool its server marks
  `readOnlyHint`, board bookkeeping the mesh redoes itself (`add_task`,
  `update_task`, `finish_task`, …), or a tool you mark `changes_nothing`
  (2.4.491: `@tool(..., changes_nothing=True)`, `@global_tool(...,
  changes_nothing=True)`, a class tool's `CHANGES_NOTHING = True`, or
  `changes_nothing: true` on a `zapier` / `composio` / `n8n` row). Any other
  tool keeps the turn out. `current_time`, `random_number` and `system_info`
  are not on the list.
- **Mark `changes_nothing` only when the answer also does not depend on WHEN
  it ran** — a policy table, a rate card, static reference data. A read of
  live data (an invoice's status, stock levels, a queue to claim from) must
  stay off: a replay would hand back a stale answer. Claiming work, sending,
  writing, remembering, scheduling or reading the clock are never
  `changes_nothing`.
- **Never personal data or a secret.** A request or reply carrying an email,
  phone, card, bank or ID number, or any secret the mesh knows, is not stored
  at all (not masked).
- `GET /api/llm/cache/stats` shows `near_hits` and why answers were not kept:
  `not_stored_tools`, `not_stored_personal_data`, `not_stored_secret`.
- The cache is keyed on the model that really answers — a tenant's picked
  model never shares answers with the agent's model (2.4.488).

---

## The mesh's own sign-in (2.4.497)

Each mesh signs in to LeafCraft with its own Ed25519 key pair; the build
carries no shared key.

- **First start** registers the key with `LEAFMESH_LICENSE_KEY` +
  `LEAFMESH_ENV_TOKEN` (the real token from Studio; `development`, `default`
  or empty can't register). ACTIVE at once when both are valid. PENDING only
  if the organisation turned on "require approval": a brand-new mesh then
  stops at start ("…waiting for approval in Studio (Keys → SDK access)…");
  a mesh that already ran keeps going on its cached / signed licence.
  Organisation admins are emailed on every new registration. A cloud identity
  outside the organisation's trusted connection is refused, not pending.
- **Key store:** `security.sdk_auth.key_store: vault` (default) — encrypted
  with `LEAFMESH_VAULT_KEY` in the mesh's store, shared by every replica
  (the first makes it under a lock). A wiped store or a new vault key makes a
  new key pair that registers again; revoke the old one in Studio.
  `key_store: file` only for a single host with no shared store.
- **CLI:** `leafmesh auth status [--check]` (ids and fingerprints, never a
  key), `leafmesh auth register`, `leafmesh auth rotate` (switches once the
  new key is active, then revokes the old). A revoked or expired key is never
  revived.
- **The env token also namespaces the store.** An existing agency moving
  from `LEAFMESH_ENV_TOKEN=development` to its real token starts on an empty
  keyspace (vault, sessions, lessons, board); the old data stays under the
  old prefix. Set the real token before data goes in.
- **Shown once (from 5 Dec 2026, SDK >= 2.4.497).** Org API keys, agency
  tokens, environment tokens and the licence key are shown once at creation
  or rotation, then only a hint. A lost environment token is rotated in
  Studio — which moves the mesh to a new, empty keyspace, so rotate before
  data goes in. People reach a mesh with Studio's short-lived pass (no edit
  rights = view only); systems with the org API key (kept after 5 Dec).

## What a running Docker project picks up (2.4.495)

The image holds the Python code (a create-leafmesh project has no
configuration file); `.env` is read when the container is created; the store
keeps the configuration.

- **Live, no restart:** every agent field edited in Studio, `wake_up`
  included (2.4.492: added, changed, deleted or renamed, on every pod);
  adding or deleting an agent; vault changes (model keys, MCP, webhooks,
  connectors, Slack tokens, and since 2.4.492 an email account's
  credentials). An agent switched off for a missing connection or address
  switches back on by itself.
- **Reload in place (seconds, no restart):** a seat's `channels`, and mesh
  fields `architecture`, `manager.enabled`, `limits.consumer_inflight_max`,
  `runtime.lease_*`, `self_healing.enabled`, `api.cors_origins`, `brokers`,
  `auto_discover`. Each field's `applies` (live | reload | process_restart)
  is in the Studio contract. Only `evolution_api.*` needs a process restart.
- **`docker compose up -d`:** any `.env` change. Since 2.4.492 a model key in
  the vault wins over the same key in `.env`, with a warning; since 2.4.497
  so does every value the vault holds (endpoints, organisation / project ids,
  cloud identities). The `.env` value returns when the record goes.
- **Rebuild (`docker compose up -d --build`):** Python code — programmatic
  agents, `@tool` / `@global_tool`, `@pre_compose`. It loads at start only.
  Since 2.4.492 a programmatic agent that says `integration: python` (pure
  Python) is switched off while its function is missing; one that names a
  connector, or says nothing, stays on and a call to missing code fails.
- **Never:** a configuration file (a create-leafmesh project has none; a
  new, empty store is loaded again by `create-leafmesh --start`).
- **Several containers on one store:** a save reaches each within about 15 s
  (`runtime.config_sync_poll_s`); a `wake_up` fires once across them.
- **Upgrades:** the stored configuration is not migrated. If a newer SDK
  refuses it ("Configuration has N error(s) in the stored configuration"),
  repair it with the mesh stopped (2.4.492+; reads `.env`, the agency from
  `--agency`, `LEAFMESH_AGENCY_NAME`, or a `configs/config.yaml` / `config.yaml` if there is one):
  `leafmesh config check` (each problem with its line), `versions` (which
  pass, which is in use), `rollback` (to the newest that passes, saved as a
  new version), `export` / `import` (edit by hand; import checks first). In
  Docker: `docker compose run --rm <app service> leafmesh config check`.

## Quick "why is my agent misbehaving?" checklist

| Symptom | Likely rule |
|---|---|
| Decorators / function "do nothing", raw LLM output routed | #1 (2-param signature) |
| Downstream agent ignores upstream fields | #2 (handoff rendering / stale SDK < 2.4.104) |
| Array yield comes back as strings | #3A (declare `items`) |
| "Gemini is inconsistent / empty / truncated" | #5 (thinking eats max_tokens) or #3 |
| Agent runs as pure-YAML unexpectedly | #7 (discover name mismatch) |
| Agent schedules itself instead of acting | #8 (schedule_followup misuse) |
| "Provider X behaves differently from Y" on yields | #4 (they don't — parity since 2.4.103) |
| A handoff fired that the function's return should have prevented | Upgrade — since 2.4.106 `can_call` and `@compose` evaluate the FUNCTION's return, never the raw LLM yields |
| Data I stashed for later "leaked" into the LLM prompt | #11 (used a reserved key like `prepared_data`) |
| Data I put in `context` vanished at the next agent | #11 (`context` is per-turn; use yields for cross-agent) |
| Two copies of the same output / doubled counts downstream | `scaling.copies` in `fixed` mode — every copy got the whole job; use `mode: auto` with `work:` / `claim_tool:` (see Scaling) |
| Config refused: "agent 'x': instances, max_concurrent … are replaced by the scaling block (2.4.484). Write instead: …" | [Scaling](#scaling-scaling-24484--the-rules-that-surprise-people) — write the `scaling:` lines the message gives |
| I edited `config.yaml` and nothing changed (boot: "… that edit was NOT applied") | #25 — the configuration lives in the store; change it in Studio or `PUT /api/yaml/raw` |
| "model 'X' needs the <provider> provider, which has no key here" | Add the key in `.env` or on Infrastructure → Models (2.4.482 no longer falls back to the local model) |
| New sessions answered with HTTP 402 | The licence: plan at its limit or an unpaid invoice blocks NEW sessions; runs in flight carry on (2.4.481) |
| Traces show `<redacted bytes:N>` instead of the agent's text | `security.telemetry_redact_pii` is `true` by default (2.4.480); set `false` to read content. `<platform_prompt:N chars>` / `<elided:N chars>` are LeafCraft's own text, always hidden |
| The model can't see my MCP server's tools | #12 (declare `mcp:` on the agent; don't list them in `tools:`) |
| MCP tool calls fail with "tool not found" | #12 (tools are namespaced `<server>_<tool>`) |
| Config refused: "approval is routing" | #20 (route to a human agent instead) |
| Agent "switched off" at boot | #21 (it names a vault connection that does not exist) |
| Config refused: "… is no longer read from the config — keys, tokens, … are entered only in the vault" | [Vault-only values](#vault-only-values-24481) — move the value to a vault record, pick it with `connection:` |
| Agent stopped calling tools and answered early | #16 (`finish_reason: tool_cap` — raise the cap) |
| Agent says an API "isn't available" | The endpoint is switched off on the Tools page (`api_tools`, see agent-config-fields) — the agent names it |
| Gemini 2.5 Pro step has a loop with no output and a second try | #5 (2.5 Pro's thinking used `max_tokens` — raise it) |
| Command Center board looks empty or generic | It designs after `design_after_runs` real runs; and it can only speak the language your yields use |
| Config refused: "tool 'zapier_action' was removed in 2.4.485" (or `mcp_call`, `composio_action`, `n8n_workflow`, category `integration`) | Declare the agent's `zapier:` / `mcp:` / `composio:` / `n8n:` block, each picking a vault record (#15) |
| Boot: "`CREWAI_ENDPOINT` is set but is no longer read" (any connector variable) | External agents read only their vault record since 2.4.485 — put the value on the record, remove the variable |
| Boot: "vault record 'X': the query row 'Y' is no longer sent" | [The vault keeps sign-in only](#the-vault-keeps-sign-in-only-24486) — set it on the page that uses the record |
| Config refused: "agent 'x' is a human seat: scaling.copies would ask the same person…" | Remove `copies`; keep `scaling.runs.max` (2.4.485) |
| Nobody answered and nothing escalated | [A seat waits its time and stops](#a-seat-waits-its-time-and-stops-24486) |
| A person said "thank you" and the conversation closed | Intended (2.4.486): an answer no route takes ends it — [A person's reply](#a-persons-reply--what-reads-it-and-where-it-goes-24486) |
| The fan-in target ran twice | Intended (2.4.486): it runs when `wait_for` is met and again as late work arrives (`update_from`) — [Fan-in](#fan-in-runs-now-and-again-as-late-work-arrives-24486) |
| `from_yaml` raises "still has a persistence: block whose values differ from .env" | #24 — add the named lines to `.env`, remove the block |
| "yields 'x.y' is a list with no item type" warning | Declare the item type with `type: array`: `{type: array, items: string}` or `{type: array, items: {type: object, fields: {...}}}`. Write `array` in the dict form; `{type: list, …}` is read as `array` too since 2.4.487 (before, the model was told it was an object) (#3, Trap A) |
| Agent "switched off" at start: "not set up" / "its n8n connector has no address" | 2.4.490: the connector has no address (n8n `webhook_url`, A2A `url`, …). Put it in the vault record — it switches back on with no restart; it is never called or quarantined meanwhile |
| `from_yaml` gives `config.agents` empty, with no error | By design since 2.4.481: a file that does not pass validation loads only its boot part (agency name, store). `start()` reports the file's problems when it imports it. Fix them and start again |
| A Super-Agent run costs several times more model calls | `super_agent.tries` (2.4.491): `count` × `rounds` attempts per step — lower them or use `mode: auto` |
| The response cache never hits | `GET /api/llm/cache/stats`: `not_stored_tools` (a tool not marked `changes_nothing`), `not_stored_personal_data`, `not_stored_secret` — [the response cache](#memory-experience-and-the-response-cache-24486) |
| "this tenant has not connected <record>" | The agent has `tenant_credentials_only: true` and the run's tenant has no record of its own (2.4.488) — the tenant fills it (`GET /api/infra/tenant-credentials`) |
