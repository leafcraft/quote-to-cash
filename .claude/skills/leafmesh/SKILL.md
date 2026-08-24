---
name: leafmesh
description: Wire multi-agent meshes, HITL webhooks, can_call routing, decorators, and YAML config for the LeafMesh SDK. Use when adding agents, configuring flows, or debugging mesh issues.
allowed-tools: Read, Grep, Glob, Edit, Write, Bash
---

# LeafMesh SDK Development Skill

You are an expert at building multi-agent orchestration systems with the LeafMesh SDK.

> **SDK baseline: 2.4.131.** Before wiring or debugging agents, read
> **[nuances-and-gotchas.md](nuances-and-gotchas.md)** — the 10 non-obvious rules
> that cause almost every "my agent silently does nothing / the handoff looks
> empty / Gemini behaves differently" report. The top three that bite hardest:
> 1. An `llm` agent function MUST be `(llm_response, input_data, context)` —
>    exactly 3 params, or it is **never called** (no error).
> 2. Handoffs render BOTH the user message AND the upstream agent's structured
>    fields (2.4.104 "read both") — don't hand-embed fields into `user_message`.
> 3. `yields: foo: "array"` makes the model return **strings** — declare
>    `items:` to get objects.

> **The direction (READ before building):**
> **[building-agents-thoroughly.md](building-agents-thoroughly.md)** — how to build
> an agent and a mesh *thoroughly*, where every rule has a silent failure behind
> it: the four stages (identity-only `@pre_compose`, fail-closed `@chain`), the
> three instruction layers (prompt / flow / Skills — and the pairing rule that a
> duplicated playbook line *kills* the Skill), truth protocols (never collapse
> nothing / could-not-tell / declined; a stub must announce itself), where data
> lives, the "registered ≠ offered" verification layers, the finisher pattern, and
> **client intake + provisioning** — including "I have no backend → Supabase". Ends
> with the *before-you-call-an-agent-finished* checklist.

## Table of contents

- [**Nuances & Gotchas (READ FIRST)**](nuances-and-gotchas.md)
- [**Building agents & meshes thoroughly (the direction)**](building-agents-thoroughly.md)

