# LeafMesh SDK — Complete Reference

## SDK Public Methods

```python
from leafmesh import LeafMesh

# Initialization — the configuration lives in the agency's STORE (2.4.481)
sdk = LeafMesh.from_yaml("configs/config.yaml")   # First boot on an empty store: the file is imported
                                                   # as version 1. Later boots run the store's latest
                                                   # version; the file is read only for the agency's name
                                                   # and an edit to it is NOT applied (boot says so).
sdk = LeafMesh.from_store()                        # No file: name from LEAFMESH_AGENCY_NAME, store from .env;
                                                   # an empty store starts a blank agency (built in Studio)
sdk = LeafMesh.from_dict(config_dict)              # From Python dict
sdk = LeafMesh(config=LeafMeshConfig(...))          # Direct instantiation

# Lifecycle
await sdk.start()                                   # Initialize everything
await sdk.stop()                                    # Graceful shutdown
async with sdk as mesh:                             # Context manager

# Core execution
result = await sdk.mesh_call(
    entry_point_name="greet",
    input_data={"message": "Hello"},
    session_id="optional-session-id",               # Auto-generated if omitted
)

# Re-run a single agent inside an existing session (1.0.299+)
# Routes through Manager.execute_state — same conductor as strict yields enforcement.
result = await sdk.rerun_agent(
    agent_name="advisor_agent",
    session_id="sess-123",
    feedback={"error": "missing action_items"},      # optional; merged as _rerun_context
    reason="user_request",                            # optional audit string
    new_input={"x": 1},                               # optional; falls back to auto_store_agent_input
)
# Returns: {"status": "dispatched", "agent": ..., "session_id": ..., "input_source": ..., "reason": ...}
# Same primitive is exposed at POST /api/sessions/{session_id}/agents/{agent_name}/rerun

# Agent registration (alternative to auto-discover)
@sdk("agent_name")
async def agent_name(llm_response, input_data, context):
    return {"result": llm_response}

# Auto-discover agents from directory
sdk.discover(directory="./agency", pattern="*_agent.py", recursive=False)

# Ad-hoc LLM calls (outside agent context)
result = await sdk.call_llm(
    prompt="Analyze this data",
    session_id="sess-123",
    model="gpt-4o",
    system_prompt="You are a data analyst",
    temperature=0.2,
    max_tokens=1000,
    business_context="Financial analysis for Q3",
    care_instructions="Be precise with numbers",
    sentiment_guidance="Professional tone",
    guardrails="Do not provide investment advice",
)

# Public per-agent / per-session reads
status      = sdk.get_status()                      # SDK lifecycle snapshot
agent_stats = await sdk.get_agent_stats(agent_id)   # Per-agent runtime stats

# Operator analytics (usage totals, LLM cache hit rate, cost breakdowns)
# are surfaced in Studio's Dashboard — operators view them there.

# Feed (cursor-based pagination, latest-first)
posts, next_cursor = await sdk.get_global_feed(count=100, cursor="+")
posts, next_cursor = await sdk.get_agent_feed("agent_name", count=50, cursor="+")
posts, next_cursor = await sdk.get_session_feed("session_id", count=50, cursor="+")

# Custom LLM provider — use only for providers NOT already built in.
# Built-in providers — PyPI 2.4.418 (customers today): 10 + any OpenAI-compatible
# endpoint. Dev 2.4.434+: 27 — OpenAI, Anthropic, Google, DeepSeek, AWS Bedrock,
# GCP Vertex, Azure Foundry, xAI Grok (XAI_API_KEY), Mistral (MISTRAL_API_KEY),
# local/self-hosted, and 17 chat-completions vendors — OpenRouter, Groq,
# Cerebras, Moonshot Kimi, Alibaba Qwen, Z.AI GLM, MiniMax, Inception, Meta
# Muse, Tencent Hunyuan, Xiaomi MiMo, StepFun, Upstage, Poolside, Reka, Arcee,
# Cohere (env vars in the table at the end). Any OpenAI-compatible model is
# also reachable via openrouter/<lab>/<model>. You only need
# register_llm_provider for something truly new (e.g. an internal gateway).
sdk.register_llm_provider(
    name="my_internal_gateway",
    provider_class=MyInternalGatewayProvider,
    model_prefixes=["internal/"],
    api_key="...",
)

# Self-healing — driven by YAML config, not Python API.
# A TOP-LEVEL `self_healing:` block in config.yaml (not under manager:).
# Watching + notifying is on by default; acting (restart / spawn a
# backup) needs `self_healing: {actions_enabled: true}`. Monitoring starts
# at sdk.start(); health and recovery activity show in Studio's Dashboard.
# `manager.self_healing: true` loads but does nothing.

# Evolution — operators kick off scoring runs from Studio's
# Evolution tab. The optimizer is no longer in-process; nothing in
# the customer SDK surface to call here.
```

