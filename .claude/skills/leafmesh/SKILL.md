---
name: leafmesh
description: Wire multi-agent meshes, HITL webhooks, can_call routing, decorators, and YAML config for the LeafMesh SDK. Use when adding agents, configuring flows, or debugging mesh issues.
allowed-tools: Read, Grep, Glob, Edit, Write, Bash
---

# LeafMesh SDK Development Skill

You are an expert at building multi-agent orchestration systems with the LeafMesh SDK.

## When the user asks you to... do this:

| User says | Action |
|-----------|--------|
| "Add a new LLM agent" | 1. Add YAML block in `configs/config.yaml` 2. Create `agency/<name>_agent.py` (optional -- pure YAML works) 3. Wire `can_call` from upstream agents 4. Add entry point if needed |
| "Add a programmatic agent" | 1. Add YAML block with `agent_type: "programmatic"` 2. If connector-only: add `integration` + `connector_config` (no Python needed) 3. If Python logic: create `agency/<name>_agent.py` 4. Wire `can_call` |
| "Add an external agent" | 1. Add YAML block with `agent_type: "external"`, `framework`, and `connector_config` (no Python needed) 2. Optionally add `agency/<name>_agent.py` to post-process connector result 3. Wire `can_call` |
| "Integrate with Zapier/n8n/Composio/MCP" | Programmatic: `integration: "zapier"` + `connector_config`. External: `framework: "n8n"` + `connector_config`. Pre-compose helper: `@pre_compose(context_processor=zapier(...))`. See reference.md for all connector fields. |
| "Set up HITL / human review" | Pick **one** `human_interface`: `default` (inbox), `webhook` (channels/HTTP), or `api` (Python callback). Each one accepts a *different* set of config fields — see HITL section below. Mixing them (e.g. `default` + `webhook_config`) is rejected at YAML load. |
| "Connect agents" / "wire routing" | Add `can_call` entries with conditions. Use `calling_agent_response.field` in conditions. |
| "Add a tool" | Create `@global_tool` in `agency/tools.py`, add tool name to agent's `tools:` list in YAML |
| "Fan-out / fan-in" | Add multiple agents in `can_call` (fan-out), add `wait_for` expression on aggregator (fan-in) |
| "Schedule an agent" | Add `wake_up: "cron expression"` to agent YAML |
| "Debug why agent X isn't called" | Check `can_call` conditions, verify `calling_agent_response` fields match, check `communication_type` |
| "Validate my config" | POST the config to `/api/yaml/validate` or read `configs/config.yaml` and check structure |
| "Add a Super-Agent" / "this task needs multi-step planning + verification" | Set `super_agent: true` on an LLM agent in YAML; add `super_agent_cost_ceiling`, `super_agent_step_cap`, `super_agent_reflection_budget`, `synth_max_tokens_floor`, `synth_max_tokens_ceiling`. See [Super-Agent v3](#super-agent-v3) section. Use it when the task is genuinely multi-step (research synthesis, multi-file edits, multi-page analysis) — for one-shot tasks, plain LLM agent is faster + cheaper |
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
(judgment never moves into a programmatic agent). One `wake_up` per
agent: cron responsibilities merge only when one schedule can carry
both.

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

**Execution flow**: Entry point -> agent function runs -> SDK handles mesh communication (can_call), session state, Redis persistence, and observability automatically.

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
# HTTP — same primitive, for non-Python clients (e.g. ADK Studio rerun button)
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

All agent types work from pure YAML. For programmatic and external agents, a connector (`integration` or `framework` + `connector_config`) can be the entire execution engine -- no Python code needed. The connector response is returned as-is. Optionally add `@sdk.intelligence()` to post-process the connector result.

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
    super_agent: true                       # the on-switch
    super_agent_cost_ceiling: 100000        # hard ceiling on aggregate token cost for one run
    super_agent_step_cap: 12                # max executable steps before hard-stop
    super_agent_reflection_budget: 2        # max reflect-then-amend cycles per run
    super_agent_wall_clock: 900             # per-agent wall-clock seconds (15 min)
    synth_max_tokens_floor: 16384           # lower bound on synthesis call's max_tokens (Anthropic non-streaming guardrail)
    synth_max_tokens_ceiling: 32768         # upper bound for cost protection
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
- The synthesis call's `max_tokens` floor matters on Anthropic non-streaming — without `synth_max_tokens_floor`, Anthropic silently truncates outputs that exceed an internal guardrail. Set the floor explicitly for any task that produces > 8K-output.
- `super_agent_cost_ceiling` is a hard stop. Once aggregate token cost crosses the ceiling, the run cancels and stamps a `cost_ceiling.exceeded` event. Pick the ceiling based on the task's realistic worst case, not the average.

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

## STRICT — fields by `agent_type`

YAML load rejects fields that don't apply to the declared `agent_type`. Set only the fields that match.

| `agent_type` | Allowed type-specific fields |
|---|---|
| `llm` | `model`, `prompt`, `temperature`, `max_tokens`, `max_completion_tokens`, `reasoning`, `thinking`, `reasoning_budget` (`thinking_budget` is a deprecated alias), `enable_prompt_caching`, `response_format`, `optimization_strategy`, `context_parts`, `tools`, `tool_choice`, `max_tool_calls_per_message`, `tool_call_timeout`, `allow_parallel_tool_calls`, `tool_categories`, `skills`, `super_agent`, `super_agent_cost_ceiling`, `super_agent_step_cap`, `super_agent_reflection_budget`, `super_agent_wall_clock`, `synth_max_tokens_floor`, `synth_max_tokens_ceiling`, `effort` |
| `human` | `human_interface`, `human_timeout_seconds`, `human_context_template`, `human_prompt_template`, `fallback_on_timeout`, `fallback_response`, `require_human_confirmation`, `human_escalation_triggers`, `operator_ids`, `webhook_config`, `channels` |
| `external` | `framework` (**required**), `connector_config` |
| `programmatic` | `integration`; `connector_config` allowed only when `integration` is set |

**Universal fields** (any type): `name`, `description`, `agent_type`, `communication_type`, `parallel`, `max_concurrent`, `wake_up`, `yields`, `inputs`, `can_call`, `narration`, `wait_for`, `wait_for_timeout`, `auto_store_response`, `auto_store_yields`, `enforce_yields`, `enforce_yields_retry`, `memory`, `knowledge`, `skills`, `listen_events`.

**Do not set `is_human_powered` manually** — it's auto-derived from `agent_type` and is silently overwritten by the validator.

## STRICT — `human_interface` rules

A human agent picks **exactly one** interface. The fields below depend on which one.

| `human_interface` | Path | Required fields | Forbidden together |
|---|---|---|---|
| `default` | ADK-Frontend HITL inbox (hosted only) | none | do NOT set `webhook_config` or `channels` — they're ignored at runtime |
| `webhook` | Outbound HTTP / channel adapters | `webhook_config.outbound_url` OR `channels` (one is enough) | — |
| `api` / `custom` | Python callback registered via `sdk.register_human_handler()` | none | do NOT set `webhook_config` or `channels` |

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
        condition: "not calling_agent_response.from_agent"
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

#### Option B — `human_interface: default` (ADK-Frontend HITL inbox, hosted only)

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
        condition: "not calling_agent_response.from_agent"
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
        condition: "not calling_agent_response.from_agent"
    yields: {request_data: "object"}
    inputs: {user_message: "string"}
```

```python
# Register the Python handler for human_interface: api
async def my_human_handler(context, session_id, timeout):
    return {"human_decision": "approved", "human_message": "Looks good"}
sdk.register_human_handler("client", my_human_handler)
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
    # tool_choice: leave unset for framework default — when runtime tools
    # (memory/knowledge/CoT scaffolding) are configured, the framework
    # promotes to 'required' on the first iteration so they actually fire.
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
  #   human_interface: "default"      # writes only to ADK-Frontend HITL inbox
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
    condition: "not calling_agent_response.from_agent"   # Falsy check
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
  enabled: true
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

- **[agency-development.md](agency-development.md)** — **The method for building a whole agency (template) end-to-end.** Read this FIRST when starting or elevating a template: the seven first principles, the nine-phase process (story → cast roles → draw flow → YAML-vs-Python → decorators → connectors → controls → verify → document), the agent-type & decorator decision tables, the mesh boundary for external parties, the verification doctrine (config-load ≠ runtime proof), the adversarial self-check, and the anti-patterns. SKILL.md tells you which field does what; this tells you how to think and in what order.
- **[agent-config-fields.md](agent-config-fields.md)** — **Authoritative field reference for every YAML field**. Lists every option for every agent type (`llm`, `human`, `external`, `programmatic`), plus `WebhookConfig`, `ChannelConfig`, `Memory`, `EscalationConfig`, `EscalationTarget`, `LeafMeshConfig`, `ManagerConfig`, `MeshConfig` (Bedrock / Vertex / Foundry / Local), `RedisConfig`, `EvolutionConfig`, `DataStructure`, `Entry Points`, all per-framework `connector_config` schemas, and the **Field Applicability by Agent Type** matrix. Read this file when in doubt about any field, accepted values, default, or what's allowed where.
- **[reference.md](reference.md)** — SDK Python API (`sdk.start()`, `sdk.mesh_call()`, `@global_tool`, decorators, error classes, env vars, etc.).
- **[examples.md](examples.md)** — copy-paste agent patterns (HITL, fan-out, hub-and-spoke, race, etc.).

> When the user asks "what fields can I put on a programmatic agent?" / "what's the default for `temperature`?" / "what does `wait_for: A AND B?` mean?" / "how do I configure n8n callback mode?" / "what fields does `EscalationTarget` accept?" — the answer lives in **agent-config-fields.md**. Don't guess; quote the file.


---

# Complete Agent Config Field Reference

_Inlined from `agent-config-fields.md` — every field, every default, every allowed value._

This document lists every configuration field, its type, default value, and accepted values. Use this to build frontend forms, dropdowns, and validation.

---


## Agent Types

| Value | Description |
|-------|-------------|
| `llm` | LLM-powered agent (default). Executes via OpenAI, Claude, Bedrock, Vertex, or Foundry. |
| `human` | Human operator agent. Routes to a person via API, webhook, or channel. |
| `programmatic` | Python function with business logic. No LLM calls. |
| `external` | Delegates to an external framework (CrewAI, LangGraph, AutoGen, etc.). |

---

## AgentConfig — Core Fields (All Types)

These fields apply to every agent regardless of `agent_type`.

| Field | Type | Default | Accepted Values | Required | Description |
|-------|------|---------|-----------------|----------|-------------|
| `name` | string | — | any string | **yes** | Unique agent name within the mesh |
| `description` | string | `null` | any string | no | Agent description and purpose |
| `agent_type` | string | `"llm"` | `llm`, `human`, `programmatic`, `external` | no | Agent execution type (see note below) |
| `communication_type` | string | `"dual"` | `dual`, `chain`, `execute` | no | How agent communicates with the mesh |
| `parallel` | bool | `false` | `true`, `false` | no | Enable parallel processing |
| `max_concurrent` | int | `null` | 1 – unlimited | no | Max concurrent calls when `parallel: true` (null = unlimited) |
| `wake_up` | string | `null` | cron expression (e.g. `"0 9 * * *"`) | no | Schedule for periodic wake-up |
| `listen_events` | list | `[]` | list of [`EventListener`](#event-listeners--brd-021-kafka--sqs--mqtt--redis-streams--imap) entries | no | Bind agent to external event sources (Kafka, SQS, MQTT, Redis Streams, IMAP). Each entry references a broker from the top-level `brokers:` block. Parallel to `wake_up` — both are agent-level trigger surfaces |
| `yields` | dict | `{}` | key: field name, value: type string or nested object | no | Output schema — what agent produces |
| `inputs` | dict | `{}` | key: field name, value: type string or nested object | no | Input schema — what agent expects |
| `can_call` | list | `[]` | list of `{"agent": "name"}` or `{"agent": "name", "condition": "expr"}` | no | Agents this agent can invoke |
| `narration` | string | `null` | any string (multiline supported) | no | Plain-English routing hints for the Manager — evaluated by the Summarizer when conditions don't cover everything (see [Narration Routing](#narration-routing)) |
| `wait_for` | string or list | `[]` | agent names or expression string | no | Fan-in/join condition |
| `wait_for_timeout` | int | `60` | 1 – unlimited (seconds) | no | Hard timeout for fan-in |
| `auto_store_response` | bool | `true` | `true`, `false` | no | Auto-store responses in Redis |
| `auto_store_yields` | bool | `true` | `true`, `false` | no | Auto-store yields in Redis |
| `memory` | bool or dict | `false` | `true`, `false`, or memory config dict | no | Agent memory — see [Memory Config](#memory-config) |
| `memory_limit` | int | `10` | 1 – 100 | no | Legacy: max recent feed posts (use `memory.limit` instead) |
| `knowledge` | bool or dict | `false` | `false`, or `{serviceName, enabled, groupName}` | no | Knowledge/RAG — see [Knowledge Config](#knowledge-config) |
| `enforce_yields` | bool | `false` | `true`, `false` | no | Strictly validate this agent's output against the declared `yields:` schema. `false` (default) fills missing keys with type defaults and logs warnings; `true` triggers a Manager-driven retry up to `enforce_yields_retry` times, then escalates. See [Yields Enforcement](#yields-enforcement). |
| `enforce_yields_retry` | int | `0` | 0 – unlimited | no | Maximum self-correction attempts when `enforce_yields: true`. `0` fails on first contract violation. Each retry passes the previous output + validation errors as feedback so LLM/external/human/programmatic agents can self-correct. Honored by every agent type. |

### Yields Enforcement

`enforce_yields` and `enforce_yields_retry` work together to make `yields:` an enforceable contract on the producer side, without coupling agents to each other's shapes.

**Default behavior (`enforce_yields: false`)** — lenient mode, backwards-compatible:

- Missing yield keys → filled with type defaults (`""`, `0`, `[]`, `{}`, `false`).
- Type mismatches → kept verbatim, WARNING logged.
- `can_call` conditions evaluate on a known shape (no more silent skips on undefined keys).
- **Exception — dual-callback republishes get NO default-filling**: when
  a `dual` agent's downstream response is republished as the origin's
  output, the responder's payload doesn't owe the caller's contract, so
  missing keys (booleans included) stay missing and conditions on them
  fail closed (route skipped). Always explicitly yield every field a
  downstream condition reads.

**Strict mode (`enforce_yields: true`)** — for production-critical agents:

- On contract violation, the SDK fires a Manager-driven retry through `Manager.execute_state(...)`.
- Up to `enforce_yields_retry` attempts. Each retry sees the previous (wrong) output + validation errors as `_rerun_context`:
  - **LLM agents** — prompt builder appends a correction note.
  - **Human agents** — outbound payload exposes `_rerun_context`; inbox/channel UI surfaces what's needed.
  - **External connectors** — `data._rerun_context` is added to the workflow payload.
  - **Programmatic agents** — `input_data._rerun_context` is available alongside the (possibly Summarizer-corrected) inputs.
- After the retry budget is exhausted, fires `AGENT_ERROR` with `error_type="YieldContractFailure"` + `retry_exhausted=true`. Routes through `manager.escalation:` if configured.

**Example:**

```yaml
agents:
  client:
    agent_type: human
    human_interface: webhook
    yields:
      request_data: object
      decision: string
    enforce_yields: true        # strict
    enforce_yields_retry: 3     # 3 self-correction attempts before escalating
```

**Programmatic agents are retryable too** — the Summarizer can inspect the failure and produce a `corrected_input` (e.g. fix `"ORGANIZATION"` → `"Organization"`). The retry runs the same deterministic function with the corrected input and produces a different result. See [Manager — Rerun Flow](../core-concepts/manager#rerun) for the full path.

### Changing `agent_type`

You can change an agent's type via `PATCH /api/yaml/agents/{name}`. When `agent_type` changes, the ADK automatically **removes fields that don't belong to the new type**:

| Switching away from... | Fields removed |
|------------------------|----------------|
| `llm` | `model`, `prompt`, `temperature`, `max_tokens`, `max_completion_tokens`, `reasoning`, `thinking`, `reasoning_budget` (and legacy `thinking_budget`), `tools`, `tool_categories`, `context_parts`, `tool_choice`, `response_format` |
| `human` | `webhook_config`, `human_interface`, `human_timeout_seconds`, `channels`, `is_human_powered` |
| `external` | `framework`, `connector_config` |
| `programmatic` | `integration` |

This prevents stale configuration from the old type interfering with the new type's execution.

### `yields` and `inputs` Type Strings

Values can be a simple type string (flat field) or a nested object definition.

**Flat fields** — value is a type string:

| Type String | Description |
|-------------|-------------|
| `"string"` | Text value |
| `"number"` | Numeric value |
| `"boolean"` | True/false |
| `"list"` | Array/list |
| `"object"` | Dictionary/object (unstructured) |

**Nested fields** — value is an object with `type` and `fields`:

```yaml
inputs:
  # Flat fields
  name: string
  email: string

  # Nested object with defined sub-fields
  arguments:
    type: object
    fields:
      summary: string
      start_datetime: string
      end_datetime: string
      timezone: string

yields:
  # Flat
  status: string

  # Nested
  data:
    type: object
    fields:
      result: string
      metadata: object
```

When a field uses the nested format, the frontend renders individual sub-field editors instead of a single text input. This is useful for external framework integrations (Composio, Zapier, etc.) where the request body has a known structure.

### `wait_for` Expression Syntax

```yaml
# Simple list — all required (AND)
wait_for:
  - agent_a
  - agent_b

# Expression strings
wait_for: "agent_a AND agent_b"                            # Wait for both
wait_for: "agent_a OR agent_b"                             # Wait for first
wait_for: "agent_a AND agent_b?"                           # agent_b is optional (? suffix)
wait_for: "agent_a AND (agent_b OR agent_c)"               # Nested logic
wait_for: "agent_a AND (agent_b OR agent_c) AND agent_d?"  # Complex expression
```

### `can_call` Format

```yaml
# Simple
can_call:
  - agent: "next_agent"

# With condition
can_call:
  - agent: "next_agent"
  - agent: "conditional_agent"
    condition: "calling_agent_response.status == 'ready'"
```

### Narration Routing

`narration` is an agent-level field for routing hints you **can't express as conditions**. Conditions handle definitive routes ("if category is billing, call billing_agent"). Narration handles non-definitive routes ("if the customer sounds frustrated and mentions cancelling, maybe call retention_agent").

```yaml
agents:
  triage:
    yields:
      category: "string"
      urgency: "number"
    can_call:
      - agent: "billing_agent"
        condition: "category == 'billing'"
      - agent: "technical_agent"
        condition: "category == 'technical'"
    narration: >
      If the customer mentions cancelling their subscription, route to retention_agent.
      If the customer mentions a competitor by name, route to win_back_agent.
      If the customer asks about enterprise plans, route to sales_agent.
```

**How it works:**

1. Conditions are evaluated first by the control plane (AST, instant, deterministic)
2. Condition targets are dispatched immediately
3. The Summarizer — which already analyzes every agent output via LLM — sees the narration in its prompt context
4. The Summarizer's `next_agents` recommendation now reflects both condition-routed agents and narration-suggested agents
5. The Manager compares `next_agents` against what conditions already dispatched, and calls the difference

**Key rules:**

- Conditions are the authority — narration never overrides a condition result
- Narration targets are **additive** — they add to condition targets, never remove
- Narration can reference **any agent** in the mesh, not just those in `can_call`
- No narration = zero overhead (the Summarizer's prompt is unchanged)
- If the Manager is disabled, narrations are ignored

See **[Manager — Narration Routing](../core-concepts/manager#narration-routing)** and **[Message Routing](../messages/routing#narration-routing)** for the full flow.

### Knowledge Config

`knowledge` enables RAG-powered context injection from a vector database. The agent gets both pre-call injection (automatic) and a `query_knowledge` tool (on-demand) — same dual pattern as memory.

```yaml
agents:
  support_agent:
    knowledge:
      serviceName: "mongo_main"
      enabled: true
      groupName: "product_docs"
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `serviceName` | string | yes | — | Provider name (configured via Knowledge API, stored in Redis) |
| `enabled` | bool | no | `true` | Enable/disable knowledge for this agent |
| `groupName` | string | no | `null` | Query a specific group. Omit to query all groups. |

**Key points:**

- Provider connection details (connection strings, API keys, embedding model) are configured via the Knowledge API, not in YAML
- When enabled, both retrieval paths are active automatically — no mode flag
- `query_knowledge` tool is stripped from agents without knowledge enabled
- The Manager can also have knowledge for SOP awareness (configured under `manager.knowledge`)

See **[Manager — Narration Routing](../core-concepts/manager#narration-routing)** for how knowledge integrates with the Summarizer.

---

## LLM Agent Fields (`agent_type: "llm"`)

These fields are used when `agent_type` is `"llm"`. Ignored for other types.

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `model` | string | `"gpt-4o-mini"` | see [Model List](#model-list) below | LLM model name |
| `prompt` | string | `null` | any string (multiline supported) | System prompt |
| `temperature` | float | `0.1` | `0.0` – `2.0` | LLM temperature (creativity/randomness) |
| `max_tokens` | int | `800` | 1 – model max | Max output tokens (legacy models) |
| `max_completion_tokens` | int | `null` | 1 – model max | Max completion tokens (o1, gpt-5.x models) |
| `thinking` | bool | `false` | `true`, `false` | Enable SDK chain-of-thought scaffolding tools (works with any model). **Was `reasoning` pre-v2.2.24** |
| `reasoning` | bool | `false` | `true`, `false` | Enable provider-native extended thinking/reasoning (requires a reasoning-capable model — see below). **Was `thinking` pre-v2.2.24** |
| `reasoning_budget` | int | `null` | 1024 – 32768 (tokens) | Max native reasoning tokens. Provider defaults apply when omitted. `thinking_budget` is a deprecated alias (silently migrated) |
| `enable_prompt_caching` | bool | `false` | `true`, `false` | Enable provider-native prompt caching for cost reduction (see below) |
| `response_format` | dict | `null` | JSON Schema object | Structured output — forces LLM to respond with valid JSON matching this schema |
| `optimization_strategy` | string | `null` | `performance`, `cost`, `speed` | Per-agent model selection strategy |
| `context_parts` | dict | `null` | see below | Optional context parts |
| `tools` | list | `[]` | tool name strings | Available tools |
| `tool_choice` | string | `"auto"` | `auto`, `none`, or specific tool name | Tool selection strategy |
| `max_tool_calls_per_message` | int | `5` | 0 – 20 | Max tool calls per LLM message |
| `tool_call_timeout` | float | `30.0` | 0.1 – 300 (seconds) | Tool execution timeout |
| `allow_parallel_tool_calls` | bool | `true` | `true`, `false` | Allow parallel tool execution |
| `tool_categories` | list | `[]` | category name strings | Tool categories agent can access |

### `context_parts` Keys

Each key is injected as a separate system message with a bracketed label, in the order below. Custom keys are also supported — they receive an auto-generated label from their name (`MY_KEY` → `[MY KEY]`).

| Key | Label injected | Description |
|-----|---------------|-------------|
| `care` | `[EMPATHY & TONE]` | Warmth/empathy instructions — shapes how the agent expresses itself |
| `sentiment_analysis` | `[SENTIMENT ANALYSIS]` | Tone detection instructions — tells the agent to read user mood |
| `guardrails` | `[SAFETY GUARDRAILS]` | Safety and compliance rules — what the agent must never do |
| `flows` | `[FLOW INSTRUCTIONS]` | **Per-caller routing behaviour** — what the agent should do differently depending on who called it and where in the mesh it is |

Values are free text strings. All keys are optional — use any combination.

```yaml
context_parts:
  care: |
    Always respond with empathy. Acknowledge frustration before solving.
  guardrails: |
    Never share internal system details. No PII disclosure.
  flows: |
    When called from the entry point (no from_agent):
      - This is a new user. Greet warmly and gather requirements.
    When called from client (human agent):
      - The human has already responded. Don't re-greet. Summarise and proceed.
    When called from scheduler_agent:
      - This is a scheduled run. Skip greeting, produce a structured summary.
```

### Model List

> **Canonical source:** the live model catalog is
> `leafmesh.llm.adaptive_executor.MODEL_DEFAULT_BENCHMARKS` (42 models,
> incl. `claude-fable-5`), served at **`GET /api/registry`** (per-provider
> `models` lists, plus connectors/integrations/channels). When in doubt,
> hit the endpoint — don't guess. A model id that matches **no known
> provider prefix and no catalog entry warns at load and silently routes
> to the `local` provider** (it then fails at the first LLM call unless
> you really run a local server) — typos like `gpt4o-mini` are the
> classic case.

**OpenAI:**
- `gpt-4o-mini`, `gpt-4o`
- `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`
- `gpt-5.1`, `gpt-5.2`, `gpt-5.3`, `gpt-5.5` (v2.3.x additions)
- `o1`, `o1-mini`, `o3`, `o3-mini`, `o4-mini`

**Anthropic:**
- `claude-opus-4-6`, `claude-sonnet-4-6`
- `claude-haiku-4-5-20251001`
- `claude-opus-4-8` (v2.3.x — supports `effort: "low" | "medium" | "high"` parameter)

**Google:**
- `gemini-2.0-flash`, `gemini-2.5-pro`
- `gemini-3` (v2.3.x — GA)

**DeepSeek:**
- `deepseek-chat`, `deepseek-reasoner`

**xAI Grok (v2.3.x — native provider):**
- `grok-2`, `grok-3`, `grok-beta`
- Requires `XAI_API_KEY` env var
- Supports tool calling; native chat-completions endpoint (no Bedrock routing)

**Mistral (v2.3.x — native provider):**
- `mistral-large`, `mistral-small`, `mistral-medium`
- `mixtral-8x22b`, `mixtral-8x7b`
- `codestral-latest`
- Requires `MISTRAL_API_KEY` env var
- Native chat + tools API (no Bedrock routing)

**AWS Bedrock:**
- Any Bedrock model ID (e.g. `anthropic.claude-3-sonnet-20240229-v1:0`, `amazon.titan-text-premier-v1:0`)
- Requires `mesh.bedrock` config

**Google Vertex AI:**
- Any Vertex model ID (e.g. `gemini-1.5-pro`)
- Requires `mesh.vertex` config

**Azure Foundry:**
- Any Azure deployment name
- Requires `mesh.foundry` config

**Local Models (vLLM, SGLang, Ollama, llama.cpp, etc.):**
- Any model name supported by your local server
- Requires `mesh.local` config (or `LOCAL_MODEL_ENDPOINT` env var)
- See [LocalModelConfig](#localmodelconfig) for server setup

### `reasoning` vs `thinking`

Two **separate** features. **v2.2.24 SWAPPED these keys** — pre-v2.2.24
configs (and older templates) have them backwards. Current meaning:

| Feature | `thinking: true` | `reasoning: true` |
|---------|-------------------|-------------------|
| **What it does** | SDK injects chain-of-thought scaffolding tools (`chain_of_thought` + `metacognitive_reflection`) the LLM calls in-loop | Enables provider-native extended thinking/reasoning via the provider API |
| **Works with** | Any model (tool injection) | Only reasoning-capable models: OpenAI o-series / gpt-5.x, Claude 3.7 / 4.x / 5.x, Gemini 2.5+ / 3.x, deepseek-reasoner, Grok |
| **Token cost** | Tool call overhead — needs ≥ 1500 `max_tokens` headroom (warns below) | Dedicated reasoning tokens (billed as output); cap via `reasoning_budget` |
| **Quality** | Good for structured multi-field revision | Best quality — model's internal reasoning |

**Which to use when:** `thinking: true` for structured multi-step work
on any model (including gpt-4o-mini). `reasoning: true` ONLY on a
reasoning-capable model — setting it on e.g. `gpt-4o-mini` has no
native-reasoning surface and **warns at boot** (the provider no-ops or
rejects it). You can use both together on a reasoning-capable model.

### Native Reasoning (`reasoning: true`) — Provider Support

| Provider | Model Requirement | Behavior |
|----------|------------------|----------|
| **Anthropic** | Claude 3.7 / Sonnet 4.x / Opus 4.x–4.7 / Haiku 4.5+ | Extended thinking with `budget_tokens` (Opus 4.8+ uses `effort` instead — manual thinking is rejected) |
| **OpenAI** | o-series, gpt-5.x | `reasoning_effort` parameter |
| **Google** | Gemini 2.5+ (`thinkingBudget`), Gemini 3.x (`thinkingLevel`) | `thinkingConfig` |
| **DeepSeek** | deepseek-reasoner | Native chain-of-thought (`reasoning_content`) |
| **xAI Grok** | Grok reasoning models | `reasoning_effort` parameter |
| **Bedrock** | Claude models on Bedrock | `additionalModelRequestFields.thinking` |
| **Vertex** | Claude + Gemini on Vertex | Both thinking APIs supported |
| **Foundry** | Azure o-series models | `reasoning_effort` parameter |
| **Local** | Depends on model/server | Passthrough if server supports it |

### Prompt Caching — Provider Support

| Provider | How it works | Savings |
|----------|-------------|---------|
| **Anthropic** | `cache_control: ephemeral` on system prompt + tools | ~90% on cached reads |
| **Bedrock** | `promptCaching` parameter | ~90% on cached reads |
| **Vertex (Claude)** | `cache_control: ephemeral` on system prompt | ~90% on cached reads |
| **OpenAI** | Automatic — no config needed (stats in response) | ~50% on cached |
| **Google** | Context caching API (requires separate setup) | Varies |

### `response_format` — Structured Output

Forces the LLM to respond with valid JSON matching a JSON Schema. Supported across all providers — each provider translates the schema to its native structured output API.

```yaml
agents:
  data_extractor:
    agent_type: llm
    model: gpt-4o
    prompt: "Extract structured data from the user's message."
    response_format:
      type: json_schema
      json_schema:
        name: extracted_data
        strict: true
        schema:
          type: object
          properties:
            name:
              type: string
            email:
              type: string
            priority:
              type: string
              enum: [low, medium, high]
          required: [name, email, priority]
          additionalProperties: false
```

| Provider | Native API used |
|----------|----------------|
| **OpenAI** | `response_format` parameter (structured outputs) |
| **Anthropic** | Tool-based JSON extraction with schema |
| **Google** | `response_schema` in generation config |
| **DeepSeek** | `response_format` parameter |
| **Bedrock** | Schema injected into system prompt |
| **Foundry** | `response_format` parameter |
| **Local** | `response_format` passthrough |

### Example

```yaml
agents:
  analyst:
    agent_type: llm
    model: claude-sonnet-4-6
    reasoning: true             # provider-NATIVE extended thinking (claude-4 family supports it)
    reasoning_budget: 8192      # max 8K native reasoning tokens
    thinking: true              # also inject SDK chain-of-thought scaffolding tools
    enable_prompt_caching: true # cache system prompt + tools
    prompt: |
      You are a data analyst. Analyze the provided data thoroughly.
```

---

## Human Agent Fields (`agent_type: "human"`)

These fields are used when `agent_type` is `"human"`. `is_human_powered` is auto-set to `true`.

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `is_human_powered` | bool | `false` | `true`, `false` | Auto-synced to `true` when agent_type="human" |
| `human_interface` | string | `"api"` | `default`, `api`, `webhook`, `custom` | How human receives/submits input (see below) |
| `human_timeout_seconds` | int | `300` | 1 – 3600 (seconds) | Human response timeout |
| `human_context_template` | string | `null` | any string | Template for presenting context to human |
| `human_prompt_template` | string | `null` | any string | Template for human prompts |
| `fallback_on_timeout` | bool | `true` | `true`, `false` | Use fallback response when human doesn't respond |
| `fallback_response` | dict | `null` | arbitrary JSON | Default response on human timeout |
| `require_human_confirmation` | bool | `false` | `true`, `false` | Require approval before proceeding |
| `human_escalation_triggers` | list | `[]` | free text strings | Conditions triggering human escalation |
| `operator_ids` | list | `[]` | list of strings (email or ID) | Operators who can see this agent's HITL requests. Empty = broadcast (all operators see it). |
| `webhook_config` | object | `null` | see [WebhookConfig](#webhookconfig) | Webhook settings (required for `webhook` interface) |
| `channels` | dict | `{}` | see [ChannelConfig](#channelconfig) | Native channel adapters (Slack, Telegram, etc.) |

### `human_interface` — Interface Types

| Value | Description | How it works |
|-------|-------------|-------------|
| `default` | **ADK-Frontend HITL Inbox** (recommended) | Writes request to Redis, emits stream event. ADK-Frontend renders an inbox with conversation thread. Human replies via the UI. Supports parallel requests per session. |
| `webhook` | **External webhook** | POSTs request to `webhook_config.outbound_url`. Human responds via inbound webhook endpoint. Also supports native channel adapters (Slack, Telegram, etc.). |
| `api` | **Python callback** | Calls a Python handler registered via `sdk.register_human_handler()`. No outbound HTTP. Used for custom integrations and testing. |
| `custom` | **Custom handler** | Same as `api` — uses the registered `human_interface_handler` callback. |

> **Note:** `default` is only available on the LeafMesh hosted platform. For self-hosted deployments, use `webhook` with your own `outbound_url`, or `api` with a Python callback.

### Example — Default (ADK-Frontend Inbox)

```yaml
agents:
  support_human:
    agent_type: human
    human_interface: default          # ADK-Frontend inbox
    human_timeout_seconds: 300
    yields:
      resolution: string
      action_taken: string
```

### Example — Webhook with Channel Adapter

```yaml
agents:
  support_human:
    agent_type: human
    human_interface: webhook
    human_timeout_seconds: 600
    webhook_config:
      outbound_url: "https://my-app.com/api/human-requests"
    channels:
      slack:
        bot_token: "${SLACK_BOT_TOKEN:}"
        signing_secret: "${SLACK_SIGNING_SECRET:}"
        post_channel: "C123456"
```

### Two Scenarios for Human Agent Sessions

Human agents support two interaction patterns via the same webhook endpoint:

**Scenario 1 — Resume (session_id present):** When a POST to `/webhook/{entry_point}` includes a `session_id` that matches a pending HITL request, the ADK resumes that session. The operator's response is routed via `can_call` to the next agent.

**Scenario 2 — New (no session_id or not found):** When a POST has no `session_id` or the session has no pending expectation, the ADK creates a new workflow. If the human agent has no upstream caller, the operator's message is immediately routed via `can_call` — no HITL pending step is created.

---

## External Agent Fields (`agent_type: "external"`)

These fields are used when `agent_type` is `"external"`.

| Field | Type | Default | Accepted Values | Required | Description |
|-------|------|---------|-----------------|----------|-------------|
| `framework` | string | `null` | `crewai`, `langgraph`, `autogen`, `a2a`, `mcp`, `zapier`, `composio`, `n8n`, `hermes`, `lyzr`, `writer`, `dify`, `flowise`, `voiceflow`, `cognigy`, `vellum`, `stackai`, `agentforce`, `watsonx`, `relevance`, `wordware`, `claude_agent`, `openai_agents`, `custom` | **yes** | External framework name |
| `connector_config` | dict | `{}` | framework-specific key-values | no | Connection configuration — passed as `**kwargs` to the connector |

> **One agent = one action/workflow.** Each agent targets one specific endpoint, graph, tool, or action. Create multiple agents with different `connector_config` values to call different workflows.
>
> All `connector_config` fields can also be overridden per-call via `request.connector_config` at runtime.

### Common connector_config fields (all frameworks)

These fields are available on **every** connector type:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `"sync"` | Execution mode: `"sync"` (wait for HTTP response) or `"callback"` (fire request, wait for external system to POST back) |
| `callback_timeout` | float | `120.0` | Seconds to wait for a callback response before timing out (only used when `mode: "callback"`) |

#### Sync vs Callback Mode

**Sync mode** (default): The connector POSTs to the external system and holds the HTTP connection open until the response arrives. This works when the external system returns the actual result in the same HTTP response.

**Callback mode**: The connector POSTs to the external system with a `_leafmesh_callback_url` and `_leafmesh_session_id` injected into the payload. The connector then blocks internally until the external system POSTs the result back to `/callback/{agent_name}`. Use this when:
- The external workflow takes longer than the HTTP timeout
- The external system uses "fire and forget" (e.g., n8n's "Respond Immediately" mode)
- You need the external system to process asynchronously and deliver results later

**How external systems use callbacks:**

The LeafMesh connector injects these fields into the outbound payload:
- `_leafmesh_callback_url` — the URL to POST the result back to
- `_leafmesh_session_id` — the session ID to include in the callback

The external system should POST to `_leafmesh_callback_url` with a JSON body containing:
```json
{
  "session_id": "<the _leafmesh_session_id value>",
  "result": { ... }
}
```

### connector_config fields per framework

#### crewai

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `endpoint` | string | `""` | **yes** | `CREWAI_ENDPOINT` | HTTP endpoint for deployed CrewAI crew |
| `api_key` | string | `""` | no | `CREWAI_API_KEY` | Bearer Token for authentication |
| `user_api_key` | string | `""` | no | `CREWAI_USER_API_KEY` | User Bearer Token (preferred over `api_key` when both are set) |
| `poll_interval` | float | `2.0` | no | — | Seconds between status polls |
| `max_poll_seconds` | float | `300.0` | no | — | Max total polling time (seconds) |
| `http_timeout` | float | `30.0` | no | — | HTTP request timeout (seconds) |

#### langgraph

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `endpoint` | string | `""` | **yes** | `LANGGRAPH_ENDPOINT`, `LANGCHAIN_ENDPOINT` | LangGraph Platform deployment URL |
| `api_key` | string | `""` | no | `LANGCHAIN_API_KEY`, `LANGGRAPH_API_KEY` | API key |
| `graph_id` | string | `"agent"` | no | — | **Which graph to run** — this is the workflow selector |
| `poll_interval` | float | `1.0` | no | — | Seconds between status polls |
| `max_poll_seconds` | float | `300.0` | no | — | Max total polling time (seconds) |
| `http_timeout` | float | `30.0` | no | — | HTTP request timeout (seconds) |

#### autogen

Connects to an external AutoGen Studio or custom AutoGen API service via HTTP.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `endpoint` | string | `""` | **yes** | `AUTOGEN_ENDPOINT` | AutoGen service base URL (e.g. `http://localhost:8081`) |
| `api_key` | string | `""` | no | `AUTOGEN_API_KEY` | Bearer token for authentication |
| `workflow_id` | string | `""` | no | — | Workflow/agent ID to execute on the AutoGen service |
| `timeout` | float | `120.0` | no | — | HTTP request timeout (seconds) |
| `poll_interval` | float | `2.0` | no | — | Seconds between status poll requests |
| `max_poll_seconds` | float | `300.0` | no | — | Max total polling time (seconds) |

#### a2a

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `url` | string | `""` | **yes** | `A2A_AGENT_URL` | A2A-compatible agent server base URL |
| `auth_token` | string | `""` | no | `A2A_AUTH_TOKEN` | Bearer token for authentication |
| `auth_scheme` | string | `"Bearer"` | no | — | Authorization header scheme |
| `poll_interval` | float | `2.0` | no | — | Seconds between task status polls |
| `max_poll_seconds` | float | `300.0` | no | — | Max total polling time (seconds) |
| `http_timeout` | float | `30.0` | no | — | HTTP request timeout (seconds) |

#### mcp

MCP supports two transport modes. `tool_name` is always required.

**Common fields (both transports):**

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `tool_name` | string | `""` | **yes** | — | **Which MCP tool to call** — the workflow selector |
| `transport` | string | `"stdio"` | no | — | Transport mode: `"stdio"` or `"http"` |
| `timeout` | float | `60.0` | no | — | Request timeout (seconds) |

**stdio transport fields:**

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `command` | string | `""` | **yes** (stdio) | Executable to launch (e.g. `"npx"`) |
| `args` | list | `[]` | no | Command arguments (e.g. `["-y", "@mcp/server-npm"]`) |
| `env` | dict | `null` | no | Environment variables for the subprocess |

**http transport fields:**

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `url` | string | `""` | **yes** (http) | MCP server HTTP/SSE endpoint |
| `auth_token` | string | `""` | no | Bearer token |

#### zapier

Tool name is built as `{connection}_{action}` (e.g. `google_sheets_create_row`).

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `connection` | string | `""` | yes* | — | Zapier app name (e.g. `"google_sheets"`, `"slack"`, `"gmail"`) |
| `action` | string | `""` | yes* | — | Action name (e.g. `"create_row"`, `"send_message"`) |
| `mcp_key` | string | `""` | yes† | `ZAPIER_MCP_KEY` | Zapier MCP key — used first if `prefer_mcp=true` |
| `api_key` | string | `""` | yes† | `ZAPIER_API_KEY` | Zapier REST API key — used as fallback |
| `prefer_mcp` | bool | `true` | no | — | Try MCP path first; fall back to REST on failure |
| `instructions` | string | `""` | no | — | Optional natural language instructions (REST path only) |
| `timeout` | float | `60.0` | no | — | HTTP request timeout (seconds) |

*At least one of `connection` or `action` required for the tool name. †At least one of `mcp_key` or `api_key` required.

#### composio

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `action` | string | `""` | **yes** | — | **Composio action enum** (e.g. `"GITHUB_STAR_A_REPOSITORY"`) — the workflow selector |
| `entity_id` | string | `"default"` | no | `COMPOSIO_ENTITY_ID` | User/entity context for managed auth |
| `api_key` | string | `""` | no | `COMPOSIO_API_KEY` | Composio API key |
| `timeout` | float | `60.0` | no | — | Execution timeout (seconds) |

#### n8n

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `webhook_url` | string | `""` | **yes** | `N8N_WEBHOOK_URL` | Full webhook trigger URL — **one URL per n8n workflow** |
| `auth_token` | string | `""` | no | `N8N_AUTH_TOKEN` | Bearer token |
| `timeout` | float | `60.0` | no | — | HTTP request timeout (seconds, sync mode only) |

**n8n webhook URL types:**
- **Production:** `https://your-instance.app.n8n.cloud/webhook/<id>` — works when workflow is **activated** (toggle ON)
- **Test:** `https://your-instance.app.n8n.cloud/webhook-test/<id>` — only works while n8n editor has "Listen for Test Event" active (one-shot, for development only)

**n8n + callback mode:**

When `mode: "callback"`, the n8n workflow should:
1. Start with a Webhook trigger node (receives the payload including `_leafmesh_callback_url`)
2. Configure the Webhook node to "Respond Immediately" (optional — sync mode works too)
3. Process the workflow
4. End with an HTTP Request node that POSTs back to `{{ $json._leafmesh_callback_url }}` with body:
   ```json
   { "session_id": "{{ $json._leafmesh_session_id }}", "result": { ... } }
   ```

#### hermes

Calls a running Nous Research Hermes Agent API server (OpenAI-compatible); returns the agent's output inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `endpoint` | string | `"http://127.0.0.1:8642"` | no | `HERMES_ENDPOINT` | Hermes API server base URL |
| `api_key` | string | `""` | no | `HERMES_API_SERVER_KEY`, `API_SERVER_KEY` | Bearer token (the host-side `API_SERVER_KEY`) |
| `model` | string | `"hermes-agent"` | no | — | Model name sent in the request |
| `api_mode` | string | `"chat"` | no | — | API surface: `"chat"` (`/v1/chat/completions`) or `"responses"` (`/v1/responses`, server-side multi-turn memory) |
| `system_prompt` | string | `""` | no | — | Optional system message prepended to the call |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### lyzr

Calls a Lyzr Agent Studio hosted agent through its synchronous inference API; returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `agent_id` | string | `""` | **yes** | `LYZR_AGENT_ID` | **Which Studio agent to invoke** — the workflow selector |
| `api_key` | string | `""` | **yes** | `LYZR_API_KEY` | Header API key (`x-api-key`) from the agent's "Agent API" panel |
| `endpoint` | string | `"https://agent-prod.studio.lyzr.ai"` | no | `LYZR_ENDPOINT` | Lyzr inference base URL |
| `user_id` | string | `"leafmesh"` | no | `LYZR_USER_ID` | Who Lyzr attributes the run to |
| `api_mode` | string | `"chat"` | no | — | API surface: `"chat"` or `"stream"` (streamed chunks assembled into one answer) |
| `system_prompt_variables` | dict | `{}` | no | — | Lyzr system-prompt template variables |
| `filter_variables` | dict | `{}` | no | — | Lyzr filter/routing variables |
| `features` | list | `[]` | no | — | Lyzr feature toggles passed through to the agent |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### writer

Calls Writer's (Palmyra) OpenAI-compatible chat/agents API; returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | `WRITER_API_KEY` | Bearer API key |
| `endpoint` | string | `"https://api.writer.com"` | no | `WRITER_ENDPOINT` | Writer API base URL |
| `model` | string | `"palmyra-x5"` | no | — | Writer model to call |
| `system_prompt` | string | `""` | no | — | Optional system message prepended to the call |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### dify

Calls a Dify hosted chat/agent app through its blocking chat endpoint; returns the full reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | `DIFY_API_KEY` | Per-app API key (NOT the account key) |
| `endpoint` | string | `"https://api.dify.ai/v1"` | no | `DIFY_ENDPOINT` | Dify API base URL |
| `user_id` | string | `"leafmesh"` | no | `DIFY_USER_ID` | End-user identifier Dify attributes the run to |
| `app_mode` | string | `"chat"` | no | — | **Which Dify app surface to call**: `"chat"` (chat-messages) or `"completion"` (completion-messages) |
| `input_key` | string | `"query"` | no | — | For completion apps, the input variable name the message maps to |
| `inputs` | dict | `{}` | no | — | Extra Dify app input variables |
| `conversation_id` | string | `""` | no | — | Dify's own conversation id to continue a chat (NOT the mesh session_id) |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### flowise

Calls a Flowise chatflow/agentflow prediction endpoint; returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `chatflow_id` | string | `""` | **yes** | `FLOWISE_CHATFLOW_ID` | **Which chatflow/agentflow to run** — the workflow selector |
| `endpoint` | string | `"http://localhost:3000"` | no | `FLOWISE_ENDPOINT` | Flowise instance base URL |
| `api_key` | string | `""` | no | `FLOWISE_API_KEY` | Optional bearer key (flows are public unless a key is assigned) |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### voiceflow

Calls a Voiceflow Dialog Manager agent (interact endpoint); returns the assistant trace text inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | `VOICEFLOW_API_KEY` | Dialog Manager API key (sent in `Authorization`, no Bearer prefix) |
| `endpoint` | string | `"https://general-runtime.voiceflow.com"` | no | `VOICEFLOW_ENDPOINT` | Voiceflow runtime base URL |
| `version_id` | string | `"production"` | no | `VOICEFLOW_VERSION_ID` | `versionID` header — which published version to run |
| `http_timeout` | float | `120.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### cognigy

Calls a Cognigy.AI REST/Webhook Endpoint synchronously; returns the AI reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `endpoint` | string | `""` | **yes** | `COGNIGY_ENDPOINT` | **The per-bot REST/Webhook Endpoint URL** — the workflow selector (each bot is its own URL) |
| `user_id` | string | `"leafmesh"` | no | `COGNIGY_USER_ID` | `userId` sent to Cognigy |
| `basic_user` | string | `""` | no | `COGNIGY_BASIC_USER` | Optional HTTP Basic username configured on the Endpoint |
| `basic_password` | string | `""` | no | `COGNIGY_BASIC_PASSWORD` | Optional HTTP Basic password configured on the Endpoint |
| `http_timeout` | float | `120.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### vellum

Calls a Vellum workflow deployment through its synchronous execute endpoint; returns the selected output inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | `VELLUM_API_KEY` | API key (sent in `X-API-KEY`, NOT Bearer) |
| `workflow_deployment_name` | string | `""` | yes* | `VELLUM_WORKFLOW_DEPLOYMENT_NAME` | **Which workflow deployment to run** — the workflow selector |
| `workflow_deployment_id` | string | `""` | yes* | — | Alternative to `workflow_deployment_name` |
| `endpoint` | string | `"https://predict.vellum.ai"` | no | `VELLUM_ENDPOINT` | Vellum API base URL |
| `release_tag` | string | `""` | no | — | Optional release tag to pin the deployment version |
| `input_name` | string | `"message"` | no | — | Which workflow input the mesh message maps to |
| `output_name` | string | `""` | no | — | Which named output becomes the reply (defaults to the first output) |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

*Either `workflow_deployment_name` or `workflow_deployment_id` is required.

#### stackai

Calls a Stack AI exported flow through its synchronous run endpoint; returns the selected output inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | `STACKAI_API_KEY` | Bearer API key |
| `org_id` | string | `""` | **yes** | `STACKAI_ORG_ID` | Stack AI organization id (in the run URL) |
| `flow_id` | string | `""` | **yes** | `STACKAI_FLOW_ID` | **Which flow to run** — the workflow selector (in the run URL) |
| `endpoint` | string | `"https://stack-inference.com"` | no | `STACKAI_ENDPOINT` | Stack AI inference base URL |
| `input_key` | string | `"in-0"` | no | — | Which flow input key the mesh message maps to |
| `output_key` | string | `""` | no | — | Which output field becomes the reply (defaults to surfacing the whole outputs object) |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### agentforce

Calls a Salesforce Agentforce agent via the Agent API (OAuth token → open session → send message); returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `agent_id` | string | `""` | **yes** | `AGENTFORCE_AGENT_ID` | **Which Agentforce agent to invoke** — the workflow selector |
| `domain_url` | string | `""` | **yes** | `AGENTFORCE_DOMAIN_URL` | Org My Domain URL (e.g. `https://mycompany.my.salesforce.com`) — used for OAuth |
| `client_id` | string | `""` | **yes** | `AGENTFORCE_CLIENT_ID` | Connected/External Client App client id (client-credentials flow) |
| `client_secret` | string | `""` | **yes** | `AGENTFORCE_CLIENT_SECRET` | Connected/External Client App client secret |
| `api_base` | string | `"https://api.salesforce.com"` | no | `AGENTFORCE_API_BASE` | Agent API base URL |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### watsonx

Calls an IBM watsonx Orchestrate agent through its OpenAI-compatible chat endpoint (IBM Cloud key → IAM bearer token, or a ready bearer); returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `service_url` | string | `""` | **yes** | `WATSONX_SERVICE_URL` | Orchestrate service instance URL (per-tenant) |
| `api_key` | string | `""` | yes* | `WATSONX_API_KEY` | IBM Cloud API key (exchanged for an IAM bearer token) |
| `bearer_token` | string | `""` | yes* | `WATSONX_BEARER_TOKEN` | A ready IAM bearer token (skips the key exchange) |
| `agent_id` | string | `""` | yes† | `WATSONX_AGENT_ID` | **Which Orchestrate agent to invoke** — the workflow selector (goes in the request path) |
| `iam_url` | string | `"https://iam.cloud.ibm.com/identity/token"` | no | — | IBM IAM token endpoint |
| `chat_path` | string | `""` | no | — | Full override of the path after `service_url` (built from `agent_id` when unset) |
| `model` | string | `""` | no | — | Optional model name sent in the payload |
| `system_prompt` | string | `""` | no | — | Optional system message prepended to the call |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

*One of `api_key` or `bearer_token` is required. †`agent_id` is required unless an explicit `chat_path` is given.

#### relevance

Calls a Relevance AI agent via its async trigger + poll API; returns the agent's answer once the run completes.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `project_id` | string | `""` | **yes** | `RELEVANCE_PROJECT_ID` | Relevance project id (half of the `{project_id}:{api_key}` auth token) |
| `api_key` | string | `""` | **yes** | `RELEVANCE_API_KEY` | Relevance API key |
| `agent_id` | string | `""` | **yes** | `RELEVANCE_AGENT_ID` | **Which agent to trigger** — the workflow selector |
| `region` | string | `""` | no | `RELEVANCE_REGION` | Region used to build the base URL (`https://api-{region}.stack.tryrelevance.com`) |
| `base_url` | string | `""` | no | `RELEVANCE_BASE_URL` | Explicit base URL (overrides `region`) |
| `poll_interval` | float | `3.0` | no | — | Seconds between async polls |
| `max_poll_seconds` | float | `120.0` | no | — | Max total polling time (seconds) |
| `http_timeout` | float | `60.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### wordware

Calls a Wordware released app (NDJSON streaming run); the connector assembles the streamed output into one final answer.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | `WORDWARE_API_KEY` | Bearer API key |
| `app_id` | string | `""` | **yes** | `WORDWARE_APP_ID` | **Which released app to run** — the workflow selector |
| `endpoint` | string | `"https://app.wordware.ai"` | no | `WORDWARE_ENDPOINT` | Wordware API base URL |
| `version` | string | `"^1.0"` | no | — | App version constraint sent with the run |
| `input_key` | string | `"message"` | no | — | Which app input the mesh message maps to |
| `inputs` | dict | `{}` | no | — | Extra app input variables |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

> **In-process agent SDKs (frameworks, not HTTP services).** The two connectors below run an agent SDK locally inside the LeafMesh process — there is no hosted endpoint to POST to. (Raw Claude/OpenAI model calls live in the LLM provider layer, not here.)

#### claude_agent

Runs an agent built on the Claude Agent SDK (`claude-agent-sdk`) in-process via `query()`; returns the final result. Requires `pip install claude-agent-sdk` and the Claude Code CLI on the host.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | no | `ANTHROPIC_API_KEY` | Anthropic API key (passed to the SDK subprocess via options.env) |
| `model` | string | `""` | no | — | Model the agent runs on (SDK default when empty) |
| `system_prompt` | string | `""` | no | — | System prompt for the agent |
| `max_turns` | int | `null` | no | — | Max agent turns (SDK default when unset) |
| `allowed_tools` | list | `null` | no | — | Tools the agent is allowed to use |
| `permission_mode` | string | `""` | no | — | SDK permission mode for tool use |
| `cwd` | string | `""` | no | — | Working directory for the agent run |
| `timeout` | float | `600.0` | no | — | Max run time (seconds; also accepts `http_timeout`) |

#### openai_agents

Runs an agent built on the OpenAI Agents SDK (`openai-agents`) in-process via `Runner.run()`; returns `final_output`. Requires `pip install openai-agents`.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | no | `OPENAI_API_KEY` | OpenAI API key (per-run model provider; falls back to env when empty) |
| `name` | string | `"LeafMesh Agent"` | no | — | Agent name |
| `instructions` | string | `""` | no | — | Agent instructions (the system prompt) |
| `model` | string | `""` | no | — | Model the agent runs on (SDK default when empty) |
| `max_turns` | int | `null` | no | — | Max agent turns (SDK default when unset) |
| `timeout` | float | `600.0` | no | — | Max run time (seconds; also accepts `http_timeout`) |

---

## Programmatic Agent Fields (`agent_type: "programmatic"`)

These fields are used when `agent_type` is `"programmatic"`.

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `integration` | string | `null` | `zapier`, `composio`, `n8n`, `mcp` | Integration connector (optional) |
| `connector_config` | dict | `{}` | integration-specific key-values | Same fields as the matching external framework connector — see tables above |

**Validation rule:** `integration` is only valid when `agent_type` is `"programmatic"`.

When `integration` is set, `connector_config` is passed as `**kwargs` to the connector's `__init__`. Use the same fields as the matching framework in the tables above (zapier → zapier fields, mcp → mcp fields, etc.).

The common fields (`mode`, `callback_timeout`) are also available here — programmatic agents with connectors support the same sync/callback modes as external agents.

---

## WebhookConfig

Used inside `webhook_config` for human agents.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `outbound_url` | string | `null` | URL to POST responses to external system |
| `outbound_headers` | dict | `{}` | Headers for outbound webhook (key-value string pairs) |
| `outbound_timeout` | int | `30` | Timeout for outbound calls (seconds) |
| `inbound_endpoint` | string | `null` | Endpoint path for inbound responses (e.g. `"/webhook/human_contact"`). If not set, derived from entry points. |
| `inbound_auth_token` | string | `null` | Auth token for validating inbound requests |
| `response_mapping` | dict | `{}` | Field mapping for webhook response transformation |
| `max_retries` | int | `3` | Max retry attempts for failed outbound webhooks |
| `retry_delay` | int | `5` | Delay between retries (seconds) |

---

## ChannelConfig

Used inside `channels` dict for human agents. Keys are provider names.

### Supported Provider Keys

| Key | Provider |
|-----|----------|
| `slack` | Slack Bot API |
| `telegram` | Telegram Bot API |
| `discord` | Discord Bot API |
| `whatsapp` | WhatsApp Business API (Meta Cloud API) |
| `teams` | Microsoft Teams Bot Framework |
| `email` | SMTP outbound + IMAP inbound (BRD-020, v2.3.x). Optional provider-API mode for Mailgun / SendGrid / Postmark. Talon reply-stripping built in. Threading via `Message-ID` / `In-Reply-To` / `References` headers. See per-provider semantics below. |

### Fields Per Channel

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `bot_token` | string | `null` | Bot/API token for the provider (see per-provider notes below) |
| `signing_secret` | string | `null` | Request verification secret (see per-provider notes below) |
| `listen_channels` | list | `[]` | Channel/chat IDs to accept inbound messages from (empty = all) |
| `post_channel` | string | `null` | Default channel/chat ID for outbound messages (see per-provider notes below) |
| `verify_token` | string | `null` | Webhook verification token — **WhatsApp only** (`hub.verify_token`) |

**Note:** `ChannelConfig` allows extra fields (`extra="allow"`) for any provider-specific config.

### Per-Provider Field Semantics

| Provider | `bot_token` | `signing_secret` | `post_channel` | `verify_token` |
|----------|------------|------------------|----------------|----------------|
| `slack` | Bot OAuth token (`xoxb-…`) | Slack signing secret (HMAC-SHA256) | Channel ID (e.g. `C123456`) | — |
| `telegram` | Bot token from @BotFather | Secret token set when registering webhook | Chat ID | — |
| `discord` | Bot token (without `Bot ` prefix) | App public key (Ed25519 — requires `pynacl`) | Channel ID | — |
| `whatsapp` | Meta Graph API access token | Meta app secret (HMAC-SHA256) | Phone number ID | `hub.verify_token` for webhook registration |
| `teams` | Bot Framework App ID | Bot Framework App password | Conversation ID | — |
| `email` | — (uses `smtp_*` / `imap_*` fields, not `bot_token`) | — (use `dkim_private_key` for outbound DKIM) | `from_address` is the canonical outbound sender | — |

### Email-channel-specific fields (v2.3.x — BRD-020)

| Field | Type | Purpose |
|---|---|---|
| `smtp_host` / `smtp_port` / `smtp_user` / `smtp_password` | str / int / str / str | Outbound SMTP transport. Use `aiosmtplib` (non-blocking) |
| `from_address` | str | Canonical outbound sender (e.g. `support@example.com`) |
| `dkim_private_key` | str | Optional — DKIM signing for outbound mail |
| `imap_host` / `imap_port` / `imap_user` / `imap_password` | str / int / str / str | Inbound IMAP. Polled (IMAP isn't push) |
| `imap_folder` | str | Inbox folder to watch (default `INBOX`) |
| `provider` | str | Optional — `mailgun` / `sendgrid` / `postmark` to use provider API instead of raw SMTP |
| `provider_api_key` | str | API key for the chosen provider |

### Inbound Route Registered Per Provider

| Provider | Route |
|----------|-------|
| `slack` | `POST /channels/slack/{agent_name}/events` |
| `telegram` | `POST /channels/telegram/{agent_name}/webhook` |
| `discord` | `POST /channels/discord/{agent_name}/interactions` |
| `whatsapp` | `GET /channels/whatsapp/{agent_name}/webhook` (verification) + `POST` (messages) |
| `teams` | `POST /channels/teams/{agent_name}/messages` |
| `email` | No HTTP route — inbound is polled via IMAP; outbound bounce/complaint webhooks may be configured separately at the provider |

### Example

```yaml
channels:
  slack:
    bot_token: "${SLACK_BOT_TOKEN:}"
    signing_secret: "${SLACK_SIGNING_SECRET:}"
    listen_channels: ["C123456", "C789012"]
    post_channel: "C123456"
    operators:                                    # v2.2.44+ per-operator routing
      alice: "U0ALICE"                            # Slack user ID (DM)
      bob:   "U0BOB"

  telegram:
    bot_token: "${TELEGRAM_BOT_TOKEN:}"
    signing_secret: "${TELEGRAM_SECRET_TOKEN:}"   # optional
    listen_channels: []                            # empty = all chats
    post_channel: ""
    operators:
      alice: "12345678"                           # Telegram chat_id

  discord:
    bot_token: "${DISCORD_BOT_TOKEN:}"
    signing_secret: "${DISCORD_PUBLIC_KEY:}"       # Ed25519 public key
    listen_channels: ["987654321098765432"]
    post_channel: "987654321098765432"

  whatsapp:
    bot_token: "${WHATSAPP_ACCESS_TOKEN:}"
    signing_secret: "${META_APP_SECRET:}"
    post_channel: "${WHATSAPP_PHONE_NUMBER_ID:}"   # phone number ID, not a phone number
    verify_token: "my_verify_token"                # set same value in Meta dashboard
    operators:
      alice: "+14155551234"                       # WhatsApp phone number

  teams:
    bot_token: "${TEAMS_APP_ID:}"
    signing_secret: "${TEAMS_APP_PASSWORD:}"
    post_channel: ""                               # set at runtime from inbound activity
```

### Dynamic Per-Call Routing (v2.2.44+)

`operator_ids` is the logical roster ("alice, bob"). Each channel's `operators:` map resolves those logical ids to channel-specific recipient ids. Pre-compose then steers per call by setting `_target_operator` in `input_data`:

```python
from leafmesh import pre_compose

@pre_compose(input_data=lambda data, ctx: {
    **data,
    "_target_operator": _todays_oncall(),    # "alice" Mon, "bob" Tue, ...
})
async def escalation_agent(input_data, context):
    return {"alert": input_data["incident"]}
```

With Slack + WhatsApp configured, the same `_target_operator: "alice"` dispatches to alice's Slack DM AND alice's WhatsApp number in parallel — each channel pulls from its own `operators:` map. Fail-soft: if alice has no entry under `whatsapp.operators`, WhatsApp falls back to `post_channel`.

Other pre-compose routing keys (escape hatches for dynamic recipients):

| Key | Effect |
|---|---|
| `_target_channel_id` | Raw recipient id — bypasses operator lookup, useful when the id comes from a Zapier / DB lookup |
| `_target_channel_provider` | Pins outbound to one provider when several configured (`"slack"`) |
| `_target_webhook_url` | Raw URL override for the webhook fallback path |

---

## Event Listeners — BRD-021 (Kafka / SQS / MQTT / Redis Streams / IMAP)

Fire agents automatically when an **external event** arrives — no `mesh_call` needed. Two-part config: declare broker connections at the top level, then bind agents to topics/queues via per-agent `listen_events:`.

### Install only what you need

```bash
pip install leafmesh[kafka]       # aiokafka
pip install leafmesh[sqs]         # aioboto3
pip install leafmesh[mqtt]        # asyncio-mqtt (listener lands in a follow-up)
pip install leafmesh[imap]        # aioimaplib (listener lands in a follow-up)
pip install leafmesh[listeners]   # all four bundled
# Redis Streams uses the core `redis` dep — no extra needed
```

### Part 1 — top-level `brokers:` block (connection definitions)

```yaml
brokers:
  orders_kafka:                              # arbitrary connection name
    type: kafka
    bootstrap_servers: ["kafka-1:9092", "kafka-2:9092"]
    security_protocol: SASL_SSL              # PLAINTEXT | SSL | SASL_PLAINTEXT | SASL_SSL
    sasl_mechanism: SCRAM-SHA-512            # PLAIN | SCRAM-SHA-256 | SCRAM-SHA-512 | GSSAPI
    sasl_username: leafmesh
    sasl_password: ${KAFKA_PASSWORD}
    # ssl_cafile / ssl_certfile / ssl_keyfile for mTLS

  support_queue:
    type: sqs
    region: us-east-1
    # aws_access_key_id / aws_secret_access_key — only when running outside AWS;
    # otherwise the IAM role chain is used.
    # endpoint_url: http://localhost:4566    # LocalStack / VPC endpoints

  iot_feed:
    type: mqtt
    host: broker.example.com
    port: 8883
    use_tls: true
    username: leafmesh
    password: ${MQTT_PASSWORD}
    client_id: "leafmesh-iot"                # random if unset
    keepalive_s: 60

  upstream_events:
    type: redis_streams
    url: redis://events.example.com:6379     # distinct from SDK's primary Redis
    db: 0

  ticket_inbox:
    type: imap
    host: imap.example.com
    port: 993
    username: support@example.com
    password: ${IMAP_PASSWORD}
    use_tls: true
```

### Part 2 — bind agents via `listen_events:` (per agent)

```yaml
agents:
  order_processor:
    agent_type: programmatic
    listen_events:
      - broker: orders_kafka                 # references brokers.orders_kafka above
        topic: orders.created                # Kafka topic
        group_id: leafmesh-order-processor   # consumer group; defaults to <sdk-name>-<agent-name>
        batch_size: 10
        filter:                              # CloudEvents-style AND-equality filter
          type: "com.example.order.created"
          source: "/region/us-east-1"
        deserialize: "my_app.schemas:OrderEvent"   # Pydantic class — ValidationError → DLQ
        delivery:
          max_retries: 3
          backoff: exponential                # linear | exponential
          backoff_initial_s: 1.0
          backoff_max_s: 60.0
          dead_letter:
            broker: orders_kafka
            topic: orders.dlq

      - broker: support_queue                # SQS queue (parallel binding on same agent)
        queue: support-tickets
        visibility_heartbeat: true           # auto-extend SQS visibility while handler runs
        batch_size: 5

  iot_telemetry:
    agent_type: programmatic
    listen_events:
      - broker: iot_feed
        mqtt_topic: "sensors/+/temperature"  # wildcards: + (single) and # (multi)
        qos: 1                               # 0 = at-most-once, 1 = at-least-once, 2 = exactly-once

  email_triage:
    agent_type: llm
    listen_events:
      - broker: ticket_inbox
        folder: INBOX
        unseen_only: true
        poll_interval_s: 30                  # IMAP is not push, polled
```

### Source-field cheat sheet (only one set per listener)

| Broker `type` | Destination fields | Notes |
|---|---|---|
| `kafka` | `topic`, `group_id` | `group_id` defaults to `<sdk-name>-<agent-name>` |
| `sqs` | `queue` | Use queue name or full URL. `visibility_heartbeat: true` for long handlers |
| `redis_streams` | `stream`, `consumer_group` | At-least-once via consumer groups + XACK |
| `mqtt` | `mqtt_topic`, `qos` | Wildcards: `+` single-level, `#` multi-level |
| `imap` | `folder`, `poll_interval_s`, `unseen_only` | Polling (IMAP doesn't push) |

### Universal listener fields

| Field | Default | Purpose |
|---|---|---|
| `broker` | (required) | Name of a broker in the top-level `brokers:` block |
| `filter` | `null` | CloudEvents attribute filter — message must match ALL `(key, value)` pairs |
| `deserialize` | `null` | `"module.path:ClassName"` Pydantic class — `ValidationError` routes to DLQ |
| `delivery.max_retries` | `3` | Retry attempts before DLQ |
| `delivery.backoff` | `"exponential"` | `linear` or `exponential` |
| `delivery.backoff_initial_s` | `1.0` | Initial backoff seconds |
| `delivery.backoff_max_s` | `60.0` | Backoff cap |
| `delivery.dead_letter` | `null` | DLQ destination (`{broker, topic/queue/stream}`) |
| `batch_size` | `1` | Messages fetched per poll cycle (1–1000) |

### Delivery semantics

- **At-least-once** across all sources. Idempotency keying is `(listener_name, message_id)` — your agent handler should be safe to re-execute on retry.
- After `delivery.max_retries`, the message is moved to `delivery.dead_letter` if configured, otherwise logged and dropped.
- Listener tasks live for the SDK process lifetime — graceful shutdown via `sdk.stop()`.
- Each listener is **parallel** with mesh_call entry points and `wake_up` cron — they're independent trigger surfaces on the same agent.

### When to use what

| Use case | Broker |
|---|---|
| Microservice event bus, high throughput | `kafka` |
| AWS-native job queue with retries | `sqs` |
| IoT telemetry / pub-sub | `mqtt` |
| Same-stack event stream (no new infra) | `redis_streams` |
| Email-to-agent ingestion | `imap` |

---

## Memory Config

Field: `memory` — accepts `bool` or `dict`.

### Simple Mode

```yaml
memory: false   # Disabled (default)
memory: true    # Enabled with defaults
```

### Advanced Mode (Dict)

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `strategy` | string | `"recency"` | `recency`, `relevance`, `hybrid` | Memory retrieval strategy |
| `limit` | int | `10` | 1 – 100 | Max feed posts per invocation |
| `cross_session` | bool | `false` | `true`, `false` | Persist memory across sessions |
| `cross_session_limit` | int | `50` | 1 – 500 | Max cross-session posts to retain |
| `relevance_weight` | float | `0.6` | 0.0 – 1.0 | Weight for relevance scoring |
| `recency_weight` | float | `0.4` | 0.0 – 1.0 | Weight for recency scoring |
| `decay_hours` | int | `24` | 1 – unlimited | Hours before entries decay |

### Example

```yaml
memory:
  strategy: "hybrid"
  limit: 10
  cross_session: true
  cross_session_limit: 50
  relevance_weight: 0.6
  recency_weight: 0.4
  decay_hours: 24
```

---

## EscalationConfig

Used inside `manager.escalation`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `targets` | list of [EscalationTarget](#escalationtarget) | `[]` | Escalation targets — all fire in parallel |
| `auto_escalate` | dict | see below | Auto-escalation rules |

### `auto_escalate` Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | int | `3` | Max retry attempts before escalating |
| `max_errors_per_session` | int | `5` | Error count threshold per session |
| `timeout_threshold` | int | `2` | Consecutive timeouts before escalating |

---

## EscalationTarget

Each target in the `escalation.targets` list.

| Field | Type | Default | Accepted Values | Applies To |
|-------|------|---------|-----------------|------------|
| `type` | string | **required** | `human_agent`, `webhook`, `channel` | all |
| `agent` | string | `null` | agent name | `human_agent` |
| `entry_point` | string | `null` | entry point name | `human_agent` |
| `url` | string | `null` | URL | `webhook` |
| `method` | string | `"POST"` | `POST`, `PUT`, `PATCH` | `webhook` |
| `headers` | dict | `{}` | key-value string pairs | `webhook` |
| `payload_template` | dict | `null` | JSON with `{{var}}` placeholders | `webhook` |
| `provider` | string | `null` | `slack`, `telegram`, `discord`, `whatsapp`, `teams` | `channel` |
| `channel_id` | string | `null` | channel ID | `channel` |
| `message_template` | string | `null` | text with `{{var}}` placeholders | `channel` |

### Example

```yaml
escalation:
  targets:
    - type: "human_agent"
      agent: "customer_support_team"

    - type: "webhook"
      url: "https://incident.example.com/api/escalate"
      method: "POST"
      headers:
        Authorization: "Bearer ${ESCALATION_TOKEN:}"
      payload_template:
        incident_id: "{{session_id}}"
        severity: "{{severity_level}}"
        message: "{{error_message}}"

    - type: "channel"
      provider: "slack"
      channel_id: "#critical-incidents"
      message_template: "Escalation: {{message}} (session: {{session_id}})"

  auto_escalate:
    max_retries: 3
    max_errors_per_session: 5
    timeout_threshold: 2
```

---

## Top-Level Config (LeafMeshConfig)

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `name` | string | `"default_mesh"` | any string | Mesh name |
| `version` | string | `"1.0.0"` | any string | Configuration version |
| `architecture` | string | `"managed_mesh"` | `managed_mesh` | Architecture type (only one supported) |
| `debug` | bool | `false` | `true`, `false` | Enable debug mode |
| `log_level` | string | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | Logging level |
| `environment` | string | `"development"` | `development`, `production` | Environment |
| `redis` | object | see [RedisConfig](#redisconfig) | — | Redis connection |
| `manager` | object | see [ManagerConfig](#managerconfig) | — | Manager coordination + analysis |
| `mesh` | object | see [MeshConfig](#meshconfig--cloud-providers) | — | Mesh network + cloud providers |
| `agents` | dict | `{}` | agent name → AgentConfig | Agent configurations |
| `entry_points` | list | `[{"name": "default_entry", "target": "summarizer", "condition": "always"}]` | see [Entry Points](#entry-points) | Named portals into mesh |
| `data_structures` | dict | `{}` | name → DataStructure | Custom data type definitions |
| `auto_discover` | dict | `null` | `{"directory": "path", "pattern": "*.py", "recursive": true}` | Auto-discover agent files |
| `evolution` | object | see [EvolutionConfig](#evolutionconfig) | — | Evolutionary optimization |
| `brokers` | dict | `{}` | name → KafkaBrokerConfig \| SQSBrokerConfig \| MQTTBrokerConfig \| RedisStreamsBrokerConfig \| IMAPBrokerConfig | External broker connection definitions for [Event Listeners — BRD-021](#event-listeners--brd-021-kafka--sqs--mqtt--redis-streams--imap). Referenced by name from each agent's `listen_events:` block |

**Note:** `LeafMeshConfig` has `extra="forbid"` — unknown top-level keys will raise a validation error.

---

## ManagerConfig

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `enabled` | bool | `true` | `true`, `false` | Enable manager + summarizer |
| `model` | string | `"gpt-4o-mini"` | same as [Model List](#model-list) | LLM model for Summarizer analysis |
| `domain` | string | `"generic"` | `generic`, `ecommerce`, `data_analysis` | Summarizer domain specialization |
| `prompt` | string | `null` | any string (multiline supported) | **Evaluation criteria** — tell the Manager what success looks like, what to escalate on, and what patterns to watch. Injected into every Summarizer analysis call as an `EVALUATION CRITERIA` section, alongside the domain prompt. |
| `can_intervene` | bool | `true` | `true`, `false` | Allow manager interventions (false = read-only) |
| `coordination_rules` | dict | `{}` | arbitrary key-values | User-defined business rules |
| `chain_completion_timeout` | float | `60.0` | seconds | Wait time before checking chain completeness |
| `health_check_interval` | int | `60` | seconds | Seconds between health checks |
| `agent_timeout_threshold` | int | `180` | seconds | Seconds before agent is timed out |
| `escalation` | object | `null` | see [EscalationConfig](#escalationconfig) | Escalation targets and rules |
| `routing` | dict | see below | — | Manager routing configuration |

### `manager.prompt` — Evaluation Criteria

Gives the Manager direct context about your mesh's specific purpose, success criteria, and escalation triggers. The Summarizer reads this on every agent turn alongside its domain template.

```yaml
manager:
  model: "gpt-4o-mini"
  domain: "generic"
  prompt: |
    This mesh handles customer support tickets.
    A successful flow means:
      - greeter identifies the issue category correctly
      - processor routes to the right specialist agent
      - the customer receives a clear resolution within 5 minutes

    Escalate if:
      - the same issue loops more than twice
      - sentiment is negative AND no resolution has been proposed
      - the human agent times out without responding

    Watch for:
      - advisor_agent confidence scores below 0.6
      - processor_agent routing to fallback more than 50% of the time
```

### `routing` Fields

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `mode` | string | `"static"` | `static`, `learning` | Routing mode (static=YAML only, learning=adaptive) |
| `memory_size` | int | `100` | 1 – 1000 | Max routing decisions to remember |
| `confidence_threshold` | float | `0.7` | 0.0 – 1.0 | Min confidence to accept learned route |
| `fallback` | string | `"all"` | `all` | Fallback when confidence too low |
| `decay_days` | int | `30` | 1 – 365 | Days before old routing memory decays |

### `human_input_rules` (Defaults)

| Field | Type | Default |
|-------|------|---------|
| `max_concurrent_requests` | int | `3` |
| `max_agent_requests` | int | `5` |
| `enable_request_queuing` | bool | `true` |

### `timeout_rules` (Defaults)

| Field | Type | Default |
|-------|------|---------|
| `max_timeouts_before_escalation` | int | `2` |
| `timeout_escalation_enabled` | bool | `true` |
| `escalation_notify_managers` | bool | `true` |

### `workflow_pause_rules` (Defaults)

| Field | Type | Default |
|-------|------|---------|
| `max_pause_duration_minutes` | int | `30` |
| `max_concurrent_paused_workflows` | int | `2` |
| `pause_monitoring_enabled` | bool | `true` |

### `human_response_rules` (Defaults)

| Scenario | `requires_manager_review` | `auto_escalate` |
|----------|--------------------------|-----------------|
| `approval` | `false` | `false` |
| `escalation` | `true` | `true` |
| `timeout` | `true` | `false` |

---

## MeshConfig & Cloud Providers

### MeshConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `call_timeout` | int | `30` | Call timeout in seconds |
| `max_chain_events` | int | `50` | Hard cap on chain events per session before the cycle breaker stops the chain (session `status: stopped` + `ChainCapExceeded`). Raise for legitimately deep flows (research / batch fan-out) — see [Rule 3](#rule-3--bound-every-retry-back-edge) |
| `bedrock` | object | `null` | AWS Bedrock config |
| `vertex` | object | `null` | Google Vertex AI config |
| `foundry` | object | `null` | Microsoft Foundry/Azure AI config |
| `local` | object | `null` | Local model server config (vLLM, SGLang, Ollama, etc.) |

### BedrockConfig (AWS)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `region` | string | `"us-east-1"` | AWS region |
| `profile` | string | `null` | AWS profile from `~/.aws/credentials` |
| `endpoint_url` | string | `null` | Custom Bedrock endpoint URL |

Auth: `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars, IAM role, or `~/.aws/credentials`

### VertexConfig (Google Cloud)

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `project` | string | — | **yes** | GCP project ID |
| `location` | string | `"us-central1"` | no | GCP region |

Auth: `GOOGLE_APPLICATION_CREDENTIALS` env var or `gcloud auth`

### FoundryConfig (Azure)

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `endpoint` | string | — | **yes** | Foundry endpoint URL (e.g. `https://<resource>.openai.azure.com`) |
| `api_version` | string | `null` | no | Azure API version (e.g. `2024-10-21`). Omit for v1 endpoint. |

Auth: `AZURE_FOUNDRY_API_KEY` or `AZURE_FOUNDRY_TOKEN` env vars

### LocalModelConfig

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `endpoint` | string | `"http://localhost:11434/api/generate"` | no | Model server URL |
| `server_type` | string | `null` (auto-detect) | no | Server type: `openai`, `ollama`, `textgen`, `huggingface` |
| `timeout` | float | `120.0` | no | Request timeout in seconds |
| `headers` | dict | `{}` | no | Custom HTTP headers (e.g. for auth) |

Env fallbacks: `LOCAL_MODEL_ENDPOINT`, `LOCAL_MODEL_SERVER_TYPE`, `LOCAL_MODEL_TIMEOUT`

**Supported servers and their `endpoint` + `server_type`:**

| Server | `server_type` | Example `endpoint` |
|--------|--------------|-------------------|
| vLLM | `openai` | `http://localhost:8000/v1/chat/completions` |
| SGLang | `openai` | `http://localhost:30000/v1/chat/completions` |
| llama.cpp server | `openai` | `http://localhost:8080/v1/chat/completions` |
| LM Studio | `openai` | `http://localhost:1234/v1/chat/completions` |
| LocalAI | `openai` | `http://localhost:8080/v1/chat/completions` |
| TGI (--api openai) | `openai` | `http://localhost:8080/v1/chat/completions` |
| TensorRT-LLM | `openai` | `http://localhost:8000/v1/chat/completions` |
| Triton + vLLM | `openai` | `http://localhost:8000/v1/chat/completions` |
| Ollama | `ollama` | `http://localhost:11434/api/generate` |
| Text Gen Web UI | `textgen` | `http://localhost:5000/api/v1/generate` |
| HF Inference | `huggingface` | `https://api-inference.huggingface.co/models/...` |

> **Tip:** Most production servers (vLLM, SGLang, TGI, llama.cpp) expose OpenAI-compatible endpoints. Use `server_type: openai` for all of them. If `server_type` is omitted, it's auto-detected from the URL.

```yaml
mesh:
  local:
    endpoint: http://localhost:8000/v1/chat/completions
    server_type: openai
    timeout: 120
    headers:
      Authorization: "Bearer ${VLLM_API_KEY:}"
```

---

## RedisConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | string | `"localhost"` | Redis server host |
| `port` | int | `6379` | Redis server port |
| `db` | int | `0` | Redis database number |
| `password` | string | `null` | Redis password |
| `decode_responses` | bool | `true` | Decode Redis responses |
| `auto_storage` | bool | `true` | Enable automatic data storage |
| `default_ttl` | int | `3600` | Default TTL (seconds) |
| `session_ttl` | int | `7200` | Session TTL (seconds) |
| `cluster_mode` | bool | `false` | Use Redis cluster |
| `cluster_nodes` | list | `[]` | Cluster node addresses (strings) |
| `ssl` | bool | `false` | Enable TLS for Redis connection |
| `ssl_cert_reqs` | string | `"required"` | TLS verification mode: `required` \| `optional` \| `none` |
| `ssl_ca_certs` | string | `null` | Path to CA bundle for verifying Redis server cert |
| `ssl_certfile` | string | `null` | Client TLS cert path (mutual TLS) |
| `ssl_keyfile` | string | `null` | Client TLS private key path (mutual TLS) |
| `ssl_check_hostname` | bool | `true` | Verify server hostname against certificate |

---

## APIConfig

Top-level `api:` block Configures the ADK's HTTP server.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cors_origins` | list[string] | `[]` | Additional CORS origins, appended to the ADK's built-in defaults (`https://platform.leafcraft.ai` + localhost dev ports). Each entry must be a full origin (`scheme://host[:port]`). |

---

## EvolutionConfig

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `enabled` | bool | `false` | `true`, `false` | Enable evolutionary optimization |
| `strategy` | string | `"genetic"` | free text | Evolution strategy |
| `population_size` | int | `20` | 1+ | Population size per generation |
| `generations` | int | `50` | 1+ | Maximum generations |
| `mutation_rate` | float | `0.1` | 0.0 – 1.0 | Mutation probability |
| `crossover_rate` | float | `0.7` | 0.0 – 1.0 | Crossover probability |
| `elite_size` | int | `2` | 1+ | Elite genomes to preserve per generation |
| `mutation_types` | list | `["prompt_variation", "temperature_adjustment", "tool_selection"]` | `prompt_variation`, `temperature_adjustment`, `tool_selection` | Mutation types |
| `fitness_function` | string | `"task_completion_rate"` | free text | Fitness evaluation function |
| `selection_method` | string | `"tournament"` | free text | Selection method |
| `test_scenarios` | list | `[]` | list of scenario dicts — see below | Weighted test scenarios for fitness evaluation |

### `test_scenarios` — Scenario Dict Fields

Each scenario in `test_scenarios` is a dict with these fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | `"scenario_N"` | Human-readable label — shown in logs and Studio |
| `entry_point` | string | `"test"` | Which mesh entry point to call |
| `input` | any | `"Test scenario input"` | Input data passed to the mesh call |
| `expected_outcome` | dict | `{}` | Key/value pairs the response must contain. All keys checked — partial matches return a partial score. |
| `weight` | float | `1.0` | How much this scenario counts toward the overall fitness score. Higher = matters more. |
| `timeout` | float | `30.0` | Per-scenario timeout in seconds |

**Fitness formula:**
```
fitness = Σ (weight × scenario_score) / Σ (weights)
```
where `scenario_score = outcome_match_ratio × (1 − latency_penalty)`.

A scenario with `weight: 2.0` counts twice as much as one with `weight: 1.0`. Timed-out scenarios score 0 and still count toward the denominator.

### Example

```yaml
evolution:
  enabled: true
  population_size: 20
  generations: 50
  elite_size: 2
  test_scenarios:
    - name: "happy_path"
      entry_point: "greet_user"
      input: { "message": "I need help with my order" }
      expected_outcome:
        status: "success"
      weight: 1.0

    - name: "escalation_path"
      entry_point: "greet_user"
      input: { "message": "This is urgent and completely broken" }
      expected_outcome:
        escalated: true
      weight: 2.0          # weighted heavier — escalation correctness matters more

    - name: "hitl_flow"
      entry_point: "human_contact"
      input: { "user_message": "I want a refund" }
      expected_outcome:
        human_involved: true
      weight: 1.5
```

---

## DataStructure

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | **required** | `object`, `string`, `number`, `boolean`, `list` |
| `properties` | dict | `null` | Object properties (for type=object) |
| `required` | list | `[]` | Required field names |
| `validation_rules` | dict | `{}` | Validation rules (key-value strings) |

---

## Entry Points

Each entry point is a named portal into the mesh.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | **required** | Entry point name |
| `target` | string | **required** | Target agent name |
| `description` | string | optional | Description |
| `condition` | string | `"always"` | Trigger condition |

### Example

```yaml
entry_points:
  - name: "greet_user"
    target: "greeter_agent"
    description: "Main entry — greets user and starts the agent chain"
  - name: "direct_research"
    target: "researcher_agent"
    description: "Skip greeting, go straight to research"
```

---

## Validation Rules

These are enforced by Pydantic validators in the ADK:

| Rule | Constraint |
|------|-----------|
| `agent_type` | Must be `llm`, `human`, `programmatic`, or `external` |
| `human_interface` | Must be `api`, `webhook`, `custom`, or `default` — anything else **raises at load** (used to fail silently at the first live request) |
| `entry_points` targets | `target` / `target_agent` must name a real agent — a typo **raises `ConfigError` at load** instead of failing at the first `mesh_call` |
| `model` | Unknown model id (no provider prefix, not in the catalog) **warns at load** and routes to the `local` provider — see [Model List](#model-list) |
| prompt ↔ `yields` | A prompt committing to JSON keys with zero overlap with the `yields` schema **raises at load** (the "Hello!" silent-fallback bug class) |
| `temperature` + `yields` | `temperature > 0.5` with a yields contract **warns** — keep ≤ ~0.3 for structured output |
| `communication_type` | Must be `dual`, `chain`, or `execute` |
| `optimization_strategy` | Must be `performance`, `cost`, or `speed` (or null) |
| `max_tool_calls_per_message` | Must be 0–20 |
| `tool_call_timeout` | Must be > 0 and <= 300 seconds |
| `tool_choice` | Must be a non-empty string (`auto`, `none`, or tool name) |
| `framework` | Must be `crewai`, `langgraph`, `autogen`, `a2a`, `mcp`, `zapier`, `composio`, `n8n`, `hermes`, `lyzr`, `writer`, `dify`, `flowise`, `voiceflow`, `cognigy`, `vellum`, `stackai`, `agentforce`, `watsonx`, `relevance`, `wordware`, `claude_agent`, `openai_agents`, `custom` (or null) |
| `framework` required | When `agent_type` is `external`, `framework` must be set |
| `integration` | Must be `zapier`, `composio`, `n8n`, `mcp` (or null) |
| `integration` restricted | Only valid when `agent_type` is `programmatic` |
| `is_human_powered` sync | Auto-set to `true` when `agent_type="human"`, forced to `false` when `agent_type="llm"` |
| `AgentConfig` extras | Allows arbitrary extra fields (`extra="allow"`) |
| `LeafMeshConfig` extras | Rejects unknown top-level keys (`extra="forbid"`) |

---

## Field Applicability by Agent Type

Shows which fields are **used** (U), **ignored** (—), or **required** (R) for each agent type.

| Field | `llm` | `human` | `programmatic` | `external` |
|-------|-------|---------|----------------|------------|
| `name` | R | R | R | R |
| `description` | U | U | U | U |
| `model` | U | — | — | — |
| `prompt` | U | — | — | — |
| `temperature` | U | — | — | — |
| `max_tokens` | U | — | — | — |
| `max_completion_tokens` | U | — | — | — |
| `reasoning` | U | — | — | — |
| `thinking` | U | — | — | — |
| `reasoning_budget` | U | — | — | — |
| `enable_prompt_caching` | U | — | — | — |
| `response_format` | U | — | — | — |
| `optimization_strategy` | U | — | — | — |
| `context_parts` | U | — | — | — |
| `tools` | U | — | — | — |
| `tool_choice` | U | — | — | — |
| `max_tool_calls_per_message` | U | — | — | — |
| `tool_call_timeout` | U | — | — | — |
| `allow_parallel_tool_calls` | U | — | — | — |
| `tool_categories` | U | — | — | — |
| `is_human_powered` | — | auto | — | — |
| `human_interface` | — | U | — | — |
| `human_timeout_seconds` | — | U | — | — |
| `human_context_template` | — | U | — | — |
| `human_prompt_template` | — | U | — | — |
| `fallback_on_timeout` | — | U | — | — |
| `fallback_response` | — | U | — | — |
| `require_human_confirmation` | — | U | — | — |
| `human_escalation_triggers` | — | U | — | — |
| `webhook_config` | — | U | — | — |
| `channels` | — | U | — | — |
| `framework` | — | — | — | R |
| `connector_config` | — | — | — | U |
| `integration` | — | — | U | — |
| `communication_type` | U | U | U | U |
| `parallel` | U | U | U | U |
| `max_concurrent` | U | U | U | U |
| `wake_up` | U | U | U | U |
| `listen_events` | U | U | U | U |
| `yields` | U | U | U | U |
| `inputs` | U | U | U | U |
| `can_call` | U | U | U | U |
| `narration` | U | U | U | U |
| `knowledge` | U | U | U | U |
| `wait_for` | U | U | U | U |
| `wait_for_timeout` | U | U | U | U |
| `auto_store_response` | U | U | U | U |
| `auto_store_yields` | U | U | U | U |
| `memory` | U | U | U | U |

**Legend:** R = required, U = used, — = ignored, auto = auto-set