- [When the user asks you to… do this](#when-the-user-asks-you-to-do-this) — quick action table
- [Rule 1 — A mesh is a TEAM, not a pipeline](#rule-1--a-mesh-is-a-team-not-a-pipeline)
- [Rule 2 — One ROLE, multiple RESPONSIBILITIES](#rule-2--one-role-multiple-responsibilities-the-hiring-test)
- [Rule 3 — Bound every retry back-edge](#rule-3--bound-every-retry-back-edge)
- [How This Project Works](#how-this-project-works) · [Core SDK Pattern](#core-sdk-pattern) · [User-Facing APIs](#user-facing-apis)
- [Agent Types](#agent-types) · [Super-Agent v3](#super-agent-v3) · [Skills System](#skills-system)
- [Command Center (the business board)](#command-center-the-business-board) · [Image generation](#image-generation)
- [STRICT — fields by `agent_type`](#strict--fields-by-agent_type) · [STRICT — `human_interface` rules](#strict--human_interface-rules)
- [Human-in-the-Loop (HITL)](#human-in-the-loop-hitl)
- [YAML Agent Config (All Fields)](#yaml-agent-config-all-fields) · [Condition Syntax](#condition-syntax-can_call-conditions)
- [Decorators — Making an Agent Self-Reliant](#decorators--making-an-agent-self-reliant)
- [Communication Types](#communication-types) · [Fan-In Patterns (`wait_for`)](#fan-in-patterns-wait_for) · [Tools](#tools)
- [Manager (Coordination + Escalation)](#manager-coordination--escalation) · [LLM Providers](#llm-providers)
- [Building New Agents — Step by Step](#building-new-agents----step-by-step)
- [Session & Upstream Yields](#session--upstream-yields)
- [Additional Resources](#additional-resources) · [Field reference](#field-reference)

## When the user asks you to... do this:

| User says | Action |
|-----------|--------|
| "Add a new LLM agent" | 1. Add YAML block in `configs/config.yaml` 2. Create `agency/<name>_agent.py` (optional -- pure YAML works) 3. Wire `can_call` from upstream agents 4. Add entry point if needed |
| "Add a programmatic agent" | 1. Add YAML block with `agent_type: "programmatic"` 2. If connector-only: add `integration` + `connector_config` (no Python needed) 3. If Python logic: create `agency/<name>_agent.py` 4. Wire `can_call` |
| "Add an external agent" | 1. Add YAML block with `agent_type: "external"`, `framework`, and `connector_config` (no Python needed) 2. Optionally add `agency/<name>_agent.py` to post-process connector result 3. Wire `can_call` |
| "Let this agent use an MCP server's tools" | Agent-level `mcp:` block — the server's tools join that agent's tool list. Do **not** re-list them under `tools:`. See [MCP servers as tools](agent-config-fields.md#mcp--mcp-servers-as-tools-the-normal-way) |
| "Integrate with Zapier/n8n/Composio/MCP" | Programmatic: `integration: "zapier"` + `connector_config`. External: `framework: "n8n"` + `connector_config`. Pre-compose helper: `@pre_compose(context_processor=zapier(...))`. See reference.md for all connector fields. |
| "Set up HITL / human review" | Pick **one** `human_interface`: `default` (inbox), `webhook` (channels/HTTP), or `api` (Python callback). Each one accepts a *different* set of config fields — see HITL section below. Mixing them (e.g. `default` + `webhook_config`) is rejected at YAML load. |
| "Connect agents" / "wire routing" | Add `can_call` entries with conditions. Use `calling_agent_response.field` in conditions. |
| "Add a tool" | Create `@global_tool` in `agency/tools.py`, add tool name to agent's `tools:` list in YAML |
| "Fan-out / fan-in" | Add multiple agents in `can_call` (fan-out), add `wait_for` expression on aggregator (fan-in) |
| "Schedule an agent" | Add `wake_up: "cron expression"` to agent YAML |
| "Debug why agent X isn't called" | Check `can_call` conditions, verify `calling_agent_response` fields match, check `communication_type` |
| "Validate my config" | POST the config to `/api/yaml/validate` or read `configs/config.yaml` and check structure |
| "Add a Super-Agent" / "this task needs multi-step planning + verification" | Set `super_agent: true` (on, defaults) or a **dict** to tune it: `super_agent: {cost_ceiling, wall_clock, synth_max_tokens, step_concurrency, …}` (2.4.123+; the dict is the only tuning path — flat `super_agent_*` keys and `LEAFMESH_SUPER_AGENT_*` env vars are dead). See [Super-Agent v3](#super-agent-v3) section. Use it when the task is genuinely multi-step (research synthesis, multi-file edits, multi-page analysis) — for one-shot tasks, plain LLM agent is faster + cheaper |
| "Add Skills" / "give this agent reusable playbooks" | Add `skills: {sourceName: "...", enabled: true, names: [...]}` on the agent. **Local `.md` files are NOT auto-loaded** — the default source is hosted (Redis). For filesystem skills, register a source via `POST /api/skills/sources` first. See [Skills System](#skills-system) section |
| "Retry when X fails" / "loop back to re-do upstream work" | NEVER write an unbounded retry back-edge. Add a per-session exhaustion counter in the agent's Python, yield a `*_retry_exhausted` boolean, gate the back-edge on it, add a terminal route. See [Rule 3](#rule-3--bound-every-retry-back-edge) |
| "Use Grok or Mistral as the model" | Set `model: "grok-2"` (or `grok-3`, `grok-beta`) and `XAI_API_KEY` env var; or `model: "mistral-large"` (or `mistral-small`, `mixtral-8x22b`, `codestral-latest`) and `MISTRAL_API_KEY` env var. Both are native providers — no Bedrock/Vertex routing needed |
| "Send / receive email from an agent" | Add Email channel adapter: `channels: {email: {smtp_host, smtp_port, smtp_user, smtp_password, imap_host, imap_user, imap_password}}`. Outbound via SMTP/Mailgun/SendGrid/Postmark; inbound via IMAP with talon reply-stripping. Use for customer support, partner notifications, internal escalations |

## Current project config
!`cat configs/config.yaml 2>/dev/null | head -30`

## Rule 1 — A mesh is a TEAM, not a pipeline

This is the most important thing to internalise before designing or
modifying a mesh.

Treat the mesh as **a team of capable agents that talk peer-to-peer**.
Agents call each other directly via `can_call`, fan-in via `wait_for`,
react to events on the bus. **The Manager is the supervisor** — it
watches via the Summarizer and steps in on exceptions, narration
hints, escalations, contract violations. It is not a router that
sits between every step.

### What "peer-to-peer" actually means in LeafMesh

| Move | Who decides | SDK construct |
|---|---|---|
| Agent A finishes, calls agent B because B can do the next thing | **A itself** | `can_call:` with `condition:` evaluated at A's site |
| Multiple agents collaborate before the next step | **The agents** | `wait_for: "A AND B AND C?"` on the joining agent |
| Same event lights several agents at once | **The event bus** | each agent's `listen_events:` / its position in `can_call` of an upstream |
| Same agent behaves differently depending on who called it | **The agent** | `context_parts.flows:` |
| Reroute because the LLM mentioned cancellation, low confidence, or anything condition can't catch | **The Manager (via Summarizer + narration)** | `narration:` on the agent + `manager.routing` |
| Stop on a contract violation and retry with feedback | **The Manager** (`enforce_yields` is the trigger) | `enforce_yields: true` + `enforce_yields_retry: N` |
| Escalate after N errors / timeouts | **The Manager** | `manager.escalation.targets` + `auto_escalate` |

Peer-to-peer is the **default**. The Manager is the **exception path**.

### Design rules

- **Not every agent has to be wired into a fixed chain.** Agents
  declare what they CAN do and who they CAN talk to via `can_call:`;
  whether the call fires depends on the `condition:` and the upstream
  yields at runtime.
- **Every wire is conditional.** Use `condition:` expressions
  everywhere — bare unconditional edges are a code smell. If A always
  calls B with no condition, ask whether they should just be one
  agent.
- **The workflow can start from anywhere.** Declare multiple
  `entry_points:` — one per real-world trigger (Kafka topic, webhook,
  Slack command, scheduled wake-up, mobile capture). Don't force every
  flow through a single "intake" agent.
- **The workflow can end anywhere.** Any agent can be a terminus
  (`can_call: []`). Sometimes the right answer is halt-at-HITL with
  no auto-continue; sometimes it's archive; sometimes it's both in
  parallel.
- **Bidirectional `can_call` is fine.** A calls B; B can also call A
  back if its yields say so. Real specialists collaborate — they
  don't only run forward through a pipeline.
- **`narration:` is for what conditions can't catch.** Plain-English
  hints the Summarizer reads on every turn ("if the customer mentions
  a competitor, also consider retention_agent"). Conditions are
  deterministic and instant; narration is the team-coach voice.
- **`manager.routing.mode: "learning"` lets the team adapt.** For
  regulated paths and safety gates use `"static"`. For everything
  else, let the Manager learn which agent combinations actually work.

### The mental model

```
   Multi-entry  (broker, webhook, cron, slack, mobile, …)
   ──────────────────┬──────────┬───────────┬───────────────
                     │          │           │
                     ▼          ▼           ▼
                 ┌───────┐  ┌───────┐   ┌───────┐
                 │agent A│◀▶│agent B│──▶│agent C│──▶  any
                 └───┬───┘  └───┬───┘   └───┬───┘    terminus
                     │ ▲        │ ▲         │
                     │ │        │ │         │
                     │ │ peer-to-peer       │
                     │ │ can_call / wait_for│
                     │ │ + bidirectional    │
                     ▼ │        ▼ │         ▼
                  events emitted on every state change
                                │
                                ▼
                       ┌────────────────────┐
                       │  Summarizer        │  observes all events
                       │  └→ Manager        │  intervenes when narration
                       │     ├ rerun        │  / escalation / contract
                       │     ├ redirect     │  violation triggers
                       │     └ escalate     │
                       └────────────────────┘
```

Agents do the work peer-to-peer. The Manager hovers above, watching
the stream, intervening only when the team needs the supervisor —
ambiguity, escalation, drift, contract failure. Most ticks the Manager
is silent because the team is handling itself.

The opposite (and wrong) model is a fixed pipeline `A → B → C → D`
where the wires are baked at design time, the flow can only start at
A, and one rigid graph handles every variant. That model is fragile,
hides judgment in code, and wastes both the peer collaboration the
SDK gives you and the supervisor the Manager is built to be.

## Rule 2 — One ROLE, multiple RESPONSIBILITIES (the hiring test)

An agent is a **person you would hire**. Its name is a job title. Its
prompt sections, module functions, and crons are that person's
multiple responsibilities. `can_call` is colleagues talking — you put
one human on a job and ask several things of them; the mesh works the
same way.

**The test, for any two agents:** *would a real company hire two
different people for this?* If no — they are ONE role, and the second
agent is a responsibility wearing a name tag. Merge it.

Smells that an agent is a responsibility, not a role:
- It only ever runs immediately after one other agent, same type,
  unconditionally (a pipeline step in costume).
- Its name describes an ACTION (`*_detector`, `*_drafter`, `*_tracker`)
  and another agent of the same domain exists that a single hire would
  obviously also cover.
- Two agents share a domain noun (`pipeline_health_*` twice; three
  `*_drafter`s writing candidate letters) — one analyst, one writer.

How to merge: the surviving agent takes the union of yields, the
union of responsibilities in its prompt/module (sequenced stages),
and the union of outbound edges. An LLM role absorbs deterministic
responsibilities into its module post-processing — never the reverse
(judgment never moves into a programmatic agent). Since 2.4.107 one
agent can hold MULTIPLE wake_up schedules, each with its own `input`
({cron, input} list entries) — so cron responsibilities that share an
agent's role no longer need to share one schedule; distinct schedules
with distinct inputs beat one overloaded cron. Since 2.4.124 crons
run in the agent's `timezone:` (default UTC; per-entry `timezone`
overrides per schedule) — always set it when the schedule means a
LOCAL time of day.

**What is NEVER merged — roles are not the only thing in a mesh.
Controls stay separate at any cost:**
- Deterministic gates (approval routers, playbook matrices) — code
  decides who approves money, never an LLM, never blended into one.
- Reviewer independence (a QA agent never merges into the drafter it
  reviews).
- Actuators behind human gates (ERP poster, schedule release, cloud
  tuner, publisher) — the thing that ACTS stays a thin, fail-closed
  agent on the far side of the human.
- Anonymity controls (e.g. an anonymised survey agent never merges
  into a performance reviewer).
- Parallel second opinions (an agent that deliberately reads the same
  event independently).
- Audit sinks, humans, humanoids.

A mesh designed this way reads like an org chart: every box is a hire
you could explain to a CFO, every wire is two colleagues talking, and
every control is a policy the company would enforce on people too.

## Rule 3 — Bound every retry back-edge

**NEVER write an unbounded retry back-edge.** This is the single most
common way a production mesh dies:

```yaml
# BAD — loops until the chain cap kills the session
matching_agent:
  can_call:
    - agent: "intake_agent"        # "go re-extract and try again"
      condition: "calling_agent_response.po_found == false"
```

If the thing being retried never succeeds (the PO genuinely isn't in
the document), this edge fires every lap until the per-session chain
cap trips. Real customer meshes have looped to the cap **re-asking the
human agent the same question on every lap**.

### What happens when the cap trips

The chain stops at `mesh.max_chain_events` (default **50** events per
session). The session is persisted `status: "stopped"`
(`stop_reason: max_chain_events_exceeded`), one `AGENT_ERROR` with
`error_type: "ChainCapExceeded"` is emitted, and every further dispatch
for that session halts — the session does NOT recover on its own. A
new entry-point call on the same session resets it to `active` and
re-arms the breaker. `max_chain_events` is raisable in YAML for
legitimately deep flows (research, batch fan-out) — raising it is
**not** a fix for an unbounded loop.

### The REQUIRED pattern — retry-exhaustion counter

Bound the loop in the agent's Python intelligence: count attempts per
session, yield an exhaustion boolean, gate the back-edge on it, and
give the exhausted case a terminal route.

```yaml
matching_agent:
  yields:
    po_found: "boolean"
    po_retry_exhausted: "boolean"    # loop guard
  can_call:
    # Retry edge — bounded by the exhaustion flag
    - agent: "intake_agent"
      condition: "calling_agent_response.po_found == false and calling_agent_response.po_retry_exhausted == false"
    # Terminal route when retries are spent — NEVER loop again
    - agent: "vendor_comms_agent"
      condition: "calling_agent_response.po_found == false and calling_agent_response.po_retry_exhausted == true"
```

```python
# agency/matching_agent.py — per-session attempt counter
_MAX_REEXTRACTION_ATTEMPTS = 1

async def matching_agent(llm_response, input_data, context):
    result = do_matching(...)
    result["po_retry_exhausted"] = False
    if not result.get("po_found"):
        session_id = context.get("session_id") or input_data.get("session_id", "")
        stash = stash_get(session_id)                  # in-process dict keyed by session
        attempts = int(stash.get("po_reextraction_attempts") or 0)
        if attempts >= _MAX_REEXTRACTION_ATTEMPTS:
            result["po_retry_exhausted"] = True        # steers the terminal edge
        else:
            stash["po_reextraction_attempts"] = attempts + 1
            stash_put(session_id, stash)
    return result
```

Rules of thumb:

- Every back-edge whose condition can stay true forever needs an
  exhaustion counter + a terminal route for the exhausted case.
- Back-edges through a **human agent** are the worst offenders — the
  human gets re-asked on every lap. Bound them first.
- There is **no** `once_per_session` agent flag — bound repeats in
  agent code (counter above) or via `manager.escalation.auto_escalate`.
- A→B→A ping-pong is allowed by the runtime (critic↔writer patterns
  are legitimate) — the chain cap is the only safety net, so the
  bounding is YOUR job.

---

## How This Project Works

```
configs/config.yaml    <- Agent definitions, mesh topology, entry points, HITL config
agency/*_agent.py      <- Agent logic (auto-discovered by filename match)
agency/tools.py        <- Custom tools (@global_tool, @tool)
main.py                <- Entry point: loads config, starts mesh + API server
hitl_stub_receiver.py  <- Webhook stub for testing HITL locally
.env                   <- API keys, Redis, license key
```

**Auto-discovery**: The SDK matches Python function names to YAML agent names. `greeter_agent()` in `agency/greeter_agent.py` binds to the `greeter_agent:` block in `config.yaml`.

**Execution flow**: Entry point -> agent function runs -> SDK handles mesh communication (can_call), session state, persistence, and observability automatically.

**Persistence is a deployment choice, not a code one.** The same agency runs on
Redis or on Postgres — `persistence: backend: redis` (default) or
`backend: postgres`. Nothing in your agents or YAML changes between them, so
never write agent code that assumes Redis.

## Core SDK Pattern

```python
from leafmesh import LeafMesh

sdk = LeafMesh.from_yaml("configs/config.yaml")
await sdk.start()   # Starts Redis, agent registry, API server, scheduler
result = await sdk.mesh_call("entry_point_name", input_data={"message": "Hello"}, session_id="optional")
await sdk.stop()
```

## User-Facing APIs

The SDK auto-starts a FastAPI server. These are the APIs users call to trigger workflows and interact with the mesh:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/mesh/request` | Trigger a workflow via entry point |
| POST | `/api/mesh/stream` | SSE stream of LLM response via entry point |
| POST | `/webhook/{entry_point}` | Webhook: new task OR HITL human response |
| POST | `/callback/{agent_name}` | Connector callback: async response from external system (n8n, Zapier, etc.) |
| GET | `/api/mesh/entry_points` | List available entry points |
| GET | `/api/webhook/secret` | Get HMAC signing secret for webhooks |
| POST | `/api/yaml/validate` | Validate a full config (for frontend editors) |
| POST | `/api/sessions/{session_id}/agents/{agent_name}/rerun` | Re-run an agent in an existing session, with optional feedback / new input |
| GET | `/api/registry` | Canonical catalog of valid model ids, agent types, connectors, integrations, channels (with config-field schemas). Use this — don't guess model names |
| POST / GET | `/api/skills/sources` | Register / list skill sources (e.g. a `filesystem` source so local `.md` skills load) |
| GET | `/api/sessions/hitl` | HITL inbox listing — ONE record per session, all pending asks nested in `requests[]` (oldest-first) |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive API docs (ReDoc) |

### Triggering a workflow

```bash
# Via API
curl -X POST http://127.0.0.1:18820/api/mesh/request \
  -H "Content-Type: application/json" \
  -d '{"entry_point": "greet_user", "data": {"message": "Hello"}}'

# Via webhook (external systems: Slack, Zapier, n8n, etc.)
curl -X POST http://127.0.0.1:18820/webhook/greet_user \
  -H "Content-Type: application/json" \
  -H "X-LeafMesh-Signature: sha256=<hmac>" \
  -d '{"message": "Hello"}'
```

### Webhook smart routing

The webhook endpoint routes automatically based on the payload:

| Payload | Behavior |
|---------|----------|
| No `session_id` | **New task** -- routes to the entry point's target agent |
| `session_id` + agent is paused (HITL) | **Resume** -- delivers human response to waiting agent |
| `session_id` + agent is busy (mid-chain) | **Rejected** -- returns `status: "busy"` |
| `session_id` + agent is idle | **New task on same session** -- preserves conversation history |

### HMAC webhook signing

```bash
# Get secret
SECRET=$(curl -s http://127.0.0.1:18820/api/webhook/secret | jq -r .secret)

# Sign a payload
BODY='{"session_id": "sess1", "decision": "approved", "message": "Looks good"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

# Send signed webhook
curl -X POST http://127.0.0.1:18820/webhook/greet_user \
  -H "Content-Type: application/json" \
  -H "X-LeafMesh-Signature: sha256=$SIG" \
  -d "$BODY"
```

### Rerunning an agent

Re-run a single agent inside an existing session, optionally with feedback so it can self-correct (`leafmesh >= 1.0.299`). Use this for a "Rerun" button in your UI, custom retry rules outside Manager analysis, or debugging from a script.

```python
# Python — same input as last time, no feedback
result = await sdk.rerun_agent(
    agent_name="advisor_agent",
    session_id="sess-123",
)

# Python — with feedback (caller spotted a bad shape)
result = await sdk.rerun_agent(
    agent_name="advisor_agent",
    session_id="sess-123",
    feedback={"error": "missing action_items", "expected_shape": {"action_items": "list"}},
    reason="schema_mismatch",
)

# Python — deliberately steer with new input
result = await sdk.rerun_agent(
    agent_name="processor_agent",
    session_id="sess-123",
    new_input={"message": "Now check refunds instead", "request_type": "refund"},
)
```

```bash
# HTTP — same primitive, for non-Python clients (e.g. LeafCraft Studio rerun button)
curl -X POST http://127.0.0.1:18820/api/sessions/sess-123/agents/advisor_agent/rerun \
  -H "Content-Type: application/json" \
  -d '{"feedback": {"error": "lacks specifics"}, "reason": "user_request"}'
```

`feedback` is rendered per agent type — LLM agents see a correction note in their prompt, human agents see it in their inbox/channel UI, external connectors receive `data._rerun_context`, programmatic agents receive `input_data._rerun_context`. Both Python and HTTP forms route through `Manager.execute_state` — same conductor as strict yields enforcement (`enforce_yields: true`).

Returns dispatch metadata (the agent runs asynchronously — subscribe to events on `session_id` for the result):

```json
{"status": "dispatched", "agent": "advisor_agent", "session_id": "sess-123", "input_source": "stored_original", "reason": "user_request"}
```

When `new_input` is omitted, the SDK pulls the agent's most recent stored input from `auto_store_agent_input`. If neither exists, the call raises `LeafMeshError`.

## Agent Types

| Type | Use When | LLM? | Pure YAML? | Example |
|------|----------|------|------------|---------|
| `llm` | Need AI reasoning, generation, analysis | Yes | Yes | Conversation, research, advisory |
| `llm` + `super_agent: true` | Multi-step task that needs planning + per-step verification + retry-once + cost ceiling + cancellation. The orchestrator wraps the LLM agent transparently — same yields, same downstream routing | Yes | Yes | Complex research synthesis, multi-file code changes, multi-page document analysis. See [Super-Agent v3](#super-agent-v3) |
| `human` | Need human decisions, approvals, HITL review | No | Yes | Approval gates, chat interfaces |
| `programmatic` | Deterministic logic, API calls, data transforms | No | Yes (with connector) | Data processing, Zapier/n8n actions |
| `external` | Wrap existing framework (CrewAI, LangGraph, n8n, etc.) | Varies | Yes (with connector) | Framework integration |

All agent types work from pure YAML. For programmatic and external agents, a connector (`integration` or `framework` + `connector_config`) can be the entire execution engine -- no Python code needed. The connector response is returned as-is. Optionally add `@sdk.intelligence("agent_name")` to post-process the connector result (the decorator takes the agent name as a required argument — `@sdk.intelligence()` with no name will not register).

Super-Agent is **opt-in** on an LLM agent — set `super_agent: true` and the SDK wraps the agent in the plan → execute → verify → reflect → finalize orchestrator (§[Super-Agent v3](#super-agent-v3)). For one-shot tasks, leave it off — a plain LLM agent is faster and cheaper.

## Super-Agent v3

A Super-Agent is an LLM agent wrapped in a transparent multi-phase orchestrator. Same `model`, `tools`, `knowledge`, `skills`, `memory`, `yields` fields — the orchestration is internal. Downstream callers see the same OpenAI-compatible response shape.

### When to enable

Use Super-Agent when the task **genuinely has multi-step structure** and the value of catching one bad step outweighs the orchestration overhead:

- Complex research synthesis across many sources
- Multi-file code changes that need verification per file
- Multi-page document analysis where each section needs a separate pass
- Pipeline-style work where each step has a checkable outcome

Do **not** enable Super-Agent for:
- One-shot Q&A, classification, summarization — plain LLM agent is faster and cheaper
- Tight latency budgets — orchestration overhead is real (additional plan + verify + reflect LLM calls)
- Tasks where you can already decompose into named agents with `can_call` — that's the better pattern

### Phase taxonomy

The orchestrator runs five phases per request. Each phase emits its own span in the trace tree.

| Phase | What runs | Persisted to |
|---|---|---|
| **plan** | LLM produces a structured task plan (list of steps with `expected_outcome` per step) | Plan Store in Redis, keyed by `(session_id, agent_name, run_id)` |
| **execute** | LLM runs each step in sequence | Scratchpad (per-run, cleared at finalize) |
| **verify** | LLM checks each step's output against the plan's `expected_outcome` | Plan Store — step status: `done` / `soft_failure` / `failed` |
| **retry-once** | On `soft_failure`, the orchestrator re-runs the step with failure context appended | Same step entry, `attempt_count` incremented |
| **reflect** | On hard failure or budget exhaustion, the LLM reads plan + scratchpad and proposes a plan amendment | Plan Store — `mutation_history` |
| **finalize** | LLM synthesises the final output against the original goal, honours `yields`, respects the per-agent `max_tokens` ceiling | Agent's normal output channel |

### Operator primitives (YAML keys on the LLM agent)

```yaml
agents:
  research_synthesiser:
    agent_type: "llm"
    model: "claude-sonnet-4-6"
    super_agent:                            # DICT form = the tuning path (2.4.123+); the ONLY way to tune it
      cost_ceiling: 100000                  # aggregate token budget per run (default 50000)
      wall_clock: 900                       # per-run wall-clock seconds (default 600)
      synth_max_tokens: 32768               # cap on the final synthesis call
      goal_check_view_chars: 12000          # chars the goal-check phase sees (default 12000)
      step_concurrency: 4                   # parallel plan steps when the DAG allows
    # super_agent: true is the shorthand — on with all defaults.
    # NOTE: the old FLAT keys (super_agent_cost_ceiling, super_agent_step_cap,
    #       synth_max_tokens_floor, …) were never wired — do not use them; and
    #       the LEAFMESH_SUPER_AGENT_* env vars are dead as of 2.4.131.
    prompt: |
      You are a research synthesiser. ...
    yields:
      summary: "string"
      sources: "list"
      confidence: "number"
```

### Two orchestration tools the Super-Agent gets

Beyond its normal tool surface, every Super-Agent gets these two:

- **`TodoWrite`** — the LLM modifies its own plan (add / edit / reorder steps) without leaving the run. Use case: mid-execution the LLM realises an earlier assumption was wrong; it amends the remaining steps.
- **`Pause`** — the LLM signals "I need a human here." Run yields control to the human-in-the-loop flow via the configured HITL mechanism. Root span stamps `status=OK` (designed exit, not failure) — operators do not get paged on Pause.

### Sentinel-exit handling

When a Super-Agent exits cleanly via `Pause` or via `cancellation_token`, the root span is stamped `status=OK` — not `UNSET`. Pause is a designed exit path, not a failure mode. Alerting rules can rely on this distinction.

### Output propagation

Every Super-Agent span carries an *informative* output attribute (not just `ok` / `failed`) so the trace tree reads as a step-by-step ledger. The orchestrator stamps each phase's output up the span tree as the run unwinds, so the root span's `output` field is a complete execution record without consumers having to walk children.

### Honest caveats

- Orchestration overhead is real — plan + verify + reflect are additional LLM calls per run. Don't enable for one-shot work.
- **Tune with the dict form, not flat keys.** As of 2.4.123 `super_agent:` takes a bool *or* a dict, and as of 2.4.131 the **dict is the only tuning path** — `super_agent: {cost_ceiling, wall_clock, step_max_tokens, synth_max_tokens, verify_view_chars, goal_check_view_chars, step_concurrency}` (defaults: `cost_ceiling` 50000, `wall_clock` 600, `goal_check_view_chars` 12000). The old **flat** `super_agent_*` / `synth_max_tokens_*` keys were never wired, and the `LEAFMESH_SUPER_AGENT_*` env vars are dead — don't use either.

## Skills System

Skills are reusable instruction blocks (playbooks) that agents load on demand — think of them as the agent's **"skill buddies"**, small sidekick playbooks loaded only when the work calls for them. The system prompt establishes who the agent **is**; skills establish how the agent **handles a specific kind of problem**. A support agent might have system-prompt instructions for tone and brand voice, plus 12 skills covering refund flow, account migration, billing dispute — each one a self-contained playbook the agent fetches only when relevant.

### Why use skills (vs. one long system prompt)

- **Token economy**: skills are fetched on demand. A 12-playbook agent doesn't burn tokens on 11 unused playbooks every call.
- **Attention**: the LLM's attention stays on the current task; playbook material is pulled in only when its relevance is asserted by a tool call.
- **Iteration safety**: editing the refund flow can't regress unrelated areas.
- **Reusability**: the same playbook (e.g. "GDPR Article 17 erasure procedure") can be referenced by multiple agents.

### Agent configuration

```yaml
agents:
  support_agent:
    agent_type: "llm"
    model: "gpt-4o-mini"
    skills:
      sourceName: "support_playbooks"   # registered skills source — see below
      enabled: true                      # on-switch (default true)
      names:                             # REQUIRED, non-empty — empty list clears the field (no skills)
        - "refund_flow"
        - "account_migration"
        - "churn_save"
        - "billing_dispute"

  # Shortform — list of names, routed to the "default" source (HOSTED):
  # skills: ["refund_flow", "billing_dispute"]
```

At runtime, the LLM sees a compact skills *index* in its system prompt:

```
Skills available to this agent. Call load_skill_reference(skill_name, file_name)
to read the full body of a multi-file skill, or just (skill_name) for single-file:

  - refund_flow: 7-step refund evaluation with regional tax handling
  - account_migration: enterprise account migration with downtime windows
  - churn_save: churn-mitigation talking points by tenure segment
  - billing_dispute: 4-step dispute resolution
```

When the user message is about refunds, the LLM calls `load_skill_reference("refund_flow")`, receives the full multi-paragraph body as the tool result, and continues with full playbook context.

### Strict gating gotchas

- `skills: true` (bare bool) is **rejected at YAML load** — `skills` must be a list of names (shortform) or a `{sourceName, enabled, names}` dict.
- `names` is **required and non-empty**. An empty `names` list does NOT mean "all skills" — it clears the field and the agent gets no skills.
- Shortform `skills: [name1, name2]` normalises to `{sourceName: "default", enabled: true, names: [...]}`.

### Source registration — local SKILL.md files are NOT auto-loaded

The agent's `sourceName` must match a **registered source**. If no
sources are registered, the SDK auto-creates one source named
`"default"` — and it is **HOSTED** (Redis-backed, Studio's skill
library). A project `skills/` directory full of `.md` files does
nothing on its own.

There is **no top-level `skills:` YAML block** — the config loader
rejects unknown top-level keys. Sources are registered at runtime via
the API (persisted in Redis, reloaded on every SDK start):

```bash
# Register a filesystem source so local skills/*.md actually load
curl -X POST http://127.0.0.1:18820/api/skills/sources \
  -H "Content-Type: application/json" \
  -d '{"name": "support_playbooks", "source_type": "filesystem", "config": {"root": "./skills"}}'
```

Then point the agent at it: `skills: {sourceName: "support_playbooks", enabled: true, names: [...]}`.

| Connector (`source_type`) | Storage | Use case |
|---|---|---|
| `filesystem` | `.md` files under a root dir. Root resolution: `config.root` > `LEAFMESH_SKILLS_DIR` env > `./skills/` (cwd) | Local dev, on-prem, version-controlled skill libraries |
| `hosted` | LeafCraft Hosted backend (Studio's skill library); auth via tier-keyed API key. This is what the auto-created `"default"` source uses | Centrally-managed skills, multi-replica deployments |

### Multi-file skills

A complex skill can be a directory containing multiple markdown files.
For the filesystem connector, single-file skills are `<name>.md` and a
multi-file skill is a subfolder whose primary file MUST be named
`SKILL.md` (Anthropic format — a subfolder without `SKILL.md` is
silently skipped):

```
skills/
  churn_save.md           # single-file skill
  refund_flow/
    SKILL.md              # primary — loaded by load_skill_reference("refund_flow")
    eu_vat_specifics.md   # loaded by load_skill_reference("refund_flow", "eu_vat_specifics.md")
    subscription_prorating.md
  account_migration/
    SKILL.md
    enterprise_downtime.md
```

The LLM first calls `load_skill_reference("refund_flow")` for the primary body, then `load_skill_reference("refund_flow", "eu_vat_specifics.md")` for a specific reference. This mirrors the Claude-Code "load only what's needed, when it's needed" pattern.

### Skills vs. Tools — the distinction

| | Skills | Tools |
|---|---|---|
| What they do | **Instruct** (return text the LLM reads) | **Act** (execute code with side effects) |
| Trust surface | Cannot do more than mislead the LLM — no `eval()`, no API call | Can take destructive actions; permission-gated by YAML |
| Authoring | Markdown files; non-technical people can write them | Python code; `@global_tool` decorator |
| Versioning | Live editing supported; next agent run picks up the new body | Compiled into the SDK / app code |

A compromised skill body cannot do more than produce bad text, which the Summarizer + yields contract are designed to catch. A compromised tool can have real-world side effects.

## Command Center (the business board)

The agency designs its own business KPI board by watching what its agents
actually do. **You do not write the metrics** — that is the whole point. It
watches a few real runs, infers what this agency exists to achieve, and derives
the numbers from real outcomes rather than from the config.

```yaml
manager:
  command_center:
    enabled: true
    design_after_runs: 3     # runs to observe before designing (1–50)
    max_metrics: 24
    model: null              # defaults to the manager's model
```

What this means when you are building an agency:

- **Name yields in business language.** The board is derived from what agents
  yield and which tools they run. `status: "settled"` and `claim_value` produce
  a board about claims; `output_1` and `flag_2` produce nothing anyone can read.
  This is the single biggest thing you control.
- **Nothing is pre-built.** There is no default metric set to switch on, and no
  template. An empty-looking board early on means it has not seen enough work
  yet, not that something is broken.
- **Work done before the board exists is not lost.** Events are buffered and
  replayed at their original timestamps once the schema lands.
- **The board is business, never machinery.** It talks about invoices, tickets
  and cases — not agents, tokens or queues. Do not try to make it show
  operational metrics; the dashboards already do that.
- **Operators can edit, export and re-import it**, and ask for a redesign in
  plain words when the business changes what matters.

## Image generation

An agent that produces images picks an image model the same way any other agent
picks a text one. Routing and capability checks are handled for you — an image
model is never selected for a text agent, or the reverse.

```yaml
  - name: creative_agent
    agent_type: llm
    model: gemini-3-pro-image
```

Available: `gemini-3-pro-image`, `gemini-2.5-flash-image` (Google);
`gpt-image-1`, `dall-e-3`, `dall-e-2` (OpenAI); Imagen 3 (Vertex);
Titan Image Generator v2, Nova Canvas, Stable Diffusion XL (Bedrock).

## STRICT — fields by `agent_type`

YAML load rejects fields that don't apply to the declared `agent_type`. Set only the fields that match.

| `agent_type` | Allowed type-specific fields |
|---|---|
| `llm` | `model`, `prompt`, `temperature`, `max_tokens`, `max_completion_tokens`, `reasoning`, `thinking`, `reasoning_budget`, `thinking_budget` (legacy, still declared), `enable_prompt_caching`, `response_format` (accepted extra), `optimization_strategy`, `context_parts`, `tools`, `tool_choice`, `max_tool_calls_per_message`, `tool_call_timeout`, `allow_parallel_tool_calls`, `tool_categories`, `skills`, `super_agent`, `effort`, `receive_conversation_history`, `history_limit`, `stream_yield`, `llm_hard_timeout_s`, `response_overrides` — (tune `super_agent` via its **dict** form, e.g. `super_agent: {cost_ceiling, wall_clock, …}`, not flat `super_agent_*` keys) |
| `human` | `human_interface`, `human_timeout_seconds`, `human_context_template`, `human_prompt_template`, `fallback_on_timeout`, `fallback_response`, `require_human_confirmation`, `human_escalation_triggers`, `operator_ids`, `webhook_config`, `channels` |
| `external` | `framework` (**required**), `connector_config` |
| `programmatic` | `integration`; `connector_config` allowed only when `integration` is set |

**Universal fields** (any type): `name`, `description`, `agent_type`, `communication_type`, `parallel`, `max_concurrent`, `wake_up`, `wake_up_input`, `timezone`, `yields`, `inputs`, `can_call`, `narration`, `wait_for`, `wait_for_timeout`, `auto_store_response`, `auto_store_yields`, `enforce_yields`, `enforce_yields_retry`, `memory`, `knowledge`, `skills`, `listen_events`.

**Do not set `is_human_powered` manually** — it's auto-derived from `agent_type` and is silently overwritten by the validator.

## STRICT — `human_interface` rules

A human agent picks **exactly one** interface. The fields below depend on which one.

| `human_interface` | Path | Required fields | Forbidden together |
|---|---|---|---|
| `default` | hosted HITL inbox (LeafCraft Studio) (hosted only) | none | do NOT set `webhook_config` or `channels` — they're ignored at runtime |
| `webhook` | Outbound HTTP / channel adapters | `webhook_config.outbound_url` OR `channels` (one is enough) | — |
| `api` / `custom` | Python callback registered via `sdk.agent_registry.register_human_agent(name, human_interface_handler=fn)` (there is **no** `sdk.register_human_handler()`) | none | do NOT set `webhook_config` or `channels` |

`channels` only fires when `human_interface: webhook`. Setting `channels` with `default` or `api` is silently ignored at runtime — don't do it.

## Human-in-the-Loop (HITL)

The human agent is a full mesh node -- not just an approval step. It participates in the agent chain like any other agent, with `can_call` conditions that route based on context.

### HITL YAML Config — pick **one** of these three blocks

> Don't mix interfaces. The validator rejects fields that don't apply to the chosen `human_interface`.

#### Option A — `human_interface: webhook` (outbound webhook OR channel adapter)

```yaml
agents:
  client:
    agent_type: "human"
    human_interface: "webhook"            # outbound HTTP / channels
    communication_type: "dual"            # respond + wait for inbound response
    human_timeout_seconds: 300
    # operator_ids: ["alice@co.com"]      # restrict who sees this in inbox (empty = all)

    webhook_config:
      outbound_url: "http://127.0.0.1:9999/human-notify"
      outbound_headers: {Content-Type: "application/json"}
      outbound_timeout: 30
      max_retries: 1
      retry_delay: 2
      # inbound_endpoint is auto-derived from entry_points

    # OR (instead of webhook_config) use a native channel adapter:
    # channels:
    #   slack:
    #     bot_token: "${SLACK_BOT_TOKEN}"
    #     signing_secret: "${SLACK_SIGNING_SECRET}"
    #     listen_channels: ["${SLACK_CHANNEL_ID}"]
    #     post_channel: "${SLACK_POST_CHANNEL}"

    can_call:
      - agent: "greeter_agent"
        condition: "not calling_agent_response.from_agent"   # works ONLY because human agents ALWAYS emit from_agent (maybe ""). Never `not` a field that can be absent — see gotcha #14
      - agent: "processor_agent"
        condition: "calling_agent_response.from_agent == 'greeter_agent'"

    yields: {request_data: "object"}
    inputs: {user_message: "string"}

entry_points:
  - name: "greet_user"
    target: "greeter_agent"
  - name: "human_contact"
    target: "client"
```

#### Option B — `human_interface: default` (hosted HITL inbox (LeafCraft Studio), hosted only)

> Inbox shape: `GET /api/sessions/hitl` returns **one record per
> session** with every pending ask nested in `requests[]`
> (oldest-first — `requests[0]` is the one to act on first;
> top-level `request_id` mirrors it, `request_count` is the total).

```yaml
agents:
  client:
    agent_type: "human"
    human_interface: "default"            # writes to Redis inbox + stream — that's it
    communication_type: "dual"
    human_timeout_seconds: 300
    # operator_ids: ["alice@co.com"]
    # NO webhook_config, NO channels — they're ignored on this interface
    can_call:
      - agent: "greeter_agent"
        condition: "not calling_agent_response.from_agent"   # works ONLY because human agents ALWAYS emit from_agent (maybe ""). Never `not` a field that can be absent — see gotcha #14
      - agent: "processor_agent"
        condition: "calling_agent_response.from_agent == 'greeter_agent'"
    yields: {request_data: "object"}
    inputs: {user_message: "string"}
```

#### Option C — `human_interface: api` (Python callback)

```yaml
agents:
  client:
    agent_type: "human"
    human_interface: "api"                # call into Python — no HTTP, no inbox
    communication_type: "dual"
    human_timeout_seconds: 300
    # NO webhook_config, NO channels
    can_call:
      - agent: "greeter_agent"
        condition: "not calling_agent_response.from_agent"   # works ONLY because human agents ALWAYS emit from_agent (maybe ""). Never `not` a field that can be absent — see gotcha #14
    yields: {request_data: "object"}
    inputs: {user_message: "string"}
```

```python
# Register the Python handler for human_interface: api
async def my_human_handler(context, session_id, timeout):
    return {"human_decision": "approved", "human_message": "Looks good"}
# The real API (verified as of 2.4.104) — there is NO sdk.register_human_handler():
sdk.agent_registry.register_human_agent("client", human_interface_handler=my_human_handler)
# Or, to attach a handler to an already-declared human agent:
# sdk.agent_registry.update_human_interface_handler("client", my_human_handler)
```

### HITL Scenarios

**Scenario 1 (System-initiated):** System triggers workflow, human reviews mid-flow
```
POST /api/mesh/request {"entry_point": "greet_user", "data": {"message": "..."}}
  -> greeter_agent (LLM) -> client (HITL, outbound webhook sent)
  -> [human reviews, responds via webhook]
  -> from_agent == "greeter_agent" -> processor_agent -> researcher + fallback -> advisor
```

**Scenario 2 (Human-initiated):** Human contacts mesh first via webhook
```
POST /webhook/human_contact {"message": "I need help with..."}
  -> client (no from_agent -> routes to greeter)
  -> greeter_agent (LLM, dual callback -> client)
  -> client (HITL, outbound webhook sent)
  -> [human reviews, responds via webhook]
  -> from_agent == "greeter_agent" -> processor_agent -> researcher + fallback -> advisor
```

**Scenario 3 (Same session, new message):** Human sends another message after workflow completes
```
POST /webhook/human_contact {"session_id": "existing-session", "message": "Now check my refund"}
  -> Session not paused -> treated as new request on same session
  -> Conversation history preserved from previous interaction
```

### How from_agent Routing Works

When an agent calls the human agent, the SDK stores `called_by` in Redis. When the human responds via webhook, the SDK includes `from_agent` in the output data so `can_call` conditions can route based on who called.

```yaml
# In output_data available to can_call conditions:
calling_agent_response.from_agent        # Who called the human ("greeter_agent" or "")
calling_agent_response.human_message     # What the human said
calling_agent_response.human_decision    # Human's decision field
calling_agent_response.human_data        # Any data from the human
calling_agent_response.human_initiated   # true (always for human output)
calling_agent_response.source_agent      # The human agent name ("client")
```

### Channel Adapters (Slack, Telegram, etc.)

`channels` only fires when `human_interface: webhook`. Other interfaces silently ignore it. To make a channel actually deliver messages, the human agent must declare the webhook interface:

```yaml
agents:
  client:
    agent_type: "human"
    human_interface: "webhook"        # REQUIRED for channels to fire
    communication_type: "dual"
    channels:
      slack:
        bot_token: "${SLACK_BOT_TOKEN}"
        signing_secret: "${SLACK_SIGNING_SECRET}"
        listen_channels: ["${SLACK_LISTEN_CHANNEL}"]
        post_channel: "${SLACK_POST_CHANNEL}"
      telegram:
        bot_token: "${TELEGRAM_BOT_TOKEN}"
      email:                              # v2.3.x — BRD-020
        # Outbound — SMTP, or provider API (Mailgun / SendGrid / Postmark)
        smtp_host: "${SMTP_HOST}"
        smtp_port: 587
        smtp_user: "${SMTP_USER}"
        smtp_password: "${SMTP_PASSWORD}"
        from_address: "support@example.com"
        # Inbound — IMAP (talon reply-stripping is automatic)
        imap_host: "${IMAP_HOST}"
        imap_port: 993
        imap_user: "${IMAP_USER}"
        imap_password: "${IMAP_PASSWORD}"
        imap_folder: "INBOX"
        # Optional — DKIM signing
        dkim_private_key: "${DKIM_PRIVATE_KEY}"
        # Optional — provider API mode (skip SMTP)
        # provider: "mailgun" | "sendgrid" | "postmark"
        # provider_api_key: "${MAILGUN_API_KEY}"
```

The HITL flow works identically across all channels -- the SDK handles transport, the agent handles routing. With multiple channels configured, the SDK tries each in order; if all fail, it falls back to `webhook_config.outbound_url` (when set).

**Email channel specifics (BRD-020, v2.3.x).** Email is **asymmetric** — outbound goes via SMTP (or provider API), inbound goes via IMAP. Threading is automatic via `Message-ID` / `In-Reply-To` / `References` headers, matching the same session-reconstruction pattern Slack uses with `thread_ts`. Reply / signature stripping uses `talon` (Mailgun's MIT-licensed library, used by Front / Help Scout / Intercom) so the LLM sees only the user's new message, not quoted history. Bounces and complaints publish `email.bounce` / `email.complaint` events to the Redis Stream — operators can suppress the recipient or mark the session for human review.

## YAML Agent Config (All Fields)

```yaml
agents:
  # ── LLM Agent ──
  my_agent:
    name: my_agent
    agent_type: "llm"              # llm | human | programmatic | external
    description: "What this agent does"
    model: "gpt-4o-mini"           # Any supported model
    prompt: "You are a helpful..." # System prompt
    temperature: 0.1
    max_tokens: 800
    max_completion_tokens: 1000    # For o1/o3/gpt-5.x reasoning models
    communication_type: "dual"     # dual | chain | execute

    # Mesh routing
    can_call:
      - agent: "next_agent"
        condition: "calling_agent_response.status == 'ready'"
    wait_for: "agent_a AND (agent_b OR agent_c)"
    wait_for_timeout: 60

    # Tools
    tools: ["word_count", "timestamp"]
    tool_categories: ["data", "utility"]
    # tool_choice: defaults to the string "auto" (never "unset") — when runtime
    # tools (memory/knowledge/CoT scaffolding) are configured, the framework
    # auto-promotes "auto" -> "required" on the first iteration so they fire.
    # Leave at "auto" unless you must force "required"/"none".
    max_tool_calls_per_message: 5
    allow_parallel_tool_calls: true
    tool_call_timeout: 30

    # Features (v2.2.24 SWAPPED the keys — see "reasoning vs thinking")
    thinking: true                 # SDK chain-of-thought scaffolding tools (works with ANY model; needs >= 1500 max_tokens)
    reasoning: true                # Provider-NATIVE extended thinking (reasoning-capable models ONLY — o-series/gpt-5.x, claude-4+, gemini-2.5+, deepseek-reasoner; warns at boot otherwise)
    reasoning_budget: 8192         # Max native reasoning tokens (thinking_budget is a deprecated alias)
    enable_prompt_caching: true    # Provider-native prompt caching (~90% savings on Anthropic)
    parallel: true                 # Parallel execution
    max_concurrent: 3              # Max concurrent invocations
    wake_up: "0 9 * * *"          # Cron schedule
    timezone: "Asia/Kolkata"       # 2.4.124+ — cron zone; OMIT = UTC (9:00 UTC != 9:00 local!)
    optimization_strategy: "performance"  # performance | cost | speed

    # Structured output — force LLM to respond with valid JSON schema
    # response_format:
    #   type: "object"
    #   properties:
    #     summary: { type: "string" }
    #     score: { type: "number" }
    #   required: ["summary"]

    # Smart memory
    memory:
      strategy: "hybrid"           # recency | relevance | hybrid
      limit: 10
      cross_session: true
      cross_session_limit: 50
      relevance_weight: 0.6
      recency_weight: 0.4
      decay_hours: 24

    # Yields & inputs
    yields: {summary: string, score: number}
    inputs: {query: string, context: object}

    # Context parts (shape LLM tone)
    context_parts:
      care: "Be empathetic and patient"
      sentiment_analysis: "Detect user frustration"
      guardrails: "Never discuss competitors"

    # auto_store_response: true    # Auto-store responses in Redis (default: true)
    # auto_store_yields: true      # Auto-store yields in Redis (default: true)

  # ── Programmatic Agent (connector-only, no Python needed) ──
  zapier_agent:
    agent_type: "programmatic"
    integration: "zapier"          # zapier | composio | n8n | mcp
    connector_config:
      connection: "google_sheets"
      action: "create_spreadsheet_row"
      api_key: "${ZAPIER_API_KEY}"
      # mode: "callback"           # For async workflows
      # callback_timeout: 120
    parallel: true                 # Parallel execution
    max_concurrent: 3              # Max concurrent invocations
    yields: {status: string}
    inputs: {data: object}

  # ── External Agent (connector-only, no Python needed) ──
  crew_agent:
    agent_type: "external"
    framework: "crewai"            # crewai | langgraph | autogen | a2a | mcp | n8n | zapier | composio | custom
    connector_config:
      endpoint: "http://localhost:9000"
      api_key: "${CREWAI_API_KEY}"              # Bearer Token
      # user_api_key: "${CREWAI_USER_API_KEY}"  # User Bearer Token (preferred over api_key)
    yields: {result: object}
    inputs: {task: string}

  # ── Human Agent — webhook interface (with optional channels) ──
  reviewer:
    agent_type: "human"
    human_interface: "webhook"        # default | webhook | api | custom
    communication_type: "dual"
    human_timeout_seconds: 300
    # operator_ids: ["alice@co.com"]  # restrict inbox (empty = all)
    # fallback_on_timeout: true
    # fallback_response: {decision: "timeout_default", message: "Request timed out"}
    # require_human_confirmation: false
    # human_escalation_triggers: ["urgent", "high_value"]

    # webhook_config — required when human_interface: webhook AND no channels
    webhook_config:
      outbound_url: "http://127.0.0.1:9999/human-notify"
      outbound_headers: {Content-Type: "application/json"}
      outbound_timeout: 30
      # inbound_endpoint: "/webhook/review"  # auto-derived from entry_points
      # inbound_auth_token: "${WEBHOOK_AUTH_TOKEN}"
      max_retries: 1
      retry_delay: 2
      # response_mapping: {user_reply: "response"}

    # channels — only valid when human_interface: webhook
    channels:
      slack:
        bot_token: "${SLACK_BOT_TOKEN}"
        signing_secret: "${SLACK_SIGNING_SECRET}"
        listen_channels: ["${SLACK_CHANNEL_ID}"]
        post_channel: "${SLACK_POST_CHANNEL}"

    can_call:
      - agent: "publisher"
        condition: "calling_agent_response.human_decision == 'approved'"
    yields: {decision: string}
    inputs: {request: object}

  # ── Human Agent — default (inbox) interface — hosted only ──
  # reviewer_inbox:
  #   agent_type: "human"
  #   human_interface: "default"      # writes only to hosted HITL inbox (LeafCraft Studio)
  #   communication_type: "dual"
  #   human_timeout_seconds: 300
  #   # NO webhook_config, NO channels — runtime ignores them
  #   can_call: [...]
  #   yields: {decision: string}
  #   inputs: {request: object}

  # ── Human Agent — api interface (Python callback) ──
  # reviewer_api:
  #   agent_type: "human"
  #   human_interface: "api"          # routed to a registered Python handler
  #   communication_type: "dual"
  #   human_timeout_seconds: 300
  #   # NO webhook_config, NO channels
  #   can_call: [...]
  #   yields: {decision: string}
  #   inputs: {request: object}
```

## Condition Syntax (can_call conditions)

Conditions evaluate agent output data:

```yaml
can_call:
  - agent: "specialist"
    condition: "calling_agent_response.status == 'needs_specialist'"
  - agent: "escalation"
    condition: "calling_agent_response.priority == 'high'"
  - agent: "greeter"
    condition: "not calling_agent_response.from_agent"   # works ONLY because human agents ALWAYS emit from_agent (maybe ""). Never `not` a field that can be absent — see gotcha #14   # Falsy check
  - agent: "processor"
    condition: "calling_agent_response.from_agent == 'greeter_agent'"
  - agent: "default"
    condition: "true"                                     # Always matches
  - agent: "urgent"
    condition: "calling_agent_response.item_count > 0"   # Numeric comparison
```

**Operators**: `==`, `!=`, `>`, `<`, `>=`, `<=`, `and`, `or`, `not`
**Access**: `calling_agent_response.field_name` for the upstream agent's output

### Conditions fail CLOSED — always yield what downstream conditions read

A condition that references a **missing field evaluates false** (route
skipped). And `yields` default-filling is NOT applied on dual-callback
republishes — when a `dual` agent's downstream response is republished
as the origin's output, missing keys (including booleans) stay missing
rather than being manufactured as `false`/`""`. Two consequences:

- Every field a downstream `can_call` condition reads MUST be
  explicitly present in the producing agent's output — yield it from
  the Python intelligence, don't rely on schema defaults.
- Write boolean edges as explicit pairs (`x == true` / `x == false`
  plus the exhaustion flag — see [Rule 3](#rule-3--bound-every-retry-back-edge));
  a missing field makes BOTH edges skip, which is the safe outcome.

### Authoring hygiene — avoid boot warnings

- **`temperature` ≤ ~0.3 for agents with a `yields` contract.** Above
  0.5 with yields declared warns at load — high temperature drifts
  JSON generation.
- **Prompt and `yields` must agree.** A prompt that asks for JSON keys
  with zero overlap with the `yields` schema is a **hard load error**.
- **`thinking: true` needs ≥ 1500 `max_tokens`** (the SDK CoT tools +
  final answer share one turn) and is wasted on agents with ≤ 1 yields
  field — both warn.
- **`reasoning: true` on a non-reasoning-capable model warns** — you
  probably meant `thinking: true` (see [reasoning vs thinking](#reasoning-vs-thinking)).
- **Unknown names warn at load**: `can_call` / `wait_for` referencing
  an agent that doesn't exist, and circular *unconditional* `can_call`
  edges. `entry_points` targets are stricter — a typo'd target raises
  `ConfigError` at load.

## Decorators — Making an Agent Self-Reliant

**We are not wiring a workflow of nodes. We are building an OPERATION —
a team of self-reliant agents.** A node waits to be handed clean inputs
and emits a fixed output. An AGENT, like a capable hire, does its own
job end to end: it gathers what it needs before it decides, makes sense
of what a system hands back, finishes its own work before passing it
on, and addresses each colleague in the language that colleague needs.
The decorators below are how an agent becomes self-reliant instead of a
step in a pipe.

An agent may call peers (`can_call`) — that *is* the operation. But it
owns its own preparation and post-processing; it never leans on the next
agent to clean up after it. **Self-reliant first, collaborative second.**

(Most pure-LLM agents need NONE of these — the SDK derives behaviour
from `yields`. Reach for a decorator only when the agent must do real
work *around* the model.)

| The agent needs to… | Reach for | When it runs |
|---|---|---|
| gather facts/inputs it needs BEFORE reasoning (fetch a CRM tier, clean the input, load policy) | `@pre_compose` | before the LLM |
| make sense of a system-of-record's RAW response (a connector returned JSON → turn it into yields) | `@sdk.intelligence` | *is* the agent's logic |
| finish its OWN work after deciding (validate, score, format, bound a retry) | `@chain` | after the LLM, in order |
| keep each step's result, not just the final (a derivation with an audit trail of stages) | `@chain_with_results` | after the LLM |
| do extra work ONLY in some cases (escalate + approve only when flagged) | `@conditional_chain` | after the LLM, if-condition |
| hand a DIFFERENT shape to each peer it calls (billing wants the invoice, support the summary) | `@compose` | shaping the handoff |

One judgment to keep straight: an agent that **always** needs a fact
should `@pre_compose` it — don't make the model *decide* to fetch a
thing it always needs. Pre-fetched facts the model reasons over; a
**tool call** is the opposite (optional, model-chosen, for things it
*may* reach for). Confusing the two is the most common modelling error.

### @pre_compose — gather what you need before you decide
*Essence: run fetch / clean / enrich BEFORE the model sees the prompt,
so the agent reasons over already-resolved facts instead of choosing to
go get them. The professional pulls the file before the meeting.*
*Reach for it when* the agent must cite a live external fact (CRM tier,
account balance, today's rate) or a normalised input in its reasoning,
every time it runs.
*Instead of* a tool call (optional, model-decided) or a fetch buried in
the agent body (runs after the model already guessed).
```python
from leafmesh import pre_compose

@pre_compose(
    context_processor=enrich_context,    # -> context["prepared_data"]["business_context"]
    input_processor=clean_input,         # -> context["prepared_data"]["clean_user_input"]
    others_processor=load_extras,        # -> context["prepared_data"]["others"]
)
async def my_agent(llm_response, input_data, context):
    prepared = context.get("prepared_data", {})
    return {"result": llm_response}
```

### @sdk.intelligence — make sense of what a system hands back
*Essence: a connector (`integration:` / `framework:`) returns its
system's RAW response; the intelligence function IS the agent's logic
that turns that raw payload into the agent's declared `yields`. Without
it the connector response passes through as-is — fine ONLY when the
system's shape already matches your contract (it rarely does).*
*Reach for it when* a programmatic/external agent calls a real system of
record (CRM/ERP/WMS via MCP/Zapier/n8n) and you must map its response
into the fields your wires and downstream agents expect.
*Instead of* trusting the connector's shape to match your yields, or
making a downstream agent reshape it (that's the next agent cleaning up
after this one — not self-reliant).
```python
# Programmatic/external agent: the connector runs, then THIS shapes its
# raw result into the agent's yields. Registered via the SDK (see the
# audit sink in agency/_shared/ for the registration form).
async def crm_lookup_agent(connector_response, input_data, context):
    # connector_response = the CRM's raw JSON
    return {
        "customer_id": connector_response.get("id", ""),
        "tier": connector_response.get("account", {}).get("tier", "standard"),
    }
```

### @chain — finish your own work before handing off
*Essence: run validate / score / format / bound-a-retry AFTER the model,
in order, as part of THIS agent's job — so what it hands a colleague is
already finished, not half-done.*
*Reach for it when* the agent must clamp or validate its output, compute
a deterministic field from the model's judgment, or bound a retry
back-edge before it routes.
*Instead of* leaving cleanup to the downstream agent, or scattering
post-processing inline with no order guarantee.
```python
from leafmesh import chain

@chain(validate, format_output)
async def my_agent(llm_response, input_data, context):
    return {"recommendations": llm_response}
# Runs: agent() -> validate() -> format_output()
```

### @chain_with_results — keep the trail, not just the answer
*Essence: like `@chain`, but preserves EACH stage's result, not only the
final one — for when the operation needs an audit trail of how the agent
got there.*
*Reach for it when* a multi-stage derivation must be inspectable after
the fact (compliance, debugging a scored decision).
*Instead of* `@chain`, when the intermediate results are throwaway.
```python
from leafmesh import chain_with_results

@chain_with_results(step1, step2, step3)
async def my_agent(llm_response, input_data, context):
    return {"main": llm_response}
# Returns: {"main_result": ..., "chain_results": [step1_result, step2_result, step3_result]}
```

### @conditional_chain — do the extra work only when it's warranted
*Essence: run a follow-on pipeline ONLY if a condition on the result
holds — the agent enriches/escalates itself when needed and skips the
cost when not.*
*Reach for it when* extra steps (a second review, an approval pass)
apply to some results, not all.
*Instead of* always running the steps (waste), or pushing the branch
onto a `can_call` wire when it's really part of THIS agent's own job.
```python
from leafmesh import conditional_chain

@conditional_chain(
    lambda result, ctx: result.get("needs_review"),
    review_step, approval_step
)
async def my_agent(llm_response, input_data, context):
    return {"needs_review": True, "data": llm_response}
```

### @compose — speak to each colleague in their language
*Essence: shape a DIFFERENT payload for each downstream agent this one
calls — billing gets the invoice, support gets the summary — instead of
broadcasting one fat dict and making each peer dig for its part.*
*Reach for it when* one agent fans out to several peers that each need a
different slice or shape of its result.
*Instead of* emitting one combined dict and relying on every downstream
agent to extract its part (which couples them all to your shape).
```python
from leafmesh import compose

@compose(
    billing_agent=lambda result, ctx: {"invoice": result["invoice_id"]},
    support_agent=lambda result, ctx: {"ticket": result["summary"]},
)
async def my_agent(llm_response, input_data, context):
    return {"invoice_id": "INV-123", "summary": "Issue resolved"}
```

**Combining decorators** (order matters -- bottom-up execution):
```python
@chain(validate, score)        # 3. Post-process
@compose(report=shape_report)  # 2. Shape per-target
async def advisor(llm_response, input_data, context):
    return {...}               # 1. Agent logic
```

## Communication Types

| Type | Behavior |
|------|----------|
| `dual` | Agent responds immediately, then calls downstream agents asynchronously |
| `chain` | Routes to downstream agent, waits for its result, returns combined |
| `execute` | Calls downstream, uses result inline, continues processing |

## Fan-In Patterns (wait_for)

```yaml
wait_for: "A AND B"                    # Wait for both
wait_for: "A OR B"                     # First one wins (race)
wait_for: "A AND B?"                   # A required, B optional
wait_for: "A AND (B OR C)"            # A required + race between B and C
```

Optional-contributor (`B?`) semantics — current (v2.4.22+):

- An optional sibling **dispatched from the same upstream output** is
  **waited for** — in-flight contributors count as pending, not absent.
  The fan-in no longer completes early with partial data while a
  sibling is still running.
- Late arrivals to an already-completed fan-in are **dropped as
  redundant** — no re-trigger, no duplicate downstream run.
- On `wait_for_timeout`: if only in-flight **optionals** are missing,
  the target runs with what it has; a missing **required** contributor
  still escalates `FanInTimeout` to the Manager.
- A contributor that **never gets dispatched at all** (no upstream
  route fires it) stalls the fan-in until `wait_for_timeout`. Every
  name in `wait_for` should be reachable from some upstream `can_call`
  in the same flow.

Access upstream yields in agent function:
```python
upstream_yields = input_data.get("upstream_yields", {})
agent_a_data = upstream_yields.get("agent_a", {})
```

## Tools

```python
from leafmesh import global_tool, tool

@global_tool(name="lookup", description="Look up a record", category="data",
             allowed_agents=["researcher_agent"], requires_confirmation=True)
def lookup(record_id: str) -> dict:
    return {"id": record_id, "data": "..."}

@tool(name="format_md", description="Format as markdown")
def format_md(items: list) -> str:
    return "\n".join(f"- {item}" for item in items)
```

## Manager (Coordination + Escalation)

```yaml
manager:
  # on by default — omit `enabled` (set `enabled: false` only to kill
  # coordination + the summarizer entirely; rare)
  model: "gpt-4o-mini"          # Summarizer model
  domain: "generic"              # generic | ecommerce | data_analysis
  routing:
    mode: "learning"             # static | learning (adaptive routing)
    confidence_threshold: 0.7
    fallback: "all"
  escalation:
    targets:
      - type: "human_agent"
        agent: "client"
      # - type: "webhook"
      #   url: "${ESCALATION_WEBHOOK_URL}"
      # - type: "channel"
      #   provider: "slack"
      #   channel_id: "${ESCALATION_SLACK_CHANNEL}"
    auto_escalate:
      max_retries: 3
      max_errors_per_session: 5
      timeout_threshold: 2
```

## LLM Providers

| Provider | Model Prefix | Config |
|----------|-------------|--------|
| OpenAI | `gpt-`, `o1-`, `o3-`, `o4-`, `chatgpt-` | `OPENAI_API_KEY` env var |
| Anthropic | `claude-` | `ANTHROPIC_API_KEY` env var |
| Google | `gemini-` | `GOOGLE_API_KEY` env var |
| DeepSeek | `deepseek-` | `DEEPSEEK_API_KEY` env var |
| AWS Bedrock | `bedrock/model-name` | `mesh.bedrock.region` in YAML |
| Google Vertex | `vertex/model-name` | `mesh.vertex.project` + `location` |
| Azure Foundry | `foundry/model-name` | `mesh.foundry.endpoint` in YAML |
| **xAI Grok** | `grok-` | `XAI_API_KEY` env var (added v2.3.x — native provider, no Bedrock/Vertex routing) |
| **Mistral** | `mistral-`, `mixtral-`, `codestral-` | `MISTRAL_API_KEY` env var (added v2.3.x — native provider, no Bedrock/Vertex routing) |
| Local (vLLM, Ollama, etc.) | any name | `mesh.local.endpoint` + `server_type` in YAML |

## Building New Agents -- Step by Step

1. **Add YAML config** in `configs/config.yaml` under `agents:`
2. **For connector-only agents** (programmatic with `integration` or external with `framework`): done -- no Python needed
3. **For agents with custom logic**: create `agency/<name>_agent.py` -- function name must match agent name
4. **Add to can_call** of upstream agents that should route to it
5. **Add entry point** if it should be directly invocable
6. **Restart** the mesh (`python main.py`)

### Common Patterns

**Hub-and-spoke**: One router agent that calls specialists based on conditions
```yaml
router_agent:
  can_call:
    - agent: "sales_agent"
      condition: "calling_agent_response.intent == 'sales'"
    - agent: "support_agent"
      condition: "calling_agent_response.intent == 'support'"
```

**Pipeline**: Linear A -> B -> C chain
```yaml
intake_agent:
  can_call: [{agent: "analyzer_agent"}]
analyzer_agent:
  can_call: [{agent: "responder_agent"}]
```

**Fan-out/fan-in**: Parallel processing with aggregation
```yaml
splitter_agent:
  can_call:
    - {agent: "worker_a"}
    - {agent: "worker_b"}
aggregator_agent:
  wait_for: "worker_a AND worker_b"
```

**Race pattern**: Multiple approaches, first wins
```yaml
consumer_agent:
  wait_for: "fast_agent OR slow_agent"
```

**HITL approval gate**: Agent -> human review -> continue or revise
```yaml
draft_agent:
  can_call: [{agent: "reviewer"}]
reviewer:
  agent_type: "human"
  communication_type: "dual"
  can_call:
    - agent: "publisher"
      condition: "calling_agent_response.human_decision == 'approved'"
    - agent: "draft_agent"
      condition: "calling_agent_response.human_decision == 'revision_needed'"
```

## Session & Upstream Yields

```python
async def my_agent(llm_response, input_data, context):
    upstream = input_data.get("upstream_yields", {})
    caller_data = upstream.get("caller_agent_name", {})
    session_id = context.get("session_id")
    memory_posts = context.get("memory_posts", [])
    prepared = context.get("prepared_data", {})
```

## Additional Resources

- **[building-agents-thoroughly.md](building-agents-thoroughly.md)** — **The direction — how Claude should build an agent and a mesh thoroughly.** Read alongside `agency-development.md`. Part A: the agent, built thoroughly (four stages, three instruction layers + the pairing rule, tools/identity-from-code, truth protocols, where data lives, the registered/permitted/offered/called verification layers, boundary-shipping, and the finished-agent checklist). Part B: the mesh, from the expense-reimbursement pod (coordinator + specialists + finisher, one-human-one-agent-one-system, default-deny, WORM, the finisher pattern). Part C: **client intake + provisioning** — inventory → membership bar → cast → connectors → **"no backend → provision Supabase"** (identity/domain/ledger/storage mapping) → controls + verification.
- **[agency-development.md](agency-development.md)** — **The method for building a whole agency (template) end-to-end.** Read this FIRST when starting or elevating a template: the seven first principles, the nine-phase process (story → cast roles → draw flow → YAML-vs-Python → decorators → connectors → controls → verify → document), the agent-type & decorator decision tables, the mesh boundary for external parties, the verification doctrine (config-load ≠ runtime proof), the adversarial self-check, and the anti-patterns. SKILL.md tells you which field does what; this tells you how to think and in what order.
- **[agent-config-fields.md](agent-config-fields.md)** — **Authoritative field reference for every YAML field**. Lists every option for every agent type (`llm`, `human`, `external`, `programmatic`), plus `WebhookConfig`, `ChannelConfig`, `Memory`, `EscalationConfig`, `EscalationTarget`, `LeafMeshConfig`, `ManagerConfig`, `MeshConfig` (Bedrock / Vertex / Foundry / Local), `RedisConfig`, `EvolutionConfig`, `DataStructure`, `Entry Points`, all per-framework `connector_config` schemas, and the **Field Applicability by Agent Type** matrix. Read this file when in doubt about any field, accepted values, default, or what's allowed where.
- **[reference.md](reference.md)** — SDK Python API (`sdk.start()`, `sdk.mesh_call()`, `@global_tool`, decorators, error classes, env vars, etc.).
- **[examples.md](examples.md)** — copy-paste agent patterns (HITL, fan-out, hub-and-spoke, race, etc.).

> When the user asks "what fields can I put on a programmatic agent?" / "what's the default for `temperature`?" / "what does `wait_for: A AND B?` mean?" / "how do I configure n8n callback mode?" / "what fields does `EscalationTarget` accept?" — the answer lives in **agent-config-fields.md**. Don't guess; quote the file.

---

## Field reference

The complete field reference — every field, type, default, and accepted value for every agent type and config object — lives in its own file: **[agent-config-fields.md](agent-config-fields.md)**. Read it there.

> This section previously inlined a full copy of `agent-config-fields.md`. The copy was **removed** because it drifted out of sync with the source (diverging `tool_choice` defaults, missing LLM fields, stale `skills`/`session_ttl`/`super_agent` claims). There is now a single source of truth — always consult `agent-config-fields.md` for field-level questions.