## Full Config YAML Structure

This is the shape of the agency's configuration document. Since 2.4.481 it
lives in the store: `configs/config.yaml` is imported once on the first boot,
after which the document is changed in Studio (settings or the YAML editor) or
with `PUT /api/yaml/raw` / `PATCH /api/yaml/config` (`"save_to_disk": true`) —
each save is a new version, applied without a restart (only
`evolution_api` host/port/enabled need one). A blank agency's document writes
every setting with its default (agent-config-fields.md → Runtime Config Blocks).

```yaml
# ── Top-level ──
name: "my_mesh"
version: "1.0.0"
architecture: "managed_mesh"    # Only supported type
environment: "development"      # development | production
debug: false
log_level: "INFO"               # DEBUG | INFO | WARNING | ERROR

# ── Datastore — NOT configured here (2.4.482) ──
# Where the store is lives in .env ONLY (LEAFMESH_STORE, REDIS_*, POSTGRES_* —
# see Environment Variables below). A `persistence:` or top-level `redis:`
# block in this file is IGNORED on 2.4.482–2.4.485 (boot warns "the
# persistence block is no longer read"); from 2.4.486 LeafMesh.from_yaml RAISES
# ConfigError if its values differ from .env, naming each .env line to add
# (a matching block still loads, with the warning). Remove it. Studio → Infrastructure → Datastores
# (GET /api/infra/datastore) shows whether the store is reachable; it never
# shows the address or password. Business-logic persistence (sessions, agent
# state, yields, feed, HITL) runs on either backend; nothing here changes.

# ── Auto-discover ──
auto_discover:
  directory: "./agency"
  pattern: "*_agent.py"
  recursive: false

# ── Manager (coordination + summarizer) ──
manager:
  # on by default — omit `enabled`; set `enabled: false` only to disable
  # coordination + the summarizer entirely (rare; no interventions, no feed)
  model: "gpt-4o-mini"                 # Model for summarizer LLM calls
  domain: "generic"                     # Summarizer domain specialization
  can_intervene: true                   # Allow automatic interventions
  health_check_interval: 60            # Seconds between health checks
  agent_timeout_threshold: 180         # Seconds before agent timeout
  chain_completion_timeout: 1800.0     # Seconds for can_call chain completeness
  coordination_rules: {}               # Custom business rules (max_call_depth, agent_rules, reflection_budget, …)
  # The rule sets sit DIRECTLY under manager: — never under
  # coordination_rules: (2.4.482; an old file is moved at load, with a warning)
  human_input_rules:
    max_concurrent_requests: 3
    max_agent_requests: 5
    enable_request_queuing: true
  # timeout_rules: REMOVED in 2.4.486 (dropped with a warning) — a seat waits its
  # time and stops; nobody answering is not escalated
  workflow_pause_rules:
    max_pause_duration_minutes: 30
    max_concurrent_paused_workflows: 2
    pause_monitoring_enabled: true
  human_response_rules:
    approval:   {requires_manager_review: false, auto_escalate: false}
    escalation: {requires_manager_review: true,  auto_escalate: true}
    # timeout: REMOVED in 2.4.486 (dropped with a warning)
  # temperature: 0.1 / max_tokens: 4000 — the Manager's defaults; it reads its own (2.4.485)

# ── Security ──
security:
  telemetry_redact_pii: true           # default TRUE (2.4.480): customer content in traces reads
                                       # <redacted bytes:N>; false = readable. Credentials masked either way

# ── Timeouts ──
# (scheduler / runtime / limits / connectors / self_healing: see
# agent-config-fields.md "Runtime Config Blocks")
timeouts:
  mesh_call_default_timeout_s: 300     # How long mesh_call waits when no timeout= is passed.
                                       # `mesh.call_timeout` is GONE (2.4.482) — moved here at
                                       # load with a warning. Default has been 300 since 2.4.382.

# ── Mesh ──
mesh:
  max_chain_events: 50                 # Per-session chain cap — cycle breaker stops the chain past this
                                       # (session status=stopped + ChainCapExceeded). Raise for deep
                                       # research/batch-fanout flows; NOT a fix for unbounded retry edges
  reply_stream: false                  # default false; always on in workers mode
  # Provider accounts are vault-only (2.4.481): region / endpoint_url /
  # project / location / endpoint / headers written here FAIL TO LOAD.
  bedrock:                             # AWS Bedrock (optional)
    connection: "aws-bedrock"          # AWS Bedrock connection: region (+ endpoint_url)
    profile: null                      # AWS profile name on the host
  vertex:                              # Google Vertex AI (optional)
    connection: "gcp-vertex"           # Google Vertex connection: project_id + location
  foundry:                             # Azure AI Foundry (optional)
    connection: "azure-foundry"        # Azure Foundry connection: endpoint + key
    api_version: null

# ── Entry Points ──
# `target:` must name an agent DEFINED in this same config — the loader
# rejects a target it cannot resolve.
entry_points:
  - name: "greet_user"
    target: "agent_name"
    condition: "always"

# ── Skills — NOT configured here ──
# There is NO top-level skills: block (the loader rejects unknown top-level
# keys). Skill sources are registered at runtime via the API and persisted
# in Redis (reloaded on every start):
#   POST /api/skills/sources
#     {"name": "support_playbooks", "source_type": "filesystem",
#      "config": {"root": "./skills"}}
# With no registered sources, the SDK auto-creates a "default" source —
# which is HOSTED (Redis), so local skills/*.md files do NOT load until a
# filesystem source is registered. Agents reference sources by name via
# agents.<name>.skills.sourceName. See SKILL.md → Skills System.

# ── Brokers (v2.3.x — BRD-021 Event Listeners) ──
# A broker holds ONLY how to REACH the system. What to read from it —
# topic, consumer group, folder, qos — belongs on the agent's
# `listen_events`, because two agents may read different topics from one
# broker. Every broker model is extra="forbid", so putting them here is a
# load error, not a warning.
# HOW to reach it — address, sign-in, secrets — is vault-only (2.4.481):
# the block picks a vault connection of the broker's type with `connection:`;
# bootstrap_servers / host / port / username / password / url written here
# FAIL TO LOAD. A missing record switches the consumer off, never blocks boot.
brokers:
  order_events_kafka:                    # name referenced from agents.<name>.listen_events
    type: "kafka"
    connection: "orders-kafka"           # kafka connection: bootstrap_servers + sign-in
  support_inbox_imap:
    type: "imap"
    connection: "support-imap"           # imap connection: host, port, username, password

# …and the agent says what it wants from them:
#
# agents:
#   order_processor:
#     listen_events:
#       - broker: order_events_kafka
#         topic: "orders.created"
#         consumer_group: "leafmesh-order-processor"
#       - broker: support_inbox_imap
#         folder: "INBOX"
#         poll_interval_s: 30
#         unseen_only: true

# ── Agents ──
agents:
  agent_name:
    name: "agent_name"
    # ... (see SKILL.md for all fields)
    # super_agent: true   ← v2.3.x — wraps an LLM agent in the multi-phase orchestrator
    # skills: {sourceName: "support_playbooks", enabled: true, names: [...]}   ← v2.3.x
    # listen_events: [{broker: "order_events_kafka", session_strategy: "..."}] ← v2.3.x BRD-021

# ── Data Structures ──
data_structures:
  customer_record:
    type: "object"
    properties:
      name: {type: "string"}
      score: {type: "number"}
    required: ["name"]

# ── Evolution ──
evolution:
  enabled: false
  strategy: "genetic"                  # genetic | particle_swarm | simulated_annealing
  population_size: 20
  generations: 50
  mutation_rate: 0.1
  crossover_rate: 0.7
  elite_size: 2
  fitness_function: "task_completion_rate"
  selection_method: "tournament"
  test_scenarios: []
```

