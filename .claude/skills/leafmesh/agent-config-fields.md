# LeafMesh Agent Configuration — Complete Field Reference

This document lists every configuration field, its type, default value, and accepted values. Use this to build frontend forms, dropdowns, and validation.

**SDK baseline: 2.4.502** (templates pin `leafmesh>=2.4.502`). The fields below make up the agency's configuration document, which **lives in its store** since 2.4.481 — a create-leafmesh project ships no configuration file (`create-leafmesh --start` loads the team with `leafmesh config import --if-empty`; a file given to `from_yaml` is imported only on the first boot); after that it is changed in Studio or through the config API, and a saved setting applies without a restart ([When a saved setting applies](#when-a-saved-setting-applies-24484)).

---

## Table of Contents

1. [Agent Types](#agent-types)
2. [AgentConfig — Core Fields (All Types)](#agentconfig--core-fields-all-types) · [scaling](#scaling--how-an-agent-runs-in-parallel-24484)
3. [LLM Agent Fields](#llm-agent-fields-agent_type-llm)
4. [Human Agent Fields](#human-agent-fields-agent_type-human)
5. [External Agent Fields](#external-agent-fields-agent_type-external) · [External Policy](#external-policy)
6. [Device Block](#device-block) · [Programmatic Agent Fields](#programmatic-agent-fields-agent_type-programmatic)
7. [WebhookConfig](#webhookconfig)
8. [ChannelConfig](#channelconfig)
9. [Memory Config](#memory-config)
10. [EscalationConfig](#escalationconfig)
11. [EscalationTarget](#escalationtarget)
12. [Top-Level Config (LeafMeshConfig)](#top-level-config-leafmeshconfig) · [Self-Healing](#self-healing-self_healing)
13. [ManagerConfig](#managerconfig)
14. [MeshConfig & Cloud Providers](#meshconfig--cloud-providers)
15. [Datastore (.env only)](#datastore-env-only)
16. [EvolutionConfig](#evolutionconfig)
17. [DataStructure](#datastructure)
18. [Entry Points](#entry-points)
19. [Validation Rules](#validation-rules)
20. [Field Applicability by Agent Type](#field-applicability-by-agent-type)

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
| `description` | string | `null` | any string | no | Agent description and purpose. **2.4.487:** the agent it hands work to is told who sent it — name, this description (first 300 characters) and, for a seat, whom it `represents` — in its prompt, or in the call for an outside agent. Write a real one |
| `agent_type` | string | `"llm"` | `llm`, `human`, `programmatic`, `external` | no | Agent execution type (see note below) |
| `communication_type` | string | `"dual"` | `dual`, `chain` | no | `dual`: answers its caller and continues down `can_call` (the human / webhook boundary agent). `chain`: the caller waits for this agent's answer (every peer behind the boundary). `execute` is a deprecated alias — read as `chain` (`dual` on a human seat) with a warning; write `chain` |
| `scaling` | object | `{runs: {}, copies: {mode: fixed, count: 1, max: 10, handoff: last}}` | see [scaling](#scaling--how-an-agent-runs-in-parallel-24484) | no | **How this agent runs in parallel — one block (2.4.484).** `runs.max`: at most N of this agent's jobs at once across ALL pods. `copies`: several copies on ONE job, results combined. Replaces `parallel`, `max_concurrent`, `instances`, `instances_handoff` |
| ~~`parallel`~~, ~~`max_concurrent`~~, ~~`instances`~~, ~~`instances_handoff`~~ | — | — | — | — | **Refused at load since 2.4.484**, with the `scaling:` lines to write. Left at their old defaults (`false` / unset / `1` / `last`) they are dropped quietly |
| `notify` | object | `null` | `{webhook: <name>, when: done\|failed\|both}` | no | **Post this agent's output to a webhook when it finishes (2.4.485; 2.4.486 form).** See [notify](#notify--post-the-output-to-a-webhook-24485) |
| `monthly_token_budget` | int | `null` | > 0 | no | Opt-in monthly token cap for this agent (auto-resets each calendar month). The gate pre-estimates each call and refuses BEFORE spending — the cap is never exceeded. Checked before each model call and each external-agent call (the connector's reported spend counts). Inert on human and programmatic agents. The agent is told on every call where it stands against an even pace for the month, so it paces itself instead of spending it in two days. Ahead of that pace it runs in **lean mode** (2.4.457): every task still runs, each with one normal task's share, and the owner gets a daily Inbox notice. Separately, every LLM task has a ceiling learned from the agent's last normal tasks (about 4× a typical one, once 10 are known); at the ceiling the task answers from what it has. Neither has a field — do not invent one. On an external agent whose connector reports no spend (`framework: custom`, `n8n`, `zapier`, `mcp`, `a2a`, …) the spend is estimated: each call reserves the last call's spend, tokens are estimated from what is sent and received; a cost cap there needs `price_per_1k_tokens` |
| `monthly_cost_budget` | float | `null` | > 0 (USD) | no | Same as above in dollars; either cap trips the gate |
| `budget_on_exhaust` | string | `graceful` | `graceful`, `escalate` | no | What exhaustion does: `graceful` = the agent stops cleanly with a `budget_exhausted` marker (yields filled with defaults, chain continues, no alarm); `escalate` = routed to the Manager as an error |
| `id` | string | generated | any stable string | no | The agent's permanent identity. Memory, experience and channel bindings hang off it, not off `name`. Generated and kept at first boot when omitted |
| `previous_name` | string | `null` | the old agent name | no | Rename that KEEPS memory: on the renamed agent, name what it was called. Ignored once the move has happened (safe to leave). Refused if the old name is still declared, the agent already has an identity, or two agents claim the same name |
| `wake_up` | string or list | `null` | cron string; OR (2.4.107+) a list of cron strings; OR a list of `{cron, input, timezone}` entries | no | Scheduled wake-up(s). Multiple schedules per agent are supported; each entry may carry its own `input` dict merged into that wake's payload, and (2.4.124+) its own `timezone` overriding the agent-level one for that schedule. Standard cron day-of-week (0 = Sunday … 6 = Saturday, or `SUN`–`SAT`); a schedule the scheduler cannot run is **refused at load**. See [gotcha #13](nuances-and-gotchas.md#13-wake_up-crons-run-in-utc-unless-you-declare-a-timezone-24124) for `7`, `#n` and `L` |
| `wake_up_input` | dict | `null` | any JSON object | no | 2.4.107+ — declared input template for scheduled wake-ups. Merged as the BASE of every wake payload (per-schedule `input` overrides it; trigger markers `wake_up_trigger`/`trigger_time` always win). Cron-woken agents receive real input instead of a bare trigger |
| `timezone` | string | `null` (= UTC) | any IANA zone, e.g. `"Asia/Kolkata"` | no | 2.4.124+ — timezone governing this agent's `wake_up` cron schedules. **Without it, crons run in UTC** — `"0 9 * * *"` fires at 14:30 IST, not 9:00. Validated at config load (a fake zone like `Asia/Bangalore` fails boot with a clear error). Studio offers a picker fed by `GET /api/registry?category=timezones` (2.4.125+) |
| `listen_events` | list | `[]` | list of `EventListener` entries (see [Event Listeners](#event-listeners--brd-021)) | no | Bind agent to external event sources (Kafka, SQS, MQTT, Redis Streams, IMAP). Each entry references a broker from the top-level `brokers:` block. Parallel to `wake_up` — both are agent-level trigger surfaces |
| `yields` | dict | `{}` | key: field name, value: type string or nested object | no | Output schema — what the agent produces. Nested objects: `{type: object, fields: {...}}`; arrays: `{type: array, items: ...}`. Any declaration may add `nullable: true` (2.4.104) to accept an explicit null — declare it instead of leaving legitimately-null fields undeclared |
| `inputs` | dict | `{}` | key: field name, value: type string or nested object | no | Input schema — what agent expects |
| `can_call` | list | `[]` | list of `{"agent": "name"}` or `{"agent": "name", "condition": "expr"}` | no | Agents this agent can invoke |
| `narration` | string | `null` | any string (multiline supported) | no | Plain-English routing hints for the Manager — evaluated by the Summarizer when conditions don't cover everything (see [Narration Routing](#narration-routing)) |
| `wait_for` | string or list | `[]` | agent names or expression string | no | Fan-in/join condition |
| `wait_for_timeout` | int | `60` | 1 – unlimited (seconds) | no | Hard timeout for fan-in |
| `auto_store_response` | bool | `true` | `true`, `false` | no | Auto-store responses in Redis |
| `auto_store_yields` | bool | `true` | `true`, `false` | no | Auto-store yields in Redis |
| `memory` | bool or dict | `false` | `true`, `false`, or memory config dict | no | Agent memory — see [Memory Config](#memory-config) |
| `memory_limit` | int | `10` | 1 – 100 | no | Max recent feed posts to load when `memory: true`. **Still a real declared field** (`int`, default `10`) in 2.4.33 — `memory: true` + `memory_limit: N` is valid and verified. Alternatively pass `memory` as a config dict (see [Memory Config](#memory-config)). |
| `knowledge` | bool or dict | `false` | `false`, or `{serviceName, enabled, groupName}` | no | Knowledge/RAG — see [Knowledge Config](#knowledge-config) |
| `enforce_yields` | bool | `false` | `true`, `false` | no | Strictly validate this agent's output against the declared `yields:` schema. `false` (default) fills missing keys with type defaults and logs warnings; `true` triggers a Manager-driven retry up to `enforce_yields_retry` times, then escalates. See [Yields Enforcement](#yields-enforcement). |
| `enforce_yields_retry` | int | `0` | 0 – unlimited | no | Maximum self-correction attempts when `enforce_yields: true`. `0` fails on first contract violation. Each retry passes the previous output + validation errors as feedback so LLM/external/human/programmatic agents can self-correct. Honored by every agent type. |

### `scaling:` — how an agent runs in parallel (2.4.484)

One block, two parts. Both models are `extra="forbid"` (an unknown key is refused).

```yaml
scaling:
  runs:
    max: 4            # at most 4 of this agent's jobs at once across ALL pods; extra jobs wait their turn
  copies:
    mode: auto        # fixed (default) | auto
    max: 10           # auto: ceiling of copies on one job
    work: items       # auto: the input field holding the list (or claim_tool — exactly one)
    handoff: last     # last (default) | each
```

| Field | Type | Default | Accepted | Description |
|---|---|---|---|---|
| `runs.max` | int | unset (no cap) | ≥ 1 | At most this many of the agent's jobs run at once **across every pod**; the rest wait their turn in order. (`max_concurrent` counted per pod.) |
| `copies.mode` | string | `fixed` | `fixed`, `auto` | `fixed`: exactly `count` copies, each with the whole job. `auto`: the mesh hands out the work item by item and starts a copy only while there is an item for it |
| `copies.count` | int | `1` | 1–50 | `fixed`: copies per job (1 = a single run). Was `instances` |
| `copies.max` | int | `10` | 1–50 | `auto`: never more than this many copies on one job |
| `copies.work` | string | unset | an input field name | `auto`: the input field holding the list. Each copy gets one item (the field holds just that item); it takes the next with the built-in `next_work_item` tool; no two copies get the same item. An empty list → one run on the job as it came |
| `copies.claim_tool` | string | unset | one of the agent's own tools | `auto`: the tool that hands out the next item (work the agent finds itself, e.g. a backlog). The mesh calls it — no model run — before starting a copy and when a copy asks for more; it starts a copy only when the tool returns an item |
| `copies.handoff` | string | `last` | `last`, `each` | `last`: one combined output is handed on, once — lists joined, numbers summed, other fields from the final copy, no field dropped. `each`: every copy hands on its own output. Was `instances_handoff` |

- **Checked at load:** `mode: auto` needs **exactly one** of `work` / `claim_tool`;
  `fixed` takes **neither** (every copy gets the whole job).
- **What a copy's input carries:** `_instance: {id, of}` (`of` = the count in
  `fixed`, `"auto"` in `auto`); in `auto` also `_work: {item, field, tool}`.
- **`next_work_item`** (built in, offered only to an `auto` copy): returns
  `{item}`, or `{done: true}` when nothing is left — then the copy answers for
  the items it did.
- **The combined output** (`handoff: last`) carries
  `_instances: {count, results, failed}` — `results` keyed by copy id,
  `failed` naming the copies that failed; `upstream_yields` downstream carries
  the same combined payload.
- An `auto` job holds one `runs` slot however many copies it has.
- **Old fields → `scaling`** (the refusal prints these lines):
  `instances: N` + `instances_handoff: H` → `copies: {mode: fixed, count: N, handoff: H}`;
  `max_concurrent: N` → `runs: {max: N}`; `parallel` → drop it.
- **A human seat is never copied (2.4.485):** `copies` with `mode: auto` or
  `count` > 1 on a human seat is refused at load ("scaling.copies would ask
  the same person the same thing several times"). `runs.max` still caps how
  many of the seat's requests are open at once.

### `notify:` — post the output to a webhook (2.4.485)

```yaml
  invoice_matcher:
    notify:
      webhook: erp_inbox     # a webhook on Tools → Webhooks (never an address)
      when: done             # done (default) | failed | both
```

- **`webhook` names a webhook made on Tools → Webhooks** (2.4.486). That
  webhook picks an Outbound webhook record in the vault (the address and
  sign-in) and sets the method, path and fixed query values. Its body fields
  are for an LLM calling it as a tool — `notify` posts the agent's output in
  their place. (In 2.4.485 `webhook` named the Outbound webhook vault record
  itself.) An address (`://` or `www.`) is refused at load; a name with no
  such webhook is not checked at load — the post fails and is logged.
- **Body** = the agent's output as it is handed on (the mesh's own `_…` keys
  left out). **Headers:** `X-LeafMesh-Agent`, `X-LeafMesh-Session`,
  `X-LeafMesh-Execution`, `X-LeafMesh-Status` (`done` / `failed`).
- Sent **by the mesh in the background** — no model turn, never holds up the
  hand-off, **never fails the run**. Retried with the webhook-seat defaults
  (3 retries, 5 s doubling, 30 s timeout); a post that still fails is logged
  and marked on the trace (span `notify:<webhook>`). A seat still waiting for
  its person has no output yet, so nothing is posted.
- Studio's picker: `GET /api/infra/choices`, list `notify`.

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
    name: "client"
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

You can change an agent's type via `PATCH /api/yaml/agents/{name}`. When `agent_type` changes, the SDK automatically **removes fields that don't belong to the new type**:

| Switching away from... | Fields removed |
|------------------------|----------------|
| `llm` | `model`, `prompt`, `temperature`, `max_tokens`, `max_completion_tokens`, `reasoning`, `thinking`, `reasoning_budget`, `tools`, `tool_categories`, `context_parts`, `tool_choice`, `response_format` |
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
| `"list"` | Array/list — of **text items**. On an LLM agent, a list with no item type, at any depth, is a **warning** at start and in `/api/yaml/validate` (2.4.486): the model is told to write text items. Declare it as `{type: array, items: string}`, or for objects `{type: array, items: {type: object, fields: {...}}}`. Write `array` in the dict form. Since 2.4.487 `{type: list, items: …}` is read as `array` everywhere too (the model's output hint and the JSON schema; before, it was sent as an object), but `array` is the one form every version reads the same |
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

Optional-contributor (`?`) semantics — current (v2.4.22+):

- An optional sibling **dispatched from the same upstream output** is
  **waited for** (in-flight counts as pending, not absent) — the fan-in
  no longer completes early with partial data while a sibling runs.
- **The target runs as soon as the expression is met, and again as each
  agent still running arrives (2.4.486).** `"processor AND (fallback OR
  researcher)"`: when processor and fallback have answered, the target runs
  now; when researcher answers later, the target runs **again** on everything
  gathered, as an update. Its input says so: `still_running: [names]` on a run
  while more is coming, `update_from: <name>` on the re-run. A contributor that
  fails after the target ran runs nothing (the target keeps its answer). A
  second request in the same session starts a new round. (2.4.462–2.4.485
  held the target until a running side of an OR finished; before that, late
  arrivals were dropped.)
- Optional `?` contributors are still waited for, as above.
- On `wait_for_timeout`: if only in-flight **optionals** are missing,
  the target runs with what it has; a missing **required** contributor
  still escalates `FanInTimeout` to the Manager.
- A contributor that **never gets dispatched** (no upstream route fires
  it) stalls the fan-in until `wait_for_timeout` — every `wait_for`
  name should be reachable from some upstream `can_call` in the flow.

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
    name: "triage"
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
    name: "support_agent"
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
| `model` | string | **none — declare it** | see [Model List](#model-list) below | LLM model name. No default since 2.4.135 — the SDK never picks one for you. Non-LLM agents need none. **Read the note below: nothing stops you booting without it.** |
| `model_connection` | string | `null` | a model record's name | **2.4.486.** Which vault sign-in this agent's model calls use when there is more than one for its provider (`openai-prod` / `openai-dev`). Unset: the provider's own record. A missing record, one of another provider, or one with no key fails the call naming the record — never another key. Bedrock / Vertex / Foundry read it as a cloud identity |
| `tenant_credentials_only` | bool | `false` | `true`, `false` | **2.4.488 (any agent type).** When a run carries a tenant id, use only that tenant's own credentials: its model record (and the `model` it picked from the organisation's `tenant_models`) and its record of the name this agent's `connector_config` picks. A tenant with none is stopped with "this tenant has not connected <record>" — never the organisation's. Runs with no tenant use the organisation's records as normal. The Manager always uses the organisation's key. See [SKILL.md → Vault references](SKILL.md#vault-references-your-own-code-and-file-credentials) |
| `prompt` | string | `null` | any string (multiline supported) | System prompt |
| `temperature` | float | `0.1` | `0.0` – `2.0` | LLM temperature (creativity/randomness). One default everywhere since 2.4.485 — some run paths used to fall back to 0.3 |
| `max_tokens` | int | `800` | 1 – model max | Max output tokens (legacy models). One default everywhere since 2.4.485 — some run paths used to fall back to 300 |
| `max_completion_tokens` | int | `null` | 1 – model max | Max completion tokens (o-series, GPT-5.x, GPT-6 models) |
| `thinking` | bool | `false` | `true`, `false` | Enable SDK chain-of-thought scaffolding tools (works with any model): `chain_of_thought`, `metacognitive_reflection`, `apply_edits`. **Text-only — `thinking` NO LONGER runs code.** The old `python_exec` tool (which ran model code *inside the mesh process*) was removed entirely with no fallback; to run code, use [`sandbox`](#sandbox--sandbox_exec-running-code) instead. **Was `reasoning` pre-v2.2.24** |
| `reasoning` | bool | `false` | `true`, `false` | Enable provider-native extended thinking/reasoning (requires a reasoning-capable model — see below). **Was `thinking` pre-v2.2.24** |
| `reasoning_budget` | int | `null` | tokens (provider-specific) | Max native reasoning tokens. Provider defaults apply when omitted. `thinking_budget` is a deprecated alias: the loader reads it as `reasoning_budget` and warns — write `reasoning_budget` |
| `fallback_models` | list | `[]` | model names a configured provider serves | Models tried in order when a call on `model` fails. Never picked for you: empty = no fallback. A call whose tools may already have run is never retried on another model |
| `device` | dict | `null` | `{connection, room?, approval?}` — see [Device Block](#device-block) | Lets this agent ask a device to do something through the `device_action` tool. Off by default |
| `enable_prompt_caching` | bool | `false` | `true`, `false` | Enable provider-native prompt caching for cost reduction (see below) |
| `cache` | bool | `null` | `true`, `false` | LLM-text cache opt-out (2.4.107). The SDK cache reuses ONLY the model's text on identical requests — your function/@chain/@compose always run fresh (side effects re-execute). `false` disables even that reuse for agents that need a fresh model call every time |
| `strict_tools` | bool | `false` | `true`, `false` | Provider-native strict tool schemas (`strict: true`): the model cannot pass hallucinated or extra arguments to tools. Turn on when tool-arg discipline matters more than model flexibility |
| `kanban` | — | — | *(removed from agents in 2.4.397)* | **The board is the mesh's, not the agent's.** As of 2.4.397 an agent has no board setting of its own — the top-level `kanban:` block names the one board and every agent works it. A per-agent `kanban:` block still loads, is **warned as moved to the mesh, changes nothing, and is dropped on the next save**. There is no per-agent opt-out and no second board; `kanban.enabled: false` at the top is the only way off. See the mesh board section in `SKILL.md` |
| `sandbox` | bool or dict | `null` | `true`, or a map of limits | Run code in a contained sandbox — gives an LLM agent a `sandbox_exec(code, language)` tool (`python`/`shell`). `true` = safe defaults (no network, 30s wall-clock, 5s CPU, 256 MiB memory, 64 MiB workspace); a map widens a limit or allows a host. **LLM agents only (2.4.395)** — human, external AND programmatic agents cannot declare a sandbox; a `sandbox` block on them refuses to load. See [`sandbox`](#sandbox--sandbox_exec-running-code) |
| `mother_tongue` | string | `null` | ≤40 chars | The language the agent reasons in. It still ALWAYS writes in the language of the conversation — the person's, or, when it works from other agents' output, the language that work is in (2.4.486; before, such an agent fell back to its mother tongue) |
| `nationality` | string | `null` | ≤40 chars | Whose conventions (dates, money, names, formality) the agent treats as normal |
| `memory_strategy` | string | `"both"` | `tool`, `inject`, `both` | How memory REACHES the agent: `tool` (lazy, the model calls `recall_memory`), `inject` (put in the prompt up front), `both`. Which posts are recalled (`recency` / `relevance` / `hybrid`) is `memory.strategy`, not this — `memory_strategy: hybrid` is refused at load |
| `knowledge_strategy` | string | `"both"` | `tool`, `inject`, `both` | Same for knowledge: `tool` (lazy `query_knowledge`), `inject` (eager RAG), `both` |
| `response_format` | dict | *(accepted extra — not a declared field)* | JSON Schema object | Structured output — forces LLM to respond with valid JSON matching this schema. **Not a declared `AgentConfig` field**; it is accepted via `extra='allow'` and consumed by the provider layer (works, but has no schema-level default/validation). |
| `optimization_strategy` | string | `null` | `performance`, `cost`, `speed` | Per-agent model selection strategy |
| `context_parts` | dict | `null` | see below | Optional context parts |
| `tools` | list | `[]` | tool name strings | Available tools. The generic `zapier_action`, `mcp_call`, `composio_action` and `n8n_workflow` were **removed in 2.4.485** (they took an address or key from the model or the environment): listing one refuses the config, naming the agent's `zapier:` / `mcp:` / `composio:` / `n8n:` block that replaces it |
| `tool_choice` | string | unset | `auto`, `none`, or a specific tool name | Unset by default: the SDK then pins its configured memory / knowledge / reasoning tools on the first turn so they actually fire (gpt-class models otherwise skip them on simple inputs). An explicit `"auto"` switches that pin off. Leave it unset unless you must force `none` or one tool. |
| `max_tool_calls_per_message` | int | `5` | 0 – 20 | Max tool calls per LLM message — every call the model makes counts (the SDK's own memory / board / playbook calls are free). Reaching it is a **warning, not a failure**: see [gotcha #16](nuances-and-gotchas.md) |
| `tool_call_timeout` | float | unset | 0.1 – 300 (seconds) | Unset by default: each tool's own budget applies (MCP / Zapier / Composio / n8n declare 60s). Any value you set — 30 included — wins on every tool path |
| `allow_parallel_tool_calls` | bool | `true` | `true`, `false` | Allow parallel tool execution |
| `tool_categories` | list | `[]` | category name strings | Tool categories agent can access. `integration` is **refused** since 2.4.485 (its four generic tools were removed) |
| `effort` | string | `null` | `"low"`, `"medium"`, `"high"` | v2.3.x — Claude 4.8 (Opus / Sonnet) `effort` parameter. Higher effort = deeper reasoning + more output tokens. Only applies to Anthropic Claude 4.8 family; ignored for other models. |
| `super_agent` | bool \| dict | `false` | `true` / `false` / a tuning dict | Wrap this LLM agent in the multi-phase orchestrator (plan → execute → verify → reflect → finalize). `true` = on with defaults; a **dict** tunes it — the dict is the **only** tuning path (2.4.123+); `tries` (2.4.491) sets attempts per step. See [Super-Agent v3 fields](#super-agent-v3-fields) below |
| `skills` | list \| dict | `null` | `["name", …]` **or** `{sourceName, enabled, names}` | v2.3.x — Skills (reusable instruction playbooks) loaded on demand. `skills: true` (bare bool) is **rejected at YAML load** (`ValidationError`: must be a non-empty list of names, or a `{sourceName, enabled, names}` dict). See [Skills Config](#skills-config) below |
| `receive_conversation_history` | bool | `false` | `true`, `false` | Inject prior turns of the session's conversation into this agent's context (see `history_limit`). |
| `history_limit` | int | `20` | ≥ 0 | Max prior turns injected when `receive_conversation_history: true`. |
| `llm_hard_timeout_s` | float | `null` | seconds | Hard per-call wall-clock timeout for the LLM request; the call is aborted if exceeded. |
| `response_overrides` | list \| dict | `null` | override rules | Post-hoc overrides applied to the LLM response (e.g. force/patch specific yields). Advanced; see the SDK reference. |
| `skills_eager` | bool | unset (= `runtime.skills_eager`, itself default `false`) | `true`, `false` | Ship every skill's **full body** in the prompt instead of lazily via `load_skill_reference`. Per-agent override of the mesh default `runtime.skills_eager` (the old `LEAFMESH_SKILLS_EAGER` env var is a deprecated alias that boot warns about; a declared value wins). For finer control use the per-skill `eager: [names]` sub-key of `skills:` (see [Skills Config](#skills-config)). |
| `schedule_followup` | bool | `true` | `true`, `false` | Offer the `schedule_followup` tool (the agent re-wakes itself later to finish its own work). `false` withholds it from this agent |
| `max_followup_depth` | int | unset (= 5) | ≥ 1 | How many follow-ups may chain from one another (a follow-up scheduling a follow-up …) |
| `max_followups_per_session` | int | unset (= 20) | ≥ 1 | Most follow-ups this agent may schedule in one session |
| `schedule_targets` | list | unset (= its `can_call` agents) | agent names | Agents a follow-up from this agent may be addressed to |
| `output_modality` | string | `"text"` | `"text"`, `"image"` | (declared field since 2.4.121) Output type for the agent. Pair `"image"` with an image-capable model and `image_options`. |
| `image_options` | dict | `null` | provider image opts | (2.4.104, fixed 2.4.108) Options for image generation when `output_modality: "image"` (size, quality, etc.). **≥2.4.108 required** — earlier versions ran image models as TEXT turns on the mesh path (full token bill, empty content, yields failure). |

> **⚠️ A missing `model` is NOT caught where you would expect, and the two
> validators disagree.** Verified against `leafmesh==2.4.265`:
>
> | What you run | LLM agent with no `model` |
> |---|---|
> | `load_yaml_config(path)` | **loads fine** — `agent.model` is `None` |
> | `validate_config(cfg)` | **`valid: True`** — it does not check agent models at all |
> | Studio / `POST /api/yaml/validate` | **error:** `LLM agent 'x' has no model configured` |
> | Boot | **starts** — nothing refuses |
> | The agent's first LLM call | **`ModelNotConfiguredError`** naming the agent and the field |
>
> So a template can pass `validate_config` green, boot green, and then fail at
> the first real message — in front of a user. `validate_config` is NOT a
> sufficient gate for this; check every LLM agent has a model yourself, or
> validate through the API path. What 2.4.135 changed is that there is no
> longer a default to fall back on: before, a missing model silently spent the
> customer's money on a model they never chose.

> **⚠️ Tune Super-Agent with the DICT form — not flat keys.** As of **2.4.123** `super_agent:` accepts either a bool (`true` = on with defaults) **or a dict** of tuning keys, and as of **2.4.131 the dict is the ONLY way to tune it** (the three `LEAFMESH_SUPER_AGENT_*` env vars are dead). The old **flat** keys — `super_agent_cost_ceiling`, `super_agent_step_cap`, `super_agent_reflection_budget`, `super_agent_wall_clock`, `synth_max_tokens_floor/ceiling` — were **never wired** (accepted only as `extra='allow'` and ignored); **do not use them.** Allowed **dict** keys and defaults:
>
> | Dict key | Default | Governs |
> |---|---|---|
> | `cost_ceiling` | `50000` | aggregate token budget for one run |
> | `wall_clock` | `600` | per-run wall-clock seconds |
> | `step_max_tokens` | — | cap per plan step |
> | `synth_max_tokens` | — | cap on the final synthesis call |
> | `verify_view_chars` | — | chars of context the verify phase sees |
> | `goal_check_view_chars` | `12000` | chars the goal-check phase sees |
> | `step_concurrency` | `4` | parallel plan steps when the `depends_on` DAG allows |
> | `tries` | `{mode: fixed, count: 1, rounds: 2}` | **2.4.491.** Attempts per plan step: `count` (1–10) at once per round, up to `rounds` (1–10) rounds, each new round given the last one's critiques; `mode: auto` starts one attempt first and `count` only after a failed check. `tries: 3` = `{mode: fixed, count: 3}`. Unknown keys refused. The best answer of every round is kept. `count` × `rounds` multiplies model calls; `cost_ceiling` / `wall_clock` still bound the run |
>
> Any key you omit takes the SDK default. `super_agent: true` is the shorthand for "on, all defaults".

### Super-Agent v3 Fields

Super-Agent is opt-in on an LLM agent. Setting `super_agent: true` wraps the agent in the orchestrator:

```yaml
agents:
  research_synthesiser:
    name: "research_synthesiser"
    agent_type: "llm"
    model: "claude-sonnet-4-6"
    super_agent:                         # DICT form = the tuning path (2.4.123+); the ONLY way to tune it
      cost_ceiling: 100000               # aggregate token budget for one run (default 50000)
      wall_clock: 900                    # per-run wall-clock seconds (default 600)
      synth_max_tokens: 32768            # cap on the final synthesis call
      goal_check_view_chars: 12000       # chars the goal-check phase sees (default 12000)
      step_concurrency: 4                # parallel plan steps when the DAG allows
      tries: {mode: auto, count: 3, rounds: 2}   # 2.4.491: one attempt; 3 at once only after a failed check
    # (super_agent: true is the shorthand — on with all defaults)
    prompt: |
      You are a research synthesiser. Plan the investigation, execute
      each step, verify outputs against expected outcomes, and produce
      a final synthesis that satisfies the yields contract below.
    yields:
      summary: "string"
      sources: "list"
      confidence: "number"
```

**Two extra tools** the Super-Agent receives beyond its normal `tools:`:

- `TodoWrite` — the LLM modifies its own plan mid-run (add / edit / reorder steps) without leaving the run.
- `Pause` — the LLM signals "I need a human here." Run yields control to HITL; root span stamps `status=OK` (designed exit).

**When to enable**: complex research synthesis, multi-file code changes, multi-page document analysis. **When not to**: one-shot Q&A, classification, summarization — plain LLM agent is faster + cheaper.

### Skills Config

Skills are reusable instruction blocks (playbooks) that agents load on demand via the `load_skill_reference` tool. The LLM sees a compact skills index in its system prompt and fetches full bodies on demand.

```yaml
agents:
  support_agent:
    name: "support_agent"
    agent_type: "llm"
    model: "gpt-4o-mini"
    skills:
      sourceName: "support_playbooks"   # a REGISTERED source name (default: "default" — hosted)
      enabled: true                      # on-switch (default true)
      names:                             # REQUIRED, non-empty — empty list clears the field (no skills)
        - "refund_flow"
        - "account_migration"
        - "tone"
      eager:                             # (2.4.123) full-body in the prompt; the rest stay lazy
        - "tone"                         # every name here MUST appear in `names` or load fails

    # Shortform — routed to the "default" source (HOSTED):
    # skills: ["refund_flow", "account_migration"]
```

> **`eager` vs lazy:** `names` are advertised in a compact index and fetched on demand via `load_skill_reference`. `eager: [...]` ships those skills' full bodies resident in the prompt — for the one skill that is *always* relevant (house tone, a policy matrix). Every `eager` name is validated against `names` at load, so a typo fails fast instead of silently delivering nothing. Mesh default is `runtime.skills_eager` (default `false`); the per-agent `skills_eager: true` field forces all-eager.

**Source registration is NOT in YAML** — there is no top-level `skills:`
block (the loader rejects unknown top-level keys). Register sources via
the API; they persist in Redis and reload on every SDK start:

```bash
curl -X POST http://127.0.0.1:18820/api/skills/sources \
  -H "Content-Type: application/json" \
  -d '{"name": "support_playbooks", "source_type": "filesystem", "config": {"root": "./skills"}}'
```

If no sources are registered, the SDK auto-creates a `"default"` source
of type **hosted** — local `skills/*.md` files do NOT load until a
`filesystem` source is registered and referenced by `sourceName`.

**Strict gating**: `skills: true` (bare bool) is **rejected at YAML load** — `skills` must be a list of names or a `{sourceName, enabled, names}` dict, and `names` must be non-empty.

**Connectors** (`source_type`): `filesystem` (skills as `.md` files; root resolution: `config.root` > `LEAFMESH_SKILLS_DIR` env > `./skills/`) and `hosted` (LeafCraft Studio's skill library). Multi-file skills are supported: a skill directory's primary file MUST be named `SKILL.md` (a subfolder without one is silently skipped); the LLM calls `load_skill_reference("skill_name")` for the primary body and `load_skill_reference("skill_name", "deep_dive.md")` for a specific supporting file.

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
> `leafmesh.llm.adaptive_executor.MODEL_DEFAULT_BENCHMARKS` (76 current
> models as of 2.4.436), served at **`GET /api/registry`** (per-provider
> `models` lists, plus connectors/integrations/channels). When in doubt,
> hit the endpoint — don't guess. A model id that matches **no known
> provider prefix and no catalog entry goes to your local model server**
> (an INFO log line says so). With no local server set up, 2.4.497 refuses it
> and says where to add it (2.4.495 sent it to `default_provider`, else the
> first loaded provider). Add the model on the
> Models page to send it anywhere else. A prefix that names a known provider
> with no key **raises** at the call. Typos like `gpt4o-mini` are the
> classic case.

**Retired or superseded — never write these in a new config:** `deepseek-chat`,
`deepseek-reasoner`, `grok-3`, `grok-4`, `grok-4-mini`, `grok-2*`,
`gemini-2.0-flash*`, `gemini-3-pro-preview`, `gemini-3.5-flash`,
`mistral-large-2`, `mistral-medium-3`, `mistral-small-3`, `codestral-2`,
`claude-sonnet-4-7`, `claude-haiku-4-6`, `o1`, `o1-mini`, `o3-mini`. They
keep a price for old traces but the picker no longer offers them.

Every key below can be set in `.env` **or** saved on the Infrastructure
page (Infrastructure → Models — the vault); `.env` wins when both are set.
A known model whose provider has **no key** is refused plainly (2.4.482):
"model 'X' needs the <provider> provider, which has no key here — add one on
Infrastructure → Models, then try again" — never sent to the local model.

**Provider count depends on the SDK:** PyPI 2.4.418 (customers today) has 10
built in plus any OpenAI-compatible endpoint; dev 2.4.434+ has 27 (the lists
below).

**OpenAI** (`OPENAI_API_KEY`):
- `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`
- `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`
- `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.2`, `gpt-5.1`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano`
- `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4o`, `gpt-4o-mini`, `o3`, `o4-mini`
- GPT-6 / GPT-5.6 / `-pro` / Codex go through OpenAI's Responses API
  automatically (2.4.435) — same config, same tool loop. GPT-5/6 and
  o-series take no temperature (the SDK drops it).

**Anthropic** (`ANTHROPIC_API_KEY`):
- `claude-fable-5-1`, `claude-fable-5`
- `claude-opus-5-5`, `claude-opus-5`, `claude-sonnet-5-5`, `claude-sonnet-5`, `claude-haiku-5-5`
- `claude-opus-4-8`, `claude-opus-4-7`, `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-sonnet-4-5`, `claude-haiku-4-5`
- Opus 4.7+ / all 5.x / Fable / Mythos are adaptive-thinking: no
  sampling params, depth by `effort`, never a token budget.

**Google** (`GOOGLE_API_KEY` or `GEMINI_API_KEY`):
- `gemini-4-argon`, `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`
- `gemini-3.1-pro-preview`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview`
- `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`

**DeepSeek** (`DEEPSEEK_API_KEY`):
- `deepseek-v4-pro`, `deepseek-flash`
- Billed 2× in DeepSeek's peak hours (01–04 and 06–10 UTC, weekdays);
  the SDK prices each call by its time.

**xAI Grok** (`XAI_API_KEY` or `GROK_API_KEY`):
- `grok-4.7`, `grok-4.6`, `grok-4.5`, `grok-4.3`
- `grok-4.20-0309-reasoning`, `grok-4.20-0309-non-reasoning`, `grok-build-0.1`

**Mistral** (`MISTRAL_API_KEY`):
- `mistral-large-4-0`, `mistral-medium-3-5-26-04`, `mistral-small-4-0-26-03`, `mistral-large-3-25-12`
- `codestral-2508`
- Ids carry a version date — write them out in full.

**Chat-completions vendors (2.4.434 / 2.4.436) — one key each, `.env` or Infrastructure page.**
A vendor that serves its own models routes by the model name; a host of
other labs' models routes by a prefix the SDK strips before sending.
Each also reads `<NAME>_BASE_URL` (or the connection's optional
Endpoint) for another region or a proxy.

| Vendor | Model ids | Current picker ids | Key env var (first = canonical) |
|---|---|---|---|
| OpenRouter | `openrouter/<lab>/<model>` | live list | `OPENROUTER_API_KEY` |
| Groq | `groq/<model>` | live list (e.g. `groq/openai/gpt-oss-120b`) | `GROQ_API_KEY` |
| Cerebras | `cerebras/<model>` | live list | `CEREBRAS_API_KEY` |
| Moonshot Kimi | `kimi-…`, `moonshot-…` | `kimi-k3` | `MOONSHOT_API_KEY`, `KIMI_API_KEY` |
| Alibaba Qwen | `qwen…` | `qwen3.8-max`, `qwen3.7-plus`, `qwen3.7-flash` | `DASHSCOPE_API_KEY`, `QWEN_API_KEY` |
| Z.AI GLM | `glm-…` | `glm-5.3`, `glm-5.3-flash` | `ZAI_API_KEY`, `GLM_API_KEY` |
| MiniMax | `minimax-…` | `minimax-m3`, `minimax-m3.1-flash` | `MINIMAX_API_KEY` |
| Inception (Mercury) | `mercury-…` | `mercury-3` | `INCEPTION_API_KEY` |
| Meta (Muse) | `muse-…` | `muse-spark-1.3`, `muse-wonder-1.0` | `META_API_KEY`, `MODEL_API_KEY` |
| StepFun | `step-…` | `step-5-preview`, `step-3.7-flash` | `STEPFUN_API_KEY`, `STEP_API_KEY` |
| Arcee | `trinity-…`, `arcee-…` | `trinity-large-thinking` | `ARCEE_API_KEY`, `ARCEEAI_API_KEY` |
| Tencent Hunyuan | `hy3…`, `hy4…`, `hunyuan-…` | live list | `HUNYUAN_API_KEY` |
| Xiaomi MiMo | `mimo-…` | live list | `MIMO_API_KEY` |
| Upstage (Solar) | `solar-…` | live list | `UPSTAGE_API_KEY` |
| Poolside (Laguna) | `poolside/…` — sent **as is** (part of the id) | live list (e.g. `poolside/laguna-s-2.1`) | `POOLSIDE_API_KEY` |
| Reka | `reka-…` | live list | `REKA_API_KEY` |
| Cohere | `command-…` | live list | `CO_API_KEY`, `COHERE_API_KEY` |

"live list" = the vendor's own model list, fetched once the key is saved
(`GET /api/registry`). The list is only suggestions: each of these vendors
takes any of its own model ids, a host's with its prefix
(`openrouter/anthropic/claude-sonnet-5`) (2.4.458). Copy the id exactly from
the vendor's own model list — never guess one. Vendor rules the SDK applies for you: Xiaomi and Tencent honour only
`tool_choice: auto` (a pinned choice is left unset); Cohere is never sent
`parallel_tool_calls`; Groq never gets temperature 0; a hosted GPT-5/6 or
Claude 4.7+ is never sent temperature. OpenRouter reports each call's
cost itself; vendors with no published price show "cost unknown".

**Three ways to reach a model:** (1) each vendor with its own key — the
default; (2) the customer's own cloud — `bedrock/…`, `vertex/…`,
`foundry/…`; (3) `openrouter/…` — one optional key for the long tail.

**AWS Bedrock:**
- Any Bedrock model ID (e.g. `anthropic.claude-sonnet-4-20250514-v1:0`, `amazon.titan-text-premier-v1:0`), or an SDK alias (`claude-sonnet-4-20250514`, `llama3.1-70b`, `mistral-large`, `command-r-plus`, …)
- Requires `mesh.bedrock` config

**Google Vertex AI:**
- Any Vertex model ID (e.g. `gemini-2.5-pro`); an id with no alias is sent as written
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
| **Works with** | Any model (tool injection) | Only reasoning-capable models: OpenAI o-series / GPT-5.x / GPT-6, Claude 3.7 / 4.x / 5.x, Gemini 2.5+ / 3.x+, Grok 4.5+ |
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
| **Anthropic** | Claude 3.7+ | Extended thinking with `budget_tokens` on Sonnet 4.6 / Haiku 4.5 and older; Opus 4.7 / 4.8, all 5.x (incl. Haiku 5.5), Fable and Mythos are adaptive-only and use `effort` (manual thinking is rejected) |
| **OpenAI** | o-series, GPT-5.x, GPT-6 | Reasoning effort; GPT-6 / 5.6 / -pro via the Responses API automatically (effort `none` never sent to GPT-6 Astra / 6.1 Sol) |
| **Google** | Gemini 2.5+ (`thinkingBudget`), Gemini 3.x (`thinkingLevel`) | `thinkingConfig` |
| **DeepSeek** | Reasoner family only (`deepseek-reasoner`, retired) | `deepseek-v4-pro` / `deepseek-flash` are not the reasoner family — `reasoning: true` adds nothing; use `thinking: true` |
| **xAI Grok** | `grok-4.5`, `grok-4.6`, `grok-4.7` | Reasoning effort `low`/`medium`/`high` (+ `xhigh` on 4.6 / 4.7); the highest level the model accepts not above the one asked |
| **Mistral** | — | No native reasoning mode — use `thinking: true` (SDK CoT scaffolding) instead |
| **Bedrock** | Claude models on Bedrock | `additionalModelRequestFields.thinking` |
| **Vertex** | Claude + Gemini on Vertex | Both thinking APIs supported |
| **Foundry** | Azure o-series + GPT-5.x deployments | `reasoning_effort` parameter |
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
    name: data_extractor
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
    name: "analyst"
    agent_type: llm
    model: claude-sonnet-4-6
    reasoning: true             # provider-NATIVE extended thinking (claude-4 family supports it)
    reasoning_budget: 8192      # max 8K native reasoning tokens
    thinking: true              # also inject SDK chain-of-thought scaffolding tools
    enable_prompt_caching: true # cache system prompt + tools
    prompt: |
      You are a data analyst. Analyze the provided data thoroughly.
```

### `sandbox` — `sandbox_exec` (running code)

Code execution lives behind its own `sandbox` field (2.4.391+). `thinking` no
longer runs code — the old `python_exec` tool, which ran the model's code
*inside the mesh process* (with its environment, every tenant's data, files,
memory and network), is **removed entirely, with no fallback**.

```yaml
agents:
  researcher:
    agent_type: llm
    model: claude-sonnet-4-6
    sandbox: true              # safe defaults — gives a sandbox_exec(code, language) tool
    # sandbox:                 # …or a map to widen a limit / allow a host:
    #   network: {allow: ["api.example.com:443"]}
    #   timeout_seconds: 60
    #   cpu_seconds: 15
    #   memory_mb: 512
    #   workspace_mb: 128
```

- **The tool.** `sandbox: true` gives the agent a `sandbox_exec(code, language)`
  tool (`language` is `python` or `shell`). It may run anything inside the
  sandbox — code, files in its own fresh workspace, installed packages.
- **The defaults** (safe): no network, 30s wall-clock, 5s CPU, 256 MiB memory,
  64 MiB workspace. A map widens any of `timeout_seconds`, `cpu_seconds`,
  `memory_mb`, `workspace_mb`, or allows hosts with `network: {allow: ["host:port", …]}`.
- **Isolation.** A locked-down child process inside the mesh container — its
  own workspace the only writable dir, read-only system dirs (Landlock), raw
  sockets / ptrace / mounts / namespaces denied (seccomp), CPU/memory/file/proc
  caps, and (when the mesh runs as root) dropped to an unprivileged user. It
  **never runs in the mesh process.**
- **Network is deny-by-default.** With no `network.allow` there is no network;
  an allowed host is reached only through a mesh-run egress proxy, every other
  destination refused.
- **Host-dependent, logged at boot.** The SDK logs one line — *full* (every
  layer active; tool offered, allowlist honoured), *partial* (some layers
  missing; tool offered but network refused), or *unavailable* (tool withheld,
  config still loads). macOS reports *full* via the system sandbox. Studio reads
  it from `GET /api/registry?category=sandbox`.
- **Who may declare it: LLM agents only (2.4.395).** Human, external and
  programmatic agents cannot have a sandbox; a `sandbox` block on them refuses
  to load (`sandbox` is an LLM-only field — a programmatic agent's code is its
  own). The earlier `context["sandbox"]` / `sdk.run_sandboxed` path for
  programmatic agents was removed in 2.4.395.

---

## Human Agent Fields (`agent_type: "human"`)

These fields are used when `agent_type` is `"human"`. `is_human_powered` is auto-set to `true`.

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `is_human_powered` | bool | `false` | `true`, `false` | Auto-synced to `true` when agent_type="human" |
| `human_interface` | string | `"api"` | `default`, `api`, `webhook`, `custom` | How human receives/submits input (see below). **2.4.486:** the default is still `"api"`, but an `api` seat with no handler registered by your code is answered in the **Inbox** (start logs "no code answers it … its requests appear in the Inbox") — so a seat declared with nothing else works. Before, it failed on its first question |
| `human_timeout_seconds` | int | `300` | > 0 (seconds; no upper cap) | How long the seat waits for the person. When it is up the seat **stops waiting** (2.4.486) — see [timeouts](#when-nobody-answers-24486) |
| `human_context_template` | string | `null` | any string | Template for presenting context to human |
| `human_prompt_template` | string | `null` | any string | Template for human prompts |
| `fallback_on_timeout` | bool | `false` | `true`, `false` | OPT-IN: when the seat's time is up, answer with `fallback_response` (plus `human_decision: "timeout"`, `timeout: true`) and carry on down `can_call`. Default `false` — nobody answering is never an assumed answer |
| `reply_reader` | dict | `null` | `{model, prompt, memory, knowledge, skills, experience, model_connection, temperature, max_tokens}` | **2.4.486 — replaces `intent_model` / `intent_prompt`.** The model that reads what the person MEANT. See [reply_reader](#reply_reader--reading-a-persons-reply-24486) |
| ~~`intent_model`~~, ~~`intent_prompt`~~ | — | — | — | **Moved into `reply_reader` at load (2.4.486)** as its `model` / `prompt`. Both forms on one seat that disagree are refused. (The load still prints "'intent_model' is not an agent setting this SDK reads" — ignore it; the value is moved. Write `reply_reader`.) |
| `fallback_response` | dict | `null` | arbitrary JSON | Default response on human timeout |
| `operator_ids` | list | `[]` | list of strings (email or ID) | Operators who can see this agent's HITL requests. Empty = broadcast (all operators see it). |
| `represents` | string | unset | `organisation`, `customer` | Who the people on this seat speak for. `organisation` (staff): their decisions become the asking agents' standing rules. `customer` (the public): a reply decides the request in hand and is never kept as a rule. Unset: an Inbox seat with `operator_ids` is the organisation's; a channel or webhook seat is the organisation's only for a reply from a declared operator |

> **Removed in 2.4.382 — approval is routing.** `require_human_confirmation`,
> `confirmation_seat` and `human_escalation_triggers` are gone. One set ON
> **refuses the config at load**; one set off / empty is dropped. A person who
> must sign off is a human agent the work is routed to: a `can_call` with a
> condition on the agent before it, and `can_call` from that seat to the agent
> that acts. See [SKILL.md — Approval is routing](SKILL.md#approval-is-routing).
| `webhook_config` | object | `null` | see [WebhookConfig](#webhookconfig) | Webhook settings (required for `webhook` interface) |
| `channels` | dict | `{}` | see [ChannelConfig](#channelconfig) | Native channel adapters (Slack, Telegram, etc.) |

### `human_interface` — Interface Types

| Value | Description | How it works |
|-------|-------------|-------------|
| `default` | **HITL Inbox (LeafCraft Studio)** (recommended) | Writes request to the mesh's own Redis, emits stream event. Studio's Inbox renders it with the conversation thread. Human replies via the UI. Supports parallel requests per session. No `webhook_config` — works out of the box, hosted **or self-hosted**. |
| `webhook` | **External webhook** | POSTs request to the address of the vault record `webhook_config.connection` picks ("Add custom" record, service type 'Outbound webhook'). Human responds via inbound webhook endpoint. Also supports native channel adapters (Slack, Telegram, etc.). |
| `api` | **Python callback** | Calls a Python handler registered via `sdk.agent_registry.register_human_agent(name, human_interface_handler=fn)` (or `sdk.agent_registry.update_human_interface_handler(name, fn)` to attach a handler to an already-declared human agent). **There is no `sdk.register_human_handler()`** — that method does not exist in 2.4.33. No outbound HTTP. Used for custom integrations and testing. |
| `custom` | **Custom handler** | Same as `api` — uses the registered `human_interface_handler` callback. |

> **Note:** `default` (the Inbox) works on hosted and self-hosted meshes alike — the request lives in the mesh's own Redis and the seat logs "Inbox registered for human agent" at boot. A seat is Inbox **or** webhook, never both. Use `webhook` only when the person answers in your own system, `api` for a Python callback.

### Example — Default (HITL Inbox)

```yaml
agents:
  support_human:
    name: "support_human"
    agent_type: human
    human_interface: default          # the Inbox — hosted or self-hosted
    human_timeout_seconds: 28800      # 8h — a PERSON answers this. 300 = five minutes.
    yields:
      resolution: string
      action_taken: string
```

### Example — Webhook with Channel Adapter

```yaml
agents:
  support_human:
    name: "support_human"
    agent_type: human
    human_interface: webhook
    human_timeout_seconds: 600
    webhook_config:
      connection: "support-desk-hook"    # "Add custom" record, service type 'Outbound webhook': base URL = the address
    channels:
      slack:
        connection: "slack-workspace"    # the vault holds bot_token + signing_secret
        post_channel: "C123456"
```

### Where a seat is reached — one service (2.4.486)

A seat picks **one** service: the Inbox, an Outbound webhook record, or one
Slack / Teams / Telegram / WhatsApp / Discord / Cliq / Email sign-in. Studio's
picker (`GET /api/infra/choices`, list `human_seat`, the Inbox first) shows
each sign-in as "Provider · record" and writes exactly what it needs:

| Picked | Written on the seat |
|---|---|
| Inbox | `human_interface: default` |
| An Outbound webhook record | `human_interface: webhook` + `webhook_config: {connection: <record>}` |
| A messaging / email sign-in | `human_interface: webhook` + `channels: {<channel>: {connection: <record>}}` |

A seat declared with nothing else is answered in the Inbox. `api` is only for
a seat your code answers (`register_human_agent(..., human_interface_handler=fn)`).

### `reply_reader` — reading a person's reply (2.4.486)

The model that reads what a person MEANT, in any words and any language. It
replaces `intent_model` / `intent_prompt` (moved in at load).

```yaml
  client:
    name: client
    agent_type: human
    human_interface: default
    reply_reader:
      model: gpt-4o-mini             # required
      prompt: |                      # how to read replies here (it never adds a field, value or route)
        "go ahead" and "fine" mean approved. A question back is not a decision.
      experience: true               # give it this seat's own learned rules (confirmed first)
      # knowledge: {serviceName: ..., enabled: true}   memory: true   skills: [...]
      # model_connection: openai-dev   temperature: 0.0   max_tokens: 300
    can_call:
      - agent: refunds_agent
        condition: "calling_agent_response.intent == 'refund'"
```

| Field | Default | Notes |
|---|---|---|
| `model` | **required** | No default anywhere. No reader → a reply no condition can read is not passed on |
| `prompt` | — | The owner's guidance, used in every reading (fields, which question, approval) |
| `temperature` | `0.0` | |
| `max_tokens` | per reading: 300 (fields), 400 (a decision), 40 (which question) | |
| `model_connection` | the provider's own record | Which model sign-in it uses |
| `memory`, `knowledge`, `skills` | off | Each adds a bounded piece to the reading (knowledge, memory and each skill ≤ 3,000 characters). `memory: true` = 5 relevant memories |
| `experience` | off | `true`/`false` only |

- Anything else in the block — `tools` included — is refused: the reader only
  reads.
- **One lean model call per reading** (~500 tokens), not an agent run. It is a
  step of the seat's own run in the trace. It goes through the response cache.
- **It never picks a route.** It fills the fields the seat's `can_call`
  conditions read (values named in `==` and `!=` conditions are offered to it);
  `can_call` — or the Manager — decides. An answer to an agent's question is
  read before it routes too.
- **A person's answer that no route takes ends the conversation and closes
  the ticket** (e.g. "thank you"). It is not sent to an agent by default.
- **Shared threads:** a thread keeps every open question asked in it. A reply
  answers one question; the same asker asking again replaces its earlier
  question (closed as `superseded` — no notice, nothing judged). When questions
  from different askers are open, the reader picks which one the reply answers;
  without a reader, or if it cannot tell, the newest. A seat owns only the
  questions it asked.
- For experience, the decision in a reply is read by the reader, else by the
  asking agent's own `model`. Neither → nothing filed.

### When nobody answers (2.4.486)

**A seat waits its time and stops.** When `human_timeout_seconds` is up, the
request closes (`request_timeout` in the Inbox) and `HUMAN_INPUT_TIMEOUT` is
published. There is no "timed out and escalated" note to the person, no
escalation to the Manager, and no check-back that re-runs the asking agent. A
late reply still lands (it is marked `answered_late`). Nobody answering is not
judged, and a person is never coached.

- `fallback_on_timeout: true` + `fallback_response` still answer for the seat
  and carry the chain on.
- On an `api` seat whose handler does not answer in time, with no fallback,
  the run fails with a timeout error.
- Removed (dropped with a warning if still present):
  `manager.timeout_rules`, `manager.escalation.auto_escalate.timeout_threshold`,
  `manager.human_response_rules.timeout`.
- What to do about an approval nobody answers: see
  [nuances-and-gotchas.md → A seat waits its time and stops](nuances-and-gotchas.md#a-seat-waits-its-time-and-stops-24486).

### Two Scenarios for Human Agent Sessions

Human agents support two interaction patterns via the same webhook endpoint:

**Scenario 1 — Resume (session_id present):** When a POST to `/webhook/{entry_point}` includes a `session_id` that matches a pending HITL request, the SDK resumes that session. The operator's response is routed via `can_call` to the next agent.

**Scenario 2 — New (no session_id or not found):** When a POST has no `session_id` or the session has no pending expectation, the SDK creates a new workflow. If the human agent has no upstream caller, the operator's message is immediately routed via `can_call` — no HITL pending step is created.

---

## External Agent Fields (`agent_type: "external"`)

These fields are used when `agent_type` is `"external"`.

| Field | Type | Default | Accepted Values | Required | Description |
|-------|------|---------|-----------------|----------|-------------|
| `external_agent` | string | `null` | the name of an entry on the **External agents page** | no | **2.4.486 — the normal way.** The external agent is set up once on Studio's External agents page (`/api/external-agents`: framework, vault record, framework settings); the agent names the entry and nothing else about it. The mesh fills in `framework` and `connector_config` from the entry — at start, on every save, and on other pods when the entry changes. A `framework` or `connector_config` written beside it that **differs** from the entry is refused (one that matches is accepted). Only `external_agent` is saved. An entry that is gone: start logs it and the agent **refuses its calls** — it never runs as `custom`. See [External agents page](#external-agents-page-24486) |
| `framework` | string | `null` | `crewai`, `langgraph`, `autogen`, `a2a`, `custom_api`, `mcp`, `zapier`, `composio`, `n8n`, `hermes`, `lyzr`, `writer`, `dify`, `flowise`, `vellum`, `stackai`, `agentforce`, `watsonx`, `relevance`, `wordware`, `lindy`, `claude_agent`, `openai_agents`, `claude_managed`, `openai_agents_api`, `foundry_agents`, `vertex_agent_engine`, `bedrock_agentcore`, `copilot_studio`, `mistral_agents`, `letta`, `glean_agents`, `servicenow`, `sap_joule`, `workday`, `box`, `atlassian_rovo`, `gemini_enterprise`, `custom` | **yes**, unless `external_agent` is set | External framework name. `custom_api` is new in 2.4.486 (see [custom_api](#custom_api-24486)). The valid list = every registered connector + `custom` (derived live from the connector registry). **`lindy` was added in 2.4.406** (webhook-triggered, callback-answering — see [lindy](#lindy-24406)). **`voiceflow` and `cognigy` were removed in 2.4.395** (voice/chat-bot platforms; LeafMesh agents are task agents) — a config naming either refuses to load. See [Managed-agent platforms](#managed-agent-platforms-2439596) and [A2A platform services](#a2a-platform-services-24396) |
| `connector_config` | dict | `{}` | framework-specific key-values | no | How this agent calls the system (which graph / flow / agent id, mode, timeouts) — passed as `**kwargs` to the connector. Keys, tokens, addresses, account ids and header rows are **vault-only** (picked with `connection`) — see [Common connector_config fields](#common-connector_config-fields-all-frameworks) |
| `external_policy` | dict | safe defaults | see [External Policy](#external-policy) | no | What this agent may reach, what is sent to it, the largest reply accepted, and when it is quarantined. Safe with no block at all |
| `request_form` | dict | `{}` | any keys / JSON values, see [Request form](#request-form) | no | Your own fields sent with every request, in that system's place for caller data. Also on a programmatic agent with an `integration` |

### External agents page (2.4.486)

An external agent is now **set up once**, on Studio's External agents page,
like Models and Tools: its framework, the vault record that signs it in, and
the framework's own settings (graph id, poll timing …; never a key or
address). Agents pick it:

```yaml
agents:
  billing_bot:
    name: billing_bot
    agent_type: external
    external_agent: billing_a2a      # the entry's name on the External agents page
    communication_type: chain
```

- The page's API: `GET/POST /api/external-agents`, `GET/PUT/DELETE
  /api/external-agents/{name}`, `GET /api/external-agents/frameworks` (what
  each framework's form asks for), `GET /api/external-agents/records?framework=`
  (the vault records it can sign in with). An entry an agent picks cannot be
  deleted; changing it reloads the agents that pick it.
- **The record decides the kind (2.4.491).** An entry takes its framework from
  the vault record it picks: a CrewAI record is a CrewAI agent, a LangGraph
  record a LangGraph agent. Leave the entry's `framework` out. Only a custom
  record needs one — `a2a` (Custom: A2A) or `custom_api` (Custom: API). A
  `framework` that contradicts the record is refused on save ("the vault
  record 'x' is a CrewAI record — this agent is CrewAI, not …").
  `GET /api/external-agents/records` **with no** `framework` lists every record
  an external agent can use, each with its `framework` (`null` for a custom
  record).
- **Custom: API from a swagger file (2.4.491).** `POST
  /api/external-agents/from-spec` with `{"spec": "<the file's text>"}` lists
  the POST / PUT / PATCH operations a Custom API agent can be (`method`,
  `path`, summary) and the file's `servers` (use one as the record's base
  URL). Nothing is saved; the address and keys still go only in the vault.
- Tool platforms (`mcp`, `zapier`, `composio`, `n8n`) are **not** external
  agents on this page — they are set up on the Tools page.
- **Custom agents are an API or A2A, nothing else:** the page offers
  "Custom: API" (`custom_api`) and "Custom: A2A" (`a2a` with a custom 'External
  agent' record) first. `framework: custom` (your own Python function) is not
  on the page.
- **The old shape still works.** An agent that writes `framework:` +
  `connector_config: {connection: …}` and no `external_agent` loads and runs
  as before (verified on 2.4.491); Studio's agent form lists only the page's
  entries.

### Managed-agent platforms (2.4.395/96)

The agent is **built and runs on the vendor's platform**; the mesh sends the
input and takes the finished result, keeping one conversation per mesh session.
Each is a normal `agent_type: external` with its `framework` set:

| `framework` | Platform |
|---|---|
| `claude_managed` | Claude Managed Agents |
| `openai_agents_api` | OpenAI Agents API (distinct from the self-hosted `openai_agents`) |
| `foundry_agents` | Microsoft Foundry Agents |
| `copilot_studio` | Microsoft Copilot Studio / Dynamics 365 |
| `vertex_agent_engine` | Google Vertex AI Agent Engine |
| `bedrock_agentcore` | AWS Bedrock AgentCore |
| `mistral_agents` | Mistral Agents (2.4.396) |
| `letta` | Letta (2.4.396) |
| `glean_agents` | Glean Agents (2.4.396) |

Every external agent can carry a monthly budget: where the platform reports
usage it is metered; where it does not, the mesh estimates each call and
reserves the agent's average before calling (set `price_per_1k_tokens` for a
cost budget). **Tools, playbook, follow-ups, image output, eager skills and
`sandbox` are LLM-only** — a config that sets one on an external agent must
remove it.

### A2A platform services (2.4.396)

Six enterprise agent platforms reached **over A2A**, each listed as its own
`framework` (its own Studio entry, Infrastructure card, and name in traces/cost) rather
than a bare `a2a`:

| `framework` | Platform |
|---|---|
| `servicenow` | ServiceNow AI Agents |
| `sap_joule` | SAP Joule agents |
| `workday` | Workday agents |
| `box` | Box AI agents |
| `atlassian_rovo` | Atlassian Rovo agents |
| `gemini_enterprise` | Gemini Enterprise agents |

Each takes the agent's A2A address (its agent-card URL) from that vendor. An
A2A agent whose Agent Card changes is quarantined until a person re-approves it.

### External Policy

One block on the external agent governs everything that goes out and comes
back. With no block at all the agent is already safe: only its own configured
host, HTTPS, a 1 MB reply cap, quarantine after 5 failures in a row, and vault
secrets never sent.

**An agent with no address is not set up (2.4.490).** When the connector's
address is empty (n8n / Lindy `webhook_url`, A2A `url`, CrewAI / LangGraph /
AutoGen / Foundry `endpoint`, `custom_api` / Glean / Relevance `base_url`,
Agentforce `domain_url`, watsonx `service_url`, MCP `url` — or `command` for
stdio), the agent is switched off at start with "not set up". It is never
called and never counts toward `quarantine_after` (before 2.4.490 every run
called it, it failed at once, and the 5th failure quarantined it). Put the
address in the vault record; the agent switches back on with no restart.
`framework: custom` is exempt.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allowed_hosts` | list | `[]` | Hosts it may call **besides** the host of its own configured URL (`url` / `endpoint` / `webhook_url` / `base_url`). Exact names or `*.example.com`. Host names, not URLs — a URL is refused at load. Any other host is refused; non-local hosts must use HTTPS |
| `max_response_bytes` | int | `1000000` | Largest reply accepted. A larger reply is refused as a failure — never silently cut short |
| `quarantine_after` | int | `5` | Consecutive failures after which calls fail at once without reaching it, until a person releases it with `POST /api/agents/{name}/release`. A success resets the count |
| `send_fields` | list | unset (= every field) | Only these top-level input fields are sent — the conversation history, chain history and rerun note too only when listed. Vault secrets and other internal fields are never sent either way |
| `redact` | list | `[]` | Extra regular expressions replaced with `[redacted]` in everything sent. A pattern that does not compile is refused at load |
| `allowed_tools` | list | unset (= every tool the host allows) | **2.4.486, agents that run tools in this process (`claude_agent`).** Only these tools may be called: a name (`Read`), a name pattern (`mcp__leafmesh__*`) or a tool with an argument pattern (`Bash(git *)`). Only narrows the host rights — it can never grant a tool |
| `denied_tools` | list | `[]` | **2.4.486, same agents.** Tools never called, same forms (`Bash(rm *)`, `WebFetch`). A denied call goes back to the model with the reason and is recorded on the run. A rule in neither form is refused at load |

A cancelled call (its session ended) is neither a success nor a failure for
`quarantine_after`. An invalid policy refuses the call rather than falling
back to looser defaults. A programmatic agent with an `integration:` is
governed by the same block.

`external_policy.skills` and `unknown_skill_risk` were removed with the other
approval fields (2.4.382): a skill marked `send` / `spend` / `delete`, or
`unknown_skill_risk` set to one of those, **refuses the config at load**.
A person who must see a call first is a human agent routed in before it.

```yaml
agents:
  vendor_quote_agent:
    name: "vendor_quote_agent"
    agent_type: "external"
    framework: "langgraph"
    communication_type: "chain"
    connector_config:
      connection: "vendor-langgraph"   # External agents → LangGraph: address + key
      graph_id: "quote"
    monthly_cost_budget: 50.0         # langgraph reports spend, so this can stop it
    external_policy:
      allowed_hosts: ["files.vendor.example", "*.cdn.vendor.example"]
      max_response_bytes: 200000      # a bigger reply is a failure, never cut short
      quarantine_after: 3             # 3 failures in a row → quarantined until released
      send_fields: ["sku", "quantity"]   # only these input fields go out
      redact: ["\\b\\d{16}\\b"]       # card-like numbers become [redacted]
```

**Monthly budget on an external agent.** `monthly_token_budget` /
`monthly_cost_budget` meter the spend the connector reports into the same
month. A connector that reports none (`custom`, `n8n`, `zapier`, `mcp`, `a2a`,
`composio`, `flowise`, …) is metered by estimate: before each call the gate reserves the agent's last call's spend, and tokens are estimated from what the mesh sends and receives. `monthly_token_budget` always applies; `monthly_cost_budget` needs `price_per_1k_tokens` on the agent to price the estimate (without it only a token budget can stop it). Vellum, Claude Agent and OpenAI Agents report their spend (2.4.385).
Running out is a failure: with `budget_on_exhaust: graceful` it is marked as a
budget stop, with `escalate` a plain failure — never an empty success. Each
call reserves what the agent's last call cost, so racing calls cannot
overspend.

### Request form

`request_form` is sent with every request in the framework's own slot:

| Framework | Where it goes |
|---|---|
| `n8n`, `stackai` | the request body |
| `a2a` | the message's `metadata` |
| `langgraph` | `config.configurable` |
| `dify`, `wordware`, `crewai` | `inputs` |
| `flowise` | `overrideConfig.vars` |
| `lyzr` | `system_prompt_variables` |
| `vellum` | `inputs` |
| `agentforce` | `variables` |
| `mcp`, `zapier`, `composio` | the tool's arguments |

```yaml
    request_form:
      region: "eu-west"
      priority: "high"
      crm_token: "${vault:crm.api_key}"   # resolved per call, in the request's tenant
```

- **Refused at load and save:** more than 50 keys; over 16 KB as JSON; a key
  that is empty, longer than 64 characters, starts with `_`, or holds anything
  but letters, digits, `_`, `-`, `.`; a secret written inline (use
  `${vault:<connection>.<field>}`); values that are not JSON.
- **Refused for** `writer`, `watsonx`, `autogen`, `hermes`, `relevance`,
  `claude_agent`, `openai_agents`, `custom_api` (2.4.486 — its body is the
  agent's input), `custom` (no slot on the path the connector uses), and on any agent that is not external or a programmatic agent with an
  `integration`.
- It never overrides a value the SDK sets (message, session or conversation
  ids): a clashing key is warned about once, and the SDK's value is sent.
  Values are never logged; the trace shows key names only. Read on every call,
  so an edit applies at once.

> **One agent = one action/workflow.** Each agent targets one specific endpoint, graph, tool, or action. Create multiple agents with different `connector_config` values to call different workflows.
>
> All `connector_config` fields can also be overridden per-call via `request.connector_config` at runtime.

### Common connector_config fields (all frameworks)

These fields are available on **every** connector type (external agents and programmatic agents with an `integration`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `connection` | string | — | **The only place the account comes from.** Name of a vault connection: Infrastructure → External agents → `<framework>`, or an "Add custom" record with service type 'External agent' whose base URL is the address (zapier / composio / n8n / mcp: Infrastructure → Integrations → `<name>`, or a Custom connection with service type Tools). Its keys, fields, base URL and header rows are merged in (2.4.486: a record carries header rows only — see [the vault keeps sign-in only](nuances-and-gotchas.md#vault-only-values-24481)). Resolved again on every call and when the connection is rotated — no restart. Zapier uses `vault_connection` (its `connection` is an app slug). An agent that picks an entry of the External agents page (`external_agent:`) gets this filled in from the entry |
| `account` | string | — | **Programmatic agent with an `integration` only (2.4.486):** the name of a Zapier / Composio / n8n / MCP entry on the **Tools page**. The mesh signs in with the vault record that entry picks (Studio writes this when you pick a Tools-page account on a programmatic agent). An account that is not on the Tools page, or picks no record, is logged as an error and the agent runs with no sign-in |

**Vault-only (2.4.482).** Written in `connector_config` — literal, `${ENV}` or
`${vault:…}` — these keys **fail to load**, naming them and the record to
create: `url`, `endpoint`, `base_url`, `api_base`, `webhook_url`, `domain_url`,
`service_url`, `iam_url`, `token_endpoint`, `directline_base`, `mcp_endpoint`,
`headers`, `entries`, `api_key`, `user_api_key`, `api_token`, `token`,
`auth_token`, `bearer_token`, `mcp_key`, `secret`, `password`,
`basic_user`/`basic_password`, `client_id`, `client_secret`, `tenant_id`,
`managed_identity_client_id`, `webhook_secret`, `direct_line_secret`,
`aws_access_key_id`/`aws_secret_access_key`/`aws_session_token`, `role_arn`,
`external_id`, `role_session_name`, `web_identity_token_file`,
`service_account_json`, `credential_config_json`, `azure_token_audience`,
`auth_mode`, `auth_scheme`, any `entry:*` key — plus, per framework,
`foundry_agents` `resource`/`project`, `relevance` `region`/`project_id`,
`stackai` `org_id`, `glean_agents` `instance`, `composio`
`connected_account_id`/`toolkit`, `bedrock_agentcore` `region`,
`vertex_agent_engine` `project_id`. An `mcp` connector's `env` entry whose name
looks like a credential (key/token/secret/password/auth…) is refused too — add
it as a secret body row on the connection; its body rows become the command's
environment (**2.4.486 caveat:** an "Add custom" record of service type 'Tools' now keeps header rows only — a body row is refused on save, and one saved earlier is no longer sent — so this path for a stdio command's secrets does not work on such a record in 2.4.486 (an open SDK question).). Non-credential settings (`mode`, timeouts, graph / agent /
assistant ids, prompts) stay inline. In the tables below such fields are marked
*vault*: they are fields of the picked connection.

**Env Fallback column — struck through = no longer read (2.4.485).** An
external agent's address, keys and ids come **only** from its vault record:
58 connector variables (`CREWAI_*`, `LANGGRAPH_*`, `A2A_*`, `N8N_*`,
`ZAPIER_*`, `COMPOSIO_*`, …) are not read any more. Boot logs one line for
each one still set in the environment, naming where its value goes now
("`CREWAI_ENDPOINT` is set but is no longer read — … picked with
`connection`"). What stays: model keys (`claude_agent` → `ANTHROPIC_API_KEY`,
`openai_agents` → `OPENAI_API_KEY`, only when the agent names no key and no
connection) and the host's own cloud identity (`AWS_*`, `AZURE_*`).
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
| `endpoint` | string | `""` | **yes** | ~~`CREWAI_ENDPOINT`~~ | *vault* — HTTP endpoint for deployed CrewAI crew |
| `api_key` | string | `""` | no | ~~`CREWAI_API_KEY`~~ | *vault* — Bearer Token for authentication |
| `user_api_key` | string | `""` | no | ~~`CREWAI_USER_API_KEY`~~ | *vault* — User Bearer Token (preferred over `api_key` when both are set) |
| `poll_interval` | float | `2.0` | no | — | Seconds between status polls |
| `max_poll_seconds` | float | `300.0` | no | — | Max total polling time (seconds) |
| `http_timeout` | float | `30.0` | no | — | HTTP request timeout (seconds) |

#### langgraph

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `endpoint` | string | `""` | **yes** | ~~`LANGGRAPH_ENDPOINT`~~, ~~`LANGCHAIN_ENDPOINT`~~ | *vault* — LangGraph Platform deployment URL |
| `api_key` | string | `""` | no | ~~`LANGCHAIN_API_KEY`~~, ~~`LANGGRAPH_API_KEY`~~ | *vault* — API key |
| `graph_id` | string | — | **yes** | — | **Which graph (assistant) to run** — this is the workflow selector; no default |
| `poll_interval` | float | `1.0` | no | — | Seconds between status polls |
| `max_poll_seconds` | float | `300.0` | no | — | Max total polling time (seconds) |
| `http_timeout` | float | `30.0` | no | — | HTTP request timeout (seconds) |

#### autogen

Connects to an external AutoGen Studio or custom AutoGen API service via HTTP.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `endpoint` | string | `""` | **yes** | ~~`AUTOGEN_ENDPOINT`~~ | *vault* — AutoGen service base URL (e.g. `http://localhost:8081`) |
| `api_key` | string | `""` | no | ~~`AUTOGEN_API_KEY`~~ | *vault* — Bearer token for authentication |
| `workflow_id` | string | `""` | no | — | Workflow/agent ID to execute on the AutoGen service |
| `timeout` | float | `120.0` | no | — | HTTP request timeout (seconds) |
| `poll_interval` | float | `2.0` | no | — | Seconds between status poll requests |
| `max_poll_seconds` | float | `300.0` | no | — | Max total polling time (seconds) |

#### a2a

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `url` | string | `""` | **yes** | ~~`A2A_AGENT_URL`~~ | *vault* — A2A agent server base URL. The card is read at `/.well-known/agent-card.json` (older agents `/.well-known/agent.json`); A2A 1.0 (`SendMessage` / `GetTask`) is used when the card says so, else 0.3, and a call the agent answers in the other dialect is retried once in it |
| `auth_token` | string | `""` | no | ~~`A2A_AUTH_TOKEN`~~ | *vault* — Bearer token for authentication |
| `auth_scheme` | string | `"Bearer"` | no | — | *vault* — Authorization header scheme |
| `poll_interval` | float | `2.0` | no | — | Seconds between task status polls |
| `max_poll_seconds` | float | `300.0` | no | — | Max total polling time (seconds) |
| `http_timeout` | float | `30.0` | no | — | HTTP request timeout (seconds) |

#### custom_api (2.4.486)

An agent of your own behind an HTTP API. The vault record ("Add custom",
service type 'External agent') holds the address (its base URL) and the
sign-in (header rows — an External agent record carries header rows only,
2.4.486). What is sent is set here — normally on the External agents page
entry:

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `method` | string | `"POST"` | no | `POST`, `PUT` or `PATCH` |
| `path` | string | `""` | no | Appended to the record's base URL (empty = the base URL itself) |
| `query` | dict | `{}` | no | Fixed query values sent on every call |
| `answer_path` | string | `""` | no | Dot path to the answer in the JSON reply (`data.answer`, `items.0.text`); empty = the whole reply. A path the reply does not have fails the call, naming the missing step |
| `http_timeout` | float | `120.0` | no | Seconds (also accepts `timeout`) |

**The body is the agent's input** (the mesh's own `_…` keys left out), so a
field the API wants is one of the agent's `inputs` — `request_form` is refused
on `custom_api`. Needs `httpx`.

#### lindy (2.4.406)

A Lindy agent is **webhook-triggered and callback-answering**. It is started by a POST to the agent's Lindy *Webhook Received* trigger; Lindy does **not** answer in that HTTP response — it replies by calling back. So `mode: callback` is the mode that actually returns a result; `mode: sync` (the default for every connector) only *starts* the Lindy agent — it returns an answer only if the triggering webhook's own reply happens to carry a `result` (it normally doesn't), so use `callback`.

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `webhook_url` | string | `""` | **yes** | *vault* — The *Webhook Received* trigger's URL. Without it the agent is not set up — switched off at start, never called (2.4.490) |
| `webhook_secret` | secret | — | no | *vault* — The trigger's Generate-Secret value. **Store it in the vault** (it is a secret, not a literal) |
| `mode` | string | `"sync"` | no | `"callback"` is the real mode (Lindy answers by POSTing back); `"sync"` only starts the Lindy — it returns an answer only if the webhook's reply carries a `result` (normally it doesn't) |
| `callback_timeout` | float | `120.0` | no | Seconds to wait for Lindy's callback (used only in `mode: callback`) |
| `http_timeout` | float | `30.0` | no | Timeout for the triggering POST (seconds) |
| `connection` | string | — | no | Vault connection whose credentials are merged in |

**Wiring the callback in Lindy** (for `mode: callback`): add a *Send POST Request to Callback* action (or an HTTP Request action POSTing to `{{webhook_received.request.body.callbackUrl}}`). The mesh injects `_leafmesh_callback_url`, `_leafmesh_session_id` and `_leafmesh_request_id` into the trigger body; the callback must echo `_leafmesh_session_id` and `_leafmesh_request_id` back alongside the `result`, so the mesh matches the answer to the waiting request.

#### mcp (as a connector — one tool, one agent)

> **Read this first — there are two ways to use MCP, and this is the older,
> narrower one.** What follows describes MCP as a *connector*: the whole agent
> becomes a single call to a single remote tool, named by `tool_name`.
>
> If what you want is "this agent can use the tools that server offers", you
> want the **agent-level `mcp:` block** instead — see *MCP servers as tools*
> below. That is the right default. Reach for the connector form only when the
> agent genuinely *is* one remote call and nothing else.

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
| `env` | dict | `null` | no | Environment variables for the subprocess — no credentials (refused by name); secret body rows of the `connection` become the environment (2.4.486: a custom 'Tools' record can no longer hold body rows — see the caveat above) |

**http transport fields:**

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `url` | string | `""` | **yes** (http) | *vault* — MCP server HTTP/SSE endpoint |
| `auth_token` | string | `""` | no | *vault* — Bearer token |

---

### `api_tools:` — call an HTTP API from its OpenAPI / Swagger file (2.4.419+)

When the system an agent needs is a plain HTTP API with an OpenAPI 3.0 / 3.1 or
Swagger 2.0 file, **do not write a tool for it.** The owner uploads the file
once on Studio's **Tools page** (API tab, or `POST /api/infra/api-tools`), and
any LLM agent names the entry:

```yaml
agents:
  orders_agent:
    name: orders_agent
    agent_type: llm
    model: gemini-2.5-flash
    api_tools: [shop]            # the entry's name on the Tools page
```

The agent gets a short list of the endpoints it may call and two tools:
`api_find` (the best-matching endpoints with their exact inputs) and
`api_call` (call one). Do not list `api_find` / `api_call` under `tools:`.

**Things that will bite you if you don't know them:**

- **The owner switches every endpoint.** Reads start on, writes start off. An
  endpoint that is off is never shown to the model and is refused if called.
  When the need the agent has matches an endpoint that is switched off, the
  agent is told so by name ("'get_pet_by_id' … is switched off") and passes
  that on to the person (2.4.446) — also when another endpoint that is on only
  half-matches the need (2.4.447). "The agent says it can't" usually means the
  endpoint is off on the Tools page, not that the agent is broken.
- **Sign-in comes from the spec**: API key, bearer, basic, OAuth2 — kept in the
  vault, never in config.yaml. An endpoint whose sign-in the mesh cannot do
  stays off. Specs often ask for a key the API does not check: the owner can
  mark such endpoints as needing no sign-in, and they are then called without
  one.
- **The API's own answer reaches the person** (a 404 "not found", 400, 409,
  422), and the agent carries on with the rest of the task. A read that
  answers 500/502/503/504 is tried again; writes are never repeated. A service
  that stays down is told to the person in plain words.
- **Values are checked before anything is sent.** A wrong call comes back with
  the endpoint's exact inputs; a parameter spelt another way (`pet_id` for
  `petId`) is matched to the endpoint's own when only one fits. A call refused
  before sending gives its tool call back (up to 3 per message).
- **Big answers arrive as whole items** with `next_page.params` for the next
  call, never text cut mid-value.
- Requests go only to the entry's base URL, which may not carry a password or
  point at a link-local / cloud-metadata address.
- **Fixed query values (2.4.486)** are set on the entry's Tools page (`query`):
  sent on every call and never overridden by the model. A plain query value
  no longer lives in the vault record (see [the vault keeps sign-in only](nuances-and-gotchas.md#vault-only-values-24481)).
  The entry's API tools record keeps its sign-in: header rows, a key the API
  wants in the address as a **secret** query row, and an OAuth app's client id /
  secret or a username / password as body rows.

#### Tools → Webhooks — one hand-made endpoint (2.4.486)

A **webhook** is an entry in the same API library, made by hand on Tools →
Webhooks instead of uploaded: it picks an **Outbound webhook** vault record
(the address and sign-in) and sets the method (`POST` / `PUT` / `PATCH`), the
path, the body fields and fixed query values. Two uses:

- **An LLM agent calls it as a tool** — list it like an API:
  `api_tools: [crm_hook]`. The model fills its body fields. Its one endpoint
  is always switched on.
- **`notify` posts an agent's output to it** — the output is the body, in
  place of the fields. See [notify](#notify--post-the-output-to-a-webhook-24485).

### `mcp:` — MCP servers as tools (the normal way)

**This is the one you almost always want.** An agent declares the MCP servers it
may reach, and every tool those servers publish joins the tool list its model
already sees. No separate registration, and you do **not** name the tools again
under `tools:`.

`agents:` is a **mapping keyed by agent name**, never a list — a list is
rejected at load (`Input should be a valid dictionary`).

```yaml
agents:
  research_agent:
    name: research_agent
    agent_type: llm
    model: gpt-4o-mini
    mcp:
      - transport: stdio                  # a server you launch yourself
        command: python
        args: [./servers/inventory.py]
        name: inventory
        use: [search_docs, fetch_page]    # omit to expose every tool
```

**A server added on the Tools page is named, not written out** (2.4.421):
`mcp: [{server: github}]` — the entry holds the address and its vault
connection, and the owner switches each of its tools on or off there. The same
goes for `zapier: [{account: main}]`, `composio: [{account: gh}]` and
`n8n: [{account: ops}]`; `use:` narrows further. Rows written out in full, as
below, keep working.

**`changes_nothing: true` on a `zapier` / `composio` / `n8n` row (2.4.491,
default `false`)** says every action in that row only looks things up. A turn
whose tools all change nothing may be stored in the response cache and
replayed without running them. Mark it only when the answer also does not
depend on **when** it ran (a policy table, a rate card, static reference
data). A read of live data (an invoice's status, stock levels, a queue to
claim from) stays off — a replay would be stale. Leave it off if any action
sends, writes or deletes. `mcp:` rows have no such key: an MCP tool counts as
changing nothing when its server marks it `readOnlyHint`.

```yaml
    n8n:
      - account: rates          # a Tools-page n8n entry
        changes_nothing: true   # this workflow only returns the rate card
```

**An http MCP server: pick its vault record with `connection:`** — required
for `http` / `streamable_http` / `sse`.

```yaml
mcp:
  - transport: http
    connection: "mcp-search"      # MCP server connection: its url + token
                                  # (or an "Add custom" record, service type 'Tools', base URL = the address)
```

Since 2.4.481 `url:` and `token:` are **vault-only** — written in the row,
literal or `${ENV}`, the config fails to load naming the field. A stdio
server's `env:` may keep plain settings (`LOG_LEVEL: debug`), but a secret or an
address there is written as `${vault:<field>}` of the row's `connection`
(e.g. `GITHUB_PERSONAL_ACCESS_TOKEN: "${vault:token}"`); a literal is refused.

On **<=2.4.264 an authenticated MCP server could not be configured at all**:
`token` was refused, `${ENV}` resolved to it, and `connection:` was rejected
because `MCPServerConfig` forbade extra fields and never declared it — even
though the resolver had always read that field. 2.4.265 declares it.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `transport` | string | `"http"` | `"http"` for a hosted server, `"stdio"` for one you launch |
| `connection` | string | `""` | The server's vault record (its url + token) — **required** for `http` |
| `command` | string | `""` | Executable — **required** for `stdio` |
| `args` | list | `[]` | Arguments for the stdio command |
| `env` | dict | `{}` | stdio env; secrets/addresses only as `${vault:<field>}` of `connection` |
| ~~`url`~~, ~~`token`~~ | — | — | **Refused at load since 2.4.481** — they live on the `connection` record |
| `use` | list | `[]` | Only expose these tools; empty means all of them |
| `name` | string | derived | Namespace prefix; derived from the server when unset |
| `timeout` | float | `30.0` | Per-call timeout in seconds |

**Things that will bite you if you don't know them:**

- **Tools are namespaced.** A tool arrives as `<server>_<tool>` — `inventory_search`,
  not `search` — so two servers can both publish `search` without colliding.
- **`tools:` is a positive allowlist for LOCAL tools only.** MCP tools are merged
  in automatically. An agent whose tools are all remote can omit `tools:`
  entirely; adding the MCP tool names there does nothing useful.
- **Scoped to the declaring agent.** Another agent cannot call your server's
  tools unless it declares the server too. Same rule as local tools.
- **They run like any other tool** — same permission check, same timeout, same
  guardrail on tool output, same execution record. A model can call an MCP tool
  and a local tool in the same turn, in parallel or in sequence.
- **A server that is down at startup does not stop the agency.** The agent starts
  without that server's tools and logs a warning.
- **Set `tool_choice` / `allow_parallel_tool_calls` on the agent as usual** — they
  apply to MCP tools too (SDK ≥ 2.4.112; earlier builds dropped these settings
  when saving an agent that had no local `tools:`).

#### zapier

Tool name is built as `{connection}_{action}` (e.g. `google_sheets_create_row`).

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `connection` | string | `""` | yes* | — | Zapier app name (e.g. `"google_sheets"`, `"slack"`, `"gmail"`) |
| `action` | string | `""` | yes* | — | Action name (e.g. `"create_row"`, `"send_message"`) |
| `mcp_key` | string | `""` | **yes** | ~~`ZAPIER_MCP_KEY`~~ | *vault* — Zapier MCP key — every call goes through Zapier MCP. On the record `vault_connection` picks |
| `mcp_endpoint` | string | Zapier's MCP server | no | — | *vault* — Override the Zapier MCP address |
| `vault_connection` | string | — | no | — | Vault connection holding the key (Zapier's `connection` is the app slug) |
| `timeout` | float | `60.0` | no | — | HTTP request timeout (seconds) |

*At least one of `connection` or `action` required for the tool name. There is
no REST fallback any more (2.4.385): Zapier retired the AI Actions API it used,
so `api_key`, `prefer_mcp` and `instructions` are gone — an agent with only the
old `api_key` fails with that explanation.

#### composio

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `action` | string | `""` | **yes** | — | **Composio action enum** (e.g. `"GITHUB_STAR_A_REPOSITORY"`) — the workflow selector |
| `entity_id` | string | `"default"` | no | ~~`COMPOSIO_ENTITY_ID`~~ | User/entity context for managed auth |
| `api_key` | string | `""` | no | ~~`COMPOSIO_API_KEY`~~ | *vault* — Composio API key |
| `timeout` | float | `60.0` | no | — | Execution timeout (seconds) |

#### n8n

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `webhook_url` | string | `""` | **yes** | ~~`N8N_WEBHOOK_URL`~~ | *vault* — Full webhook trigger URL — **one URL per n8n workflow**. Empty: the agent is not set up — switched off, never called (2.4.490) |
| `auth_token` | string | `""` | no | ~~`N8N_AUTH_TOKEN`~~ | *vault* — Bearer token |
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
| `endpoint` | string | `"http://127.0.0.1:8642"` | no | ~~`HERMES_ENDPOINT`~~ | *vault* — Hermes API server base URL |
| `api_key` | string | `""` | no | ~~`HERMES_API_SERVER_KEY`~~, ~~`API_SERVER_KEY`~~ | *vault* — Bearer token (the host-side `API_SERVER_KEY`) |
| `model` | string | `"hermes-agent"` | no | — | Model name sent in the request |
| `api_mode` | string | `"chat"` | no | — | API surface: `"chat"` (`/v1/chat/completions`) or `"responses"` (`/v1/responses`, server-side multi-turn memory) |
| `system_prompt` | string | `""` | no | — | Optional system message prepended to the call |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### lyzr

Calls a Lyzr Agent Studio hosted agent through its synchronous inference API; returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `agent_id` | string | `""` | **yes** | ~~`LYZR_AGENT_ID`~~ | **Which Studio agent to invoke** — the workflow selector |
| `api_key` | string | `""` | **yes** | ~~`LYZR_API_KEY`~~ | *vault* — Header API key (`x-api-key`) from the agent's "Agent API" panel |
| `endpoint` | string | `"https://agent-prod.studio.lyzr.ai"` | no | ~~`LYZR_ENDPOINT`~~ | *vault* — Lyzr inference base URL |
| `user_id` | string | `"leafmesh"` | no | ~~`LYZR_USER_ID`~~ | Who Lyzr attributes the run to |
| `api_mode` | string | `"chat"` | no | — | API surface: `"chat"` or `"stream"` (streamed chunks assembled into one answer) |
| `system_prompt_variables` | dict | `{}` | no | — | Lyzr system-prompt template variables |
| `filter_variables` | dict | `{}` | no | — | Lyzr filter/routing variables |
| `features` | list | `[]` | no | — | Lyzr feature toggles passed through to the agent |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### writer

Calls Writer's (Palmyra) OpenAI-compatible chat/agents API; returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | ~~`WRITER_API_KEY`~~ | *vault* — Bearer API key |
| `endpoint` | string | `"https://api.writer.com"` | no | ~~`WRITER_ENDPOINT`~~ | *vault* — Writer API base URL |
| `model` | string | `"palmyra-x5"` | no | — | Writer model to call |
| `system_prompt` | string | `""` | no | — | Optional system message prepended to the call |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### dify

Calls a Dify hosted chat/agent app through its blocking chat endpoint; returns the full reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | ~~`DIFY_API_KEY`~~ | *vault* — Per-app API key (NOT the account key) |
| `endpoint` | string | `"https://api.dify.ai/v1"` | no | ~~`DIFY_ENDPOINT`~~ | *vault* — Dify API base URL |
| `user_id` | string | `"leafmesh"` | no | ~~`DIFY_USER_ID`~~ | End-user identifier Dify attributes the run to |
| `app_mode` | string | `"chat"` | no | — | **Which Dify app surface to call**: `"chat"` (chat-messages) or `"completion"` (completion-messages) |
| `input_key` | string | `"query"` | no | — | For completion apps, the input variable name the message maps to |
| `inputs` | dict | `{}` | no | — | Extra Dify app input variables |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### flowise

Calls a Flowise chatflow/agentflow prediction endpoint; returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `chatflow_id` | string | `""` | **yes** | ~~`FLOWISE_CHATFLOW_ID`~~ | **Which chatflow/agentflow to run** — the workflow selector |
| `endpoint` | string | `"http://localhost:3000"` | no | ~~`FLOWISE_ENDPOINT`~~ | *vault* — Flowise instance base URL |
| `api_key` | string | `""` | no | ~~`FLOWISE_API_KEY`~~ | *vault* — Optional bearer key (flows are public unless a key is assigned) |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

> **`voiceflow` and `cognigy` were removed in 2.4.395.** They build voice and
> chat bots; LeafMesh agents are task agents. A config naming either framework
> refuses to load. If you still need one, call its endpoint through a `custom`
> connection (set its address and headers in an "Add custom" record on the
> Infrastructure page).

#### vellum

Calls a Vellum workflow deployment through its synchronous execute endpoint; returns the selected output inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | ~~`VELLUM_API_KEY`~~ | *vault* — API key (sent in `X-API-KEY`, NOT Bearer) |
| `workflow_deployment_name` | string | `""` | yes* | ~~`VELLUM_WORKFLOW_DEPLOYMENT_NAME`~~ | **Which workflow deployment to run** — the workflow selector |
| `workflow_deployment_id` | string | `""` | yes* | — | Alternative to `workflow_deployment_name` |
| `endpoint` | string | `"https://predict.vellum.ai"` | no | ~~`VELLUM_ENDPOINT`~~ | *vault* — Vellum API base URL |
| `release_tag` | string | `""` | no | — | Optional release tag to pin the deployment version |
| `input_name` | string | `"message"` | no | — | Which workflow input the mesh message maps to |
| `output_name` | string | `""` | no | — | Which named output becomes the reply (defaults to the first output) |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

*Either `workflow_deployment_name` or `workflow_deployment_id` is required.

#### stackai

Calls a Stack AI exported flow through its synchronous run endpoint; returns the selected output inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | ~~`STACKAI_API_KEY`~~ | *vault* — Bearer API key |
| `org_id` | string | `""` | **yes** | ~~`STACKAI_ORG_ID`~~ | *vault* — Stack AI organization id (in the run URL) |
| `flow_id` | string | `""` | **yes** | ~~`STACKAI_FLOW_ID`~~ | **Which flow to run** — the workflow selector (in the run URL) |
| `endpoint` | string | `"https://stack-inference.com"` | no | ~~`STACKAI_ENDPOINT`~~ | *vault* — Stack AI inference base URL |
| `input_key` | string | `"in-0"` | no | — | Which flow input key the mesh message maps to |
| `output_key` | string | `""` | no | — | Which output field becomes the reply (defaults to surfacing the whole outputs object) |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### agentforce

Calls a Salesforce Agentforce agent via the Agent API (OAuth token → open session → send message); returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `agent_id` | string | `""` | **yes** | ~~`AGENTFORCE_AGENT_ID`~~ | **Which Agentforce agent to invoke** — the workflow selector |
| `domain_url` | string | `""` | **yes** | ~~`AGENTFORCE_DOMAIN_URL`~~ | *vault* — Org My Domain URL (e.g. `https://mycompany.my.salesforce.com`) — used for OAuth |
| `client_id` | string | `""` | **yes** | ~~`AGENTFORCE_CLIENT_ID`~~ | *vault* — Connected/External Client App client id (client-credentials flow) |
| `client_secret` | string | `""` | **yes** | ~~`AGENTFORCE_CLIENT_SECRET`~~ | *vault* — Connected/External Client App client secret |
| `api_base` | string | `"https://api.salesforce.com"` | no | ~~`AGENTFORCE_API_BASE`~~ | *vault* — Agent API base URL |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### watsonx

Calls an IBM watsonx Orchestrate agent through its OpenAI-compatible chat endpoint (IBM Cloud key → IAM bearer token, or a ready bearer); returns the reply inline.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `service_url` | string | `""` | **yes** | ~~`WATSONX_SERVICE_URL`~~ | *vault* — Orchestrate service instance URL (per-tenant) |
| `api_key` | string | `""` | yes* | ~~`WATSONX_API_KEY`~~ | *vault* — IBM Cloud API key (exchanged for an IAM bearer token) |
| `bearer_token` | string | `""` | yes* | ~~`WATSONX_BEARER_TOKEN`~~ | *vault* — A ready IAM bearer token (skips the key exchange) |
| `agent_id` | string | `""` | yes† | ~~`WATSONX_AGENT_ID`~~ | **Which Orchestrate agent to invoke** — the workflow selector (goes in the request path) |
| `iam_url` | string | `"https://iam.cloud.ibm.com/identity/token"` | no | — | *vault* — IBM IAM token endpoint |
| `chat_path` | string | `""` | no | — | Full override of the path after `service_url` (built from `agent_id` when unset) |
| `model` | string | `""` | no | — | Optional model name sent in the payload |
| `system_prompt` | string | `""` | no | — | Optional system message prepended to the call |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

*One of `api_key` or `bearer_token` is required. †`agent_id` is required unless an explicit `chat_path` is given.

#### relevance

Calls a Relevance AI agent via its async trigger + poll API; returns the agent's answer once the run completes.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `project_id` | string | `""` | **yes** | ~~`RELEVANCE_PROJECT_ID`~~ | *vault* — Relevance project id (half of the `{project_id}:{api_key}` auth token) |
| `api_key` | string | `""` | **yes** | ~~`RELEVANCE_API_KEY`~~ | *vault* — Relevance API key |
| `agent_id` | string | `""` | **yes** | ~~`RELEVANCE_AGENT_ID`~~ | **Which agent to trigger** — the workflow selector |
| `region` | string | `""` | no | ~~`RELEVANCE_REGION`~~ | *vault* — Region used to build the base URL (`https://api-{region}.stack.tryrelevance.com`) |
| `base_url` | string | `""` | no | ~~`RELEVANCE_BASE_URL`~~ | *vault* — Explicit base URL (overrides `region`) |
| `poll_interval` | float | `3.0` | no | — | Seconds between async polls |
| `max_poll_seconds` | float | `120.0` | no | — | Max total polling time (seconds) |
| `http_timeout` | float | `60.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

#### wordware

Calls a Wordware released app (NDJSON streaming run); the connector assembles the streamed output into one final answer.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | **yes** | ~~`WORDWARE_API_KEY`~~ | *vault* — Bearer API key |
| `app_id` | string | `""` | **yes** | ~~`WORDWARE_APP_ID`~~ | **Which released app to run** — the workflow selector |
| `endpoint` | string | `"https://app.wordware.ai"` | no | ~~`WORDWARE_ENDPOINT`~~ | *vault* — Wordware API base URL |
| `version` | string | `"^1.0"` | no | — | App version constraint sent with the run |
| `input_key` | string | `"message"` | no | — | Which app input the mesh message maps to |
| `inputs` | dict | `{}` | no | — | Extra app input variables |
| `http_timeout` | float | `300.0` | no | — | HTTP request timeout (seconds; also accepts `timeout`) |

> **In-process agent SDKs (frameworks, not HTTP services).** The two connectors below run an agent SDK locally inside the LeafMesh process — there is no hosted endpoint to POST to. (Raw Claude/OpenAI model calls live in the LLM provider layer, not here.)

#### claude_agent

Runs an agent built on the Claude Agent SDK (`claude-agent-sdk`) in-process through its streaming client (`ClaudeSDKClient`, 2.4.486); returns the final result. Requires `pip install claude-agent-sdk` and the Claude Code CLI on the host.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | no | `ANTHROPIC_API_KEY` | *vault* — Anthropic API key (passed to the SDK subprocess via options.env). The host's `ANTHROPIC_API_KEY` (else Claude Code's own login on the host) is used only when the agent names no key and no connection; a `connection` that holds no key **refuses the run** — it never falls back to the host's key (2.4.486) |
| `model` | string | `""` | no | — | Model the agent runs on (SDK default when empty) |
| `system_prompt` | string | `""` | no | — | System prompt for the agent |
| `max_turns` | int | `null` | no | — | Max agent turns (SDK default when unset) |
| `allowed_tools` | list | `null` | no | — | **Host right.** Tools the agent is allowed to use |
| `permission_mode` | string | `""` | no | — | **Host right.** One of Claude Agent's modes: `default`, `acceptEdits`, `plan`, `bypassPermissions` |
| `cwd` | string | `""` | no | — | **Host right.** Working directory for the agent run |
| `setting_sources` | list | `[]` | no | — | **Host right (2.4.486).** Which of the host's own Claude Code settings it loads: `user`, `project`, `local`. Default none — the host's CLAUDE.md and settings do not change the agent; whatever is loaded is fingerprinted into the run's versions |
| `disallowed_tools` | list | `null` | no | — | **Host right (2.4.486).** Tools it may never use |
| `sandbox` | dict | `null` | no | — | **Host right (2.4.486).** Claude Code's command sandbox settings, e.g. `{enabled: true}` |
| `timeout` | float | `600.0` | no | — | Max run time (seconds; also accepts `http_timeout`) |

> **Host rights** — `cwd`, `allowed_tools`, `permission_mode`,
> `setting_sources`, `disallowed_tools`, `sandbox` — say what the agent may do
> on this machine, so every API write (Studio included) still refuses them.
> **Since 2.4.485 they are changed from the host** with the `leafmesh` command
> (it finds the store from `.env`, prints the change, and saves only after
> `--yes` or a typed `apply`; the save is the store's next version and every
> pod applies it):
>
> ```bash
> leafmesh agent host-rights coder --cwd /srv/work --allowed-tools Read,Edit,Bash \
>     --permission-mode acceptEdits
> leafmesh agent host-rights coder --setting-sources project --disallowed-tools WebFetch \
>     --sandbox '{"enabled": true}'
> leafmesh agent host-rights coder --clear allowed_tools --yes
> ```
>
> `--setting-sources`, `--disallowed-tools` and `--sandbox` arrived in 2.4.486.
> The agent must exist in the stored configuration with `framework:
> claude_agent` written on it; the command refuses any other agent. Writing them
> in a configuration before it is first loaded into the store still works too.
>
> **What the mesh controls while it runs (2.4.486):** Stop, a quarantine, the
> session ending or the run's timeout first asks Claude Code to interrupt its
> turn, then cancels it. Every tool call is decided by the mesh against the
> agent's `external_policy.allowed_tools` / `denied_tools` (they only narrow
> the host rights) and `allowed_hosts` (checked on WebFetch, WebSearch and URLs
> in Bash); a denied call goes back to the model with its reason and is
> recorded on the run. Each tool call is a live span under the run.
> `max_budget_usd` is set from the agent's budget share for the run. A declared
> `yields` is enforced as structured output. The board and the agent's declared
> `tools:` reach it as an in-process MCP server named `leafmesh`. File
> checkpointing is on: the files changed, a diff stat and the checkpoint id are
> recorded. An option the installed `claude-agent-sdk` lacks is left out and
> named on the run (`sdk_missing`).

#### openai_agents

Runs an agent built on the OpenAI Agents SDK (`openai-agents`) in-process via `Runner.run()`; returns `final_output`. Requires `pip install openai-agents`.

| Field | Type | Default | Required | Env Fallback | Description |
|-------|------|---------|----------|-------------|-------------|
| `api_key` | string | `""` | no | `OPENAI_API_KEY` | *vault* — OpenAI API key (per-run model provider; falls back to env when empty) |
| `name` | string | `"LeafMesh Agent"` | no | — | Agent name |
| `instructions` | string | `""` | no | — | Agent instructions (the system prompt) |
| `model` | string | `""` | no | — | Model the agent runs on (SDK default when empty) |
| `max_turns` | int | `null` | no | — | Max agent turns (SDK default when unset) |
| `timeout` | float | `600.0` | no | — | Max run time (seconds; also accepts `http_timeout`) |

---

## Device Block

`device:` on an LLM agent gives it the `device_action` tool: it can ask a
device to do something and read the outcome. Off by default.

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `connection` | string | **required** | a vault connection name | A **notifier** connection that rings the device: `fcm`, `mqtt`, `apns`, `webpush`, `hms`, `wns`, `expo`, `onesignal`, `azure_iot_hub`, `aws_iot`, `sns`, `azure_notification_hubs`, `pusher_beams`, `twilio_sms` |
| `room` | string | unset (= LeafCraft rooms) | a vault connection name | Where the mesh and the device meet: `room` (your own room service — its `url` + `api_key` only), `mqtt` (the same connection can be notifier and room), `pubnub`, `ably`, `pusher`, `livekit` |
| `approval` | string | `"ask"` | `ask`, `silent` | `ask`: the device asks its owner before it joins; nothing runs unless they allow it. `silent`: it joins without asking |

```yaml
agents:
  home_helper:
    name: "home_helper"
    agent_type: "llm"
    model: "gpt-4o-mini"
    prompt: "When the user asks for something done on their device, use device_action and report the outcome exactly."
    communication_type: "chain"
    device:
      connection: "phone-push"        # a NOTIFIER connection on the Infrastructure page (fcm, mqtt, apns, …)
      # room: "my-room"               # optional room connection; left out = LeafCraft rooms
      approval: "ask"                 # ask (default): the device asks before it joins | silent
```

Outcomes the tool returns: `done` (with the device's `data`, untrusted),
`failed`, `declined`, `sent_for_approval`, `not_joined`, `unreachable`,
`refused`. Every outcome but `done` carries `success: false` and an `error`.
Gotchas are in [nuances-and-gotchas.md — Devices](nuances-and-gotchas.md#22-devices--the-device-comes-from-the-conversation).

---

## Programmatic Agent Fields (`agent_type: "programmatic"`)

These fields are used when `agent_type` is `"programmatic"`.

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `integration` | string | `null` | `zapier`, `composio`, `n8n`, `mcp`, `python` | What a programmatic agent runs through: a connector, or `python` (2.4.492) — pure Python, your function is the whole agent, switched off while that function is not in the running project. Unset or a connector: never switched off for code |
| `connector_config` | dict | `{}` | integration-specific key-values | Same fields as the matching external framework connector — see tables above |

**Validation rule:** `integration` is only valid when `agent_type` is `"programmatic"`.

When `integration` is set, `connector_config` is passed as `**kwargs` to the connector's `__init__`. Use the same fields as the matching framework in the tables above (zapier → zapier fields, mcp → mcp fields, etc.).

**Picking a Tools-page account (2.4.486).** The sign-in can come from an
account already set up on the Tools page instead of a raw vault record:

```yaml
  order_pusher:
    name: order_pusher
    agent_type: programmatic
    integration: n8n
    connector_config:
      account: ops            # the n8n account's name on the Tools page — it picks the vault record
```

This is what Studio writes when you pick a Tools-page account on a
programmatic agent (`programmatic_writes` in `GET /api/infra/choices`).

The common fields (`mode`, `callback_timeout`) are also available here — programmatic agents with connectors support the same sync/callback modes as external agents.

---

## WebhookConfig

Used inside `webhook_config` for human agents (only on a `webhook` seat — an Inbox seat has none).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `connection` | string | `null` | The vault record the seat's webhook uses: an **"Add custom" record on the Infrastructure page, service type 'Outbound webhook'**. Its base URL is where the request is POSTed; its header rows are headers; a secret row named `inbound_token` (a header-placed row) is the token the reply POST must present (never sent out). **Since 2.4.486 the record keeps sign-in only:** a query or body row is refused when the record is saved, and one saved earlier is no longer sent (start logs each one by name). The SDK's own field description still says "query rows on the URL, body rows into the payload" — that is out of date. |
| `outbound_timeout` | int | `30` | Timeout for outbound calls (seconds) |
| `inbound_endpoint` | string | `null` | Endpoint path for inbound responses (e.g. `"/webhook/human_contact"`). If not set, derived from entry points. |
| `response_mapping` | dict | `{}` | Field mapping for webhook response transformation |
| `max_retries` | int | `3` | Max retry attempts for failed outbound webhooks |
| `retry_delay` | int | `5` | Delay between retries (seconds) |
| `operators` | dict | `{}` | Operator id → the **name** of that person's own vault record ("Add custom" record, service type 'Outbound webhook'), used with `_target_operator` in `pre_compose`. An address here is refused at load. |
| ~~`outbound_url`~~, ~~`outbound_headers`~~, ~~`inbound_auth_token`~~ | — | — | **Refused at load since 2.4.481** (vault-only): the address, header rows and `inbound_token` row live on the record `connection` picks. See [Vault-only values](nuances-and-gotchas.md#vault-only-values-24481). |

---

## ChannelConfig

Used inside `channels` dict for human agents. Keys are provider names.

### Supported Provider Keys

| Key | Provider | Threads? |
|-----|----------|----------|
| `slack` | Slack Bot API | yes |
| `teams` | Microsoft Teams Bot Framework | yes |
| `discord` | Discord Bot API | yes |
| `email` | SMTP/IMAP, or Mailgun / SendGrid / Postmark | yes (In-Reply-To / References) |
| `telegram` | Telegram Bot API | no |
| `cliq` | Zoho Cliq | no |
| `whatsapp` | WhatsApp Business API (Meta Cloud API) | no |

"Threads?" decides how a reply finds its conversation, and whether a question
the mesh asks in a shared room can be answered there at all — see THE ROOM
RULES in SKILL.md. A channel without threads gives each person one continuous
conversation.

### Fields Per Channel

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `connection` | string | `null` | **The only path.** Names a connection held in the mesh's vault, carrying the provider's WHOLE credential set and its addresses. Since 2.4.481 any vault field written in the block — `bot_token`, `signing_secret`, `app_token`, `verify_token`, `smtp_password`, `api_key`, `app_id`/`client_id`/`tenant_id`, `service_url`, `base_url`, `smtp_host`/`smtp_port`/`smtp_username`, `attachments.storage_url` … — **fails to load** naming the field, whether literal or `${ENV}`. Rows below marked *vault* are fields of the connection, not of this block. |
| `bot_token` | string | `null` | *vault* — Bot/API token, on the connection. |
| `signing_secret` | string | `null` | *vault* — Request verification secret, on the connection. |
| `app_token` | string | `null` | *vault*, **Slack only** — app-level (`xapp-`) token on the Slack connection. Its presence turns Socket Mode on: inbound arrives over an outbound WebSocket, so **no public URL is needed**. Essential for a local or NAT'd mesh. |
| `socket_mode` | bool | auto | **Slack only** — defaults to true when an `app_token` exists. Set `false` to force the webhook route on a mesh that has a public URL. |
| `operators` | dict | `{}` | Logical operator id → that channel's user handle, so a step can address a named person. Read in reverse on inbound, so the same person is recognised across channels. |
| `operators_only` | bool | `false` | Refuse anyone not listed in `operators` — checked BEFORE addressing, so it holds in a DM too. Off by default: a customer-facing seat must accept strangers. An empty `operators` map with this on fails CLOSED. |
| `service_url` | string | `null` | *vault*, **Teams only** — the Bot Framework endpoint (on the Teams connection), needed when the mesh SPEAKS FIRST (nothing inbound has arrived to learn it from). Use the global `https://smba.trafficmanager.net/teams/`; Microsoft warns against region-specific URLs. |
| `listen_channels` | list | `[]` | Channel/chat IDs to accept inbound messages from (empty = all) |
| `post_channel` | string | `null` | Default channel/chat ID for outbound messages (see per-provider notes below) |
| `verify_token` | string | `null` | *vault* — Webhook verification token on the WhatsApp connection — **WhatsApp only** (`hub.verify_token`) |
| `operators` | dict | `{}` | Declared field (v2.2.44+). Per-operator routing map: operator name → provider address/ID (e.g. Slack user ID for a DM). Used to route a human agent's message to a specific person. See the example below. |

**Note:** `ChannelConfig` allows extra fields (`extra="allow"`) for any provider-specific config.

### Per-Provider Field Semantics

`bot_token`, `signing_secret` and `verify_token` are fields of the provider's vault connection; only `post_channel` is written in the block.

| Provider | `bot_token` | `signing_secret` | `post_channel` | `verify_token` |
|----------|------------|------------------|----------------|----------------|
| `slack` | Bot OAuth token (`xoxb-…`) | Slack signing secret (HMAC-SHA256) | Channel ID (e.g. `C123456`) | — |
| `telegram` | Bot token from @BotFather | Secret token set when registering webhook | Chat ID | — |
| `discord` | Bot token (without `Bot ` prefix) | App public key (Ed25519 — requires `pynacl`) | Channel ID | — |
| `whatsapp` | Meta Graph API access token | Meta app secret (HMAC-SHA256) | Phone number ID | `hub.verify_token` for webhook registration |
| `teams` | Bot Framework App ID | Bot Framework App password | Conversation ID | — |

### Inbound Route Registered Per Provider

| Provider | Route |
|----------|-------|
| `slack` | `POST /channels/slack/{agent_name}/events` |
| `telegram` | `POST /channels/telegram/{agent_name}/webhook` |
| `discord` | `POST /channels/discord/{agent_name}/interactions` |
| `whatsapp` | `GET /channels/whatsapp/{agent_name}/webhook` (verification) + `POST` (messages) |
| `teams` | `POST /channels/teams/{agent_name}/messages` |

### Example

Every credential comes from a **connection** made on the Infrastructure page. One
connection carries that provider's whole credential set, so there is exactly
one line per channel — no token fields at all. Writing a token field here (as
a literal *or* as `${ENV}`, which resolves to one) makes the mesh refuse to
boot; see **Where each secret lives** in SKILL.md.

```yaml
channels:
  slack:
    connection: "slack-workspace"                 # bot_token + signing_secret + app_token
    listen_channels: ["C123456", "C789012"]
    post_channel: "C123456"
    operators:                                    # v2.2.44+ per-operator routing
      alice: "U0ALICE"                            # Slack user ID (DM)
      bob:   "U0BOB"

  telegram:
    connection: "telegram-bot"
    listen_channels: []                            # empty = all chats
    post_channel: ""
    operators:
      alice: "12345678"                           # Telegram chat_id

  discord:
    connection: "discord-bot"
    listen_channels: ["987654321098765432"]
    post_channel: "987654321098765432"

  whatsapp:
    connection: "whatsapp-business"
    post_channel: "123456789012345"                # phone number ID, not a phone number
    # verify_token lives on the whatsapp connection (refused here since 2.4.481)
    operators:
      alice: "+14155551234"                       # WhatsApp phone number

  teams:
    connection: "teams-bot"
    post_channel: ""                               # set at runtime from inbound activity
    # service_url (needed only when the mesh speaks first) lives on the teams connection
```

### Dynamic Per-Call Routing (v2.2.44+)

`operator_ids` is the logical roster. Each channel's `operators:` map resolves those logical ids to channel-specific recipient ids (Slack user IDs, WhatsApp numbers, email addresses). Pre-compose then steers per call by setting `_target_operator` in `input_data`:

```python
from leafmesh import pre_compose

@pre_compose(input_processor=lambda data, ctx: {
    **data,
    "_target_operator": _todays_oncall(),    # "alice" Mon, "bob" Tue, ...
})   # NOTE: the kwarg is `input_processor` (the real @pre_compose params are
     # context_processor / input_processor / others_processor). `input_data=`
     # is NOT a recognized processor — it silently lands in **processors and never runs.
async def escalation_agent(input_data, context):
    return {"alert": input_data["incident"]}
```

With Slack + WhatsApp configured, the same `_target_operator: "alice"` dispatches to alice's Slack DM AND alice's WhatsApp number in parallel — each channel pulls from its own `operators:` map. Fail-soft: if alice has no entry under `whatsapp.operators`, WhatsApp falls back to `post_channel`.

Other pre-compose routing keys (escape hatches for dynamic recipients):

| Key | Effect |
|---|---|
| `_target_channel_id` | Raw recipient id — bypasses operator lookup; useful when the id comes from Zapier / DB lookup |
| `_target_channel_provider` | Pins outbound to one provider when several configured (`"slack"`) |
| ~~`_target_webhook_url`~~ | **No longer read** (2.4.481, vault-only) — logs a warning. Set `_target_operator` and map it under `webhook_config.operators` to that person's vault record |

---

## Event Listeners — BRD-021

Fire agents automatically when an **external event** arrives — Kafka, SQS, MQTT, Redis Streams, or IMAP. Two-part config: declare broker connections at the top level, then bind agents via per-agent `listen_events:`.

**Install** (only what you need):
```bash
pip install leafmesh[kafka]       # aiokafka
pip install leafmesh[sqs]         # aioboto3
pip install leafmesh[mqtt]        # asyncio-mqtt (listener lands in a follow-up)
pip install leafmesh[imap]        # aioimaplib (listener lands in a follow-up)
pip install leafmesh[listeners]   # bundle all four
# Redis Streams uses the core redis dep — no extra needed
```

### Top-level `brokers:` block

Each entry is one connection to a message source. Reference by name from per-agent `listen_events`.

**Vault-only since 2.4.481.** A broker's address, sign-in and secrets live on a
vault connection of the broker's type (Infrastructure → Brokers & queues →
Apache Kafka / AWS SQS / MQTT / Redis Streams / IMAP Mailbox); the block picks it with
`connection: <name>` and keeps only how the broker behaves. Writing a vault field
below in the block — literal or `${ENV}` — **fails to load** naming the field.
`connection:` is required for kafka, mqtt, redis_streams and imap (SQS without
one signs in with the deployment's own AWS identity). A named connection that
doesn't exist yet doesn't block boot: the consumer is switched off until it is
created — see [Vault-only values](nuances-and-gotchas.md#vault-only-values-24481).

#### KafkaBrokerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"kafka"` | Literal — must be `"kafka"` |
| `connection` | string | (required) | The kafka vault connection |
| `security_protocol` | string | `null` | `PLAINTEXT` \| `SSL` \| `SASL_PLAINTEXT` \| `SASL_SSL` |
| `sasl_mechanism` | string | `null` | `PLAIN` \| `SCRAM-SHA-256` \| `SCRAM-SHA-512` \| `GSSAPI` \| `OAUTHBEARER` \| `AWS_MSK_IAM` |
| `sasl_kerberos_service_name`, `oauth_scope`, `aws_region`, `aws_role_arn` | string | `null` | Mechanism-specific behaviour |
| `ssl_cafile` / `ssl_certfile` / `ssl_keyfile` | string | `null` | Paths on the host to CA cert / client cert / client key |
| *vault* | | | `bootstrap_servers`, `sasl_username`, `sasl_password`, `oauth_token_url`, `oauth_client_id`, `oauth_client_secret`, `ssl_ca_pem`, `ssl_cert_pem`, `ssl_key_pem`, `ssl_key_password` |

#### SQSBrokerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"sqs"` | Literal — must be `"sqs"` |
| `connection` | string | `null` | The sqs vault connection; unset → the deployment's own AWS identity |
| `region` | string | `null` | AWS region (default: read from the queue URL) |
| `role_arn` / `role_session_name` / `external_id` | string | `null` | A role to assume (cross-account) |
| *vault* | | | `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token`, `endpoint_url` |

#### MQTTBrokerConfig

Allowed keys: `type`, `connection`, `use_tls`, `ssl_cafile`, `ssl_certfile`, `ssl_keyfile`, `client_id`, `keepalive_s`.

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"mqtt"` | Literal — must be `"mqtt"` |
| `connection` | string | (required) | The mqtt vault connection; its `url` is `mqtt://host:port` (or `mqtts://` for TLS) |
| `use_tls` | bool | `false` | Enable TLS for the broker connection |
| `ssl_cafile` / `ssl_certfile` / `ssl_keyfile` | string | `null` | Paths on the host (private CA / mTLS) |
| `client_id` | string | `null` | MQTT client ID (random if unset) |
| `keepalive_s` | int | `60` | Keepalive interval in seconds |
| *vault* | | | `host`, `port` (→ the record's `url`), `username`, `password`, `ssl_ca_pem`, `ssl_cert_pem`, `ssl_key_pem`, `ssl_key_password` |

#### RedisStreamsBrokerConfig

Allowed keys: `type`, `connection`, `db`.

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"redis_streams"` | Literal — must be `"redis_streams"` |
| `connection` | string | (required) | The redis_streams vault connection; its `url` is `redis://`, `rediss://` or `unix://` |
| `db` | int | `0` | Redis DB number |

Use this when an upstream service writes events into a Redis stream you want an agent to consume. **Distinct from the SDK's primary Redis** (used for sessions/yields/feed) — that one, with the mesh's Postgres, stays in `.env`: the one exception to vault-only.

#### IMAPBrokerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"imap"` | Literal — must be `"imap"` |
| `connection` | string | (required) | The imap vault connection |
| `auth` | string | `"password"` | `password` \| `oauth2` |
| `oauth_provider` / `oauth_grant` / `oauth_scope` | string | `null` | oauth2 behaviour |
| `use_tls` | bool | `true` | Enable TLS |
| *vault* | | | `host`, `port`, `username`, `password`, `oauth_client_id`, `oauth_client_secret`, `oauth_refresh_token`, `oauth_tenant_id`, `oauth_token_url` |

### Per-agent `listen_events:` — `EventListener`

Each entry binds the agent to one source on one broker.

| Field | Type | Default | Description |
|---|---|---|---|
| `broker` | string | (required) | Name of a broker in the top-level `brokers:` block |
| `topic` | string | `null` | **Kafka** topic to subscribe to |
| `group_id` | string | `null` | **Kafka** consumer group (defaults to `<sdk-name>-<agent-name>`) |
| `queue` | string | `null` | **SQS** queue URL or name |
| `stream` | string | `null` | **Redis Streams** stream key |
| `consumer_group` | string | `null` | **Redis Streams** consumer group |
| `mqtt_topic` | string | `null` | **MQTT** topic filter (supports `+` and `#` wildcards) |
| `qos` | int | `1` | **MQTT** QoS level: `0` at-most-once, `1` at-least-once, `2` exactly-once |
| `folder` | string | `"INBOX"` | **IMAP** folder to monitor |
| `poll_interval_s` | float | `null` | **IMAP** polling interval in seconds (IMAP doesn't push) |
| `unseen_only` | bool | `true` | **IMAP** — process only UNSEEN messages |
| `filter` | dict | `null` | CloudEvents-style attribute filter — message must match ALL `(key, value)` pairs (AND-semantics) |
| `deserialize` | string | `null` | Pydantic class for payload deserialization, format `"module.path:ClassName"`. `ValidationError` routes to DLQ |
| `delivery.max_retries` | int | `3` | Retry attempts before DLQ |
| `delivery.backoff` | string | `"exponential"` | `linear` or `exponential` |
| `delivery.backoff_initial_s` | float | `1.0` | Initial backoff in seconds |
| `delivery.backoff_max_s` | float | `60.0` | Cap on backoff delay |
| `delivery.dead_letter` | dict | `null` | DLQ destination — `{broker, topic/queue/stream}` |
| `batch_size` | int | `1` | Messages fetched per poll cycle (1–1000) |
| `visibility_heartbeat` | bool | `false` | **SQS only** — auto-extend visibility timeout while a long-running handler executes |

### Delivery semantics

- **At-least-once** across all sources. Idempotency keying is `(listener_name, message_id)` — handlers must be safe to re-execute on retry.
- After `delivery.max_retries`, the message routes to `delivery.dead_letter` if configured; otherwise it's logged and dropped.
- Listener tasks live for the SDK process lifetime — graceful shutdown via `sdk.stop()`.
- Listeners are **parallel** with mesh_call entry points and `wake_up` cron — independent trigger surfaces on the same agent.

### Full example

```yaml
brokers:
  orders_kafka:
    type: kafka
    connection: orders-kafka           # kafka connection: bootstrap_servers + SASL user/password
    security_protocol: SASL_SSL
    sasl_mechanism: SCRAM-SHA-512

  support_queue:
    type: sqs
    connection: support-aws            # sqs connection (omit to use the deployment's AWS identity)
    region: us-east-1

agents:
  order_processor:
    name: "order_processor"
    agent_type: programmatic
    listen_events:
      - broker: orders_kafka
        topic: orders.created
        group_id: leafmesh-order-processor
        batch_size: 10
        filter:
          type: "com.example.order.created"
          source: "/region/us-east-1"
        deserialize: "my_app.schemas:OrderEvent"
        delivery:
          max_attempts: 3
          backoff: exponential
          dead_letter:
            broker: orders_kafka
            topic: orders.dlq

      - broker: support_queue
        queue: support-tickets
        visibility_heartbeat: true
        batch_size: 5
```

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
| `experience` | bool | `true` (wherever memory is on) | `true`, `false` | The agent's own private long-term memory (`remember` / `recall_experience`). `experience: false` is the only opt-out: it keeps the shared activity feed and removes both tools from the prompt |

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
| ~~`timeout_threshold`~~ | — | — | **Removed in 2.4.486** — dropped with a warning when present. A question nobody answers is not escalated; the seat waits its time and stops |

---

## EscalationTarget

Each target in the `escalation.targets` list.

| Field | Type | Default | Accepted Values | Applies To |
|-------|------|---------|-----------------|------------|
| `type` | string | **required** | `human_agent`, `webhook`, `channel` | all |
| `agent` | string | `null` | agent name | `human_agent` |
| `entry_point` | string | `null` | entry point name | `human_agent` |
| `connection` | string | `null` | vault record name — an "Add custom" record, service type 'Outbound webhook' (base URL = the address, header rows = headers; the record keeps sign-in only since 2.4.486 — no query or body rows) | `webhook` |
| `method` | string | `"POST"` | `POST`, `PUT`, `PATCH` | `webhook` |
| `payload_template` | dict | `null` | JSON with `{{var}}` placeholders | `webhook` |
| `provider` | string | `null` | `slack`, `telegram`, `discord`, `whatsapp`, `teams` | `channel` |
| `channel_id` | string | `null` | channel ID | `channel` |
| `message_template` | string | `null` | text with `{{var}}` placeholders | `channel` |

A webhook target's `url` and `headers` are **refused at load since 2.4.481** (vault-only) — the shape is `{type: webhook, connection: <name>, method?, payload_template?}`.

### Example

```yaml
escalation:
  targets:
    - type: "human_agent"
      agent: "customer_support_team"

    - type: "webhook"
      connection: "incident-api"     # "Add custom" record, service type 'Outbound webhook': base URL + Authorization header row
      method: "POST"
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
| ~~`redis`~~ / ~~`persistence`~~ | — | — | — | **Not read (2.4.482).** The datastore is set in `.env` only — see [Datastore (.env only)](#datastore-env-only). A block in the YAML is ignored with a boot warning on 2.4.482–2.4.485; from 2.4.486 `LeafMesh.from_yaml` raises `ConfigError` when its values differ from `.env`, naming each `.env` line to add (a block that matches still loads, with the warning) |
| `manager` | object | see [ManagerConfig](#managerconfig) | — | Manager coordination + analysis |
| `mesh` | object | see [MeshConfig](#meshconfig--cloud-providers) | — | Mesh network + cloud providers |
| `agents` | dict | `{}` | agent name → AgentConfig | Agent configurations |
| `entry_points` | list | `[{"name": "default_entry", "target": "summarizer", "condition": "always"}]` | see [Entry Points](#entry-points) | Named portals into mesh |
| `data_structures` | dict | `{}` | name → DataStructure | Custom data type definitions |
| `auto_discover` | dict | `null` | `{"directory": "path", "pattern": "*.py", "recursive": true}` | Auto-discover agent files |
| `evolution` | object | see [EvolutionConfig](#evolutionconfig) | — | Evolutionary optimization |
| `api` | object | see [APIConfig](#apiconfig) | — | Declared top-level field. HTTP API server config (host/port/etc.). Because `LeafMeshConfig` is `extra="forbid"`, `api` must appear here, not as an extra. |
| `evolution_api` | object | `{enabled: true, host: 127.0.0.1, port: 19820}` (as a blank agency writes it) | — | Config for the evolution API surface. Distinct from `evolution`. **The only settings that need a process restart** (2.4.484) |
| `security` | object | `{telemetry_redact_pii: true}` | — | `telemetry_redact_pii` (default **true** since 2.4.480): each content value in traces reads `<redacted bytes:N>`; `false` keeps what each agent received and replied readable. Credentials are masked either way; LeafCraft's own prompts are always hidden (`<platform_prompt:N chars>`, `<elided:N chars>`). Replaces the env var `LEAFMESH_OTEL_REDACT_PII`, no longer read |
| `kanban` | object | `{enabled: true}` | — | The mesh's one board — see SKILL.md → The shared board |
| `timeouts` / `scheduler` / `runtime` / `limits` / `connectors` | object | see [Runtime Config Blocks](#runtime-config-blocks-24131--timeouts--scheduler--runtime--limits--connectors) | — | Runtime knobs, every default written out |
| `self_healing` | object | see [Self-Healing](#self-healing-self_healing) | — | What the mesh does by itself when an agent keeps failing. Top-level block (NOT under `manager:`) |
| `brokers` | dict | `{}` | name → KafkaBrokerConfig \| SQSBrokerConfig \| MQTTBrokerConfig \| RedisStreamsBrokerConfig \| IMAPBrokerConfig | External broker connection definitions for [Event Listeners — BRD-021](#event-listeners--brd-021). Referenced by name from each agent's `listen_events:` block |

**Note:** `LeafMeshConfig` has `extra="forbid"` — unknown top-level keys will raise a validation error.

### When a saved setting applies (2.4.484)

A setting saved in Studio or through the config API applies **without anyone
pressing restart**, and every pod applies it the same way (another pod picks
the new version up within ~15 s, `runtime.config_sync_poll_s`):

| Setting | Applies |
|---|---|
| Everything not listed below — agents, routes, prompts, models, schedules, limits, timeouts, and every `manager.*` setting except `enabled` (rules, timing, routing, model, what it listens to; `manager.command_center` included) | **Live**, in place |
| `brokers`, `self_healing.enabled`, `api.cors_origins`, `runtime.lease_seconds`, `runtime.lease_heartbeat_s`, `architecture`, `auto_discover`, `limits.consumer_inflight_max`, `manager.enabled` | The agency **reloads itself in place** within seconds (listed in the save's `reloading_fields`); runs in flight finish first or are picked up again |
| `evolution_api.enabled`, `.host`, `.port` | **Process restart** (listed in `restart_required_fields`) |

A setting sent as `null` goes back to its default.

### Self-Healing (`self_healing:`)

Top-level block, `extra="forbid"`. Detection and a notice are on by default;
**acting** (restarting an agent, spawning a backup and routing to it) is off
until you turn it on — a backup is a second model-spending agent.

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `true` | Watch agent health; raise `healing.*` events and an inbox notice |
| `actions_enabled` | `false` | Allow the mesh to restart a failing agent or spawn a backup |
| `consecutive_failures` | `5` | Failures in a row before an agent is CRITICAL |
| `error_rate` | `0.3` | Error share of recent runs before CRITICAL |
| `latency_factor` | `3.0` | Recent latency ÷ the agent's OWN median before it counts as slow (judged once it has 20 runs) |
| `min_quality_score` | `0.4` | Reported quality score below which an agent is CRITICAL |
| `cooldown_s` | `600` | Seconds after an action before the same agent may be acted on again |
| `max_actions_per_hour` | `3` | Healing actions per agent per rolling hour |
| `max_backups_per_agent` | `1` | Backup agents that may exist for one failing agent |
| `monitoring_interval_s` | `5.0` | How often health is sampled, seconds |

```yaml
self_healing:
  enabled: true                 # watch + notify (default true)
  actions_enabled: false        # restart / spawn a backup (default false — opt in)
  consecutive_failures: 5
  error_rate: 0.3
  latency_factor: 3.0           # × the agent's OWN median latency
  min_quality_score: 0.4
  cooldown_s: 600
  max_actions_per_hour: 3
  max_backups_per_agent: 1
  monitoring_interval_s: 5.0
```

Old keys `detection_interval`, `max_recovery_attempts` and
`recovery_strategies` are **refused at load**. `manager.self_healing: true`
loads but does nothing — the block is top-level.

---

## ManagerConfig

| Field | Type | Default | Accepted Values | Description |
|-------|------|---------|-----------------|-------------|
| `enabled` | bool | `true` | `true`, `false` | Enable manager + summarizer |
| `model` | string | **none — declare it** | same as [Model List](#model-list) | LLM model for Summarizer analysis. No default since 2.4.135 (`ManagerConfig.model` and `SummarizerConfig.model` both default to `None`). With `enabled: true` and no model, `validate_config` DOES flag this one — `"Manager model is required for analysis when enabled"` — unlike a plain agent's missing model, which it lets through. |
| `domain` | string | `"generic"` | `generic`, `ecommerce`, `data_analysis` | Summarizer domain specialization |
| `prompt` | string | `null` | any string (multiline supported) | **Evaluation criteria** — tell the Manager what success looks like, what to escalate on, and what patterns to watch. Injected into every Summarizer analysis call as an `EVALUATION CRITERIA` section, alongside the domain prompt. |
| `can_intervene` | bool | `true` | `true`, `false` | Allow manager interventions (false = read-only) |
| `coordination_rules` | dict | `{}` | arbitrary key-values | User-defined business rules (`max_call_depth`, `agent_rules`, `reflection_budget`, …). **Never holds the rule sets below** (2.4.482) |
| `human_input_rules` / `workflow_pause_rules` / `human_response_rules` | dict | see [Defaults](#human_input_rules-defaults) below | — | The three Manager rule sets — **directly under `manager:`**, never under `manager.coordination_rules:` (2.4.482; a file that still nests them is moved at load, with a warning; if both places differ, the `manager.<name>` one wins). `timeout_rules` was **removed in 2.4.486** (dropped with a warning when present, also under `coordination_rules`) |
| `chain_completion_timeout` | float | `1800.0` | seconds | Wait time before checking chain completeness (`0` or negative switches the check off) |
| `health_check_interval` | int | `60` | seconds | Seconds between health checks |
| `agent_timeout_threshold` | int | `180` | seconds | Seconds before agent is timed out |
| `escalation` | object | `null` | see [EscalationConfig](#escalationconfig) | Escalation targets and rules |
| `routing` | dict | see below | — | Manager routing configuration |
| `feed_model` | string | `null` | same as [Model List](#model-list) | Optional separate model for the Manager's live activity-feed narration (falls back to `model`). |
| `temperature` | float | `0.1` | `0.0` – `2.0` | Temperature for the Manager/Summarizer analysis call. The Manager reads its own value (2.4.485 — a hardcoded 0.1 is gone) |
| `max_tokens` | int | `4000` | 1 – model max | Max output tokens for the Manager analysis call. The Manager reads its own value (2.4.485 — a hardcoded 800 is gone) |
| `analysis_style` | string | `"coordination"` | e.g. `coordination` | Style/persona applied to the Summarizer's analysis. |
| `omnipresent_mode` | bool | `true` | `true`, `false` | When true, the Manager observes every agent turn; false narrows its attention. |
| `triggers` | dict | `null` | arbitrary | Declarative triggers for Manager intervention. |
| `yields` | dict | `null` | yield contract | Optional yields contract for the Manager's own output. |
| `super_agent` | bool | `false` | `true`, `false` | Wrap the Manager's analysis in the Super-Agent orchestrator. |
| `knowledge` | bool \| object | `false` | `false`, or see [Knowledge Config](#knowledge-config) | Knowledge/RAG config available to the Manager. Defaults to `false` (off); set an object to enable. |

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
      - a specialist fails twice in a row on the same request

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

The rule sets below are written directly under `manager:` (2.4.482):

```yaml
manager:
  human_input_rules: {max_concurrent_requests: 3, max_agent_requests: 5, enable_request_queuing: true}
  coordination_rules:          # its OTHER keys only (max_call_depth, agent_rules, reflection_budget, …)
    max_call_depth: 5
```

| Field | Type | Default |
|-------|------|---------|
| `max_concurrent_requests` | int | `3` |
| `max_agent_requests` | int | `5` |
| `enable_request_queuing` | bool | `true` |

### ~~`timeout_rules`~~ — removed (2.4.486)

`max_timeouts_before_escalation`, `timeout_escalation_enabled` and
`escalation_notify_managers` are gone with the block: a question nobody
answers is not escalated (the seat waits its time and stops). A config that
still has `manager.timeout_rules` (or `manager.coordination_rules.timeout_rules`)
loads; the block is dropped with a warning.

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

The `timeout` scenario was **removed in 2.4.486** (dropped with a warning when
present): a seat waits its time and stops.

---

## MeshConfig & Cloud Providers

### MeshConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| ~~`call_timeout`~~ | — | — | **Gone (2.4.482).** The one setting is `timeouts.mesh_call_default_timeout_s` (default **300**, since 2.4.382 — not 30). An old `mesh.call_timeout` is moved there at load, with a warning. Not to be confused with the agent field `tool_call_timeout` |
| `max_chain_events` | int | `50` | Hard cap on chain events per session before the cycle breaker stops the chain (session `status: stopped` + `ChainCapExceeded` AGENT_ERROR; a new entry-point call on the session resets it). Raise for legitimately deep flows (research / batch fan-out) — never as a fix for an unbounded retry back-edge |
| `chain_context_depth` | int | `0` | Declared field. How many prior chain hops of context to carry forward to a downstream agent (`0` = none). |
| `chain_context_max_chars` | int | `500` | Declared field. Character budget for the carried-forward chain context (truncated beyond this). |
| `bedrock` | object | `null` | AWS Bedrock config |
| `vertex` | object | `null` | Google Vertex AI config |
| `foundry` | object | `null` | Microsoft Foundry/Azure AI config |
| `local` | object | `null` | Local model server config (vLLM, SGLang, Ollama, etc.) |

### BedrockConfig (AWS)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `connection` | string | `null` | AWS Bedrock connection (or an AWS identity) holding the region and, for a private endpoint, `endpoint_url` |
| `profile` | string | `null` | AWS profile from `~/.aws/credentials` on the host |

`region` and `endpoint_url` are vault-only — **refused at load since 2.4.481**. Left out, the environment / AWS profile / instance role signs in, with the region the AWS Bedrock connection holds.

### VertexConfig (Google Cloud)

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `connection` | string | `null` | no | Google Vertex connection (or a Google Cloud identity) holding `project_id` and `location` |

`project` and `location` are vault-only — **refused at load since 2.4.481** (`project` → the record's `project_id`). Left out, Application Default Credentials sign in, with the project and location the Google Vertex connection holds.

### FoundryConfig (Azure)

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `connection` | string | `null` | no | Azure Foundry connection (or an Azure identity) holding the endpoint (e.g. `https://<resource>.openai.azure.com`) and key |
| `api_version` | string | `null` | no | Azure API version (e.g. `2024-10-21`). Omit for v1 endpoint. |
| `auth_mode` | string | `null` | no | `service_principal` \| `api_key` \| `managed_identity` |

`endpoint` is vault-only — **refused at load since 2.4.481**.

### LocalModelConfig

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `connection` | string | `null` | no | The model server's vault record: a Self-hosted model connection (endpoint + key), or an "Add custom" record, service type 'Model' (base URL = the address, header rows = headers). Left out, the Self-hosted model connection on the Infrastructure page is used |
| `server_type` | string | `null` (auto-detect) | no | Server type: `openai`, `ollama`, `textgen`, `huggingface` |
| `timeout` | float | `120.0` | no | Request timeout in seconds |

`endpoint` and `headers` are vault-only in the YAML — **refused at load since 2.4.481**.

Env: `LOCAL_MODEL_ENDPOINT`, `LOCAL_MODEL_SERVER_TYPE` — same rule as
`OPENAI_API_KEY`: **set it in `.env`, or add a Local model connection on
Infrastructure → Models**. A value in `.env` wins; otherwise the vault
connection fills it at boot.

**Supported servers and their `endpoint` (on the connection) + `server_type`:**

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
    connection: vllm-box     # Self-hosted model connection: endpoint http://localhost:8000/v1/chat/completions + key
    server_type: openai
    timeout: 120
```

> **Moved in 2.4.393 — the model server is the mesh's, not the agent's.** The
> per-agent `custom_endpoint` and `custom_headers` fields were **removed**;
> set the local model server once in `mesh.local` (its `connection` — the
> endpoint and headers live on that vault record). A config that still carries `custom_endpoint`/`custom_headers` on an
> agent is told to move them here.

---

## Runtime Config Blocks (2.4.131) — `timeouts` / `scheduler` / `runtime` / `limits` / `connectors`

**2.4.131 moved ~49 runtime knobs out of `LEAFMESH_*` environment variables into five declared top-level YAML blocks. The old env vars are NO LONGER READ** — a template or `.env` that still sets them silently gets defaults. These are top-level siblings of `mesh:` / `manager:`.

Three rules for template authors:
1. **Every field is optional and omission is meaningful.** Absent = "not declared" → the SDK default applies. From **2.4.482** every default lives on its config field, and the YAML the SDK writes for a new agency carries **every** setting with its value (the blocks below included), so the file shows each value in force. In a template you write by hand, declare a block only where it genuinely needs a non-default (e.g. a long-running research agency setting `timeouts.llm_hard_timeout_s: 300`). Sending a setting as `null` in a config save puts it back to its default.
2. **Booleans are tri-state:** absent / `true` / `false`, and an explicit `false` ≠ absent (it round-trips through save+reload).
3. **Two knowledge *document* caps went per-provider, not into `limits`:** `settings.max_docs_per_ingest` (1000) and `settings.max_doc_bytes` (2 MiB) live under a knowledge provider's `settings:`.

The defaults, exactly as the SDK (2.4.484) writes them for a new (blank) agency:

```yaml
timeouts:                       # 8 fields
  llm_hard_timeout_s: 90.0      # per LLM call; retried once then fails (super-agent phases get 600)
  llm_tool_loop_timeout_multiplier: 3.0
  llm_tool_loop_timeout_cap_s: 600.0
  mesh_call_default_timeout_s: 300   # how long mesh_call waits with no timeout= (replaces mesh.call_timeout, 2.4.482)
  ack_completion_timeout_s: 600
  sse_session_ttl_s: 900
  hitl_redrive_grace_s: 20
  super_agent_max_dispatch_s: 14400
scheduler:                      # 7 fields
  cron_min_interval_seconds: 60 # floor; lower it to allow sub-minute intervals like "30s"
  misfire_grace_s: 3600
  followup_tick_s: 2.0          # 2, not 5
  followup_max_delay_s: 2592000
  followup_record_ttl_s: 604800
  hitl_reaper_interval_s: 600
  hitl_reaper_grace_s: 900
runtime:                        # 10 written (+ lease_heartbeat_s, see below)
  pubsub_poll_s: 5.0
  pubsub_ping_quiet_s: 30.0
  pubsub_dead_s: 90.0
  lease_seconds: 30
  dispatch_claim_ttl_s: 600
  eventbus_mode_guard_ttl_s: 30
  reclaim_min_idle_ms: 720000
  config_sync_poll_s: 15
  skills_eager: false           # mesh default for skill delivery (true = every skill body in the prompt)
  live_model_discovery: true    # "Set false for offline installs"
limits:                         # 18 fields
  webhook_max_payload_bytes: 1048576
  request_max_payload_bytes: 4194304
  webhook_rate_limit_max: 60
  webhook_rate_limit_window_s: 60
  webhook_replay_skew_s: 300
  max_session_history_bytes: 5242880
  session_gather_concurrency: 4
  session_idle_active_s: 1800
  max_parallel_tool_calls: 8
  tool_result_max_chars: 100000
  followup_context_max_kb: 16
  file_max_bytes: 10485760
  file_ttl_s: 604800
  knowledge_max_ingest_total_bytes: 52428800
  knowledge_query_rate_limit_max: 120
  knowledge_query_rate_limit_window_s: 60
  tool_failure_breaker: 3
  consumer_inflight_max: 64
connectors:                     # 3 fields — all default true
  traceparent_inject: true
  external_usage_stamp: true
  external_trace_capture: true
self_healing:                   # see Self-Healing above
  monitoring_interval_s: 5.0    # (+ the other nine fields, defaults as in that table)
security:
  telemetry_redact_pii: true    # default TRUE since 2.4.480 — customer text hidden in traces
mesh:
  max_chain_events: 50
  chain_context_depth: 0
  chain_context_max_chars: 500
  reply_stream: false           # default false; always ON in workers mode regardless
kanban:
  enabled: true
evolution_api:                  # the only settings that need a process restart
  enabled: true
  host: 127.0.0.1
  port: 19820
```

Also written for a blank agency (see their sections): `manager:` with
`domain: generic`, `temperature: 0.1`, `max_tokens: 4000`,
`chain_completion_timeout: 1800.0`, the four rule sets and `routing`;
`evolution:`; `agents: {}`; `entry_points: []`; `environment: development`.

**No fixed default — left out of the YAML on purpose:** `runtime.lease_heartbeat_s`
(= `lease_seconds / 3`), `api.public_base_url` (learned from the first
authenticated request's host until you pin it), `api.cors_origins` (empty
until you list origins).

**Dead env vars — no longer read. If you find one set anywhere, here is what it became:**

| Dead env var | Now |
|---|---|
| `LEAFMESH_LLM_HARD_TIMEOUT_S` | `timeouts.llm_hard_timeout_s` |
| `LEAFMESH_CRON_MIN_INTERVAL_SECONDS` | `scheduler.cron_min_interval_seconds` |
| `LEAFMESH_WEBHOOK_{MAX_PAYLOAD_BYTES,RATE_LIMIT_MAX,RATE_LIMIT_WINDOW_S,REPLAY_SKEW_S}` | `limits.webhook_*` |
| `LEAFMESH_MAX_SESSION_HISTORY_BYTES` | `limits.max_session_history_bytes` |
| `LEAFMESH_MAX_PARALLEL_TOOL_CALLS` | `limits.max_parallel_tool_calls` |
| `LEAFMESH_KNOWLEDGE_QUERY_RATE_LIMIT_*` | `limits.knowledge_query_rate_limit_*` |
| `LEAFMESH_KNOWLEDGE_MAX_INGEST_TOTAL_BYTES` | `limits.knowledge_max_ingest_total_bytes` |
| `LEAFMESH_KNOWLEDGE_MAX_DOCS_PER_INGEST` | per-provider `settings.max_docs_per_ingest` |
| `LEAFMESH_KNOWLEDGE_MAX_DOC_BYTES` | per-provider `settings.max_doc_bytes` |
| `LEAFMESH_MESH_REPLY_STREAM` | `mesh.reply_stream` |
| `LEAFMESH_SUPER_AGENT_*` | per-agent `super_agent:` dict |
| `LEAFMESH_MANAGER_*_TAIL` | `manager:` block |

Setting any of these produces no error and no effect — the mesh runs on the
default and nothing tells you.
**Still legitimately env:** `LEAFMESH_LICENSE_KEY`, `LEAFMESH_ENV_TOKEN`, `LEAFMESH_AGENCY_NAME`, the datastore names ([Datastore](#datastore-env-only)), `WEBHOOK_SECRET`, `INTERNAL_API_KEY`, `API_URL`/`API_PORT`, `EVOLUTION_API_PORT`, `SSE_COOKIE_SAMESITE`, `WORKERS`(_MODE), `MCP_COMMAND_ALLOWLIST`, `TEAMS_ALLOW_UNVERIFIED`, `YAML_ENV_BLOCKLIST(_EXTRA)`, `HSTS_ENABLED`, `REFERRER_POLICY`, `CSP`, `LEAFMESH_SKILLS_DIR`. **No longer read (2.4.480; boot warns if still set):** `LEAFMESH_OTEL_REDACT_PII` → `security.telemetry_redact_pii`, `LEAFMESH_SKILLS_EAGER` → `runtime.skills_eager`, `LEAFMESH_REGISTRY_LIVE_MODELS` → `runtime.live_model_discovery`. Also removed: `LEAFMESH_WEBHOOK_ALLOW_LEGACY_HMAC` (signed webhooks always need the timestamp and nonce) and the prompt-guardrail bypass (2.4.382 — the guardrail is always on).

> ⚠️ **The `timeouts` block is REJECTED by ≤2.4.130** (`from_yaml` raises `ConfigError`) — it is only valid on **2.4.131+**. Ship these blocks only when the template floor is `leafmesh>=2.4.131` or higher (the shipped templates now floor at 2.4.484).

---

## Datastore (.env only)

**From 2.4.482 the datastore is never in the YAML.** The agency's configuration,
vault, sessions and lessons all live inside the store, so where the store is
comes from the environment (`.env`, or a Kubernetes/cloud secret). A
`persistence:` or top-level `redis:` block in config.yaml is **ignored** on
2.4.482–2.4.485 (boot warns "the persistence block is no longer read"). From
**2.4.486, `LeafMesh.from_yaml` raises `ConfigError`** when such a block's values
differ from `.env`, and names each `.env` line to add (e.g. `REDIS_DB=3`); a
block that matches still loads, with the warning. Always remove it, and set the store
explicitly in `.env`: `LEAFMESH_STORE`, `LEAFMESH_AGENCY_NAME`, and `REDIS_URL` or
`REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` (Postgres:
`DATABASE_URL` or `POSTGRES_*`). Studio →
Infrastructure → Datastores (`GET /api/infra/datastore`) shows whether the store
is reachable, its latency, the server, the settings in force and which `.env`
names set them; it never shows the address or password. No longer configurable
(fixed by the mesh): `auto_storage` (on), `decode_responses` (on), Postgres
`pool_idle_lifetime_s` (60 s).

Set only what you need; unset names keep the SDK defaults.

| Env name | Default | Description |
|----------|---------|-------------|
| `LEAFMESH_STORE` | `redis` | `redis` \| `postgres` |
| `LEAFMESH_AGENCY_NAME` | — | The agency's name — every key in the store is filed under it. Needed by `LeafMesh.from_store()` (a project with no `config.yaml`); with `from_yaml` the name comes from the file's `name:`. If you set both, keep them equal: the name decides which part of the store (vault, board, configuration) the agency reads |
| `REDIS_URL` | — | Whole server in one value, e.g. `redis://user:pw@host:6379/4` (`rediss://` turns TLS on). The single `REDIS_*` names fill in what it leaves out |
| `DATABASE_URL` | — | Postgres in one value, e.g. `postgresql://user:pw@host:5432/db?sslmode=require`. The single `POSTGRES_*` names fill in what it leaves out |
| `REDIS_HOST` | `localhost` | Redis server host |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_PASSWORD` | unset | Redis password |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_DEFAULT_TTL` | `3600` | Default key TTL (seconds) |
| `REDIS_SESSION_TTL` | `604800` | Session TTL (seconds). **604800 (7 days)**, not 7200 |
| `REDIS_SSL` | `false` | Enable TLS for the Redis connection |
| `REDIS_SSL_CERT_REQS` | `required` | TLS verification mode: `required` \| `optional` \| `none` |
| `REDIS_SSL_CA_CERTS` | unset | Path to CA bundle for verifying the Redis server cert |
| `REDIS_SSL_CERTFILE` | unset | Client TLS cert path (mutual TLS) |
| `REDIS_SSL_KEYFILE` | unset | Client TLS private key path (mutual TLS) |
| `REDIS_SSL_CHECK_HOSTNAME` | `true` | Verify server hostname against certificate |
| `REDIS_CLUSTER_NODES` | unset | Comma-separated `host:port` list; setting it means cluster mode |
| `POSTGRES_HOST` | `localhost` | Postgres host (with `LEAFMESH_STORE=postgres`) |
| `POSTGRES_PORT` | `5432` | Postgres port |
| `POSTGRES_DB` | `leafmesh` | Database name |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | unset | Postgres login |
| `POSTGRES_SSLMODE` | the driver's default | Postgres TLS mode (e.g. `require`) |
| `POSTGRES_DEFAULT_TTL` | `3600` | Generic key TTL (seconds) |
| `POSTGRES_SESSION_TTL` | `604800` | Session lifetime (seconds, 7 days) |
| `POSTGRES_POOL_MIN` | `1` | Connection pool minimum |
| `POSTGRES_POOL_MAX` | `10` | Connection pool maximum |

---

## APIConfig

Top-level `api:` block Configures the SDK's HTTP server.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cors_origins` | list[string] | `[]` | Additional CORS origins, appended to the SDK's built-in defaults (`https://platform.leafcraft.ai` + localhost dev ports). Each entry must be a full origin (`scheme://host[:port]`). |
| `public_base_url` | string | unset | The address the outside world reaches this mesh at (`scheme://host[:port]`, nothing after the host). Unset → learned from the first authenticated request's host; set it to pin the address |

Neither has a fixed default, so the YAML the SDK writes for a new agency leaves both out on purpose (2.4.482).

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
| `mutation_types` | list | all six below | `agent_connections`, `communication_patterns`, `agent_parameters`, `workflow_sequences`, `resource_allocation`, `timeout_settings` | Mutation types. **This is a `Literal` list — any other value is REJECTED at load**, so the three names this table used to list (`prompt_variation`, `temperature_adjustment`, `tool_selection`) do not exist and will fail validation. Evolution mutates the mesh's *shape* (wiring, timeouts, allocation), not an agent's prompt or temperature. |
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

These are enforced by Pydantic validators in the SDK:

| Rule | Constraint |
|------|-----------|
| `agent_type` | Must be `llm`, `human`, `programmatic`, or `external` |
| `human_interface` | Must be `api`, `webhook`, `custom`, or `default` — anything else **raises at load** (used to fail silently at the first live request) |
| `entry_points` targets | `target` / `target_agent` must name a real agent — a typo **raises `ConfigError` at load** instead of failing at the first `mesh_call` |
| `model` | Unknown model id (no provider prefix, not in the catalog) goes to the local model server; with none set up it is refused (2.4.497; before, `default_provider`); a known provider with no key raises — see [Model List](#model-list) |
| prompt ↔ `yields` | A prompt committing to JSON keys with zero overlap with the `yields` schema **raises at load** (the "Hello!" silent-fallback bug class) |
| `temperature` + `yields` | `temperature > 0.5` with a yields contract **warns** — keep ≤ ~0.3 for structured output |
| `communication_type` | Must be `dual` or `chain`. `execute` is read as `chain` (`dual` on a human seat) with a deprecation warning |
| `optimization_strategy` | Must be `performance`, `cost`, or `speed` (or null) |
| `max_tool_calls_per_message` | Must be 0–20 |
| `tool_call_timeout` | Must be > 0 and <= 300 seconds |
| `tool_choice` | Must be a non-empty string (`auto`, `none`, or a tool name). Leave unset — the SDK pins its configured memory / knowledge / reasoning tools on the first turn; an explicit `auto` switches that off. |
| `framework` | A registered connector name or `custom` (or null). As of 2.4.491 (unchanged since 2.4.486): `crewai`, `langgraph`, `autogen`, `a2a`, `custom_api` (2.4.486), `mcp`, `zapier`, `composio`, `n8n`, `hermes`, `lyzr`, `writer`, `dify`, `flowise`, `vellum`, `stackai`, `agentforce`, `watsonx`, `relevance`, `wordware`, `lindy`, `claude_agent`, `openai_agents`, `claude_managed`, `openai_agents_api`, `foundry_agents`, `vertex_agent_engine`, `bedrock_agentcore`, `copilot_studio`, `mistral_agents`, `letta`, `glean_agents`, `servicenow`, `sap_joule`, `workday`, `box`, `atlassian_rovo`, `gemini_enterprise`, `custom`. **`lindy` added 2.4.406. Not** `voiceflow`/`cognigy` (removed 2.4.395) |
| `framework` required | When `agent_type` is `external`, `framework` must be set — or `external_agent` (2.4.486), which fills it in from the External agents page |
| `external_agent` | A `framework` / `connector_config` beside it that differs from the page's entry → **refused** (2.4.486) |
| Retired tools | `tools: [zapier_action \| mcp_call \| composio_action \| n8n_workflow]` → **refused at load** (2.4.485), naming the block that replaces each; `tool_categories: [integration]` → **refused** |
| `notify.webhook` | A name on Tools → Webhooks; an address (`://`, `www.`) → **refused**. `notify.when` must be `done`, `failed` or `both` (2.4.485) |
| `scaling.copies` on a human seat | `mode: auto` or `count` > 1 → **refused** (2.4.485) |
| `reply_reader` | Needs `model`; only `model`, `model_connection`, `prompt`, `temperature`, `max_tokens`, `memory`, `knowledge`, `skills`, `experience` (bool); `intent_model` / `intent_prompt` disagreeing with it → **refused** (2.4.486) |
| `external_policy.allowed_tools` / `denied_tools` | Each rule a tool name, a name pattern or `Tool(arg pattern)` — anything else **refused** (2.4.486) |
| `yields` list with no item type | **Warns** at start and in validate, at any depth, on LLM agents (2.4.486) |
| `super_agent.tries` | A map `{mode: fixed\|auto, count: 1–10, rounds: 1–10}` or a whole number 1–10; an unknown key, another mode or a number out of range → **refused** (2.4.491) |
| `integration` | Must be `zapier`, `composio`, `n8n`, `mcp`, `python` (2.4.492) (or null) |
| `integration` restricted | Only valid when `agent_type` is `programmatic` |
| Approval fields | `require_human_confirmation` / `confirmation_seat` / `human_escalation_triggers` ON, or `external_policy.skills` marked send/spend/delete, or `external_policy.unknown_skill_risk: send|spend|delete` → **refused at load** (approval is routing) |
| External monthly budget | On an external agent whose connector reports no spend (incl. `framework: custom`): not refused — metered by estimate; `monthly_cost_budget` with no `price_per_1k_tokens` can never bite and draws a load warning (2.4.497) |
| `memory_strategy` / `knowledge_strategy` | Must be `tool`, `inject` or `both` |
| `device.connection` | Required when `device:` is present; `approval` must be `ask` or `silent` |
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
| `represents` | — | U | — | — |
| `webhook_config` | — | U | — | — |
| `channels` | — | U | — | — |
| `framework` | — | — | — | R |
| `connector_config` | — | — | — | U |
| `integration` | — | — | U | — |
| `communication_type` | U | U | U | U |
| `scaling` | U | U\* | U | U |
| `monthly_token_budget` | U | — | — | U |
| `monthly_cost_budget` | U | — | — | U |
| `budget_on_exhaust` | U | — | — | U |
| `external_policy` | — | — | — | U |
| `device` | U | — | — | — |
| `fallback_models` | U | — | — | — |
| `model_connection` | U | — | — | — |
| `reply_reader` | — | U | — | — |
| `external_agent` | — | — | — | U |
| `notify` | U | U | U | U |
| `cache` | ✓ | — | — | — |
| `strict_tools` | ✓ | — | — | — |
| `memory_strategy` | ✓ | — | — | — |
| `knowledge_strategy` | ✓ | — | — | — |
| `wake_up_input` | U | U | U | U |
| `wake_up` | U | U | U | U |
| `timezone` | U | U | U | U |
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

\* `scaling` on a human seat: `runs.max` only — `copies` (`mode: auto` or `count` > 1) is refused since 2.4.485. `parallel` / `max_concurrent` / `instances` / `instances_handoff` are refused on every type (2.4.484).
