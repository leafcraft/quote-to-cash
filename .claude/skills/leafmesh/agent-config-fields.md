# LeafMesh Agent Configuration — Complete Field Reference

This document lists every configuration field, its type, default value, and accepted values. Use this to build frontend forms, dropdowns, and validation.

---

## Table of Contents

1. [Agent Types](#agent-types)
2. [AgentConfig — Core Fields (All Types)](#agentconfig--core-fields-all-types)
3. [LLM Agent Fields](#llm-agent-fields-agent_type-llm)
4. [Human Agent Fields](#human-agent-fields-agent_type-human)
5. [External Agent Fields](#external-agent-fields-agent_type-external)
6. [Programmatic Agent Fields](#programmatic-agent-fields-agent_type-programmatic)
7. [WebhookConfig](#webhookconfig)
8. [ChannelConfig](#channelconfig)
9. [Memory Config](#memory-config)
10. [EscalationConfig](#escalationconfig)
11. [EscalationTarget](#escalationtarget)
12. [Top-Level Config (LeafMeshConfig)](#top-level-config-leafmeshconfig)
13. [ManagerConfig](#managerconfig)
14. [MeshConfig & Cloud Providers](#meshconfig--cloud-providers)
15. [RedisConfig](#redisconfig)
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
| `description` | string | `null` | any string | no | Agent description and purpose |
| `agent_type` | string | `"llm"` | `llm`, `human`, `programmatic`, `external` | no | Agent execution type (see note below) |
| `communication_type` | string | `"dual"` | `dual`, `chain`, `execute` | no | How agent communicates with the mesh |
| `parallel` | bool | `false` | `true`, `false` | no | Enable parallel processing |
| `max_concurrent` | int | `null` | 1 – unlimited | no | Max concurrent calls when `parallel: true` (null = unlimited) |
| `wake_up` | string | `null` | cron expression (e.g. `"0 9 * * *"`) | no | Schedule for periodic wake-up |
| `listen_events` | list | `[]` | list of `EventListener` entries (see [Event Listeners](#event-listeners--brd-021)) | no | Bind agent to external event sources (Kafka, SQS, MQTT, Redis Streams, IMAP). Each entry references a broker from the top-level `brokers:` block. Parallel to `wake_up` — both are agent-level trigger surfaces |
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

Optional-contributor (`?`) semantics — current (v2.4.22+):

- An optional sibling **dispatched from the same upstream output** is
  **waited for** (in-flight counts as pending, not absent) — the fan-in
  no longer completes early with partial data while a sibling runs.
- Late arrivals to an already-completed fan-in are **dropped as
  redundant** — no re-trigger.
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
| `tool_choice` | string | framework-managed | `auto`, `required`, `none`, or specific tool name | Tool selection strategy. **Leave unset** for framework default — the framework promotes to `required` on the first iteration when runtime tools (SDK CoT scaffolding, `recall_memory`, `query_knowledge`) are configured, so they actually fire; gpt-class models otherwise skip them on simple inputs. |
| `max_tool_calls_per_message` | int | `5` | 0 – 20 | Max tool calls per LLM message |
| `tool_call_timeout` | float | `30.0` | 0.1 – 300 (seconds) | Tool execution timeout |
| `allow_parallel_tool_calls` | bool | `true` | `true`, `false` | Allow parallel tool execution |
| `tool_categories` | list | `[]` | category name strings | Tool categories agent can access |
| `effort` | string | `null` | `"low"`, `"medium"`, `"high"` | v2.3.x — Claude 4.8 (Opus / Sonnet) `effort` parameter. Higher effort = deeper reasoning + more output tokens. Only applies to Anthropic Claude 4.8 family; ignored for other models. |
| `super_agent` | bool | `false` | `true`, `false` | v2.3.x — Wrap this LLM agent in the multi-phase orchestrator (plan → execute → verify → reflect → finalize). See [Super-Agent v3 fields](#super-agent-v3-fields) below |
| `super_agent_cost_ceiling` | int | provider-default | tokens | v2.3.x — Hard ceiling on aggregate LLM token cost (input + output) for one Super-Agent run. Breach → cancellation + `cost_ceiling.exceeded` event. Only used when `super_agent: true` |
| `super_agent_step_cap` | int | `12` | 1 – 50 | v2.3.x — Maximum executable steps before the orchestrator hard-stops. Protects against runaway plans. Only used when `super_agent: true` |
| `super_agent_reflection_budget` | int | `2` | 0 – 5 | v2.3.x — Maximum reflect-then-amend cycles per run. `0` disables reflection. Only used when `super_agent: true` |
| `super_agent_wall_clock` | int | `900` | seconds | v2.3.x — Per-agent wall-clock seconds for a Super-Agent run. Default 15 minutes. Only used when `super_agent: true` |
| `synth_max_tokens_floor` | int | `null` | tokens | v2.3.x — Lower bound on the synthesis call's `max_tokens`. Protects against Anthropic non-streaming guardrail (`max_tokens` < required → silent truncation). Recommended: `16384` for long-output Super-Agents on Claude |
| `synth_max_tokens_ceiling` | int | `null` | tokens | v2.3.x — Upper bound (per-agent) on the synthesis call's `max_tokens`. Cost protection against runaway synthesis |
| `skills` | dict | `null` | `{sourceName: str, enabled: bool, names: list}` | v2.3.x — Skills (reusable instruction playbooks) loaded on demand. **Must be a dict with `sourceName` AND `enabled: true`** — `skills: true` (bare bool) is treated as configured-but-unusable and the tool is stripped. See [Skills Config](#skills-config) below |

### Super-Agent v3 Fields

Super-Agent is opt-in on an LLM agent. Setting `super_agent: true` wraps the agent in the orchestrator:

```yaml
agents:
  research_synthesiser:
    agent_type: "llm"
    model: "claude-sonnet-4-6"
    super_agent: true
    super_agent_cost_ceiling: 100000
    super_agent_step_cap: 12
    super_agent_reflection_budget: 2
    super_agent_wall_clock: 900
    synth_max_tokens_floor: 16384
    synth_max_tokens_ceiling: 32768
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
    agent_type: "llm"
    model: "gpt-4o-mini"
    skills:
      sourceName: "support_playbooks"   # a REGISTERED source name (default: "default" — hosted)
      enabled: true                      # on-switch (default true)
      names:                             # REQUIRED, non-empty — empty list clears the field (no skills)
        - "refund_flow"
        - "account_migration"

    # Shortform — routed to the "default" source (HOSTED):
    # skills: ["refund_flow", "account_migration"]
```

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
- Native chat-completions endpoint, supports tools

**Mistral (v2.3.x — native provider):**
- `mistral-large`, `mistral-small`, `mistral-medium`
- `mixtral-8x22b`, `mixtral-8x7b`
- `codestral-latest`
- Requires `MISTRAL_API_KEY` env var
- Native chat + tools API

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
| **Mistral** | — | No native reasoning mode — use `thinking: true` (SDK CoT scaffolding) instead |
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

### Inbound Route Registered Per Provider

| Provider | Route |
|----------|-------|
| `slack` | `POST /channels/slack/{agent_name}/events` |
| `telegram` | `POST /channels/telegram/{agent_name}/webhook` |
| `discord` | `POST /channels/discord/{agent_name}/interactions` |
| `whatsapp` | `GET /channels/whatsapp/{agent_name}/webhook` (verification) + `POST` (messages) |
| `teams` | `POST /channels/teams/{agent_name}/messages` |

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

`operator_ids` is the logical roster. Each channel's `operators:` map resolves those logical ids to channel-specific recipient ids (Slack user IDs, WhatsApp numbers, email addresses). Pre-compose then steers per call by setting `_target_operator` in `input_data`:

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
| `_target_channel_id` | Raw recipient id — bypasses operator lookup; useful when the id comes from Zapier / DB lookup |
| `_target_channel_provider` | Pins outbound to one provider when several configured (`"slack"`) |
| `_target_webhook_url` | Raw URL override for the webhook fallback path |

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

#### KafkaBrokerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"kafka"` | Literal — must be `"kafka"` |
| `bootstrap_servers` | list[string] | (required) | Kafka broker addresses, e.g. `["kafka-1:9092"]` |
| `security_protocol` | string | `null` | `PLAINTEXT` \| `SSL` \| `SASL_PLAINTEXT` \| `SASL_SSL` |
| `sasl_mechanism` | string | `null` | `PLAIN` \| `SCRAM-SHA-256` \| `SCRAM-SHA-512` \| `GSSAPI` |
| `sasl_username` | string | `null` | SASL auth username |
| `sasl_password` | string | `null` | SASL auth password |
| `ssl_cafile` | string | `null` | Path to CA cert for TLS |
| `ssl_certfile` | string | `null` | Path to client cert (mTLS) |
| `ssl_keyfile` | string | `null` | Path to client key (mTLS) |

#### SQSBrokerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"sqs"` | Literal — must be `"sqs"` |
| `region` | string | (required) | AWS region, e.g. `"us-east-1"` |
| `aws_access_key_id` | string | `null` | Explicit AWS access key (otherwise IAM role / env credentials are used) |
| `aws_secret_access_key` | string | `null` | Explicit AWS secret |
| `aws_session_token` | string | `null` | STS session token (for assumed roles) |
| `endpoint_url` | string | `null` | Override endpoint (LocalStack, VPC endpoints) |

#### MQTTBrokerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"mqtt"` | Literal — must be `"mqtt"` |
| `host` | string | (required) | MQTT broker hostname |
| `port` | int | `1883` | `1883` plain, `8883` TLS |
| `username` | string | `null` | Auth username |
| `password` | string | `null` | Auth password |
| `use_tls` | bool | `false` | Enable TLS for the broker connection |
| `client_id` | string | `null` | MQTT client ID (random if unset) |
| `keepalive_s` | int | `60` | Keepalive interval in seconds |

#### RedisStreamsBrokerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"redis_streams"` | Literal — must be `"redis_streams"` |
| `url` | string | (required) | `redis://`, `rediss://`, or `unix://` URL |
| `db` | int | `0` | Redis DB number |

Use this when an upstream service writes events into a Redis stream you want an agent to consume. **Distinct from the SDK's primary Redis** (used for sessions/yields/feed).

#### IMAPBrokerConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | `"imap"` | Literal — must be `"imap"` |
| `host` | string | (required) | IMAP server hostname |
| `port` | int | `993` | `143` plain, `993` TLS |
| `username` | string | (required) | Mailbox account |
| `password` | string | (required) | Mailbox password / app password |
| `use_tls` | bool | `true` | Enable TLS |

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
    bootstrap_servers: ["kafka-1:9092", "kafka-2:9092"]
    security_protocol: SASL_SSL
    sasl_mechanism: SCRAM-SHA-512
    sasl_username: leafmesh
    sasl_password: ${KAFKA_PASSWORD}

  support_queue:
    type: sqs
    region: us-east-1

agents:
  order_processor:
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
          max_retries: 3
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
| `brokers` | dict | `{}` | name → KafkaBrokerConfig \| SQSBrokerConfig \| MQTTBrokerConfig \| RedisStreamsBrokerConfig \| IMAPBrokerConfig | External broker connection definitions for [Event Listeners — BRD-021](#event-listeners--brd-021). Referenced by name from each agent's `listen_events:` block |

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
| `max_chain_events` | int | `50` | Hard cap on chain events per session before the cycle breaker stops the chain (session `status: stopped` + `ChainCapExceeded` AGENT_ERROR; a new entry-point call on the session resets it). Raise for legitimately deep flows (research / batch fan-out) — never as a fix for an unbounded retry back-edge |
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
| `tool_choice` | Must be a non-empty string (`auto`, `required`, `none`, or tool name). Leave unset — the framework auto-promotes to `required` when runtime tools are configured so they reliably fire. |
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