## Condition Syntax (can_call conditions)

Conditions evaluate the upstream agent's output data:

```yaml
can_call:
  - agent: "specialist"
    condition: "calling_agent_response.status == 'needs_specialist'"
  - agent: "escalation"
    condition: "calling_agent_response.priority == 'high'"
  - agent: "greeter"
    condition: "not calling_agent_response.from_agent"   # works ONLY because human agents ALWAYS emit from_agent (maybe ""). Never `not` a field that can be absent — see gotcha #14   # Falsy check (HITL routing)
  - agent: "processor"
    condition: "calling_agent_response.from_agent == 'greeter_agent'"
  - agent: "urgent_handler"
    condition: "calling_agent_response.item_count > 0"
  - agent: "default"
    condition: "true"   # Always matches (fallback)
```

**Operators**: `==`, `!=`, `>`, `<`, `>=`, `<=`, `and`, `or`, `not`
**Access**: `calling_agent_response.field_name` for upstream agent output fields

### HITL output fields (available when human agent responds)
```
calling_agent_response.from_agent        # Who called the human ("greeter_agent" or "")
calling_agent_response.human_message     # What the human typed
calling_agent_response.human_decision    # Human's decision field
calling_agent_response.human_data        # Data from the human response
calling_agent_response.human_initiated   # Always true for human output
calling_agent_response.source_agent      # The human agent name
```

