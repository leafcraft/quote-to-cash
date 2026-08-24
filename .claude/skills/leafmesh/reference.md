# LeafMesh SDK — Complete Reference

## SDK Public Methods

```python
from leafmesh import LeafMesh

# Initialization
sdk = LeafMesh.from_yaml("configs/config.yaml")   # From YAML file
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
# Built-in providers (v2.3.x): OpenAI, Anthropic, Google, DeepSeek, AWS Bedrock,
# GCP Vertex, Azure Foundry, xAI Grok (XAI_API_KEY), Mistral (MISTRAL_API_KEY),
# and local/self-hosted. You only need register_llm_provider for something
# truly new (e.g. an internal model gateway).
sdk.register_llm_provider(
    name="my_internal_gateway",
    provider_class=MyInternalGatewayProvider,
    model_prefixes=["internal/"],
    api_key="...",
)

# Self-healing — driven by YAML config, not Python API.
# Set `manager.self_healing: true` in config.yaml. The SDK enables
# monitoring automatically at sdk.start(). Agent health and recovery
# activity are visible in Studio's Dashboard.

# Evolution — operators kick off scoring runs from Studio's
# Evolution tab. The optimizer is no longer in-process; nothing in
# the customer SDK surface to call here.
```

## Full Config YAML Structure

```yaml
# ── Top-level ──
name: "my_mesh"
version: "1.0.0"
architecture: "managed_mesh"    # Only supported type
environment: "development"      # development | production
debug: false
log_level: "INFO"               # DEBUG | INFO | WARNING | ERROR

# ── Redis ──
redis:
  host: "localhost"
  port: 6379
  db: 0
  password: null
  decode_responses: true
  auto_storage: true
  default_ttl: 3600
  session_ttl: 7200
  cluster_mode: false
  cluster_nodes: []

# ── Auto-discover ──
auto_discover:
  directory: "./agency"
  pattern: "*_agent.py"
  recursive: false

# ── Persistence backend (`persistence`) — Redis (default) OR Postgres ──
# Business-logic persistence (sessions, agent state, yields, feed, HITL) can
# run on either backend. Omit the block entirely for Redis via the `redis:`
# config. Postgres example:
persistence:
  backend: postgres          # redis (default) | postgres
  host: db.internal          # Postgres connection
  port: 5432
  database: leafmesh
  user: leafmesh_app
  password: "${PG_PASSWORD}"
  sslmode: require           # optional
  default_ttl: 3600          # generic key TTL (seconds)
  session_ttl: 604800        # session lifetime (7 days)
  pool_min: 1
  pool_max: 10

# ── Manager (coordination + summarizer) ──
manager:
  # on by default — omit `enabled`; set `enabled: false` only to disable
  # coordination + the summarizer entirely (rare; no interventions, no feed)
  model: "gpt-4o-mini"                 # Model for summarizer LLM calls
  domain: "generic"                     # Summarizer domain specialization
  can_intervene: true                   # Allow automatic interventions
  health_check_interval: 60            # Seconds between health checks
  agent_timeout_threshold: 180         # Seconds before agent timeout
  chain_completion_timeout: 60.0       # Seconds for can_call chain completeness
  coordination_rules: {}               # Custom business rules
  human_input_rules:
    max_concurrent_requests: 3
    max_agent_requests: 5
    enable_request_queuing: true
  timeout_rules:
    max_timeouts_before_escalation: 2
    timeout_escalation_enabled: true
  workflow_pause_rules:
    max_pause_duration_minutes: 30
    max_concurrent_paused_workflows: 2

# ── Mesh ──
mesh:
  call_timeout: 30                     # Default timeout for mesh calls
  max_chain_events: 50                 # Per-session chain cap — cycle breaker stops the chain past this
                                       # (session status=stopped + ChainCapExceeded). Raise for deep
                                       # research/batch-fanout flows; NOT a fix for unbounded retry edges
  bedrock:                             # AWS Bedrock (optional)
    region: "us-east-1"
    profile: null                      # AWS profile name
    endpoint_url: null
  vertex:                              # Google Vertex AI (optional)
    project: "my-gcp-project"
    location: "us-central1"
  foundry:                             # Azure AI Foundry (optional)
    endpoint: "https://resource.openai.azure.com"
    api_version: null

# ── Entry Points ──
entry_points:
  - name: "greet_user"
    target: "greeter_agent"
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
brokers:
  order_events_kafka:                    # name referenced from agents.<name>.listen_events
    type: "kafka"
    bootstrap_servers: "kafka.internal:9092"
    topic: "orders.created"
    consumer_group: "leafmesh-order-processor"
  support_inbox_imap:
    type: "imap"
    host: "imap.example.com"
    port: 993
    user: "support@example.com"
    password: "${IMAP_PASSWORD}"
    folder: "INBOX"
    poll_interval_s: 30

# ── Agents ──
agents:
  agent_name:
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

### CrewAI
```yaml
agents:
  crew_agent:
    agent_type: "external"
    framework: "crewai"
    connector_config:
      endpoint: "http://localhost:9000"     # CrewAI hosted API
      # api_key: "${CREWAI_API_KEY}"              # Bearer Token
      # user_api_key: "${CREWAI_USER_API_KEY}"    # User Bearer Token (preferred over api_key)
      # poll_interval: 2.0
      # max_poll_seconds: 300
