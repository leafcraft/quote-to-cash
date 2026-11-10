---
name: leafmesh
description: Wire multi-agent meshes, HITL webhooks, can_call routing, decorators, and YAML config for the LeafMesh SDK. Use when adding agents, configuring flows, or debugging mesh issues.
allowed-tools: Read, Grep, Glob, Edit, Write, Bash
---

# LeafMesh SDK Development Skill

You are an expert at building multi-agent orchestration systems with the LeafMesh SDK.

> **SDK baseline: 2.4.509** (the templates pin `leafmesh>=2.4.509`; customers
> on PyPI are still on 2.4.418 — say so before relying on anything newer).
> Four changes in 2.4.481–2.4.484 rewrite how you work: the configuration
> **lives in the store**, not in `config.yaml`
> ([Where the configuration lives](#where-the-configuration-lives-24481)); a
> saved setting **applies without a restart**
> ([What applies when](#what-applies-when-24484)); how an agent runs in
> parallel is **one `scaling:` block**
> ([agent-config-fields.md → scaling](agent-config-fields.md#scaling--how-an-agent-runs-in-parallel-24484));
> and every message names a page Studio really has
> ([Studio's Infrastructure page](#studios-infrastructure-page--where-each-record-is-made)).
> 2.4.485–2.4.486 tighten the vault and the human seat: **the vault keeps
> sign-in only** (no connector env fallbacks, no plain query/body rows — what
> is sent is set on the page that uses the record); external agents are picked
> from the **External agents page** (`external_agent:`); **a human seat waits
> its time and stops** (no timeout escalation) and its **`reply_reader`** never
> picks a route ([When nobody answers](#when-nobody-answers-24486)).
> 2.4.487–2.4.491: the response cache keeps **lookup-only turns** (a tool can
> say `changes_nothing`); a Super-Agent step can run **several attempts at
> once** (`super_agent.tries`); an external agent **takes its kind from the
> vault record** it picks; a connector with **no address is not set up**
> (switched off, never called); a tenant can **bring its own credentials**
> (`tenant_credentials_only`); cost by tenant comes **from telemetry**.
>
> Before wiring or debugging agents, read
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

- [**Rule 0 — WHO IS IN THE MESH (read first)**](#rule-0--who-is-in-the-mesh-decide-this-before-you-write-any-yaml) — people vs agents vs systems
- [When the user asks you to… do this](#when-the-user-asks-you-to-do-this) — quick action table
- [Rule 1 — A mesh is a TEAM, not a pipeline](#rule-1--a-mesh-is-a-team-not-a-pipeline)
- [Rule 2 — One ROLE, multiple RESPONSIBILITIES](#rule-2--one-role-multiple-responsibilities-the-hiring-test)
- [Rule 3 — Bound every retry back-edge](#rule-3--bound-every-retry-back-edge)
- [How This Project Works](#how-this-project-works) · [**Where the configuration lives**](#where-the-configuration-lives-24481) · [**What applies when**](#what-applies-when-24484) · [Core SDK Pattern](#core-sdk-pattern) · [User-Facing APIs](#user-facing-apis)
- [Agent Types](#agent-types) · [Super-Agent v3](#super-agent-v3) · [Skills System](#skills-system)
- [**The Board, Experience & Identity**](#the-board-experience--identity) — on by default; what you must get right · [Versions — draft, try, default](#versions--draft-try-default-24454)
- [Command Center (the business board)](#command-center-the-business-board) · [Image generation](#image-generation)
- [STRICT — fields by `agent_type`](#strict--fields-by-agent_type) · [STRICT — `human_interface` rules](#strict--human_interface-rules)
- [Human-in-the-Loop (HITL)](#human-in-the-loop-hitl)
- [**THE ROOM RULES**](#the-room-rules--get-these-wrong-and-the-mesh-is-rude-or-deaf) — when a channel message is ours, and which conversation it joins
- [Credentials — `connection:`, never a literal](#credentials--connection-never-a-literal) · [Studio's Infrastructure page](#studios-infrastructure-page--where-each-record-is-made) · [Vault references & your own code](#vault-references-your-own-code-and-file-credentials) · [Per-seat channel fields](#per-seat-channel-fields-worth-knowing) · [Inbox vs connector seats](#inbox-seats-vs-connector-seats)
- [**Approval is routing**](#approval-is-routing) — there is no approval flag
- [YAML Agent Config (All Fields)](#yaml-agent-config-all-fields) · [Scaling](#scaling--one-block-24484) · [Traces & licence](#traces-what-is-hidden-and-the-licence-24481) · [Devices](#devices--an-agent-that-reaches-a-device) · [External agents](#external-agents--external_policy-and-budgets) · [Self-healing](#self-healing) · [Condition Syntax](#condition-syntax-can_call-conditions)
- [Decorators — Making an Agent Self-Reliant](#decorators--making-an-agent-self-reliant)
- [Communication Types](#communication-types) · [Fan-In Patterns (`wait_for`)](#fan-in-patterns-wait_for) · [Tools](#tools)
- [Manager (Coordination + Escalation)](#manager-coordination--escalation) · [LLM Providers](#llm-providers)
- [Building New Agents — Step by Step](#building-new-agents----step-by-step)
- [Session & Upstream Yields](#session--upstream-yields)
- [Additional Resources](#additional-resources) · [Field reference](#field-reference)

## Rule 0 — WHO IS IN THE MESH. Decide this before you write any YAML.

Every mesh that came out wrong came out wrong HERE, before a line of config
existed. The rest of this skill tells you how the pieces talk; this tells you
what the pieces ARE. Get it wrong and you produce a config that loads, boots,
validates — and models the customer's business incorrectly, which no test
catches.

Read the customer's story and sort every noun in it into exactly one row of
the table below. Every noun lands in exactly one; nothing is allowed to be
two things.

The shape to hold in your head is the stage triad:
**the agent PRODUCES, the human DECIDES, the system RECORDS.**
Each leg is a different `agent_type`, and the SaaS itself is none of them.

| In the story | It is | It appears as |
|---|---|---|
| A **person** who decides, approves, answers, or is asked | a **human member** | `agent_type: "human"` + exactly one door (Inbox, or a `channels:` block) |
| A **worker that REASONS** — drafts, classifies, judges, summarises | an **LLM hire** — the *produces* leg | `agent_type: "llm"` + `model:` + `prompt:` |
| A **worker that RECORDS or ACTS on a system of record** — applies the config, posts the entry, issues the PO, migrates the rows | a **programmatic hire** — the *system* leg | `agent_type: "programmatic"` (+ `integration:` when it is only that connector call) |
| A **hire that lives in ANOTHER FRAMEWORK** — CrewAI, LangGraph, AutoGen, n8n, A2A | an **external hire** | `agent_type: "external"` + `external_agent:` (an entry on the External agents page, 2.4.486) or `framework:` |
| The **SaaS itself**: Slack, Freshworks, Salesforce, Gmail, Drive, Postgres, an API, an MCP server | a **TOOL, inside a hire** | `tools:`, `mcp:`, `connector_config:`, or `channels:` — **never its own agent, never a member** |

> **Keep these two apart, they are the pair most often confused:**
>
> - **`programmatic` is the SYSTEM leg.** It is the hire that touches the
>   customer's system of record, deterministically, with no reasoning —
>   Freshworks is its *tool*. "Apply the approved config to the tenant" is a
>   programmatic hire calling Freshworks. It is not Freshworks.
> - **`external` means EXTERNAL — another agent framework**, nothing else. Do
>   not reach for it because the thing being called is outside your company. A
>   REST API you call is a tool; a CrewAI crew that reasons on your behalf is an
>   external hire.
>
> So "the system records" never means "add Freshworks as a node". It means:
> **the write is owned and guarded, and the SaaS is what gets called.**

#### Where the control actually lives — this is NOT `agent_type`

The triad splits a control: whoever produces must not also be the one who
commits. But **`agent_type` is not what enforces that split.** A programmatic
actuator that simply carries out an LLM's instruction is no safer than a
guarded tool — it moves the same write one hop away and calls it a control.

The enforcement lives **inside the tool**:

- `apply_items` refuses unless a code-written stamp says a human released it.
- `run_migration` refuses without a recorded dry-run **and** the named
  authorisation.
- Batches are bounded in code; every write is read back before it is ledgered.
- The stamps are written only by `@pre_compose`, from the human's verdict —
  never by the model.

So the model may *choose to call* the tool; **code decides whether it may
succeed.** Read the triad as: **the agent produces, the human decides, the
TOOL refuses or records.**

Which `agent_type` you pick is a separate question — what the worker *is*
(reasons / writes deterministically / lives elsewhere). A pod built entirely
from `llm` hires with properly guarded tools is a legitimate design, and so is
one with programmatic actuators. What is never legitimate is an unguarded
irreversible write, whichever type performs it.

### The two mistakes that produce a broken pod

**1. Making a system into an agent.** Slack is not an agent. Nor is Freshworks,
Drive, Gmail, or your database. A system cannot be given an intent and held to
it — it has no judgement and cannot be accountable for an outcome. It is
something an agent *uses*, or the *door* a person is reached through.

> `channels: {slack: {...}}` on a HUMAN seat means "this person is reached on
> Slack". It does NOT mean "Slack is a participant". If you find yourself
> writing `agent_type: "programmatic"` for something called `slack_agent`,
> stop — you are modelling a door as a worker.

**2. Making a person into an LLM agent.** If the story says a Data Owner rules
on a question, the Data Owner is a `human` seat that gets ASKED. An LLM agent
that "acts as the Data Owner" is not a gate at all — it is the mesh asking
itself for permission, and it will approve things no person ever saw.

### The test, when you are unsure

> **If it DECIDES, it is a human seat.**
> **If it THINKS, it is an `llm` hire.**
> **If it WRITES to a system of record, it is a `programmatic` hire.**
> **If it reasons inside another framework, it is an `external` hire.**
> **If it is CALLED, it is a tool inside a hire.**
> **There is no sixth kind.**

Freshworks, Slack, Notion, Asana, Drive, your database — every one of them is
*called*. None of them is ever a box on the org chart. What goes on the chart
is the **hire that calls it**.

### Four nouns, and the one most builds miss

| Noun | Who | Where their seat lives |
|---|---|---|
| **Hire** | an AI agent you configure and instruct | `agents:` — llm / programmatic / external |
| **Member** | a person in **your** org | a `human` seat, your Inbox |
| **Participant** | a person in the **client's** org | a `human` seat too, but their availability, their timezone, their much longer timeout |
| **Tool** | a system | inside a hire — `tools:`, `mcp:`, `connector_config:`, `channels:` |

**Participants are the one most builds miss.** A client's QA Owner or Tenant
Owner is not your colleague and not an agent — they are a person outside your
org who owns one decision, may act once or never on an engagement, and cannot
be given a five-minute timeout. Sort every person into member or participant
before you pick a timeout, because that choice IS the timeout.

### There is a VAULT. Most credentials go in it, not in `.env`.

Decide this alongside the cast, because it decides what you write in config.
The mesh has an encrypted credential store — the **vault** — filled from
**Studio's Infrastructure page**, and config refers to what is in it **by
name**. It is not optional or advanced; it is the normal path.

| What | Where | How config refers to it |
|---|---|---|
| Channel credentials — Slack `bot_token`/`signing_secret`/`app_token`, Teams, Discord, Cliq, WhatsApp, Email | **the vault** | `connection: "slack-workspace"` |
| Connector credentials — MCP, Zapier, Composio, n8n, custom | **the vault** | `connection:` / `vault_connection:` |
| **Server addresses and header rows** — human-seat / escalation webhooks, broker hosts and URLs, MCP urls, `mesh.local`/`foundry`/`bedrock`/`vertex` endpoints and regions (2.4.481) | **the vault** | `connection: <name>` — see [Vault-only values](nuances-and-gotchas.md#vault-only-values-24481) |
| **Model provider keys** — `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, … | **`.env`** (or a model connection on the Infrastructure page; `.env` wins) | never named in config at all |
| Deployment identity — licence key, env token, ports, the agency's name (`LEAFMESH_AGENCY_NAME`), Redis/Postgres (`LEAFMESH_STORE`, `REDIS_*`, `POSTGRES_*`; never a YAML block, 2.4.482) | **`.env`** | exempt from the credential gate |

Two things that catch everyone:

- **A provider credential written into config makes the mesh REFUSE TO BOOT**
  (2.4.180) — and **`${ENV_VAR}` does not rescue it.** Substitution happens
  when the config loads and the gate reads the result, so an unset variable
  leaves the field empty and a set one leaves the literal token, which is
  refused. There is no third outcome. `connection:` is the only path.
  **Since 2.4.481 the same holds for addresses, client ids and header rows**
  in every block that picks a vault record (webhooks, escalation, channels,
  brokers, MCP, zapier/composio/n8n rows, mesh providers, and — from 2.4.482 —
  every external agent's `connector_config`): written inline, the
  config **fails to load** naming the field. A `connection:` whose record is
  missing never blocks boot — the agent / seat / broker consumer that needs it
  is switched off until the record is created. Full rule:
  [Vault-only values (2.4.481+)](nuances-and-gotchas.md#vault-only-values-24481).
- **Model keys are the exception: `.env` or Infrastructure → Models.** A key
  in `.env` wins; a model connection on the Infrastructure page fills what
  `.env` leaves out. A model whose provider has no key anywhere fails plainly
  (2.4.482): "model 'X' needs the <provider> provider, which has no key here —
  add one on Infrastructure → Models, then try again" — it is never sent to
  the local model any more.

Full detail: [WHERE EACH SECRET LIVES](#where-each-secret-lives--read-this-before-writing-a-env).

### Now count your cast

Before writing YAML, write the cast as a list: every hire, every member, every
participant, and — separately — every system, named as the tool of the hire
that calls it. **List the humans first, one seat per decision they own.** A pod
with one human seat and four systems-as-agents is not a design; it is a
taxonomy error that will load, boot, validate, and model the business wrongly.

### Now count your members

Before writing YAML, write the cast as a list: every human seat, every agent,
and — separately — every system, named as the tool of the agent that uses it.
A pod with four systems and no humans is almost always a taxonomy error, not a
design. So is one where a system has a `can_call`.

---

## When the user asks you to... do this:

> Every row below assumes you have already done **Rule 0** and know which
> participants are people, which are agents, and which are systems. If you have
> not, go back — none of these actions will save a wrong cast.

| User says | Action |
|-----------|--------|
| "Change the config of an agency that is already running" | **Not a file** — the configuration lives in the store (a create-leafmesh project ships no configuration file; a file given to `from_yaml` is read only on the first boot). Change it in Studio (settings, or the YAML editor), or `PUT /api/yaml/raw` / `PATCH /api/yaml/config` with `"save_to_disk": true`. Each save is a new version, applied on every pod without a restart — see [Where the configuration lives](#where-the-configuration-lives-24481) |
| "Run this agent on many items at once" / "cap how many run at once" | One `scaling:` block: `copies` (several copies on one job — `fixed` count, or `auto` handing out a list item by item) and `runs.max` (jobs at once across every pod). `parallel`, `max_concurrent`, `instances`, `instances_handoff` are refused at load — see [Scaling](#scaling--one-block-24484) |
| "Add a new LLM agent" | 1. Add the YAML block in Studio's YAML editor (or `leafmesh config export` → edit → `leafmesh config import`) 2. Create `agency/<name>_agent.py` (optional -- pure YAML works) 3. Wire `can_call` from upstream agents 4. Add entry point if needed |
| "Add a programmatic agent" | 1. Add YAML block with `agent_type: "programmatic"` 2. If connector-only: add `integration` + `connector_config` (no Python needed) 3. If Python logic: create `agency/<name>_agent.py` 4. Wire `can_call` |
| "Add an external agent" | 1. Set it up once on Studio's **External agents page** (vault record, settings; the record decides the framework since 2.4.491 — name one only for a custom record: `a2a` or `custom_api`) 2. Add a YAML block with `agent_type: "external"` + `external_agent: <entry>` (2.4.486; the old `framework` + `connector_config: {connection}` still works) — no Python needed 3. Optionally add `agency/<name>_agent.py` to post-process connector result 4. Wire `can_call`. See [External agents](#external-agents--external_policy-and-budgets) |
| "Let this agent call an HTTP API" (it has an OpenAPI / Swagger file) | Agent-level `api_tools: [entry]` after the owner uploads the file on the Tools page — **never write a tool for it**. The owner switches each endpoint on or off. See [api_tools](agent-config-fields.md#api_tools--call-an-http-api-from-its-openapi--swagger-file-24419) |
| "Let this agent use an MCP server's tools" | Agent-level `mcp:` block — the server's tools join that agent's tool list. Do **not** re-list them under `tools:`. See [MCP servers as tools](agent-config-fields.md#mcp--mcp-servers-as-tools-the-normal-way) |
| "Integrate with Zapier/n8n/Composio/MCP" | **First: this is a TOOL, not a new member.** Decide which EXISTING hire needs it and give it to that hire — `mcp:` on the agent, or `integration:`/`framework:` + `connector_config` when the hire IS only that call. Do not create an agent named after the system. See [Rule 0](#rule-0--who-is-in-the-mesh-decide-this-before-you-write-any-yaml). The generic tools `zapier_action`, `mcp_call`, `composio_action`, `n8n_workflow` and the tool category `integration` were removed in 2.4.485 (refused at load); in your own code the `n8n()` / `zapier()` / `composio()` helpers take `connection="<record>"` and refuse an inline address or key |
| "Set up HITL / human review" | Pick **one** `human_interface`: `default` (inbox), `webhook` (channels/HTTP), or `api` (Python callback). Each one accepts a *different* set of config fields — see HITL section below. Mixing them (e.g. `default` + `webhook_config`) is rejected at YAML load. A seat declared with nothing else is answered in the Inbox (2.4.486). Add a `reply_reader` so the person's words can route, and read [When nobody answers](#when-nobody-answers-24486) |
| "When this agent finishes, post its output to our system" | `notify: {webhook: <name>, when: done\|failed\|both}` — the webhook is made on Tools → Webhooks (it picks an Outbound webhook vault record). Sent by the mesh in the background, never fails the run. See [notify](agent-config-fields.md#notify--post-the-output-to-a-webhook-24485) |
| "Let a Claude Code agent use other tools / another folder / another permission mode" | Host rights — from the host: `leafmesh agent host-rights <agent> --allowed-tools … --cwd … --permission-mode …` (2.4.485). The API refuses them. Per-call narrowing: `external_policy.allowed_tools` / `denied_tools` (2.4.486) |
| "Connect agents" / "wire routing" | Add `can_call` entries with conditions. Use `calling_agent_response.field` in conditions. |
| "Add a tool" | Create `@global_tool()` in `agency/tools.py` (with parentheses: a bare `@global_tool` registers nothing, so the agent can never call the tool and start warns "not a registered tool"), import the module before `start()`, and add the tool name to the agent's `tools:` list in YAML |
| "Fan-out / fan-in" | Add multiple agents in `can_call` (fan-out), add `wait_for` expression on aggregator (fan-in) |
| "Schedule an agent" | Add `wake_up: "cron expression"` to agent YAML, and a `timezone:`. Standard cron day-of-week (0 = Sunday); a schedule the scheduler cannot run is refused at load — see [gotcha #13](nuances-and-gotchas.md#13-wake_up-crons-run-in-utc-unless-you-declare-a-timezone-24124) |
| "A person must approve before X happens" | Route the work to a human agent: a `can_call` with a condition on the agent before X, and `can_call` from the human seat to X. There is no approval flag — see [Approval is routing](#approval-is-routing) |
| "Let the agent do something on a device" | A `device:` block on the agent (a notifier connection; optional room). The device comes with the request, never from config — see [Devices](#devices--an-agent-that-reaches-a-device) |
| "Limit what an external agent can reach or receive" | An `external_policy:` block on it — see [External agents](#external-agents--external_policy-and-budgets) |
| "Debug why agent X isn't called" | Check `can_call` conditions, verify `calling_agent_response` fields match, check `communication_type` |
| "Validate my config" | `leafmesh config check` checks the stored configuration (each problem with its line). POST a config to `/api/yaml/validate`. Read what runs with `GET /api/yaml/raw` or `leafmesh config export` (the store's latest version) |
| "Add a Super-Agent" / "this task needs multi-step planning + verification" | Set `super_agent: true` (on, defaults) or a **dict** to tune it: `super_agent: {cost_ceiling, wall_clock, synth_max_tokens, step_concurrency, tries, …}` (2.4.123+; `tries` 2.4.491; the dict is the only tuning path — flat `super_agent_*` keys and `LEAFMESH_SUPER_AGENT_*` env vars are dead). See [Super-Agent v3](#super-agent-v3) section. Use it when the task is genuinely multi-step (research synthesis, multi-file edits, multi-page analysis) — for one-shot tasks, plain LLM agent is faster + cheaper |
| "Add Skills" / "give this agent reusable playbooks" | Add `skills: {sourceName: "...", enabled: true, names: [...]}` on the agent. **Local `.md` files are NOT auto-loaded** — the default source is hosted (Redis). For filesystem skills, register a source via `POST /api/skills/sources` first. See [Skills System](#skills-system) section |
| "Retry when X fails" / "loop back to re-do upstream work" | NEVER write an unbounded retry back-edge. Add a per-session exhaustion counter in the agent's Python, yield a `*_retry_exhausted` boolean, gate the back-edge on it, add a terminal route. See [Rule 3](#rule-3--bound-every-retry-back-edge) |
| "Use Grok or Mistral as the model" | Set `model: "grok-4.7"` (or `grok-4.6`, `grok-4.3`, `grok-build-0.1`) and `XAI_API_KEY`; or `model: "mistral-large-4-0"` (or `mistral-small-4-0-26-03`, `codestral-2508`) and `MISTRAL_API_KEY`. Both are native providers — no Bedrock/Vertex routing needed. `grok-4`, `grok-3`, `mistral-large-2` are retired |
| "Use Kimi / Qwen / GLM / MiniMax / another vendor" | Write the vendor's own model id — `kimi-k3`, `qwen3.8-max`, `glm-5.3`, `minimax-m3`, `mercury-3`, `muse-spark-1.3`, `step-5-preview`, `trinity-large-thinking` — and set its key (`MOONSHOT_API_KEY`, `DASHSCOPE_API_KEY`, `ZAI_API_KEY`, `MINIMAX_API_KEY`, …; full table in [LLM Providers](#llm-providers)). Routing is by the name; no provider field |
| "One key for many models" / "use OpenRouter" / "Groq" | `model: "openrouter/<lab>/<model>"` + `OPENROUTER_API_KEY` (each answer carries its real cost); `model: "groq/<model>"` + `GROQ_API_KEY`; `cerebras/<model>` + `CEREBRAS_API_KEY`. The prefix is stripped before sending. Optional — the default is each vendor with its own key |
| "Put this agent on Slack/Teams/Discord/Telegram/Cliq/WhatsApp" | `human_interface: "webhook"` + a `channels:` block. Credentials come from a **connection**, never a literal — the mesh refuses to boot on an inline provider credential. Then read [THE ROOM RULES](#the-room-rules--get-these-wrong-and-the-mesh-is-rude-or-deaf): in a shared room a bare message is IGNORED, a mention opens a NEW conversation, and a thread reply continues one. |
| "Slack but we have no public URL" | Socket Mode. Put an app-level (`xapp-`) token in the connection and it turns itself on — inbound arrives over an outbound WebSocket. Without it a local/NAT'd mesh can post but will never hear anything. |
| "Only our staff should answer this seat" | `operators_only: true` on the channel block, plus an `operators` map. Off by default, because a customer-facing seat must accept strangers. Refused senders are logged with the reason. |
| "Where do credentials go?" | A record on Studio's Infrastructure page (its section — see [Studio's Infrastructure page](#studios-infrastructure-page--where-each-record-is-made)); config references it by name (`connection: "slack-workspace"`). One connection holds the provider's whole credential set **and its addresses** (2.4.481: a URL, host, header row or client id written in a webhook / escalation / channel / broker / MCP / integration / provider block fails to load). Free-form strings elsewhere (`request_form`, tool args) can point at the vault with `${vault:conn}` / `${vault:conn.field}`; your own code uses `await secret("conn")`. `${ENV_VAR}` does NOT rescue a vault field. |
| "Send / receive email from an agent" | Add the Email channel: `channels: {email: {connection, provider, from_address, inbound_domain}}` — `smtp_host`, `smtp_port`, `smtp_username`, `smtp_password` live on the email connection (refused in the block since 2.4.481). Outbound over SMTP; inbound is the **provider's webhook** (Mailgun/SendGrid/Postmark) — there is **no IMAP**, so a mesh with no public URL cannot receive mail. The field is `smtp_username`, not `smtp_user`. |

## Current project config
!`cat configs/config.yaml 2>/dev/null | head -30`

> A project made by create-leafmesh ships **no configuration file**, so this is
> usually empty. What runs is the latest version in the agency's store — read
> it with `leafmesh config export`, `GET /api/yaml/raw` or Studio's YAML
> editor. (A project started with `from_yaml` has a file here; it is read
> only on the first boot, 2.4.481+.)

## Rule 1 — A mesh is a TEAM, not a pipeline

This is the most important thing to internalise before designing or
modifying a mesh.

> ### You can obey every word below and still build a pipeline
>
> This happened on a real build. `can_call` was wired peer-to-peer, conditions
> everywhere, no fixed chain — and the pod was still a queue. The pipeline was
> not in the wires. It was in **the state model and the triggers**:
>
> - the case record had one `stage` / `waiting_on` / `next_gate`, and setting a
>   new gate **cleared the previous one** — so only one thing could ever be
>   waiting;
> - only one hire had an `entry_point`, so every other hire could start only
>   by being handed to.
>
> **Four rules that actually prevent it:**
>
> 1. **Every hire gets its own trigger.** All of them can start on day one. A
>    hire that can only be handed to is a pipeline stage wearing an agent's name.
> 2. **Gates guard irreversible ACTIONS** — apply, send, book, issue, migrate.
>    Never gate *thinking*: reading, profiling, designing, drafting. A gate in
>    front of thought is a queue.
> 3. **Several gates must be open at once**, on different people. If your store
>    can only hold one pending gate, you have built a queue in the data.
> 4. **If your case record has a single `stage` field, you built a pipeline** —
>    whatever `can_call` says.
>
> **The test:** fire one "case opened" event. Do at least three hires start
> within the same second, each on its own responsibility? If not, it is a queue.

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
| Escalate after N errors | **The Manager** | `manager.escalation.targets` + `auto_escalate` (a person not answering is **not** escalated since 2.4.486 — [When nobody answers](#when-nobody-answers-24486)) |

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

> **This list says what must never be MERGED — not what you should add.** A
> real build read "audit sinks" here and created a `crm_audit_logger_agent`,
> which the user deleted: *"we don't have such agents, we already have
> logger."* **The SDK's own session events, feed and logs ARE the audit
> trail.** Never add a hire whose job is to write records of what other hires
> did — it is a second copy of something the mesh already keeps, and it can
> drift from it. The entry applies only when a domain genuinely requires a
> WORM terminus the SDK does not provide; then say why.

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
agency/*_agent.py      <- Agent logic (auto-discovered by filename match)
agency/tools.py        <- Custom tools (@global_tool, @tool)
main.py                <- Entry point: LeafMesh.from_store() (name + store from .env, configuration from the store), starts mesh + API server
hitl_stub_receiver.py  <- Webhook stub for testing HITL locally
.env                   <- where the store is (LEAFMESH_STORE, REDIS_* / POSTGRES_*), LEAFMESH_AGENCY_NAME, licence key,
                          model keys, CREATE_LEAFMESH_TEAM (the team the project was made from)
```

**No configuration file.** A project made by create-leafmesh ships none: the
team's configuration (agents, topology, entry points, HITL) stays in the
create-leafmesh package. `create-leafmesh --start` loads it into the store
before the first start with `leafmesh config import --if-empty -` (saved only
while the store holds no configuration, so a re-run never overwrites Studio
edits); after that it is changed in Studio.

**Auto-discovery**: The SDK matches Python function names to YAML agent names. `greeter_agent()` in `agency/greeter_agent.py` binds to the `greeter_agent:` block in the configuration.

**Execution flow**: Entry point -> agent function runs -> SDK handles mesh communication (can_call), session state, persistence, and observability automatically.

**Persistence is a deployment choice, not a code one.** The same agency runs on
Redis or on Postgres — set in **`.env` only** (2.4.482): `LEAFMESH_STORE=redis`
(default) with `REDIS_*`, or `LEAFMESH_STORE=postgres` with `POSTGRES_*`. Never
write a `persistence:` or top-level `redis:` block in config.yaml — it is
ignored with a boot warning on 2.4.482–2.4.485, and from 2.4.486
`LeafMesh.from_yaml` raises `ConfigError` if its values differ from `.env`
(naming each `.env` line to add, e.g. `REDIS_DB=3`); a matching block still
loads, with the warning.
Set the store explicitly in `.env` (`LEAFMESH_STORE`, `LEAFMESH_AGENCY_NAME`,
`REDIS_URL` or `REDIS_HOST`/`PORT`/`DB`/`PASSWORD`). Studio → Infrastructure → Datastores shows whether
the store is reachable, its latency, the server, the settings in force and which
`.env` names set them (`GET /api/infra/datastore` — never the address or
password). Nothing in your agents or YAML changes between backends, so never
write agent code that assumes Redis.

## Where the configuration lives (2.4.481)

The agency's configuration is **one YAML document in its store** (the same
Redis or Postgres that holds its sessions and vault) — not a file. A project
holds only its custom code and its `.env`. Studio edits that document.

- **Every save is a version.** A Studio save (settings or the YAML editor), or
  a config-API save, is stored as the next version; every pod runs the latest.
  Another pod picks up a saved change within about 15 s
  (`runtime.config_sync_poll_s`, default 15) and **applies it live** (2.4.484;
  2.4.481–2.4.482 reloaded the pod instead). Every save is kept, and an earlier
  version can be **made the default again** — in Studio, or with the versions
  API (kind `mesh_yaml`, name `config.yaml`): list them with
  `GET /api/versions/mesh_yaml/config.yaml`, read one's full text with
  `GET /api/versions/mesh_yaml/config.yaml/{n}`, and make it the default with
  `PUT /api/versions/mesh_yaml/config.yaml/default` `{"version": n}`. That
  applies the whole file through the normal save path — a new store version,
  live on every pod. `n` is **the version number shown in the versions list**;
  it does not match the store's internal version counter (a known item).
- **`LeafMesh.from_store()`** starts an agency from its name
  (`LEAFMESH_AGENCY_NAME` in `.env`) and where its store is (`.env`);
  everything else is read from the store at `start()`. **An empty store starts
  a blank agency** — every setting written out with its default, no agents —
  built in Studio. `from_store()` with no `LEAFMESH_AGENCY_NAME` raises
  `ConfigError` ("LEAFMESH_AGENCY_NAME is not set — the agency's name is needed
  before its configuration can be read from the store"). This is what
  create-leafmesh projects use; `create-leafmesh --start` fills the empty store
  first (`leafmesh config import --if-empty`). From 2.4.498
  `leafmesh.intelligence()` registration before `start()` works under
  `from_store()`.
- **`LeafMesh.from_yaml("config.yaml")`** (an SDK option; create-leafmesh
  projects do not use it) behaves the same once `start()` runs. The file is read for
  the agency's name; where the store is comes from `.env`. At `start()`:

  | Store | `config.yaml` | What runs | Boot log (WARNING) |
  |---|---|---|---|
  | empty | present | the file (minus any `persistence:` / `redis:` block), saved as **version 1** | "`<path>` was imported into the store as version N. The configuration lives in the store from now on — edit it in Studio; this file is no longer read for it. Only the agency's name and where its store is are still read from this file — …" The log then advises moving the agency name and the datastore settings (`REDIS_*` or `POSTGRES_*`) to `.env` and deleting the file |
  | has a version | unchanged since import | the store's latest version | "`<path>` is no longer read for the configuration — it lives in the store (version N); edit it in Studio. …" |
  | has a version | **edited after import** | the store's latest version — **the edit is NOT applied** | "`<path>` was edited after it was imported into the store — that edit was NOT applied. The configuration lives in the store now (version N); make changes in Studio. …" |
  | has a version | fails its checks | the store's latest version | "`<path>` does not pass the checks any more; it is not read for the configuration (the store's version N runs)" |
  | empty | absent (`from_store()`) | a blank agency, saved as version 1 | "A blank agency '<name>' was started: its configuration is in the store (version 1). Build it in Studio." |

  The file is **never re-imported**, never becomes a new version, and a
  restart does not apply an edit to it. There is no env flag or
  re-import-on-start; `leafmesh config import <file>` saves a file as the next
  version only when you run it.

**So, as Claude:** never add a `configs/config.yaml` to a create-leafmesh
project — it ships none and `from_store()` reads none. To fill an empty store
from a file, use `leafmesh config import --if-empty <file>`. Otherwise change
the configuration one of these ways — each save is the next version and
applies without a restart:

- Studio — the settings forms, or the raw YAML editor.
- `leafmesh config export > config.yaml`, edit, `leafmesh config import
  config.yaml` (checked before it is saved); `leafmesh config check` /
  `versions` / `rollback` to check, list and restore versions.
- `PUT /api/yaml/raw` (header `X-API-Key`) with
  `{"yaml_content": "<the whole YAML>", "save_to_disk": true}`.
- `PATCH /api/yaml/config` with `{"updates": {...}, "save_to_disk": true}` —
  changes only the keys sent. A setting sent as `null` goes back to its default.
- `PATCH` / `PUT /api/yaml/agents/{name}` for one agent.

Without `"save_to_disk": true` the change is held only in that process's memory
and is lost on restart. Never tell anyone to "edit config.yaml and restart" for
a running agency. Your **Python code** (`agency/*.py`) is not configuration —
it is loaded when the process starts.

## What applies when (2.4.484)

A saved setting applies **without anyone pressing restart**, on every pod alike:

| Kind of change | How it applies |
|---|---|
| Almost everything — agents, routes, prompts, models, schedules, limits, timeouts; the Manager and its summarizer (rules, timing, routing, model, what it listens to) | **Live**, in place (the Manager keeps what it tracks for runs in flight) |
| `brokers`, `self_healing.enabled`, `api.cors_origins`, `runtime.lease_seconds` / `lease_heartbeat_s`, `architecture`, `auto_discover`, `limits.consumer_inflight_max`, `manager.enabled` (switching the Manager on/off) | The agency **reloads itself in place** within seconds — no restart to press; runs in flight finish first or are picked up again. The save's response lists these under `reloading_fields` |
| `evolution_api.enabled` / `host` / `port` | Only these need a **process restart** (`restart_required_fields` in the save's response) |

## Core SDK Pattern

```python
from leafmesh import LeafMesh

sdk = LeafMesh.from_store()                        # create-leafmesh projects: LEAFMESH_AGENCY_NAME + the store in .env
# sdk = LeafMesh.from_yaml("config.yaml")         # SDK option: the file is imported on the first boot only
await sdk.start()   # Reads the configuration from the store, starts agent registry, API server, scheduler
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
| GET / PUT | `/api/yaml/raw` | Read the running configuration (the store's latest version) / replace it — `{"yaml_content": "...", "save_to_disk": true}` saves the next version, applied live |
| PATCH | `/api/yaml/config` | Change only the keys sent — `{"updates": {...}, "save_to_disk": true}`; a key sent as `null` resets it to its default |
| GET | `/api/versions/mesh_yaml/config.yaml` | The configuration's saved versions (numbers are the list's own, not the store's internal counter) |
| GET | `/api/versions/mesh_yaml/config.yaml/{n}` | One version's full YAML text — `n` as shown in the versions list |
| PUT | `/api/versions/mesh_yaml/config.yaml/default` | `{"version": n}` makes that version the default again: saved as a new store version, applied live on every pod |
| GET | `/api/infra/datastore` | Infrastructure → Datastores: reachable, latency, server, settings in force, which `.env` names set them — never the address or password |
| GET | `/api/infra/tenant-credentials` | 2.4.488 — the organisation's records a tenant may bring its own credentials for (name, provider, rows or `tenant_models`, `saved`). Never a value |
| DELETE | `/api/infra/tenants/{tenant}` | 2.4.489 — take a tenant off the tenants list (organisation only; refused while the tenant still holds vault records of its own) |
| GET | `/api/sessions`, `/api/sessions/{session_id}` | Each session carries `started_by` (2.4.491): `{how, via, who, requested_by, at}` — written once, display only (never routes or picks a tenant) |
| POST | `/api/sessions/{session_id}/agents/{agent_name}/rerun` | Re-run an agent in an existing session, with optional feedback / new input |
| GET | `/api/registry` | Canonical catalog of valid model ids, agent types, connectors, integrations, channels (with config-field schemas). Use this — don't guess model names |
| GET | `/api/system/status` | Agency run state → `{"state": "running"\|"stopped", "stopped_by", "stopped_at"}` (2.4.390) |
| POST | `/api/system/stop` | Pause the whole agency — body `{"by": str, "reason"?: str}`. Cancels in-flight runs; the server keeps running so Resume works. While stopped, new work (API runs, playground, reruns, Inbox, webhooks, callbacks) answers `503 {"state": "stopped", …}`; channel messages, schedules, listeners and follow-ups are dropped. The stop is kept in the business store (survives restart, holds on every worker) |
| POST | `/api/system/resume` | Resume — body `{"by": str}`. Retries nothing; a schedule that fell inside the stop is skipped, not caught up; agents switched off stay off |
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
| `llm` + `super_agent: true` | Multi-step task that needs planning + per-step verification + retry-once (tunable: `tries`, 2.4.491) + cost ceiling + cancellation. The orchestrator wraps the LLM agent transparently — same yields, same downstream routing | Yes | Yes | Complex research synthesis, multi-file code changes, multi-page document analysis. See [Super-Agent v3](#super-agent-v3) |
| `human` | Need human decisions, approvals, HITL review | No | Yes | Approval steps, chat interfaces |
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
| **retry-once** | On `soft_failure`, the orchestrator re-runs the step with failure context appended. Default one retry; `super_agent.tries` (2.4.491) sets attempts at once and rounds — see [Attempts per step](#attempts-per-step--tries-24491) | Same step entry, `attempt_count` incremented |
| **reflect** | On hard failure or budget exhaustion, the LLM reads plan + scratchpad and proposes a plan amendment | Plan Store — `mutation_history` |
| **finalize** | LLM synthesises the final output against the original goal, honours `yields`, respects the per-agent `max_tokens` ceiling | Agent's normal output channel |

### Operator primitives (YAML keys on the LLM agent)

```yaml
agents:
  research_synthesiser:
    name: "research_synthesiser"
    agent_type: "llm"
    model: "claude-sonnet-4-6"
    super_agent:                            # DICT form = the tuning path (2.4.123+); the ONLY way to tune it
      cost_ceiling: 100000                  # aggregate token budget per run (default 50000)
      wall_clock: 900                       # per-run wall-clock seconds (default 600)
      synth_max_tokens: 32768               # cap on the final synthesis call
      goal_check_view_chars: 12000          # chars the goal-check phase sees (default 12000)
      step_concurrency: 4                   # parallel plan steps when the DAG allows
      tries: {mode: auto, count: 3, rounds: 2}   # 2.4.491 — see "Attempts per step" below
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

### Attempts per step — `tries` (2.4.491)

`super_agent: {tries: {mode, count, rounds}}` sets how hard each plan step
tries to meet its check.

- `count` (1–10, default 1): attempts started **at once** in a round. The
  best-scored one is the round's answer.
- `rounds` (1–10, default 2): rounds at most. Each new round gets the
  critiques of the one before. The step stops at the first round that meets
  its check.
- `mode`: `fixed` (default) starts `count` attempts in every round. `auto`
  starts **one** attempt first, and `count` at once only after a failed check.
- Unset = `fixed`, 1, 2: one attempt and one retry with the checker's
  critique — the behaviour before 2.4.491. `tries: 3` is short for
  `{mode: fixed, count: 3}`. An unknown key, or a number outside 1–10, is
  refused: the mesh does not start and the error names the setting.
- When the rounds run out, the step keeps the **best answer of every round**,
  never a later, worse one. It is still reported as below the bar.
- A step with no expected outcome has nothing to check: one attempt.
- **Cost:** each attempt is its own model call plus its own check. `count` ×
  `rounds` multiplies the model calls per step (`count: 3, rounds: 3` can be 9
  attempts). `cost_ceiling` and `wall_clock` still bound the whole run. Prefer
  `mode: auto` — it pays for parallel attempts only on a step that failed.

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
- **Tune with the dict form, not flat keys.** As of 2.4.123 `super_agent:` takes a bool *or* a dict, and as of 2.4.131 the **dict is the only tuning path** — `super_agent: {cost_ceiling, wall_clock, step_max_tokens, synth_max_tokens, verify_view_chars, goal_check_view_chars, step_concurrency, tries}` (defaults: `cost_ceiling` 50000, `wall_clock` 600, `goal_check_view_chars` 12000). The old **flat** `super_agent_*` / `synth_max_tokens_*` keys were never wired, and the `LEAFMESH_SUPER_AGENT_*` env vars are dead — don't use either.

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
    name: "support_agent"
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

## The Board, Experience & Identity

Four things every mesh now has. Three are ON BY DEFAULT — design for them, do
not reinvent them with custom tools.

### The shared board (on by default)

Every mesh has one Kanban board. Each request opens a ticket automatically.
LLM agents get `view_board`, `add_task`, `pull_task`, `update_checklist`,
`update_task`, `finish_task` — **never write your own task/ticket tools**.

```yaml
kanban:                    # TOP-LEVEL (mesh), not per-agent — the one board
  job: customer_support    # letters, digits, _ . : - only (it becomes a storage key)
  title: Customer support
  goal: Every request answered and resolved
  enabled: true            # enabled: false is the only way off the board
```

- **The board is mesh-level only (2.4.397).** An agent has no board setting of
  its own: the top-level `kanban:` block names the one board and **every agent
  works it**. There is no per-agent opt-out and no second board.
- `kanban.enabled: false` at the **top level** removes the board from the whole
  mesh — the only way off.
- A per-agent `kanban:` block (`false`, `{job: x}`, …) still loads but is
  **warned as moved to the mesh, changes nothing, and is dropped on the next
  save**. Don't write one.
- Waiting on a person → `finish_task(waiting_on=...)`; a check-back is
  scheduled for you. Stuck tickets are freed automatically (not configurable).
- **Closing a ticket ticks its own steps (2.4.410).** `finish_task` takes
  `done=[...]` — the ids of the last steps you finished, **including the report
  you are about to give**; closing a card as done also ticks the step that is
  the card itself, so a finished ticket no longer shows the request as an open
  step. **Closing the request (the ticket that opened the session) with your
  own steps still open is refused once**, naming them, so you tick them (pass
  their ids in `done`) or explain them; a second close is then honoured. This
  refuse applies **only to the request** (origin=request, no parent) — pieces
  and subtasks with open steps close at once and hand their leftover steps back
  to their task. So: when you close the request, pass `done` with every step
  you actually closed — don't leave your own steps dangling. Steps you could
  not do: leave `unfinished_steps` at `return_to_board` (it takes one of
  `return_to_board`, `resume`, `reminder` — never a sentence) and say why in
  `note`; the close then goes through at once (2.4.432).
- **The ticket is signed in the same model call (2.4.442).** If the agent writes
  its answer while its own ticket is still open, the tool loop runs one more
  round offering only `finish_task`; the answer it wrote is what the step
  returns. A model that still does not sign is not asked again — the mesh
  closes the ticket from its answer. This round does not count against
  `max_tool_calls_per_message`. **Do not tell the agent in its prompt to call
  finish_task** — the mesh already does, at the right moment. If the agent
  answers while its own checklist steps are still open and it has tool calls
  left, it is first asked to do them — or to close and say why (2.4.448).

### Experience (on by default)

Each agent keeps private experience BY KIND OF WORK and gets `remember` /
`recall_experience`. Turn off per agent with `memory: {experience: false}`.

- **The kind of work is the playbook intent the agent used** (or an
  `intent:<name>` label on the ticket). No playbook intent, no label → nothing
  is filed automatically. So: give every LLM agent with more than one
  responsibility a `playbook:` (Rule 2) — it is also what makes it learn.
- **Human seats learn too.** A model reads what the person MEANT — any words,
  any language — and keeps the decision and reason; a "no" with a reason also
  teaches the agent that asked. The model is the seat's `reply_reader`
  (2.4.486; `intent_model` is moved into it at load), else the asking agent's
  `model`. Neither → nothing filed. `reply_reader.experience: true` hands the
  seat's own learned rules to the reader.
- **Never key behaviour on reply words.** Do not write conditions or code that
  look for "approved", "yes", "reject" in a person's text. Set a
  `reply_reader` on the human seat and route on the fields its `can_call`
  conditions name (`intent == 'refund'`). Channel replies (Slack, Teams, email) never carry a
  `human_decision` field — only the webhook API sets it.

### Identity — renaming keeps memory

Memory, experience and channel bindings follow an agent's stable id, not its
name. Changing `agent_type` keeps it. **Renaming** needs one line on the new
agent, or the migrate API:

```yaml
  refunds_specialist:
    name: refunds_specialist
    agent_type: llm
    model: claude-sonnet-4-6
    previous_name: refunds_desk     # safe to leave in; ignored after the move
```

`POST /api/yaml/agents/{agent_name}/migrate` with `{to_name?, to_type?, fields?}`
converts a human seat to AI and keeps what the person taught it.

### Versions — draft, try, default (2.4.454)

Everything that shapes an agent's run has versions (2.4.450): its config, the
mesh settings, playground changes, skills, API tools, Tools-page entries,
knowledge, connections and added models. Every run records the versions it
used. When an agent recalls what it learned, it is told what has changed
since, so it re-checks that part. Nothing to configure.

To change a live agent, do not just overwrite it:

1. **Save as draft.** `POST /api/versions/agent_config/{agent}/drafts` with
   `{"changes": {"prompt": "..."}}` (merged over the default) or
   `{"content": {...}}` (the whole agent), and an optional `why`. A draft is
   kept, not run. It is checked like a save, so a bad one is refused now.
2. **Try it once.** `POST /api/versions/try` with `{"agent": "...", "input":
   ..., "versions": [{"kind": "agent_config", "name": "...", "version": N}]}`.
   Or mark it first with `PUT /api/versions/agent_config/{agent}/staging
   {"version": N}` and leave out `versions`. It is one run through the mesh's
   own run path; every other run keeps the default. It stops at the agent's
   answer: nothing is handed on, nothing goes on the board, nothing is learned.
3. **Compare (2.4.458).** In Studio: Versions → Try, toggle "Compare with
   default v<N>". In the API: add `"compare": true` to run the same task on the
   default too, one after the other. `"inputs": [...]` (up to 10) runs several
   tasks. Use this to change an agent's model safely.
4. **Make it the default.** `PUT /api/versions/agent_config/{agent}/default
   {"version": N}`. Going back is the same call with the old number.

Inside an agent's try run you can swap its config, a playground version, a
skill's text, and an API entry's switches, no-sign-in marks and base URL.
Other items are tried on their own (2.4.458): `POST /api/versions/try
{"kind", "name", "version", "compare"?}` calls an API once, searches
knowledge, sends a model one tiny message, or reads a Tools-page entry's
tools. Mesh settings cannot be tried, and an API version with another spec is
tried only by making it the default. Knowledge, connections and added models
cannot be switched back to an older version. Never write a secret into a
draft: a version keeps no secrets, and a hidden value is filled from what runs
now when the version is applied.

### Mother tongue & nationality (opt-in)

```yaml
    mother_tongue: Hindi      # LLM agents only; ≤40 chars
    nationality: Indian
```

The agent reasons in that language and follows those conventions (dates, money,
names, formality) but ALWAYS writes in the language of the conversation — the
person's, or, when it works only from other agents' output, the language that
work is in (2.4.486). `manager:` takes
the same two fields for the Manager and Summarizer.

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
    model: null              # falls back to the SUMMARIZER's model
                             # (use_model = model or summarizer.config.model);
                             # if neither has one the design is skipped
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
| `llm` | `model`, `model_connection` (2.4.486), `prompt`, `temperature`, `max_tokens`, `max_completion_tokens`, `reasoning`, `thinking`, `reasoning_budget` (`thinking_budget` is a deprecated alias, read as `reasoning_budget` with a warning), `fallback_models`, `enable_prompt_caching`, `response_format` (accepted extra), `optimization_strategy`, `context_parts`, `tools`, `api_tools`, `tool_choice`, `max_tool_calls_per_message`, `tool_call_timeout`, `allow_parallel_tool_calls`, `tool_categories`, `skills`, `super_agent`, `effort`, `receive_conversation_history`, `history_limit`, `llm_hard_timeout_s`, `device`, `response_overrides` — (tune `super_agent` via its **dict** form, e.g. `super_agent: {cost_ceiling, wall_clock, …}`, not flat `super_agent_*` keys) |
| `human` | `human_interface`, `human_timeout_seconds`, `human_context_template`, `human_prompt_template`, `fallback_on_timeout`, `fallback_response`, `operator_ids`, `represents`, `webhook_config`, `channels`, `reply_reader` (2.4.486; replaces `intent_model` / `intent_prompt`, moved in at load). (`require_human_confirmation`, `confirmation_seat` and `human_escalation_triggers` were removed in 2.4.382: one set ON refuses the config at load, one set off is dropped. Approval is routing — see [Approval is routing](#approval-is-routing).) |
| `external` | `external_agent` (2.4.486 — fills in the next two from the External agents page) **or** `framework` (**required** without it), `connector_config`, `external_policy` |
| `programmatic` | `integration`; `connector_config` allowed only when `integration` is set (2.4.486: `{account: <Tools-page entry>}` picks its sign-in) |

**Universal fields** (any type): `name`, `description`, `agent_type`, `communication_type`, `scaling` (2.4.484 — replaces `parallel`, `max_concurrent`, `instances`, `instances_handoff`, which are refused at load; no `copies` on a human seat, 2.4.485), `notify` (2.4.485), `wake_up`, `wake_up_input`, `timezone`, `yields`, `inputs`, `can_call`, `narration`, `wait_for`, `wait_for_timeout`, `auto_store_response`, `auto_store_yields`, `enforce_yields`, `enforce_yields_retry`, `memory`, `knowledge`, `skills`, `listen_events`, `tenant_credentials_only` (2.4.488 — acts on the model record and the connector's record).

**Do not set `is_human_powered` manually** — it's auto-derived from `agent_type` and is silently overwritten by the validator.

## STRICT — `human_interface` rules

A human agent picks **exactly one** interface. The fields below depend on which one.

| `human_interface` | Path | Required fields | Forbidden together |
|---|---|---|---|
| `default` | HITL Inbox (LeafCraft Studio) — hosted **and self-hosted** | none — works out of the box | do NOT set `webhook_config` or `channels` — they're ignored at runtime |
| `webhook` | Outbound HTTP / channel adapters | `webhook_config: {connection: <name>}` (an "Add custom" record, service type 'Outbound webhook') OR `channels` (one is enough) | — |
| `api` / `custom` | Python callback registered via `sdk.agent_registry.register_human_agent(name, human_interface_handler=fn)` (there is **no** `sdk.register_human_handler()`). `api` is the field's default; **with no handler registered the seat is answered in the Inbox** (2.4.486 — start logs it; before, it failed on its first question) | none | do NOT set `webhook_config` or `channels` |

`channels` only fires when `human_interface: webhook`. Setting `channels` with `default` or `api` is silently ignored at runtime — don't do it.

## Human-in-the-Loop (HITL)

The human agent is a full mesh node -- not just an approval step. It participates in the agent chain like any other agent, with `can_call` conditions that route based on context.

### THE HOUSE PATTERN — start here, not with Option A

Option A appears first below because it is the most configurable. **It is not
the one you want.** A real build copied Option A's shape — an outbound webhook
to a local stub — and produced a pod whose human gates could not be answered
by any person, because nothing but a hand-crafted POST could answer them.

Every working mesh in this fleet does the same simple thing instead:

```yaml
agents:
  engagement_lead:
    name: "engagement_lead"
    agent_type: "human"
    human_interface: "default"        # the Studio Inbox. A real queue a real person clicks.
    is_human_powered: true
    operator_ids: ["lead@yourcompany.com"]   # WHO. Unset = shared inbox = nobody owns it.
    human_timeout_seconds: 28800      # 8 hours. A PERSON is answering this.
```

Three things that block are worth stating plainly, because each cost a build a day:

- **`human_timeout_seconds: 300` is five minutes.** Every example below used to
  say 300, and a real pod copied it: the first genuine gate auto-closed before
  the person had read it. Humans work in **hours and days** — 7200 to 28800 is
  the house range. 300 is for a machine.
- **`operator_ids` is WHO, and a placeholder routes to nobody.** Left unset the
  ask goes to a shared inbox that nobody owns. A dummy address is worse: the
  task is invisible and looks delivered.
- **Any `channels:` block makes the seat a CONNECTOR**, whatever
  `human_interface` says — the boot log will tell you the seat "lives on slack
  — no Inbox door". So a seat is *either* Inbox *or* a channel. Choose once.

Slack belongs in a mesh — as the **Manager's escalation target**, and as
Studio-side delivery. It is not how you configure a human seat.

### HITL YAML Config — pick **one** of these three blocks

> Don't mix interfaces. The validator rejects fields that don't apply to the chosen `human_interface`.

#### Option A — `human_interface: webhook` (outbound webhook OR channel adapter)

```yaml
agents:
  client:
    name: "client"
    agent_type: "human"
    human_interface: "webhook"            # outbound HTTP / channels
    communication_type: "dual"            # respond + wait for inbound response
    human_timeout_seconds: 28800      # 8h — a PERSON answers this. 300 = five minutes.
    # operator_ids: ["alice@co.com"]      # restrict who sees this in inbox (empty = all)

    webhook_config:
      connection: "client-hook"   # "Add custom" record, service type 'Outbound webhook': base URL = address,
                                  # header rows = headers, secret row inbound_token (2.4.481: no inline url/headers/token)
      outbound_timeout: 30
      max_retries: 1
      retry_delay: 2
      # inbound_endpoint is auto-derived from entry_points

    # OR (instead of webhook_config) use a native channel adapter:
    # channels:
    #   slack:
    #     connection: "slack-workspace"      # credentials come from the vault
    #     listen_channels: ["${SLACK_CHANNEL_ID}"]   # ids are not secrets — env is fine
    #     post_channel: "${SLACK_POST_CHANNEL}"

    can_call:
      - agent: "greeter_agent"
        condition: "not calling_agent_response.from_agent"   # works ONLY because human agents ALWAYS emit from_agent (maybe ""). Never `not` a field that can be absent — see gotcha #14
      - agent: "processor_agent"
        condition: "calling_agent_response.from_agent == 'greeter_agent'"

    yields: {request_data: "object"}
    inputs: {user_message: "string"}

  # An entry_point target must be a DEFINED agent — the loader rejects a
  # target it cannot find, so the agent the first entry point names has to
  # exist in the same config.
  greeter_agent:
    name: "greeter_agent"
    agent_type: "llm"
    model: "gpt-4o"
    prompt: "Greet the user and hand off to the human seat when they ask for a person."
    can_call:
      - agent: "client"
        condition: "calling_agent_response.wants_human == true"
    yields:
      wants_human: "boolean"

entry_points:
  - name: "greet_user"
    target: "greeter_agent"
  - name: "human_contact"
    target: "client"
```

#### Option B — `human_interface: default` (HITL Inbox (LeafCraft Studio), hosted or self-hosted)

> Inbox shape: `GET /api/sessions/hitl` returns **one record per
> session** with every pending ask nested in `requests[]`
> (oldest-first — `requests[0]` is the one to act on first;
> top-level `request_id` mirrors it, `request_count` is the total).

```yaml
agents:
  client:
    name: "client"
    agent_type: "human"
    human_interface: "default"            # writes to Redis inbox + stream — that's it
    communication_type: "dual"
    human_timeout_seconds: 28800      # 8h — a PERSON answers this. 300 = five minutes.
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
    name: "client"
    agent_type: "human"
    human_interface: "api"                # call into Python — no HTTP, no inbox
    communication_type: "dual"
    human_timeout_seconds: 28800      # 8h — a PERSON answers this. 300 = five minutes.
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

```text
# Built-in fields on a human seat's response — available to can_call
# conditions WITHOUT being declared in `yields:`. (The seat's declared
# yields ride alongside them by name.)
calling_agent_response.from_agent        # Who called the human ("greeter_agent" or "")
calling_agent_response.human_message     # What the human said
calling_agent_response.human_decision    # Human's decision field
calling_agent_response.human_data        # Any data from the human
calling_agent_response.human_initiated   # TRUE only when the PERSON opened the turn.
                                         # An answer to an agent's question carries
                                         # from_agent and is false. (It was hard-coded
                                         # true on every reply until this was fixed.)
calling_agent_response.operator_id       # which operator answered
calling_agent_response.source_agent      # the seat's own name
calling_agent_response.source_agent      # The human agent name ("client")
```

### The reply reader — what a person MEANT (2.4.486)

A person writes a sentence; `can_call` conditions read fields. The seat's
**`reply_reader`** fills those fields (it replaces `intent_model` /
`intent_prompt`, which are moved into it at load):

```yaml
  client:
    name: "client"
    agent_type: "human"
    human_interface: "default"
    reply_reader:
      model: "gpt-4o-mini"           # required — no default anywhere
      prompt: "'go ahead' means approved; a question back is not a decision."
      experience: true               # the seat's own learned rules, confirmed first
    can_call:
      - agent: "refunds_agent"
        condition: "calling_agent_response.intent == 'refund'"
      - agent: "advisor_agent"
        condition: "calling_agent_response.intent == 'question'"
```

- It takes only `model`, `prompt`, `memory`, `knowledge`, `skills`,
  `experience`, `model_connection`, `temperature`, `max_tokens` — no tools.
- One lean model call per reading, a step of the seat's own run.
- **It never picks a route** — `can_call` (or the Manager) does. A reply no
  route takes goes nowhere; **a person's answer that no route takes ends the
  conversation and closes the ticket**. Give the seat a route for everything a
  person may mean.
- In a shared thread a reply answers the question it answers: the same asker
  asking again replaces its earlier question; with several askers waiting the
  reader picks which one, else the newest.

Field table: [agent-config-fields.md → reply_reader](agent-config-fields.md#reply_reader--reading-a-persons-reply-24486).

### When nobody answers (2.4.486)

**A seat waits its time and stops.** When `human_timeout_seconds` is up its
request closes and `HUMAN_INPUT_TIMEOUT` is published — nothing more: no
"timed out and escalated" note to the person, no escalation, no Manager
check-back re-running the asking agent. A late reply still lands
(`answered_late`). `manager.timeout_rules`,
`manager.escalation.auto_escalate.timeout_threshold` and
`manager.human_response_rules.timeout` are removed (dropped with a warning).
`fallback_on_timeout: true` + `fallback_response` still answer for the seat and
carry the chain on.

<!-- TODO(bb): 2.4.486 escalation pattern for unanswered approvals -->

### Channel Adapters (Slack, Telegram, etc.)

`channels` only fires when `human_interface: webhook`. Other interfaces silently ignore it. To make a channel actually deliver messages, the human agent must declare the webhook interface:

```yaml
agents:
  client:
    name: "client"
    agent_type: "human"
    human_interface: "webhook"        # REQUIRED for channels to fire
    communication_type: "dual"
    channels:
      slack:
        connection: "slack-workspace"     # holds bot_token + signing_secret + app_token
        listen_channels: ["${SLACK_LISTEN_CHANNEL}"]   # channel ids are not secrets
        post_channel: "${SLACK_POST_CHANNEL}"
      telegram:
        connection: "telegram-bot"
      email:
        connection: "email-support"       # holds smtp_host/smtp_port/smtp_username/smtp_password + signing_secret
        # Outbound — SMTP (host, port, username live on the connection: inline refused since 2.4.481)
        provider: "mailgun"               # mailgun | sendgrid | postmark
        from_address: "support@example.com"
        reply_to_address: "support@example.com"
        threading: "references_first"     # or reply_to_token
        auto_reply_drop: true             # ignore vacation autoresponders
        # Inbound — the PROVIDER'S WEBHOOK, not IMAP. The adapter registers a
        # route and verifies the provider's signature; there is no IMAP client.
        # Needs leafmesh>=2.4.265: the signing_secret comes from the SAME
        # `connection:` above. (On <=2.4.264 this was impossible — the
        # validator demanded signing_secret in this block and the 2.4.180 gate
        # refused it here, with no third option.)
        inbound_domain: "mg.example.com"
        inbound_local_part_filter: ["support"]   # optional; accept only these
```

The HITL flow works identically across all channels -- the SDK handles transport, the agent handles routing. With multiple channels configured, the SDK tries each in order; if all fail, it falls back to the `webhook_config.connection` record's address (when set).

**Email channel specifics.** Email is **asymmetric** — outbound goes over SMTP, inbound arrives as the PROVIDER'S WEBHOOK (Mailgun, SendGrid or Postmark), whose signature the adapter verifies. The email CHANNEL has no IMAP client, so a mesh with no public URL cannot receive mail through it — for that case use the separate **IMAP broker** (`brokers: {name: {type: "imap", connection: <imap connection>}}` — host, port, username, password live on the connection — plus `listen_events: [{broker: name, folder, poll_interval_s}]`), which polls a mailbox and feeds the agent instead. Threading uses `In-Reply-To` / `References`, and for clients that strip those the adapter sets a plus-addressed `Reply-To` token so a reply still finds its conversation. Reply and signature stripping uses `talon` when it is installed, with a regex fallback when it is not. **Email is direct but NOT continuous:** a reply continues its conversation, a brand-new mail starts a new one — unlike a DM, where every message is one running chat.

### WHERE EACH SECRET LIVES — read this before writing a `.env`

Do not invent a `.env` full of credentials. Three kinds of secret, three
homes, and only one of them is `.env`.

| What | Where it goes | If you put it in config |
|---|---|---|
| **Channel credentials** — Slack `bot_token`, `signing_secret`, `app_token`, Teams, Discord, Cliq, WhatsApp, Email | **Vault only.** A connection made on the Infrastructure page, named by `connection:` | **Mesh REFUSES TO BOOT** (2.4.180) |
| **Connector credentials** — MCP, Zapier, n8n, Composio, custom | **Vault only.** `connection:` inside `connector_config` | Same refusal |
| **Addresses, client ids, header rows** — webhook / escalation URLs and headers, broker hosts/URLs, MCP `url`/`token`, `mesh.*` provider endpoints/regions (2.4.481), `connector_config` `url`/`endpoint`/`webhook_url`/`headers`/keys (2.4.482) | **Vault only.** The block picks the record with `connection:` (`vault_connection:` on zapier/composio/n8n rows) | **Config fails to load**, naming the field — [Vault-only values](nuances-and-gotchas.md#vault-only-values-24481) |
| **LLM provider keys** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`, `MOONSHOT_API_KEY`, … | **`.env`, or a model connection on the Infrastructure page.** See below | n/a — these are never config fields |
| **Deployment identity** — `LEAFMESH_LICENSE_KEY`, `LEAFMESH_ENV_TOKEN`, `LEAFMESH_API_PORT`, `LEAFMESH_EVOLUTION_API_PORT`, the agency's name (`LEAFMESH_AGENCY_NAME`), the datastore (`LEAFMESH_STORE`, `REDIS_*`, `POSTGRES_*` — never in the YAML, 2.4.482), `LEAFMESH_VAULT_KEY`, `LEAFMESH_WEBHOOK_SECRET`, `INTERNAL_API_KEY` | **`.env` only** | Exempt — this is the deployment's own identity, not a provider credential |

**Three `.env` values the mesh never makes for you (2.4.507).** `create-leafmesh`
writes the first two into every new project's `.env` (random, never printed, never
replaced once set); an older project adds the lines by hand:
- `LEAFMESH_VAULT_KEY` (32 random bytes, URL-safe base64): the mesh writes no key file
  and derives no key; with none it stops at start with "no vault key". A new key means
  a new, empty vault — after a vault switch the old vault is not read, and each
  credential is entered again.
- `LEAFMESH_WEBHOOK_SECRET` (same format): no longer derived from the licence key.
  Without it the mesh starts with a warning, and every signed webhook
  (`/webhook/…`, `/callback/…`, the knowledge refresh) answers 503 until it is set.
- `LEAFMESH_ENV_TOKEN`: required at start (`LeafMeshLicenseError` when missing).

**LLM keys: `.env` or the Infrastructure page.** Every provider reads its
key from the process environment. A model connection saved on the
Infrastructure page is bridged into that environment (only where the
variable is not already set, so `.env` always wins). The vault now comes up
**before** the providers register, so a vault-only key is seen at boot, and
a key saved or rotated later reaches the running provider without a restart
(xAI and Azure Foundry included since 2.4.436). The Infrastructure page's
**Test** checks every model key (2.4.436). Before 2.4.264 the vault started
too late and a vault-only `claude-*` agent fell through to the local
provider with `ConnectError` — if you see that on an old SDK, put the key
in `.env`.

So a correct `.env` for a new pod is short: the licence key, the env token,
the ports, the store (`LEAFMESH_STORE` + `REDIS_*` / `POSTGRES_*`), the
agency's name (`LEAFMESH_AGENCY_NAME`, needed by `LeafMesh.from_store()`), and
your model provider key(s). Nothing else belongs there —
every other credential goes in the vault.

> ⚠️ **`.env` gotcha that costs an afternoon.** `python-dotenv` reads
> `KEY=            # explanation` as the **comment being the value**. The mesh
> then authenticates with the literal string `# explanation` and the provider
> returns a confusing auth error. A trailing comment is only stripped when a
> real value precedes it (`KEY=value  # note` is fine). Leave the line bare —
> `ANTHROPIC_API_KEY=` — and put the explanation on its own line above.

### Credentials — `connection:`, never a literal

**The mesh REFUSES TO BOOT if it finds a provider credential written literally
in config** (2.4.180). Name a connection made on the Infrastructure page instead:

```yaml
    channels:
      slack:
        connection: "slack-workspace"   # the vault holds the secret
        post_channel: "C0123456789"
```

**`${ENV_VAR}` does NOT rescue a token field — do not reach for it.** Env
substitution happens when the config loads, and the gate reads the config
*after* substitution, so it sees whatever the variable held. The two outcomes
are both useless:

```yaml
bot_token: "${SLACK_BOT_TOKEN}"   # var unset  → becomes ""  → boots, seat has no credential
                                  # var set    → becomes the literal token → REFUSES TO BOOT
```

There is no third case. For channel and connector credentials, `connection:`
is the only path that works. (`connection:` itself may be an env reference —
`connection: "${SLACK_CONNECTION:slack-workspace}"` is fine, because a
connection *name* is not a secret and the gate never inspects it.)

One connection carries the provider's WHOLE credential set (Slack:
`bot_token` + `signing_secret` + `app_token`), so you reference it once and
every field it holds comes with it.

Connections made while the mesh is running are adopted live — for Slack that
includes opening Socket Mode from the app token, so inbound starts working
without a restart.

### Studio's Infrastructure page — where each record is made

Use these names exactly (2.4.483/2.4.484 messages use them too). There is **no
"Infrastructure → Connections" page** — older SDK messages said that; Studio
never had one. The sidebar entry is **Infrastructure**; its sections are:
Messaging · Workspace · Models · Cloud access · Knowledge · Integrations ·
External agents · Brokers & queues · Notifiers · Rooms · Agent identities ·
Datastores.

| Record for | Where |
|---|---|
| Slack, Microsoft Teams, Discord, WhatsApp, Telegram, Zoho Cliq | Infrastructure → Messaging → `<provider>` |
| Email | Infrastructure → Workspace → Email |
| A model provider's key | Infrastructure → Models → `<provider>`; a local server: Models → Local / self-hosted; cloud model services (Bedrock, Vertex, Foundry) are under Models too |
| The mesh's own cloud sign-in | Infrastructure → Cloud access |
| Knowledge stores | Infrastructure → Knowledge → MongoDB \| pgvector \| Pinecone |
| Zapier, n8n, Composio, MCP | Infrastructure → Integrations → `<platform>` (MCP moved here in 2.4.484; on 2.4.482 it is under External agents) |
| An external agent | Infrastructure → External agents → `<framework>` (CrewAI, LangGraph, A2A Protocol, …) |
| Brokers | Infrastructure → Brokers & queues → Redis Streams \| MQTT \| Apache Kafka \| AWS SQS \| IMAP Mailbox |
| A human seat's / escalation webhook | an **"Add custom"** record on the Infrastructure page, service type **'Outbound webhook'**: base URL = the address, header rows, secret row `inbound_token`. Since 2.4.486 the record keeps sign-in only — a query or body row is refused on save, and one saved earlier is no longer sent (start names it) |
| Where the store is | Not a record — `.env`. Infrastructure → Datastores only shows it |

**"Add custom"** is at the top of every section except Cloud access. Its
service types: 'Outbound webhook', 'Tools', 'External agent', 'Model',
'API tools', 'Knowledge store', 'Your own code'. Optionally give it a
**Service** name (2.4.509, free text such as "Github"), so several records of one
service sit together; one service holds one type.

The **Tools page** still exists (Tools → APIs | Webhooks | MCP servers |
Zapier | Composio | n8n): it sets up the server or tool and **picks** its
record — the record itself is made on the Infrastructure page. **What is
sent** lives there too (2.4.486): an API's fixed query values, a webhook's
method / path / body fields / fixed query. An agent's tool-platform list is
the Tools page's entries (`mcp: [{server: …}]`, `zapier: [{account: …}]`, …),
never raw vault records. Two more pages set up what agents pick: **Models**
(an added model's server, record and fixed `query`) and **External agents**
(2.4.486 — framework, record and settings; agents pick it with
`external_agent:`).

**The vault keeps sign-in only (2.4.486).** A record holds the address, keys
and header rows. A plain query or body row is refused on save — except an
**API tools** record, which keeps its sign-in body rows (OAuth client id /
secret, username / password) and a **secret** query key. Rows saved earlier
are no longer sent; start names each one. Details:
[nuances → The vault keeps sign-in only](nuances-and-gotchas.md#the-vault-keeps-sign-in-only-24486).
Every picker lists each sign-in as "Provider · record" (`GET
/api/infra/choices`).

### Vault references, your own code, and file credentials

- **One vault per mesh, chosen by the customer who runs it**: the built-in one,
  or one they connect (HashiCorp, AWS, Azure, GCP, …) on the Infrastructure page. Their
  own tenants never connect a vault; a tenant's credentials land in the chosen
  vault in a namespace of their own, and the tenant's credential is looked up
  first, then the customer's of the same name.
- **A tenant can bring its own credentials (2.4.488).** `GET
  /api/infra/tenant-credentials` (sent with the tenant's `X-Tenant-ID`) lists
  the organisation's records a tenant may fill — pasted credentials, not
  OAuth: the same name, the same provider, and for a custom record the same
  rows. On a listed provider's record the organisation offers models with
  `tenant_models`; the tenant picks one with `model` on its own record, and its
  runs use that key and that model. An agent with `tenant_credentials_only:
  true` never falls back: a tenant with no record of its own is stopped with
  "this tenant has not connected <record>". Runs with no tenant are unchanged.
  The Manager always uses the organisation's key. The tenant id is taken out
  of what a model sees and out of the input sent to an outside agent (the
  outbound call's `X-Tenant-ID` header still carries it). Cost by tenant comes
  from telemetry — see [nuances #10](nuances-and-gotchas.md#10-multi-tenancy-is-pass-through).
- **A free-form config string can point at the vault** (`request_form` values,
  a stdio MCP server's `env`): `${vault:<connection>}` is its primary secret,
  `${vault:<connection>.<field>}` one named field. Resolved where it is used,
  so rotation applies on the next request. **It fails closed**: a reference
  that cannot be resolved raises, never becomes `""`. It is **not** a way to
  fill a vault field of a block that picks a record — since 2.4.481
  `webhook_config.inbound_auth_token: "${vault:…}"` or an escalation
  `headers: {Authorization: "Bearer ${vault:…}"}` fails to load; the token is
  the record's `inbound_token` secret row, the header a header row.

  ```yaml
  request_form:
    crm_token: "${vault:crm.api_key}"   # one named field, resolved per call
  ```
- **A connection the config names but the vault lacks does not stop the mesh.**
  It starts and logs "connection 'X' does not exist in this mesh's vault…";
  each agent, human seat or broker consumer that needs the connection is
  switched off, loudly, and its runs fail at once with the reason. Add the
  connection and it switches back on with no restart.
- **A connector with no address is not set up (2.4.490).** An external or
  programmatic agent whose record has no address (n8n's `webhook_url`, A2A's
  `url`, CrewAI's `endpoint`, a custom API's `base_url`, …) is switched off at
  start with "not set up". It is never called and never counts toward
  quarantine. Put the address in the vault record; the agent switches back on
  with no restart. `framework: custom` is exempt.
- **Your own code** (a tool, a programmatic agent, a custom connector) reads a
  credential at run time — never from an env var you invented:

  ```python
  from leafmesh import global_tool, secret, secret_file

  @global_tool(name="find_order", description="Look up an order")
  async def find_order(order_id: str) -> dict:
      key = await secret("crm-api")              # the primary credential
      base = await secret("crm-api.base_url")    # one named field
      ...
  ```

  Both are `async`. A connection can name the `agents` allowed to read it; any
  other agent gets `SecretNotAllowed`. A name with nothing behind it raises
  `UnresolvedVaultRef` — never an empty string.

  For a service the mesh has no connector for, make an "Add custom" record
  with service type 'Your own code' and read all its rows at once (2.4.458):
  `rows = await connection_rows("billing-api")` (from `leafmesh`) returns
  `{"headers", "query", "body", "base_url"}`, ready to send. Same `agents`
  rule and the same errors as `secret()`; secret rows are never logged.
- **File credentials** (a service-account JSON, a client key, a `.p12`, a
  kubeconfig) — for a library that only takes a path, `await
  secret_file("gcp-reports.service_account_json")` returns the path of a
  private, owner-only file holding it. It is reused while the credential is
  unchanged, replaced on rotation, and removed when the mesh stops.

### Per-seat channel fields worth knowing

| field | what it does |
|---|---|
| `operators` | logical operator id → that channel's user handle, so a step can address a named person |
| `operators_only` | refuse anyone not in `operators`. **Off by default** — a customer-facing seat must accept strangers. Turn it on for a staff-only seat. |
| `socket_mode` | Slack: receive events over an outbound WebSocket — **no public URL needed**. Turns itself on when the connection holds an `xapp-` token. |
| `listen_channels` | channel ids to accept inbound from; empty means all |

### THE ROOM RULES — get these wrong and the mesh is rude or deaf

Two questions on every inbound: **is this for us**, then **which conversation**.

**Is it addressed to the mesh?**

```
DIRECT (a DM, or mail to the mesh's address)   → always ours, no mention needed
SHARED ROOM
  ├── @mentions the mesh / names an agent / slash command  → ours
  ├── posted inside a thread the mesh opened               → ours
  └── anything else                                        → IGNORED
```

A bare message in a room is people talking to each other. Having spoken to the
mesh before does NOT make later messages its business — that is how a "yes, go
ahead" meant for a colleague gets eaten as an answer to a pending request.
The mesh also never answers its own messages, on any channel.

**Which conversation does it join?**

```
Addressed the mesh (@mention / named agent / slash command)
    → a NEW conversation, EVEN IF a question is open.
      Nobody @-mentions a bot to answer its question; you just type.

Reply inside a thread
    ├── something pending → answers THAT message, same session
    └── nothing pending   → runs the flow again, SAME session (the Inbox rule)

New email (no In-Reply-To, no reply token)
    → a new conversation. A reply stays in its own.
```

Threads exist on **slack, teams, discord, email**. **telegram, cliq, whatsapp**
have none — there each person has one continuous conversation, and a question
asked in a Cliq room can only be answered by naming the mesh or in a DM.
A reply in a Slack thread runs in **its session's tenant** (2.4.491): the
tenant belongs to the session, and the person replying never sends it.

**When you design a seat:** if it takes work from strangers, leave
`operators_only` off and expect mentions. If it is an approval seat for staff,
turn it on. If the mesh has no public URL, Slack needs `socket_mode` (an
`xapp-` token) or it will never hear anything.

### Inbox seats vs connector seats

A seat is **either** an Inbox seat (the hosted console) **or** a connector seat
(slack/teams/…), never both. Declaring `channels:` makes it a connector seat
and it gets no Inbox door. Ownership is the login's platform role
(`operator_role: owner|admin`), and `operator_ids` are the assigned operators;
a stranger sees no tab at all.

## Approval is routing

There is **no approval switch** on an agent, a seat, a tool or an external
agent (2.4.382). `require_human_confirmation`, `confirmation_seat`,
`human_escalation_triggers`, `external_policy.skills` and `unknown_skill_risk`
are removed: one that was ON **refuses the config at load**; one that was off
is dropped. A tool's `requires_confirmation=True` does nothing.

A person who must sign off is a **human agent the work is routed to** — a node
like any other:

```yaml
agents:
  expense_checker:
    name: "expense_checker"
    agent_type: "llm"
    model: "gpt-4o-mini"
    prompt: "Check the claim. Return needs_approval true when the amount is over 500."
    temperature: 0.1
    communication_type: "chain"
    yields: {needs_approval: boolean, amount: number}
    can_call:
      - agent: "finance_lead"
        condition: "calling_agent_response.needs_approval == true"
      - agent: "payer"
        condition: "calling_agent_response.needs_approval == false"

  finance_lead:                        # the person who approves IS a node
    name: "finance_lead"
    agent_type: "human"
    human_interface: "default"
    communication_type: "dual"
    operator_ids: ["finance-lead@yourcompany.com"]
    represents: "organisation"         # staff: their decisions become standing rules
    human_timeout_seconds: 28800
    can_call:
      - agent: "payer"
        condition: "calling_agent_response.human_decision == 'approved'"

  payer:
    name: "payer"
    agent_type: "programmatic"
    communication_type: "chain"
```

`represents: customer` is for a seat the public answers: their reply decides
the request in hand and is never kept as a rule.

**The receiver is told who handed it the work (2.4.487).** Every hand-off
carries a card per sender: its name, its `description` (first 300
characters), and for a person's seat whom it `represents` (the customer, or a
colleague from the organisation's staff). Our agents read it in their prompt
("WHO THIS CAME FROM"); an outside agent gets it in the call ("Handed to you
by …"). `send_fields` still rules what else goes out. So write a real
`description` on every agent and seat — it is how the next agent knows whom
it is answering.

## YAML Agent Config (All Fields)

```yaml
agents:
  # ── LLM Agent ──
  my_agent:
    name: my_agent
    agent_type: "llm"              # llm | human | programmatic | external
    description: "What this agent does"
    model: "gpt-4o-mini"           # REQUIRED — no default since 2.4.135.
                                   # The SDK never picks one for you: boot names
                                   # every LLM agent missing one, and the call
                                   # raises ModelNotConfiguredError.
                                   # Non-LLM agents need no model.
    # model_connection: "openai-dev" # 2.4.486 — which model sign-in, when the vault has several
    prompt: "You are a helpful..." # System prompt
    temperature: 0.1               # the default
    max_tokens: 800                # the default
    max_completion_tokens: 1000    # For o-series / gpt-5.x / gpt-6 reasoning models
    communication_type: "dual"     # dual | chain  ('execute' is a deprecated alias read as chain)

    # Mesh routing
    can_call:
      - agent: "next_agent"
        condition: "calling_agent_response.status == 'ready'"
    wait_for: "agent_a AND (agent_b OR agent_c)"
    wait_for_timeout: 60

    # Tools
    tools: ["word_count", "timestamp"]
    tool_categories: ["data", "utility"]
    # tool_choice: unset by default — the SDK then pins its configured memory /
    # knowledge / reasoning tools on the first turn so they fire. An explicit
    # "auto" switches that pin off. Leave it unset unless you must force
    # "none" or one named tool.
    max_tool_calls_per_message: 5  # reaching it is a warning, not a failure (finish_reason tool_cap)
    allow_parallel_tool_calls: true
    # tool_call_timeout: unset by default — each tool's own budget applies
    # (MCP / Zapier / Composio / n8n declare 60s). Any value you set wins on every tool.

    # Features (v2.2.24 SWAPPED the keys — see "reasoning vs thinking")
    thinking: true                 # SDK chain-of-thought scaffolding tools (works with ANY model; needs >= 1500 max_tokens)
    reasoning: true                # Provider-NATIVE extended thinking (reasoning-capable models ONLY — o-series/gpt-5.x/gpt-6, claude-3.7+, gemini-2.5+, grok-4.5+; warns at boot otherwise)
    reasoning_budget: 8192         # Max native reasoning tokens (thinking_budget is a deprecated alias)
    enable_prompt_caching: true    # Provider-native prompt caching (~90% savings on Anthropic)
    scaling:                       # 2.4.484 — replaces parallel / max_concurrent / instances
      runs: {max: 3}               # at most 3 of this agent's jobs at once across ALL pods (unset = no cap)
    notify:                        # 2.4.485 — post the output when it finishes (mesh-sent, never fails the run)
      webhook: "erp_inbox"         # a webhook on Tools → Webhooks — never an address
      when: "done"                 # done (default) | failed | both
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
    name: "zapier_agent"
    agent_type: "programmatic"
    integration: "zapier"          # zapier | composio | n8n | mcp
    connector_config:
      connection: "google_sheets"   # Zapier app slug — NOT the vault record
      action: "create_spreadsheet_row"
      vault_connection: "zapier-main"   # vault record holding the Zapier MCP key; never a key inline
      # after_handoff: "wait"      # answer POSTed back later (2.4.508; was mode: "callback")
      # callback_timeout: 120
    scaling:
      runs: {max: 3}               # protect the downstream system: 3 jobs at once, the rest wait their turn
    yields: {status: string}
    inputs: {data: object}

  # ── External Agent (connector-only, no Python needed) ──
  crew_agent:
    name: "crew_agent"
    agent_type: "external"
    external_agent: "research_crew"  # 2.4.486 — an entry on the External agents page (framework + record + settings)
    # Old shape, still accepted:
    # framework: "crewai"          # crewai | langgraph | autogen | a2a | custom_api | mcp | n8n | zapier | composio | custom
    # connector_config:
    #   connection: "crewai"       # Infrastructure → External agents → CrewAI: endpoint + api_key (vault-only, 2.4.482)
    yields: {result: object}
    inputs: {task: string}

  # ── Human Agent — webhook interface (with optional channels) ──
  reviewer:
    name: "reviewer"
    agent_type: "human"
    human_interface: "webhook"        # default | webhook | api | custom
    communication_type: "dual"
    human_timeout_seconds: 28800      # 8h — a PERSON answers this. 300 = five minutes.
    # operator_ids: ["alice@co.com"]  # restrict inbox (empty = all)
    # fallback_on_timeout: true
    # fallback_response: {decision: "timeout_default", message: "Request timed out"}
    # represents: organisation          # organisation (staff: decisions become standing rules) | customer
    # reply_reader: {model: "gpt-4o-mini", prompt: "How to read replies here"}   # 2.4.486 (was intent_model)

    # webhook_config — required when human_interface: webhook AND no channels
    webhook_config:
      connection: "reviewer-hook"   # "Add custom" record, service type 'Outbound webhook': base URL = address,
                                    # header rows = headers, secret row inbound_token (inline url/headers/token refused, 2.4.481)
      outbound_timeout: 30
      # inbound_endpoint: "/webhook/review"  # auto-derived from entry_points
      max_retries: 1
      retry_delay: 2
      # response_mapping: {user_reply: "response"}

    # channels — only valid when human_interface: webhook
    channels:
      slack:
        connection: "slack-workspace"      # credentials come from the vault, never a token field
        listen_channels: ["${SLACK_CHANNEL_ID}"]
        post_channel: "${SLACK_POST_CHANNEL}"

    can_call:
      - agent: "publisher"
        condition: "calling_agent_response.human_decision == 'approved'"
    yields: {decision: string}
    inputs: {request: object}

  # ── Human Agent — default (inbox) interface — hosted or self-hosted ──
  # reviewer_inbox:
  #   agent_type: "human"
  #   human_interface: "default"      # writes only to hosted HITL inbox (LeafCraft Studio)
  #   communication_type: "dual"
  #   human_timeout_seconds: 28800   # 8h — a PERSON answers this
  #   # NO webhook_config, NO channels — runtime ignores them
  #   can_call: [...]
  #   yields: {decision: string}
  #   inputs: {request: object}

  # ── Human Agent — api interface (Python callback) ──
  # reviewer_api:
  #   agent_type: "human"
  #   human_interface: "api"          # routed to a registered Python handler
  #   communication_type: "dual"
  #   human_timeout_seconds: 28800   # 8h — a PERSON answers this
  #   # NO webhook_config, NO channels
  #   can_call: [...]
  #   yields: {decision: string}
  #   inputs: {request: object}
```

## Scaling — one block (2.4.484)

How an agent runs in parallel is **one `scaling:` block** with two parts:
`runs` (separate jobs of this agent at the same time) and `copies` (several
copies of the agent working on ONE job, their results combined).

```yaml
  invoice_matcher:
    inputs: {invoices: array}
    scaling:
      runs:
        max: 4            # at most 4 of this agent's jobs at once across ALL pods; extra jobs wait their turn
      copies:
        mode: auto        # fixed (default) | auto
        max: 10           # auto: never more than 10 copies on one job (1–50, default 10)
        work: invoices    # auto: the input field holding the list — OR claim_tool: <tool>, exactly one
        handoff: last     # last (default): one combined output, handed on once | each: every copy hands on its own
```

- **`runs.max`** caps the agent's jobs **across every pod** of the mesh (the
  old `max_concurrent` counted per pod). Unset = no cap — every agent already
  takes several jobs at once.
- **`copies.mode: fixed`** — `count` copies (1–50; default 1 = a single run)
  each get the **whole** job, with `_instance: {id, of}` in their input. Give
  them disjoint work yourself (e.g. an atomic claim in a tool), or they
  duplicate it.
- **`copies.mode: auto`** — the mesh hands the work out item by item and
  **starts a copy only when there is an item for it**: 6 items with `max: 10`
  → 6 copies, never 10. With `work: <field>` each copy's input has that field
  set to its one item, plus `_instance: {id, of: "auto"}` and
  `_work: {item, field, tool}`; when it is done it takes the next with the
  built-in **`next_work_item`** tool (`{item}`, or `{done: true}` when none is
  left) and stops when none is left. An empty list → one run on the job as it
  came. With `claim_tool: <tool>` (work the agent finds itself, e.g. a
  backlog) the mesh calls that tool — no model run — before starting a copy and
  whenever a copy asks for more, and starts a copy only when it returns an item.
  An auto job holds one `runs` slot however many copies it has.
- **Rules checked at load:** `auto` needs **exactly one** of `work` /
  `claim_tool`; neither belongs in `fixed` (refused).
- **`handoff: last`** combines every copy's output: lists joined, numbers
  summed, other fields from the final copy; the combined output carries
  `_instances: {count, results, failed}` and is handed on **once**. Summing is
  wrong for scores and ratios (`confidence 0.9 + 0.9 = 1.8`) — reshape in
  `@chain` / `@compose`. `each` hands on every copy's own output.
- **The old fields are refused at load** — `parallel`, `max_concurrent`,
  `instances`, `instances_handoff` — with the lines to write. Convert:
  `instances: N` + `instances_handoff: H` → `scaling: {copies: {mode: fixed,
  count: N, handoff: H}}`; `max_concurrent: N` → `scaling: {runs: {max: N}}`;
  `parallel` → drop it. (An old field left at its old default — `parallel:
  false`, `instances: 1`, `instances_handoff: last` — is dropped quietly,
  because Studio used to write those into every saved agent.)
- **A human seat is never copied (2.4.485):** `copies` on a human agent
  (`mode: auto`, or `count` > 1) is refused at load — copies would ask the same
  person the same thing several times. `runs.max` still caps how many of the
  seat's requests are open at once.

Full field table: [agent-config-fields.md → scaling](agent-config-fields.md#scaling--how-an-agent-runs-in-parallel-24484).

## Traces: what is hidden, and the licence (2.4.481)

- **Traces have two layers of hiding.** (1) Always on: LeafCraft's own prompts
  show as `<platform_prompt:N chars>` and raw Manager replies as
  `<elided:N chars>` — this layer hides only LeafCraft's own text, never the
  agency's material. (2) The agency's content is governed by
  `security.telemetry_redact_pii` — **default `true`** (since 2.4.480): each
  content value reads `<redacted bytes:N>`; set `false` to keep what each agent
  received and replied readable. Credentials are masked either way; names,
  models, tokens, cost, status and errors stay visible. (`LEAFMESH_OTEL_REDACT_PII`
  is no longer read — boot warns if it is still set.)
- **No secret reaches a log or a trace by a side door (2.4.485):** every
  `leafmesh.*` logger scrubs its own lines, including what reaches your
  application's own root log handlers, and an agent's returned failure reason
  is scrubbed on the trace like a raised one.
- **The licence can block new sessions** (2.4.481): a plan at its limit or an
  unpaid invoice answers a **new** session with **HTTP 402** and the reason;
  runs in flight and sessions already started carry on.
- **A blank agency starts quietly** (2.4.482): no warnings about a Manager
  model, an escalation destination or agents it does not have yet; the same
  checks speak once it has an agent.

## Devices — an agent that reaches a device

A `device:` block gives an LLM agent the `device_action` tool. The block says
how to reach devices; **which device is never config** — it comes with the
request (`"device": {"id": "phone-7", "push_token": "..."}` or `"devices": [...]`).

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

- `connection` must be a **notifier** (fcm, mqtt, apns, webpush, hms, wns, expo,
  onesignal, azure_iot_hub, aws_iot, sns, azure_notification_hubs,
  pusher_beams, twilio_sms). `room` is a room connection: your own room service
  (`url` + `api_key`), mqtt, pubnub, ably, pusher or livekit.
- Pusher as the room needs the mesh on a **public https address**; LiveKit
  needs `pip install 'leafmesh[livekit]'`. Every device connection is Tested on
  save.
- Outcomes: `done`, `failed`, `declined`, `sent_for_approval`, `not_joined`,
  `unreachable`, `refused`. A connection lost after the task was sent is
  `failed` — the device may have done it.

Fields: [Device Block](agent-config-fields.md#device-block). Gotchas:
[#22](nuances-and-gotchas.md#22-devices--the-device-comes-from-the-conversation).

## External agents — `external_policy` and budgets

An external agent is someone else's system. One `external_policy:` block on it
says what it may reach and receive; with no block it is already safe (its own
host only, HTTPS, 1 MB replies, quarantine after 5 failures, secrets never
sent).

```yaml
    external_policy:
      allowed_hosts: ["files.vendor.example", "*.cdn.vendor.example"]
      max_response_bytes: 200000      # a bigger reply is a failure, never cut short
      quarantine_after: 3             # then calls fail at once until a person releases it
      send_fields: ["sku", "quantity"]   # only these input fields go out
      redact: ["\\b\\d{16}\\b"]       # card-like numbers become [redacted]
```

For an agent that runs tools in this process (`claude_agent`), two more keys
(2.4.486): `allowed_tools` / `denied_tools` — tool names, name patterns
(`mcp__leafmesh__*`) or `Tool(arg pattern)` (`Bash(rm *)`). The mesh decides
every tool call against them; they only narrow the host rights.

Release a quarantined agent with `POST /api/agents/{name}/release`. A cancelled
call (its session ended) never counts toward quarantine, and neither does an
agent with no address (2.4.490: it is never called — it is switched off as
"not set up" until the address is in its vault record). With `send_fields`
set, ONLY those fields go out — the conversation history, chain history and
rerun note too only when you list them. A programmatic agent with an
`integration:` is governed exactly like an external agent. A monthly budget on
an external agent whose connector reports no spend (`framework: custom`,
n8n, zapier, mcp, a2a, …) is metered by estimate (a cost cap needs
`price_per_1k_tokens`); running out of it is a failure, never an empty success. Full table:
[External Policy](agent-config-fields.md#external-policy).

### Pick it from the External agents page (2.4.486)

An external agent is set up **once** on Studio's External agents page — its
framework, the vault record that signs it in, and the framework's own
settings — and an agent picks it by name:

```yaml
    agent_type: "external"
    external_agent: "billing_a2a"    # the mesh fills in framework + connector_config from the page
```

The mesh fills in the framework and settings at start, on every save, and on
other pods when the entry changes. A `framework` / `connector_config` beside
the pick that **differs** from the entry is refused. An entry that is gone
makes the agent refuse its calls (start names it) — it never runs as
`custom`. Custom agents are offered as **Custom: API** (`custom_api` —
`method`, `path`, `query`, `answer_path`; the body is the agent's input) and
**Custom: A2A**. **The entry takes its kind from the vault record it picks
(2.4.491).** A CrewAI record makes a CrewAI agent, and so on — leave the
entry's `framework` out. Only a custom record needs one: `a2a` (Custom: A2A)
or `custom_api` (Custom: API). A `framework` that contradicts the record is
refused. `GET /api/external-agents/records` with no `framework` lists every
record an external agent can use, each with its framework (`null` for a
custom one). `POST /api/external-agents/from-spec` with `{spec: <file text>}`
reads a swagger / OpenAPI file and lists the POST / PUT / PATCH operations a
Custom API agent can be (`method`, `path`) plus the file's servers; it saves
nothing. `framework: custom` (a Python function) is separate and unchanged.
The old `framework:` + `connector_config: {connection: …}`
shape still loads and runs. Tool platforms (MCP, Zapier, Composio, n8n) are
not on this page — they are Tools-page entries; a programmatic agent's
`integration` picks one with `connector_config: {account: <entry>}`.

### Credentials on an external agent

**Only the vault (2.4.485):** the 58 connector env fallbacks (`CREWAI_ENDPOINT`,
`A2A_AGENT_URL`, `N8N_WEBHOOK_URL`, …) are no longer read — boot names each one
still set. Model keys and the host's cloud identity stay in `.env`.

The account — address, keys, tokens, client / tenant ids, `auth_scheme`,
header rows — lives **only** on a vault connection (2.4.482): Infrastructure →
External agents → `<framework>`, or an "Add custom" record with service type
'External agent' whose base URL is the address (zapier / composio / n8n / mcp:
Infrastructure → Integrations, or an "Add custom" record with service type 'Tools').
`connector_config` picks it with `connection` (zapier: `vault_connection`) and
keeps only behaviour. It is resolved on **every call**, in the request's
tenant, so a rotation on the Infrastructure page applies to the next call:

```yaml
    connector_config:
      connection: "crm-agent"     # address + credentials; url / auth_token / headers here FAIL TO LOAD
      graph_id: "quote"           # behaviour (ids, mode, timeouts, prompts) stays inline
```

Written inline — literal, `${ENV}` or `${vault:…}` — a vault key refuses the
config: "connector_config url on a crewai agent: credentials, addresses and
header rows are entered only in the vault — put it in a vault connection
(Infrastructure → External agents → CrewAI, or an "Add custom" record on the
Infrastructure page with service type 'External agent' whose base URL is the
address) and pick that connection with `connection`" (2.4.484 wording). An `mcp` connector's credential-named `env` entry is
refused the same way; secret body rows on its connection become the command's
environment (2.4.486 caveat: a custom 'Tools' record now keeps header rows only,
so such body rows are refused on save and old ones are no longer sent). Full key list: agent-config-fields.md → Common connector_config fields.

### `request_form` — your own fields with every request

Fields of your own sent with every request, in that system's own place for
caller data (n8n: the webhook body; A2A: message metadata; LangGraph:
`config.configurable`; Dify / Wordware / CrewAI: `inputs`; Flowise:
`overrideConfig.vars`; MCP / Zapier / Composio: the tool's arguments; …):

```yaml
    request_form:
      region: "eu-west"
      priority: "high"
      crm_token: "${vault:crm.api_key}"   # a secret: always a vault reference
```

- Any keys, any JSON values. It never replaces what the SDK sets (the message,
  session or conversation ids) — a clashing key is warned about once and the
  SDK's value is sent. Values are never logged; only key names reach the trace.
- **Limits (refused at load and save):** at most 50 keys, 16 KB as JSON, key
  names of letters, digits, `_`, `-`, `.` (≤ 64 characters, not starting with
  `_`), no secret written inline.
- **Refused for** `writer`, `watsonx`, `autogen`, `hermes`, `relevance`,
  `claude_agent`, `openai_agents`, `custom_api` (2.4.486) and `custom` — their
  request has no place for it. Also refused on `llm` / `human` agents and on a programmatic agent with no
  `integration`.

### What an external agent reports, and what it remembers

- **Conversation continuity is automatic.** The external system's own
  conversation handle (A2A context, LangGraph thread, Dify conversation, n8n
  session id, …) is kept per agent, mesh session and tenant and sent back on
  the next turn. Two sessions or tenants never share one.
- **Every connector reports the steps its system ran** (tool calls, nodes,
  tasks). They show on the activity feed, the board ticket's checklist and the
  trace, and the experience judge learns from them. n8n reports its nodes when
  its vault connection holds your n8n API key as `api_key` (scopes
  execution:list + execution:read) — never in `connector_config`.
- **A2A 1.0 and 0.3 are both spoken**, chosen from the agent card
  (`/.well-known/agent-card.json`, older agents `/.well-known/agent.json`); an
  agent that answers in the other dialect is retried once in it. A changed card
  quarantines the agent until a person releases it.
- A reply's business field named `status` is data — only `success: false` with
  an error (the SDK's failure shape) makes a call fail. A failing MCP tool is a
  failure. A LangGraph graph stopped at an `interrupt()` is reported as one.

### What applies live (no restart)

Since 2.4.484 every saved setting applies without a restart (see
[What applies when](#what-applies-when-24484)). For external agents:
changing an external agent's `framework` or `connection:`, rotating its
connection on the Infrastructure page, `can_call` on any agent, `request_form`,
`external_policy` and `callback_timeout` all apply without a restart.
`PATCH /api/yaml/agents/{name}` merges nested blocks one level deep
(`{"external_policy": {"quarantine_after": 3}}` keeps `send_fields`; a key sent
as `null` is removed); `PUT` replaces the whole agent.

**Claude Agent's host rights** — `connector_config.cwd`, `allowed_tools`,
`permission_mode`, and from 2.4.486 `setting_sources`, `disallowed_tools`,
`sandbox` — are refused by every API write (Studio included). **Since 2.4.485
you change them from the host:**

```bash
leafmesh agent host-rights coder --cwd /srv/work --allowed-tools Read,Edit,Bash \
    --permission-mode acceptEdits          # default | acceptEdits | plan | bypassPermissions
leafmesh agent host-rights coder --clear allowed_tools --yes
```

It finds the store from `.env`, prints the change, and saves only after
`--yes` or a typed `apply`; the save is the store's next version and every pod
applies it. 2.4.486 adds `--setting-sources user,project,local` (default none:
the host's CLAUDE.md and settings do not reach the agent), `--disallowed-tools`
and `--sandbox '{"enabled": true}'`. The agent must carry `framework:
claude_agent` in the stored configuration. While it runs, the mesh controls it
(2.4.486): Stop / quarantine / session end / timeout interrupt it first,
every tool call is decided against `external_policy`, `max_budget_usd` comes
from its budget share for the run, a declared `yields` is enforced as
structured output, and changed files are recorded with a checkpoint id —
[agent-config-fields.md → claude_agent](agent-config-fields.md#claude_agent).
(`leafmesh vault rotate-key` likewise finds the store from `.env`; its
`--config` is now only an optional old file read for the agency's name.)

## Self-healing

A **top-level** `self_healing:` block (not under `manager:`). Watching and
notifying are on by default; acting (restart, spawn a backup) is off until
`actions_enabled: true`. Latency is judged against each agent's own median, and
`cooldown_s` / `max_actions_per_hour` / `max_backups_per_agent` cap what it can
do. Defaults: [Self-Healing](agent-config-fields.md#self-healing-self_healing).

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
  probably meant `thinking: true` (see [reasoning vs thinking](agent-config-fields.md#reasoning-vs-thinking)).
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
| `dual` | Answers its caller, then continues down its `can_call`. Belongs on the human / webhook boundary agent; `dual` → `dual` ping-pongs |
| `chain` | The caller waits for this agent's answer. Every AI, programmatic and external peer behind the boundary |

`execute` is a deprecated alias: the loader reads it as `chain` (`dual` on a
human seat) and warns. Write `chain`.

## Fan-In Patterns (wait_for)

```yaml
wait_for: "A AND B"                    # Wait for both
wait_for: "A OR B"                     # Runs on the first; runs again when the other arrives (2.4.486)
wait_for: "A AND B?"                   # A required, B optional
wait_for: "A AND (B OR C)"            # A required + race between B and C
```

Optional-contributor (`B?`) semantics — current (v2.4.22+):

- An optional sibling **dispatched from the same upstream output** is
  **waited for** — in-flight contributors count as pending, not absent.
  The fan-in no longer completes early with partial data while a
  sibling is still running.
- **Runs now, and again as late work arrives (2.4.486).** The target runs as
  soon as the expression is met — one side of an OR is enough, even while the
  other side is still running — and runs **again**, on everything gathered, as
  each agent still running arrives. Its input carries `still_running: [...]`
  while more is coming and `update_from: <agent>` on the re-run: write the
  target so a second run updates rather than repeats. A contributor that fails
  after the target ran runs nothing. A second request in the same session is a
  new round. (2.4.462–2.4.485 waited for the running side; before that, late
  arrivals were dropped.)
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
             allowed_agents=["researcher_agent"])
def lookup(record_id: str) -> dict:
    return {"id": record_id, "data": "..."}

@tool(name="format_md", description="Format as markdown")
def format_md(items: list) -> str:
    return "\n".join(f"- {item}" for item in items)
```

A tool has no confirmation step. `requires_confirmation=True` is still accepted
but **does nothing**: the tool runs, and the SDK logs a warning once. If a person
must sign off before a tool runs, route the work through a human agent before
the agent that calls it ([Approval is routing](#approval-is-routing)).

**`changes_nothing=True` (2.4.491)** on `@tool(...)` / `@global_tool(...)`
(a class tool: `CHANGES_NOTHING = True`; a `zapier` / `composio` / `n8n`
block: `changes_nothing: true`) says the tool only looks things up. A turn
whose tools all change nothing may be stored in the response cache and
replayed **without running its tools**. Mark only a tool whose answer also
does not depend on **when** it ran — a policy table, a rate card, static
reference data. A read of live data (an invoice's status, stock levels, a
queue to claim from) stays off: a replay would give a stale answer. Sending,
writing, claiming work or reading the clock is never `changes_nothing`. See
[nuances → the response cache](nuances-and-gotchas.md#memory-experience-and-the-response-cache-24486).

## Manager (Coordination + Escalation)

```yaml
manager:
  # on by default — omit `enabled` (set `enabled: false` only to kill
  # coordination + the summarizer entirely; rare)
  model: "gpt-4o-mini"          # Summarizer model — REQUIRED for supervision.
                                # Without it the manager/summarizer are INERT and
                                # boot says so; nothing is guessed.
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
      #   connection: "escalation-hook"   # "Add custom" record, service type 'Outbound webhook' (url/headers inline refused, 2.4.481)
      # - type: "channel"
      #   provider: "slack"
      #   channel_id: "${ESCALATION_SLACK_CHANNEL}"
    auto_escalate:
      max_retries: 3
      max_errors_per_session: 5
      # timeout_threshold: removed in 2.4.486 (dropped with a warning) — nobody answering is not escalated
  # temperature: 0.1 / max_tokens: 4000 are the Manager's defaults; it reads its own since 2.4.485
```

`manager.timeout_rules` and `manager.human_response_rules.timeout` are gone
too (2.4.486, dropped with a warning) — see [When nobody answers](#when-nobody-answers-24486).

## LLM Providers

Three ways to reach a model: **(1)** each vendor with its own key — the
default; **(2)** the customer's own cloud — `bedrock/…`, `vertex/…`,
`foundry/…`; **(3)** `openrouter/…` — one optional key for the long tail,
whose answers carry their real cost. Every key goes in `.env` or on the
Infrastructure page (a key plus, for the table vendors, an optional
Endpoint for another region or a proxy — `<NAME>_BASE_URL` in env).

**How many providers depends on the SDK.** PyPI 2.4.418 (what customers have
today): **10** built in plus any OpenAI-compatible endpoint. Dev 2.4.434+
(this baseline): **27** — the table below. Don't promise a provider the
customer's installed SDK does not have.

| Provider | Model Prefix | Config |
|----------|-------------|--------|
| OpenAI | `gpt-`, `o1`, `o3`, `o4`, `chatgpt-` | `OPENAI_API_KEY` env var |
| Anthropic | `claude-` | `ANTHROPIC_API_KEY` env var |
| Google | `gemini-` | `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) env var |
| DeepSeek | `deepseek-` | `DEEPSEEK_API_KEY` env var |
| AWS Bedrock | `bedrock/model-name` | `mesh.bedrock.connection` → an AWS Bedrock record (region) under Infrastructure → Models; or the host's AWS sign-in. `region` in YAML is refused (2.4.481) |
| Google Vertex | `vertex/model-name` | `mesh.vertex.connection` → a Google Vertex record (`project_id`, `location`); `project` / `location` in YAML are refused (2.4.481) |
| Azure Foundry | `foundry/model-name` | `mesh.foundry.connection` → an Azure Foundry record (endpoint + key), or `AZURE_FOUNDRY_API_KEY` (or `AZURE_OPENAI_API_KEY`) + `AZURE_FOUNDRY_ENDPOINT` in `.env`; `endpoint` in YAML is refused (2.4.481) |
| **xAI Grok** | `grok-` | `XAI_API_KEY` (or `GROK_API_KEY`) env var |
| **Mistral** | `mistral-`, `codestral-`, `magistral-`, `ministral-` | `MISTRAL_API_KEY` env var |
| OpenRouter | `openrouter/` (stripped) | `OPENROUTER_API_KEY` |
| Groq | `groq/` (stripped) | `GROQ_API_KEY` |
| Cerebras | `cerebras/` (stripped) | `CEREBRAS_API_KEY` |
| Moonshot Kimi | `kimi-`, `moonshot-` | `MOONSHOT_API_KEY` (or `KIMI_API_KEY`) |
| Alibaba Qwen | `qwen` | `DASHSCOPE_API_KEY` (or `QWEN_API_KEY`); Singapore endpoint by default, a key works only in its region |
| Z.AI GLM | `glm-` | `ZAI_API_KEY` (or `GLM_API_KEY`) |
| MiniMax | `minimax-` | `MINIMAX_API_KEY` |
| Inception (Mercury) | `mercury-` | `INCEPTION_API_KEY` |
| Meta (Muse) | `muse-` | `META_API_KEY` (or `MODEL_API_KEY`) |
| Tencent Hunyuan | `hy3`, `hy4`, `hunyuan-` | `HUNYUAN_API_KEY` (only `tool_choice: auto` honoured) |
| Xiaomi MiMo | `mimo-` | `MIMO_API_KEY` (only `tool_choice: auto` honoured) |
| StepFun | `step-` | `STEPFUN_API_KEY` (or `STEP_API_KEY`) |
| Upstage (Solar) | `solar-` | `UPSTAGE_API_KEY` |
| Poolside (Laguna) | `poolside/` (sent as is — part of the id) | `POOLSIDE_API_KEY` |
| Reka | `reka-` | `REKA_API_KEY` |
| Arcee | `trinity-`, `arcee-` | `ARCEE_API_KEY` (or `ARCEEAI_API_KEY`) |
| Cohere | `command-` | `CO_API_KEY` (or `COHERE_API_KEY`) |
| Local (vLLM, Ollama, etc.) | any other name | Models → Local / self-hosted record (or `LOCAL_MODEL_ENDPOINT` in `.env`) + `mesh.local.server_type`; `endpoint` in YAML is refused (2.4.481) |

Picking a model: only write ids from
[agent-config-fields.md → Model List](agent-config-fields.md#model-list).
Retired ids (`deepseek-chat`, `deepseek-reasoner`, `grok-4`, `gemini-2.0-flash`,
`mistral-large-2`, `claude-sonnet-4-7`, `claude-haiku-4-6`) still parse but
are not offered. **Fast and cheap:** `gpt-6-luna`, `claude-haiku-5-5`,
`gemini-3.5-flash-lite`, `deepseek-flash`, `mistral-small-4-0-26-03`,
`qwen3.7-flash`, `glm-5.3-flash`, `mercury-3`. **Strongest:** `gpt-6-astra`,
`claude-fable-5-1`, `gemini-4-argon`, `grok-4.7`. Costs follow how each
vendor bills: size tiers for long prompts, dated price changes, DeepSeek
off-peak; a model with no published price reports "cost unknown".

**A model on your own server is added once (2.4.458).** Never invent a model
name and hope it routes. First make its vault record: an "Add custom" record
with service type 'Model', the server's address as its base URL and any key as
a header row. Then add it on the Models page, or with `POST /api/models
{name, server: {interface, timeout?}, connection, model_id?, label?, query?,
price_id?}`. `interface` is how the server is spoken to: `vllm`, `sglang`,
`ollama`, `llamacpp`, `lmstudio`, `tgi`, `localai`, `triton`,
`openai_compatible`, … (`GET /api/models/interfaces`). After that, write its
`name` in `model:` like any other. Since 2.4.460 the Models page holds only
your own servers: `runs_on` is always `server`, and an `endpoint` in `server`
is refused (the address lives in the record). A provider's own models need
only its key. `POST /api/models/{name}/test` sends one tiny message.

**Model prices are price records, never config.yaml (2.4.457).** A record
(`POST /api/pricing {name, kind?, input, output, cache_read?, cache_write?,
note?, models?}`, USD per 1M tokens, `kind` `chat` or `embedding`) is tagged
to models, and one record can price many. An untagged model uses the SDK's
standard price. `GET /api/pricing/standard?used=true` shows each model the
agents use, its price, and where it comes from: `record`, `vendor`
(OpenRouter reports each call's cost), `standard`, or `unknown`. An `unknown`
model shows "cost unknown", never $0 — tag a record to it.

## Building New Agents -- Step by Step

1. **Add YAML config** under `agents:` — in Studio's YAML editor, with
   `PUT /api/yaml/raw` / `POST /api/yaml/agents`, or `leafmesh config export` →
   edit → `leafmesh config import` (the configuration lives in the store —
   [Where the configuration lives](#where-the-configuration-lives-24481))
2. **For connector-only agents** (programmatic with `integration`, or external with `external_agent` / `framework`): done -- no Python needed
3. **For agents with custom logic**: create `agency/<name>_agent.py` -- function name must match agent name
4. **Add to can_call** of upstream agents that should route to it
5. **Add entry point** if it should be directly invocable
6. **New or changed Python code** (`agency/*.py`) needs the process restarted
   (`python main.py`). A configuration-only change does not — it applies live
   ([What applies when](#what-applies-when-24484))

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

**Race pattern**: Multiple approaches — runs on the first, and again with the
slower one's answer as an update (2.4.486)
```yaml
consumer_agent:
  wait_for: "fast_agent OR slow_agent"
```

**HITL review (approval is routing)**: Agent -> human agent -> continue or revise.
There is no approval switch on an agent or a tool; the person's agent is a
node the work is routed to, and its `can_call` carries the work on.
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
- **[agent-config-fields.md](agent-config-fields.md)** — **Authoritative field reference for every YAML field**. Lists every option for every agent type (`llm`, `human`, `external`, `programmatic`), plus `WebhookConfig`, `ChannelConfig`, `Memory`, `EscalationConfig`, `EscalationTarget`, the agent's `scaling:` block (2.4.484), `notify` (2.4.485), `reply_reader`, `external_agent` / the External agents page, `custom_api`, `model_connection` and Claude Agent's host rights (2.4.486), `LeafMeshConfig`, `ManagerConfig`, `MeshConfig` (Bedrock / Vertex / Foundry / Local), the runtime blocks with every default as a blank agency writes it (incl. `security.telemetry_redact_pii`), what applies live / reloads / needs a restart, the Datastore `.env` names, `EvolutionConfig`, `DataStructure`, `Entry Points`, all per-framework `connector_config` schemas, and the **Field Applicability by Agent Type** matrix. Read this file when in doubt about any field, accepted values, default, or what's allowed where.
- **[nuances-and-gotchas.md](nuances-and-gotchas.md)** — the non-obvious rules (READ FIRST), incl. #25: the configuration lives in the store (create-leafmesh projects ship no configuration file; a `config.yaml` given to `from_yaml` is only the first-boot seed), settings apply live; Vault-only values with the Infrastructure page's real sections; Scaling (`scaling:`); and the "why is my agent misbehaving?" checklist.
- **[reference.md](reference.md)** — SDK Python API (`LeafMesh.from_yaml` / `from_store`, `sdk.start()`, `sdk.mesh_call()`, `@global_tool`, decorators, error classes, env vars incl. `LEAFMESH_AGENCY_NAME`, etc.).
- **[examples.md](examples.md)** — copy-paste agent patterns (HITL, fan-out, hub-and-spoke, race, copies on a list with `scaling`, etc.).

> When the user asks "what fields can I put on a programmatic agent?" / "what's the default for `temperature`?" / "what does `wait_for: A AND B?` mean?" / "how do I make n8n answer later (`after_handoff: wait`)?" / "what fields does `EscalationTarget` accept?" — the answer lives in **agent-config-fields.md**. Don't guess; quote the file.

---

## Field reference

The complete field reference — every field, type, default, and accepted value for every agent type and config object — lives in its own file: **[agent-config-fields.md](agent-config-fields.md)**. Read it there.

> This section previously inlined a full copy of `agent-config-fields.md`. The copy was **removed** because it drifted out of sync with the source (diverging `tool_choice` defaults, missing LLM fields, stale `skills`/`session_ttl`/`super_agent` claims). There is now a single source of truth — always consult `agent-config-fields.md` for field-level questions.