## All Imports

```python
# Core
from leafmesh import LeafMesh, LeafMeshConfig, AgentConfig, MeshConfig
from leafmesh import BedrockConfig, VertexConfig, FoundryConfig
from leafmesh import ChannelConfig, EscalationConfig, EscalationTarget

# Events & Sessions
from leafmesh import LeafMeshEvent, EventType, Session, SessionData

# Agents
from leafmesh import BaseAgent, AgentResponse

# Decorators
from leafmesh import pre_compose, chain, compose, conditional_chain, chain_with_results

# Tools
from leafmesh import tool, global_tool

# Integration helpers (for @pre_compose)
from leafmesh import zapier, mcp, composio, n8n

# Exceptions
from leafmesh import LeafMeshError, ConfigError, AgentError, RedisError, LeafMeshLicenseError

# Utilities
from leafmesh import LeafMeshLogger
from leafmesh import load_yaml_config, save_yaml_config, validate_config
from leafmesh import check_license_compliance, display_license_notice

# Advanced
from leafmesh import SelfHealingLeafMeshManager, AgentHealthStatus
from leafmesh import EvolutionaryLeafMeshOptimizer, LeafMeshGenome
from leafmesh import AdaptiveLLMExecutor, ModelSelectionStrategy

# LLM extensibility
from leafmesh import LLMProvider, LLMRequest, LLMResponse, StreamChunk

# Backwards compat (old names still work)
from leafmesh import SwarmSDK, SwarmConfig, SwarmEvent, SwarmError
```

## External Connectors

**`connector_config` is vault-only for the account (2.4.482).** Addresses
(`url`, `endpoint`, `webhook_url`, `base_url`, …), keys and tokens, client /
tenant ids, `auth_scheme` and `headers` written here — literal, `${ENV}` or
`${vault:…}` — **fail to load**. Create the record on Infrastructure → External
agents → `<framework>` (zapier / composio / n8n / mcp: Infrastructure →
Integrations), or an "Add custom" record with service type 'External agent' (Tools
for integrations) whose base URL is the address, and pick it with `connection`
(zapier: `vault_connection`). Only behaviour stays inline. Since 2.4.485 no
connector reads its old environment variables (`CREWAI_ENDPOINT`,
`A2A_AGENT_URL`, `N8N_WEBHOOK_URL`, …) — the record is the only source.