```

### LangGraph
```yaml
agents:
  graph_agent:
    agent_type: "external"
    framework: "langgraph"
    connector_config:
      endpoint: "http://localhost:8123"     # LangGraph Platform URL
      # api_key: "${LANGCHAIN_API_KEY}"
      graph_id: "agent"                     # Which graph to run
      # poll_interval: 1.0
      # max_poll_seconds: 300
```

### AutoGen
```yaml
agents:
  autogen_agent:
    agent_type: "external"
    framework: "autogen"
    connector_config:
      endpoint: "http://localhost:8081"     # AutoGen Studio or custom API
      # api_key: "${AUTOGEN_API_KEY}"
      # workflow_id: "my-workflow"
      # timeout: 120
      # poll_interval: 2.0
      # max_poll_seconds: 300
```

### A2A (Agent-to-Agent)
```yaml
agents:
  a2a_agent:
    agent_type: "external"
    framework: "a2a"
    connector_config:
      url: "https://remote-agent.example.com"  # A2A agent server URL
      # auth_token: "${A2A_AUTH_TOKEN}"
      # auth_scheme: "Bearer"
      # poll_interval: 2.0
      # max_poll_seconds: 300
```

### MCP (Model Context Protocol)
```yaml
agents:
  # HTTP transport — connects to remote MCP server
  mcp_http_agent:
    agent_type: "external"
    framework: "mcp"
    connector_config:
      tool_name: "search"                   # Required — which tool to call
      transport: "http"
      url: "http://localhost:3000"
      # auth_token: "${MCP_API_KEY}"
      # timeout: 60

  # stdio transport — launches local MCP server process
  mcp_stdio_agent:
    agent_type: "external"
    framework: "mcp"
    connector_config:
      tool_name: "read_file"                # Required — which tool to call
      transport: "stdio"
      command: "npx"
      args: ["-y", "@mcp/server-filesystem"]
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
    webhook_url: "https://n8n.example.com/webhook/abc"
    mode: "callback"
    callback_timeout: 300
```

### Programmatic Integrations (Zapier, Composio, n8n, MCP)

`integration` is a **string** field (not a dict). Valid values: `"zapier"`, `"composio"`, `"n8n"`, `"mcp"`.
Only valid on `agent_type: "programmatic"`.

```yaml
agents:
  zapier_agent:
    agent_type: "programmatic"
    integration: "zapier"
    connector_config:
      connection: "google_sheets"           # Service name
      action: "create_spreadsheet_row"      # Action to execute
      # mcp_key: "${ZAPIER_MCP_KEY}"       # MCP path (preferred)
      # api_key: "${ZAPIER_API_KEY}"       # REST path (fallback)
      # mode: "callback"                   # For async Zapier workflows
      # callback_timeout: 120

  composio_agent:
    agent_type: "programmatic"
    integration: "composio"
    connector_config:
      action: "GITHUB_STAR_A_REPOSITORY_FOR_THE_AUTHENTICATED_USER"
      # api_key: "${COMPOSIO_API_KEY}"
      # entity_id: "default"

  n8n_agent:
    agent_type: "programmatic"
    integration: "n8n"
    connector_config:
      webhook_url: "http://localhost:5678/webhook/my-workflow"
      # auth_token: "${N8N_AUTH_TOKEN}"
      # timeout: 60
      # mode: "callback"                   # For fire-and-forget n8n workflows
      # callback_timeout: 120
