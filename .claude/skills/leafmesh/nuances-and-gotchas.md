# LeafMesh — Nuances & Gotchas (READ FIRST)

**SDK baseline: 2.4.131.** This file captures the non-obvious rules that cause
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
strings*. Since 2.4.102 the SDK **warns** when it guesses this.

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
`max_tokens`. A small budget (e.g. the Manager's default ~1200) can be consumed
entirely by thinking → empty or truncated output. Since 2.4.101 the SDK reserves
headroom and fails MAX_TOKENS truncation loudly, but tight budgets still hurt.

**Do this:** give Gemini agents generous `max_tokens` (4000–8000), and set
`max_tokens` under the `manager:` block if the Manager runs on Gemini.

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
cleanly with a `budget_exhausted` marker; `escalate` routes to the Manager. Only
bites LLM spend (human/programmatic/external make no LLM calls).

---

## 10. Multi-tenancy is pass-through

`X-Tenant-ID` on a request scopes that request's data + events to a tenant. The
SDK never mints tenant ids — you pass them. `env_token` and other secrets are
stripped from API/UI responses; never surface them.

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
      - url: https://mcp.example.com/sse
        token: ${MCP_TOKEN}
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
  `LEAFMESH_SCHEDULER_MISFIRE_GRACE_S=none` (ops env knob; coalesce
  guarantees at most ONE catch-up per schedule).

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

`tools:` is only for tools **you** wrote. `playbook:` / `mcp:` / `zapier` /
`composio` / `n8n`, `memory: true` (→ `recall_memory`), `knowledge:` (→
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

## 16. `max_tool_calls_per_message` defaults to 5 and TRUNCATES SILENTLY

A chain that needs 7 tool calls stops at 5 — **no error, plausible answer, work
that never happened.** It looks exactly like the model deciding not to bother.
"Tool iteration 5 complete" in the logs = hit the cap, not a choice. Raise it on
any agent with a long read/act chain; **20 is the hard ceiling** (the SDK rejects
higher). This is the quietest "my agent did half the job" bug.

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
  `LEAFMESH_LLM_HARD_TIMEOUT_S` → `timeouts.llm_hard_timeout_s`, and the default
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

## Parallel instances (`instances: N`, 2.4.118+) — the rules that surprise people

One activation → N parallel copies of the agent, same session, any trigger
source (wake, request, handoff, mesh call, listener). Two fields only:

```yaml
finance_agent:
  instances: 3              # 3 copies per activation
  instances_handoff: last   # last (default) = COMBINE and route once; each = route N times
  tools: ["claim_batch"]    # an atomic claim tool splits the backlog between copies
```

What to know before using it:

- **`last` merges deterministically**: lists concatenate in instance order,
  numbers SUM, other fields take the final copy's value, and no field any
  copy produced is dropped. The per-copy detail rides on
  `result._instances = {count, results: {"1": {...}, ...}, failed: [...]}`,
  and `upstream_yields` carries the same combined payload downstream.
- **The number-sum rule cuts both ways.** `item_count` summing is right;
  `confidence: 0.9` from two copies becomes `1.8` — wrong. Agents whose
  yields carry ratios/scores should reshape with `@chain`/`@compose`
  (which receive the combined result + the `_instances` pool).
- **Without a claim tool, copies duplicate work** — and the merge honestly
  shows it (two identical items, count 2). That's not a bug; give the
  copies an atomic claim (`LPOP count` / `UPDATE … SKip LOCKED RETURNING`)
  so each pulls a disjoint batch.
- **Don't multiply triggers**: a 3-entry `wake_up` list × `instances: 3`
  = 9 runs. One cron line is all a fanned agent needs.
- **`instances` ≠ `parallel`.** `parallel`/`max_concurrent` caps INCOMING
  calls (a queue at the door); `instances` multiplies this agent's own
  execution. Fan out with `instances`, protect the shared downstream
  bottleneck (ERP, DB) with `parallel` on THAT agent.
- **Conversation/chain history keeps every copy's entry** (by design —
  the framework doesn't hide work). If the doubling bothers a prompt,
  reshape via `@compose`.
- History channels aside, failures stay visible: a dead copy is reported
  per-instance AND named in `_instances.failed`; the chain still continues
  once if any copy succeeded.

---

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
| Two copies of the same output / doubled counts downstream | `instances` without a claim tool — copies duplicated the work (see Parallel instances) |
| The model can't see my MCP server's tools | #12 (declare `mcp:` on the agent; don't list them in `tools:`) |
| MCP tool calls fail with "tool not found" | #12 (tools are namespaced `<server>_<tool>`) |
| Command Center board looks empty or generic | It designs after `design_after_runs` real runs; and it can only speak the language your yields use |