**2.4.486 — pick it from the External agents page.** Set the external agent up
once on Studio's External agents page (framework, vault record, settings) and
write only `external_agent: <entry>` on the agent; the mesh fills in
`framework` and `connector_config`. A different `framework` /
`connector_config` beside it is refused. The per-framework shapes below still
load and run as written. A custom agent is `custom_api` (`method`, `path`,
`query`, `answer_path`; the body is the agent's input) or `a2a`.

### CrewAI
```yaml
agents:
  crew_agent:
    name: "crew_agent"
    agent_type: "external"
    framework: "crewai"
    connector_config:
      connection: "crewai"                  # External agents → CrewAI: endpoint + api_key / user_api_key
      # poll_interval: 2.0
      # max_poll_seconds: 300
```

### LangGraph
```yaml
agents:
  graph_agent:
    name: "graph_agent"
    agent_type: "external"
    framework: "langgraph"
    connector_config:
      connection: "langgraph"               # External agents → LangGraph: platform URL + api_key
      graph_id: "agent"                     # Which graph to run
      # poll_interval: 1.0
      # max_poll_seconds: 300
```

### AutoGen
```yaml
agents:
  autogen_agent:
    name: "autogen_agent"
    agent_type: "external"
    framework: "autogen"
    connector_config:
      connection: "autogen"                 # External agents → AutoGen: service URL + api_key
      # workflow_id: "my-workflow"
      # timeout: 120
      # poll_interval: 2.0
      # max_poll_seconds: 300
```

### A2A (Agent-to-Agent)
```yaml
agents:
  a2a_agent:
    name: "a2a_agent"
    agent_type: "external"
    framework: "a2a"
    connector_config:
      connection: "remote-agent"            # External agents → A2A Protocol: agent URL + auth_token (+ auth_scheme)
      # poll_interval: 2.0
      # max_poll_seconds: 300
    # request_form:                 # sent as the message's metadata on every call
    #   region: "eu-west"
```

A2A 1.0 (`SendMessage` / `GetTask`) and 0.3 are both spoken: the dialect comes
from the agent card (`/.well-known/agent-card.json`, older agents
`/.well-known/agent.json`), and a call the agent answers in the other dialect
is retried once in it. The conversation continues per mesh session and tenant
(the agent's context id is kept and sent back). A changed card quarantines the
agent until a person releases it.

### MCP (Model Context Protocol)
```yaml
agents:
  # HTTP transport — connects to remote MCP server
  mcp_http_agent:
    name: "mcp_http_agent"
    agent_type: "external"
    framework: "mcp"
    connector_config:
      tool_name: "search"                   # Required — which tool to call
      transport: "http"
      connection: "mcp-search"              # Integrations → MCP (or "Add custom", service type 'Tools'): server URL + auth_token
      # timeout: 60

  # stdio transport — launches local MCP server process
  mcp_stdio_agent:
    name: "mcp_stdio_agent"
    agent_type: "external"
    framework: "mcp"
    connector_config:
      tool_name: "read_file"                # Required — which tool to call
      transport: "stdio"
      command: "npx"
      args: ["-y", "@mcp/server-filesystem"]
      # connection: "fs-mcp"                # its secret body rows become the command's env;
                                            # a credential-named key in env: is refused.
                                            # 2.4.486: a custom 'Tools' record keeps header rows only —
                                            # body rows are refused on save / no longer sent
```

### Connector Execution Modes (all frameworks)

All connectors support two execution modes via `connector_config`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `"sync"` | `"sync"` (wait for HTTP response) or `"callback"` (fire request, wait for external system to POST back) |
| `callback_timeout` | float | `120.0` | Seconds to wait for callback before timeout (callback mode only) |

**Callback mode**: The connector injects `_leafmesh_callback_url` and `_leafmesh_session_id` into the outbound payload. The external system processes async and POSTs the result back to `/callback/{agent_name}`.

```yaml
# n8n with callback mode (fire-and-forget workflow)
n8n_async:
  agent_type: "external"
  framework: "n8n"
  connector_config:
    connection: "n8n-async"             # Integrations → n8n: the webhook URL (+ auth_token)
    mode: "callback"
    callback_timeout: 300
```

### Programmatic Integrations (Zapier, Composio, n8n, MCP)

`integration` is a **string** field (not a dict). Valid values: `"zapier"`, `"composio"`, `"n8n"`, `"mcp"`.
Only valid on `agent_type: "programmatic"`.

```yaml
agents:
  zapier_agent:
    name: "zapier_agent"
    agent_type: "programmatic"
    integration: "zapier"
    connector_config:
      connection: "google_sheets"           # Zapier app slug (NOT the vault record)
      action: "create_spreadsheet_row"      # Action to execute
      vault_connection: "zapier-main"       # Integrations → Zapier: mcp_key (+ mcp_endpoint)
      # mode: "callback"                   # For async Zapier workflows
      # callback_timeout: 120

  composio_agent:
    name: "composio_agent"
    agent_type: "programmatic"
    integration: "composio"
    connector_config:
      action: "GITHUB_STAR_A_REPOSITORY_FOR_THE_AUTHENTICATED_USER"
      connection: "composio"                # Integrations → Composio: api_key
      # entity_id: "default"

  n8n_agent:
    name: "n8n_agent"
    agent_type: "programmatic"
    integration: "n8n"
    connector_config:
      connection: "n8n-workflow"            # Integrations → n8n: webhook URL + auth_token
      # timeout: 60
      # mode: "callback"                   # For fire-and-forget n8n workflows
      # callback_timeout: 120
```

### Integration Helpers with @pre_compose
```python
from leafmesh import pre_compose, zapier, mcp, composio, n8n

@pre_compose(
    context_processor=zapier(action="slack_send", connection="zapier-main"),
    # or: composio(action="GMAIL_SEND", connection="composio-main"),
    # or: mcp("http://localhost:3000", "search"),
    # or: n8n(connection="n8n-orders"),
    # callback mode: n8n(connection="n8n-orders", mode="callback", callback_timeout=120),
)
async def my_agent(llm_response, input_data, context):
    integration_result = context["prepared_data"]["business_context"]
    return {"result": llm_response, "integration": integration_result}
```

All helpers accept `mode="callback"` and `callback_timeout=N` parameters.

**Since 2.4.485 `zapier()`, `composio()` and `n8n()` read their address and key
from a vault record** named with `connection=` (Infrastructure → Integrations →
`<platform>`, or an "Add custom" record, service type 'Tools'). An address or
key written in code — `n8n("https://…")`, `webhook_url=`, `auth_token=`,
`api_key=`, `mcp_key=` — raises `ValueError` when the helper is created, naming
the record to make. The record is read at the first call, inside a started
mesh (outside one it raises). `mcp()` is unchanged.

## Event Listeners (BRD-021) — agents fired by external events

Bind agents to **Kafka, SQS, MQTT, Redis Streams, or IMAP** so they fire on message arrival — no `mesh_call` needed. See SKILL.md → *Event Listeners — BRD-021* for the full guide.

```bash
pip install leafmesh[kafka]       # aiokafka
pip install leafmesh[sqs]         # aioboto3
pip install leafmesh[mqtt]        # asyncio-mqtt (listener lands in a follow-up)
pip install leafmesh[imap]        # aioimaplib (listener lands in a follow-up)
pip install leafmesh[listeners]   # all four bundled
# Redis Streams uses the core redis dep — no extra needed
```

Two-part YAML:

```yaml
# 1. Declare broker connections at the top level
brokers:
  orders_kafka:
    type: kafka
    connection: orders-kafka     # kafka connection: bootstrap_servers + SASL user/password (vault-only, 2.4.481)
    security_protocol: SASL_SSL
    sasl_mechanism: SCRAM-SHA-512

# 2. Bind agents to topics/queues
agents:
  order_processor:
    name: "order_processor"
    agent_type: programmatic
    listen_events:
      - broker: orders_kafka
        topic: orders.created
        group_id: leafmesh-order-processor   # defaults to <sdk-name>-<agent-name>
        filter:
          source: "/region/us-east-1"        # CloudEvents-style AND-equality filter
        delivery:
          max_attempts: 3
          backoff: exponential
          dead_letter:
            broker: orders_kafka
            topic: orders.dlq
```

Source fields by broker type:

| broker `type` | listener fields |
|---|---|
| `kafka` | `topic`, `group_id` |
| `sqs` | `queue`, `visibility_heartbeat` |
| `redis_streams` | `stream`, `consumer_group` |
| `mqtt` | `mqtt_topic` (`+`/`#` wildcards), `qos` |
| `imap` | `folder`, `poll_interval_s`, `unseen_only` |

Delivery: **at-least-once**, idempotency on `(listener_name, message_id)`. After retries exhaust → DLQ if configured, otherwise dropped + logged.

## Notable Stream Events (observability)

| Event | When |
|-------|------|
| `llm.cost.tracked` | Token + USD cost, recorded once per provider call at the gate |
| `llm.cache.hit` | Model text reused (agent function/decorators still ran fresh) |
| `media.generated` | Image-generation call produced media (metadata only) |
| `reflection.doomed_skipped` | Reflection skipped — null-vs-schema conflict; fix `nullable: true` or the prompt |
| `session.result_dropped` | Completed work discarded (session already escalated) — loud, with the discarded keys |
| `dispatch.dedup_suppressed` | Duplicate work unit suppressed (exactly-once) |
| `manager.degradation` | Super-agent finished degraded; Manager reviewed without re-running |
| `budget.exhausted` | Per-agent monthly budget tripped before spend |

## Feed Post Structure

Each feed post contains:

```python
{
    "post_id": "post:uuid",
    "agent_name": "greeter_agent",
    "session_id": "sess_abc123",
    "timestamp": "2026-03-24T10:00:00",
    "summary": "Processed customer inquiry about pricing",
    "from_agent": "greeter_agent",
    "to_agent": "processor_agent",
    "action_needed": "none",           # none | review | escalate
    "priority": "medium",              # low | medium | high
    "reason": "Routing to processor",
    "next_agents": ["processor_agent"],
    "workflow_stage": "processing",
    "trigger_event": "mesh.call.completed",
    "work_log": "Received input, analyzed sentiment, produced greeting...",
    "embedding_text": "greeter_agent Processed customer inquiry..."
}
```

## The `leafmesh` command

Two operator commands, run on the host (they read the store from `.env`):

```bash
# A claude_agent's host rights, saved as the store's next version (2.4.485).
# The config API refuses these fields; this is how they change.
leafmesh agent host-rights AGENT [--cwd DIR] [--allowed-tools a,b] \
    [--permission-mode default|acceptEdits|plan|bypassPermissions] \
    [--setting-sources user,project,local] [--disallowed-tools a,b] \
    [--sandbox '{"enabled": true}'] [--clear FIELD] [--yes]
#   --setting-sources / --disallowed-tools / --sandbox: 2.4.486
#   prints the change; saves only with --yes or a typed "apply"; every pod applies it

# Move every stored credential onto a new vault master key (every worker stopped).
leafmesh vault rotate-key --new-key-file PATH [--generate] [--old-key-file PATH] [--yes]
#   2.4.485: the store is the one .env names; --config is only an optional old
#   config.yaml read for the agency's name
```

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `LEAFMESH_LICENSE_KEY` | Yes | License key from leafcraft.ai |
| `LEAFMESH_ENV_TOKEN` | No | Environment token — scopes HITL data + telemetry per environment |
| `OPENAI_API_KEY` | For OpenAI models | OpenAI API key |
| `ANTHROPIC_API_KEY` | For Claude models | Anthropic API key |
| `GOOGLE_API_KEY` | For Gemini models | Google AI API key (`GEMINI_API_KEY` also read) |
| `DEEPSEEK_API_KEY` | For DeepSeek models | DeepSeek API key |
| `AZURE_FOUNDRY_API_KEY` | For Foundry | Foundry key (`AZURE_OPENAI_API_KEY` also read); endpoint in `AZURE_FOUNDRY_ENDPOINT` or on the Azure Foundry record (`mesh.foundry.connection`) — `mesh.foundry.endpoint` is refused since 2.4.481 |
| `LEAFMESH_AGENCY_NAME` | With `LeafMesh.from_store()` | The agency's name — every key in the store is filed under it. `from_store()` raises `ConfigError` when it is unset. With `from_yaml` the name comes from config.yaml's `name:`; if both are set, keep them equal |
| `LEAFMESH_STORE` | No | Datastore backend: `redis` (default) \| `postgres`. **The datastore is set ONLY in `.env` (2.4.482)** — a `persistence:`/`redis:` block in the YAML is ignored with a boot warning (2.4.482–2.4.485); from 2.4.486 `LeafMesh.from_yaml` raises `ConfigError` if it differs from `.env`. Set only what you need; the rest default. Studio → Infrastructure → Datastores shows reachability, never the address or password |
| `REDIS_URL` / `DATABASE_URL` | No | The whole server in one value: `redis://user:pw@host:6379/4` (`rediss://` = TLS) or `postgresql://user:pw@host:5432/db?sslmode=require`. The single names below fill in what the URL leaves out |
| `REDIS_HOST` | No | Redis host (default: localhost) |
| `REDIS_PORT` | No | Redis port (default: 6379) |
| `REDIS_PASSWORD` | No | Redis password |
| `REDIS_DB`, `REDIS_DEFAULT_TTL`, `REDIS_SESSION_TTL` | No | Redis DB number; generic key TTL and session TTL (seconds) |
| `REDIS_SSL`, `REDIS_SSL_CERT_REQS`, `REDIS_SSL_CA_CERTS`, `REDIS_SSL_CERTFILE`, `REDIS_SSL_KEYFILE`, `REDIS_SSL_CHECK_HOSTNAME` | No | Redis TLS |
| `REDIS_CLUSTER_NODES` | No | Comma-separated `host:port` list; setting it means cluster mode |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | With `LEAFMESH_STORE=postgres` | Postgres address and login |
| `POSTGRES_SSLMODE`, `POSTGRES_DEFAULT_TTL`, `POSTGRES_SESSION_TTL`, `POSTGRES_POOL_MIN`, `POSTGRES_POOL_MAX` | No | Postgres TLS mode, TTLs (seconds), connection pool size |
| ~~`ZAPIER_NLA_API_KEY`~~, ~~`COMPOSIO_API_KEY`~~ | **Not read** | Zapier / Composio keys live only on their vault record (Infrastructure → Integrations), picked with `vault_connection` / `connection`. Since 2.4.485 none of the 58 connector variables (`ZAPIER_MCP_KEY`, `COMPOSIO_*`, `N8N_*`, `CREWAI_*`, `A2A_*`, …) is read; boot names each one still set |
| `XAI_API_KEY` | For Grok models | xAI API key (`GROK_API_KEY` also read) |
| `MISTRAL_API_KEY` | For Mistral models | Mistral API key |
| `OPENROUTER_API_KEY` | For `openrouter/…` models | OpenRouter key (optional single key for the long tail; reports each call's cost) |
| `GROQ_API_KEY` | For `groq/…` models | Groq key |
| `CEREBRAS_API_KEY` | For `cerebras/…` models | Cerebras key |
| `MOONSHOT_API_KEY` | For `kimi-…` models | Moonshot Kimi key (`KIMI_API_KEY` also read) |
| `DASHSCOPE_API_KEY` | For `qwen…` models | Alibaba Model Studio key (`QWEN_API_KEY` also read; region-bound — `QWEN_BASE_URL` moves it) |
| `ZAI_API_KEY` | For `glm-…` models | Z.AI key (`GLM_API_KEY` also read) |
| `MINIMAX_API_KEY` | For `minimax-…` models | MiniMax key |
| `INCEPTION_API_KEY` | For `mercury-…` models | Inception key |
| `META_API_KEY` | For `muse-…` models | Meta Model API key (`MODEL_API_KEY` also read) |
| `HUNYUAN_API_KEY` | For `hy3…` / `hy4…` / `hunyuan-…` models | Tencent Hunyuan key |
| `MIMO_API_KEY` | For `mimo-…` models | Xiaomi MiMo key |
| `STEPFUN_API_KEY` | For `step-…` models | StepFun key (`STEP_API_KEY` also read) |
| `UPSTAGE_API_KEY` | For `solar-…` models | Upstage key |
| `POOLSIDE_API_KEY` | For `poolside/…` models | Poolside key |
| `REKA_API_KEY` | For `reka-…` models | Reka key |
| `ARCEE_API_KEY` | For `trinity-…` / `arcee-…` models | Arcee key (`ARCEEAI_API_KEY` also read) |
| `CO_API_KEY` | For `command-…` models | Cohere key (`COHERE_API_KEY` also read) |
| `<NAME>_BASE_URL` | No | Moves a vendor's address (region or proxy), e.g. `QWEN_BASE_URL`, `OPENROUTER_BASE_URL` |
| ~~``timeouts.llm_hard_timeout_s``~~ | **DEAD (2.4.131)** | Moved to YAML `timeouts.llm_hard_timeout_s` (default **90**s; timed-out calls retry **once**, then fail; super-agent phases get 600s). The env var is **no longer read** — set the YAML block. Raise for long-running agents with big outputs |
| `LEAFMESH_SKILLS_DIR` | No | Root dir for `filesystem` skill sources when no `config.root` is set (default `./skills/`) |
| `LEAFMESH_API_PORT` | No | Mesh API port (default **18820**) |
| ~~``limits.max_parallel_tool_calls``~~ | **DEAD (2.4.131)** | Moved to YAML `limits.max_parallel_tool_calls` (default **8**). Env var no longer read |
| ~~`super_agent: {step_concurrency: N} on the agent`~~ | **DEAD (2.4.131)** | Now a per-agent super-agent dict key: `super_agent: {step_concurrency: N}` (default **4**). Env var no longer read |
| `LEAFMESH_WORKERS_MODE` | No | `1` enables workers/HA mode — required for running more than one instance against one Redis (exactly-once events, singleton runners, cross-instance locks) |
| `LEAFMESH_WORKERS` | No | Number of worker processes in workers mode |
| ``runtime.lease_seconds`` | No | Singleton-runner lease window (default **30**). Raise (e.g. `120`) when Redis is remote over a flaky link so connectivity blips shorter than the window never flap leased runners; heartbeat auto-scales to a third of the window (2.4.107) |
| ``runtime.lease_heartbeat_s`` | No | Explicit lease heartbeat interval override (must be < lease window). No fixed default — `lease_seconds / 3` — so the blank YAML leaves it out on purpose |

## Webhook HMAC Authentication

For human agents with webhooks, the SDK auto-derives an HMAC secret from your license key:

```python
from leafmesh import derive_webhook_secret, get_webhook_secret

# Derived from LEAFMESH_LICENSE_KEY automatically
secret = get_webhook_secret()
# Use for verifying inbound webhook signatures
```

## Error Handling

```python
from leafmesh import LeafMeshError, ConfigError, AgentError, RedisError, LeafMeshLicenseError

try:
    result = await sdk.mesh_call("entry", input_data={...})
except AgentError as e:
    # Agent execution failed
except RedisError as e:
    # Redis connection/operation failed
except ConfigError as e:
    # Configuration validation error
except LeafMeshLicenseError as e:
    # License expired or invalid
# Over HTTP (2.4.481): a plan at its limit or an unpaid invoice answers a NEW
# session with HTTP 402 and the reason; runs in flight carry on.
# A model whose provider has no key (2.4.482) raises LeafMeshError:
# "model 'X' needs the <provider> provider, which has no key here — add one on
#  Infrastructure → Models, then try again"
except LeafMeshError as e:
    # Base exception for all SDK errors
```