```

### Integration Helpers with @pre_compose
```python
from leafmesh import pre_compose, zapier, mcp, composio, n8n

@pre_compose(
    context_processor=zapier(action="slack_send", api_key="..."),
    # or: composio(action="GMAIL_SEND", api_key="..."),
    # or: mcp("http://localhost:3000", "search"),
    # or: n8n("http://localhost:5678/webhook/abc"),
    # callback mode: n8n("http://n8n.example.com/webhook/abc", mode="callback", callback_timeout=120),
)
async def my_agent(llm_response, input_data, context):
    integration_result = context["prepared_data"]["business_context"]
    return {"result": llm_response, "integration": integration_result}
```

All helpers accept `mode="callback"` and `callback_timeout=N` parameters.

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
    bootstrap_servers: ["kafka-1:9092"]
    security_protocol: SASL_SSL
    sasl_mechanism: SCRAM-SHA-512
    sasl_username: leafmesh
    sasl_password: ${KAFKA_PASSWORD}

# 2. Bind agents to topics/queues
agents:
  order_processor:
    agent_type: programmatic
    listen_events:
      - broker: orders_kafka
        topic: orders.created
        group_id: leafmesh-order-processor   # defaults to <sdk-name>-<agent-name>
        filter:
          source: "/region/us-east-1"        # CloudEvents-style AND-equality filter
        delivery:
          max_retries: 3
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

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `LEAFMESH_LICENSE_KEY` | Yes | License key from leafcraft.ai |
| `LEAFMESH_ENV_TOKEN` | No | Environment token — scopes HITL data + telemetry per environment |
| `OPENAI_API_KEY` | For OpenAI models | OpenAI API key |
| `ANTHROPIC_API_KEY` | For Claude models | Anthropic API key |
| `GOOGLE_API_KEY` | For Gemini models | Google AI API key |
| `DEEPSEEK_API_KEY` | For DeepSeek models | DeepSeek API key |
| `AZURE_OPENAI_API_KEY` | For Foundry | Azure OpenAI key |
| `REDIS_HOST` | No | Redis host (default: localhost) |
| `REDIS_PORT` | No | Redis port (default: 6379) |
| `REDIS_PASSWORD` | No | Redis password |
| `ZAPIER_NLA_API_KEY` | For Zapier | Zapier NLA key |
| `COMPOSIO_API_KEY` | For Composio | Composio key |
| `XAI_API_KEY` | For Grok models | xAI API key |
| `MISTRAL_API_KEY` | For Mistral models | Mistral API key |
| ~~`LEAFMESH_LLM_HARD_TIMEOUT_S`~~ | **DEAD (2.4.131)** | Moved to YAML `timeouts.llm_hard_timeout_s` (default **90**s; timed-out calls retry **once**, then fail; super-agent phases get 600s). The env var is **no longer read** — set the YAML block. Raise for long-running agents with big outputs |
| `LEAFMESH_SKILLS_DIR` | No | Root dir for `filesystem` skill sources when no `config.root` is set (default `./skills/`) |
| `LEAFMESH_API_PORT` | No | Mesh API port (default **18820**) |
| ~~`LEAFMESH_MAX_PARALLEL_TOOL_CALLS`~~ | **DEAD (2.4.131)** | Moved to YAML `limits.max_parallel_tool_calls` (default **8**). Env var no longer read |
| ~~`LEAFMESH_SUPER_AGENT_STEP_CONCURRENCY`~~ | **DEAD (2.4.131)** | Now a per-agent super-agent dict key: `super_agent: {step_concurrency: N}` (default **4**). Env var no longer read |
| `LEAFMESH_WORKERS_MODE` | No | `1` enables workers/HA mode — required for running more than one instance against one Redis (exactly-once events, singleton runners, cross-instance locks) |
| `LEAFMESH_WORKERS` | No | Number of worker processes in workers mode |
| `LEAFMESH_LEASE_SECONDS` | No | Singleton-runner lease window (default **30**). Raise (e.g. `120`) when Redis is remote over a flaky link so connectivity blips shorter than the window never flap leased runners; heartbeat auto-scales to a third of the window (2.4.107) |
| `LEAFMESH_LEASE_HEARTBEAT` | No | Explicit lease heartbeat interval override (must be < lease window) |

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
except LeafMeshError as e:
    # Base exception for all SDK errors
```
