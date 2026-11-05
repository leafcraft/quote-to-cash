# quote-to-cash — Quote-to-Cash Pod

Five digital employees + five human roles that run a deal from an **RFQ all
the way to cash** — **RFQ → shape a priced, policy-compliant deal
(super-agent) → approval matrix (rep / deal-desk / finance / CFO) → draft →
ISSUE the quote artifact (finisher, fail-closed) → invoice → dun the overdue
backlog** — with a human on every approval step and the systems (CPQ / ERP /
CLM / billing) as tools inside the agents, never members.

**Read `PRD.md`** for the full agent-by-agent spec. This is a **pod-standard**
template (SDK 2.4.131): a team of self-reliant agents, not a pipeline.

## Story

A mid-market RFQ lands from **ACME** — 40 Pro seats plus onboarding, close by
month-end. Today a rep would key the line items, look up costs in the price
book, guess a discount that beats the competitor, chase the right approver,
draft the quote, and — weeks later — remember to invoice and then chase the
payment. This pod runs that whole chain. **Quinn** opens the case and hands it
to **Cass**, who pulls the price book, this account's deal history, and
competitor pricing, then shapes a defensible discount. A deterministic floor
recomputes the margin and tier, so the **approval matrix routes to exactly one
human** — a healthy small deal to the rep, a deep discount straight to the CFO,
no gaming it. On approval the **drafter** assembles the quote and the
**issuer** checks who approved, then renders the real artifact and pushes it to
the CPQ — an under-approved deal is never rendered or pushed. When the customer accepts, **billing**
raises the invoice; every morning it fans out across parallel copies to dun the
overdue backlog, each copy claiming a disjoint batch so nobody is chased twice.

## Why it works in an organization

Quote-to-cash leaks at the seams: a discount that quietly dips below margin
floor, a quote approved by the wrong tier, an invoice that never goes out, an
overdue account nobody swept. This pod closes each seam the only honest way.
**Cass never invents a cost basis** — a code floor recomputes COGS, margin, and
the discount tier from the price book, so the gate fires on *computed* numbers,
not the model's. **The approval matrix is wires, not code** — the whole
amount × margin × discount policy is readable in one block, and exactly one tier
fires per deal. **The issuer re-checks that the *required* approver actually
cleared the deal** — the tier is re-derived in code from the financials and
compared with the seat that approved (recorded from the reply) — before it
renders or pushes anything, and **deletes a half-issued quote** if its floor
trips. **Silence never advances a deal** — if nobody answers within the reply
window, the Inbox card closes and the ticket records that no reply came; nothing
is approved or issued, and nobody is chased automatically. **Billing never duns a paid invoice**, and its atomic claim means
parallel copies split the backlog instead of double-chasing. Every decision,
approval, issuance, held gate, and dunning action lands in a hash-chained WORM
ledger. ROI: faster quotes, real margin control, no missed invoices, and a live
"where is my quote?" answer.

## The team (11 members)

| Agent | Role (human job title) | Responsibilities | Can perform |
|---|---|---|---|
| `quinn_coordinator_agent` | Deal Coordinator | Owns the deal end to end; opens the case, keeps live status, is the single point of contact | LLM; orchestrates Cass→drafter→issuer→billing; routes exceptions to the RevOps Lead; **never prices or approves** |
| `cass_shaper_agent` | Costing & Deal Shaper | Costs the RFQ, shapes a policy-compliant discount against history + competitive signals | LLM + **super_agent** (autonomous deal shaping) + **playbook** (quote / approve) + price/history/competitor tools; `@chain` **pricing + completeness floors** (fail closed); its wires **are** the approval matrix |
| `drafter_agent` | Quote Drafter | Assembles the approved quote body + validity and renders a draft | LLM; `@chain` **validity floor** (caps shelf life by tier); renders the draft to `./out` |
| `quote_issuer_agent` | Quote Issuer | Renders + issues the approved quote artifact and pushes it to the CPQ | Programmatic **finisher**; approve re-check + required-approver re-derivation → invariants → render `./out/<quote>.pdf` → **delete-on-block** → dev-store fallback → WORM |
| `billing_agent` | AR & Collections Clerk | Invoices accepted quotes and duns the overdue backlog | LLM + **playbook** (invoice / dun) + **scaling.copies** (backlog fan-out) + **atomic claim** tool + `wake_up`/`timezone`; `@chain` **never duns a paid invoice** |
| `sales_rep_human` | Sales Rep (Human) | Self-approves small healthy deals; reworks incomplete RFQs | Human gate |
| `deal_desk_human` | Deal Desk (Human) | Approves >10% off or >$25K list (up to 20% / $100K) | Human gate |
| `finance_approver_human` | Finance Approver (Human) | Approves >20% off or >$100K list (up to 30% / $1M) | Human gate |
| `cfo_human` | CFO (Human) | Top-tier authority (margin below 20%, over 30% off, or over $1M) | Human gate |
| `revops_lead_human` | RevOps Lead (Human) | Accountable owner — resolves escalations, owns policy calls | Human gate — everything that leaves the pod |
| `qtc_audit_logger_agent` | WORM audit | Hash-chains every decision, approval, issuance, held gate, dunning action | External (custom sink); terminus |

Approval matrix (list price × post-discount margin × discount — exactly one
tier fires): Sales Rep up to $25K and ≤ 10% off; Deal Desk up to $100K and
≤ 20%; Finance up to $1M and ≤ 30%; CFO above that, or any deal under the 20%
margin floor. Reply windows (`human_timeout_seconds`): Sales Rep 4 working hours,
Deal Desk 4 working hours, Finance 8 working hours, CFO 24 hours, RevOps Lead
24 hours.

The **LeafMesh Manager** supervises. It escalates to the RevOps Lead when an
agent fails with an error a retry cannot fix (auth, bad request, credit, bad
config), when 5 different agents fail in one session, or when restarts run out.
A broken hand-off contract raises an alert only. An RFQ still incomplete after
rework and a severely overdue account reach the Lead on the agents' own wires.

## Prerequisites — what to set, in three tiers

Everything is set in `.env` (`cp env .env`). The **whole LLM chain (shape →
approve → draft → issue → invoice → dun) runs on Tier 1 alone** against the
seeded stores (`./data`); price-book, billing, and CPQ reads use dev
stand-ins that **announce themselves** until you wire Tiers 2–3.

### Tier 1 — required to boot (dev mode)
| Setting | For | Notes |
|---|---|---|
| `LEAFMESH_LICENSE_KEY` | LeafMesh runtime | **Required.** |
| `ANTHROPIC_API_KEY` | Cass (deal shaping, Claude) | **Required.** |
| `OPENAI_API_KEY` | Quinn + drafter + billing + Manager (`gpt-4o-mini`) | **Required** unless you change the models. |
| `REDIS_HOST` / `PORT` / `PASSWORD` | State store | Defaults to `localhost:6379`. `docker run -d -p 6379:6379 redis:7-alpine`. |
| *(no setting)* — human members | Human approvals | Answer in Studio's Inbox. To notify an external tool instead, create a vault connection (an "Add custom" record on the Infrastructure page, service type 'Outbound webhook') and set `webhook_config: {connection: <name>}` on the seat. |

### Tier 2 — real system-of-record connectors (create the vault connection, uncomment the `mcp` block)
| Setting | Enables |
|---|---|
| vault connection `cpq_mcp` | Real CPQ/ERP price book + deal history (`cass_shaper_agent`) |
| vault connection `billing_mcp` | Real billing/AR reads + writes (`billing_agent`) |

> The server's URL + token are entered only in the vault (Infrastructure →
> Integrations → MCP), never in `configs/config.yaml` or `.env`. The `mcp`
> blocks ship **commented** in `configs/config.yaml`: create the connection,
> then uncomment — in the file before the first start, in Studio's YAML editor
> after it (applies live, no restart; see *Changing the configuration after the first start*).
> Nothing goes in `.env`: `agency/tools.py` checks whether the vault record
> `cpq_mcp` / `billing_mcp` exists, only to word an empty dev-store answer.
> (Billing's copies split the backlog with the atomic `claim_billing_work` tool;
> 2.4.484's `copies.mode: auto` with `claim_tool:` could replace this manual
> split — an owner decision, not done here.)

### Tier 3 — CPQ create-quote webhook (the finisher's push)
| Vault record | Enables |
|---|---|
| `cpq_webhook` — create vault record 'cpq_webhook' on Infrastructure → Add custom → service type 'Outbound webhook': base URL = your CPQ's create-quote address, a header row for its auth (the token as a secret row) | The issuer POSTs the issued quote (JSON) there and reports `cpq_pushed: true`. Until the record exists, `cpq_pushed` is false and the issuer records the quote in the dev store (`./data/issued_quotes.json`), saying so. Either way it renders `./out/<quote>.pdf` (or `.md`). Nothing goes in `.env`. |

## Run it

```bash
pip install -r requirements.txt          # core LeafMesh runs the pod day-0
docker run -d -p 6379:6379 redis:7-alpine
cp env .env                              # fill at least Tier 1
python validate_config.py                # pre-flight: wiring, yields, dead-code
python main.py                           # API at http://127.0.0.1:18820/docs
```

Submit an RFQ (day-0, against the seed store — no connector needed):

```bash
curl -X POST http://127.0.0.1:18820/api/mesh/request \
  -H "Content-Type: application/json" \
  -d '{"entry_point":"rfq_email",
       "data":{"rfq_id":"RFQ-2026-0042","customer_id":"ACME-4471",
               "segment":"mid_market",
               "line_items":[{"sku":"PRO-SEAT","qty":40,"list_price_cents":120000},
                             {"sku":"ONBOARD-STD","qty":1,"list_price_cents":500000}]}}'
```

See `examples/` for the four scenarios (rep self-approval, a deep discount that
forces the CFO tier, an accepted quote → invoice, and the dunning sweep):

```bash
python examples/run_examples.py
```

On approval, the issuer renders the approved quote to `./out/` and appends the
hash-chained ledger at `./logs/qtc_audit.jsonl`.

> Packaging note: `pip install leafmesh` (core) includes all LLM providers and
> runs the pod. For real CPQ/ERP/billing connectors add `leafmesh[mcp]`. Avoid
> `leafmesh[all]` on Python 3.12+ (it pulls `cchardet`, which has no wheel) — add
> only the specific extras you need.

---

*Built with `create-leafmesh`. The config is the department; the PRD is the brief.*
*Design doctrine: `.claude/skills/leafmesh/building-agents-thoroughly.md`.*

## Changing the configuration after the first start

`configs/config.yaml` is only the first-start seed. On the first start (an empty store) the agency imports it as version 1 and from then on keeps its configuration in the store. After that the file is not read again: an edit to it is **not** applied, even after a restart (the boot log says "that edit was NOT applied").

To change a running agency:

- **Studio** — its settings pages, or the raw YAML editor.
- **API** — `PUT /api/yaml/raw` with an `X-API-Key` header and the body `{"yaml_content": "<the whole YAML>", "save_to_disk": true}`, or `PATCH /api/yaml/config` with `{"updates": {...}, "save_to_disk": true}`.

Each save is a new version and applies live on every pod — no restart. (A few settings, such as brokers, make the agency reload itself in place within seconds.) So wherever this README or a comment says "uncomment X in `configs/config.yaml`", do it in the file before the first start, or in Studio's YAML editor after it.

## Changing a running project (Docker)

What reaches a project that is already running (leafmesh 2.4.497). The
image holds the Python code and the first-start `configs/config.yaml`;
`.env` is passed in when the container is created; the store (Redis) keeps
its data on its own volume.

| You change | When it applies |
|---|---|
| An agent in Studio (prompt, model, tools, routes, human seats, schedules, …) | At once, no restart |
| A human seat's `channels` (Slack, email, …) | The agency reloads itself in place within seconds |
| Add or delete an agent in Studio | At once, including routes and schedules |
| A connection in the vault (model keys, MCP, webhooks, connectors, Slack, email) | At once. An agent switched off for a missing connection or address switches back on by itself |
| Anything in `.env` (licence, agency name, store, ports) | After `docker compose up -d` (the container is recreated) |
| Python code (`agency/*.py`: programmatic agents, tools, `@pre_compose`) | After a rebuild: `docker compose up -d --build` |
| `configs/config.yaml` | Never after the first start. It is read only when the store is empty |
| Several app containers on one store | A Studio save reaches every one within about 15 seconds |

- Keep model keys in the vault. A key there wins over the same key in
  `.env` (the log warns), and a change applies at once. From 2.4.497 that
  holds for every value the vault holds (endpoints, organisation / project
  ids, cloud identities); the `.env` value returns when the record goes.
- Code the image does not have: an agent marked pure Python
  (`integration: python`) is switched off until its function is in the image;
  any other programmatic agent stays on, and each call to code it does not
  have fails. Rebuild the image with the code first.
- A new Redis volume is an empty store, so `configs/config.yaml` is imported
  again as version 1.
- **If the agency refuses to start after an upgrade** (a new leafmesh pin,
  then a rebuild: "Configuration has N error(s) in the stored
  configuration"), repair the stored configuration with the agency stopped:

  ```bash
  docker compose run --rm quote-to-cash leafmesh config check      # each problem, with its line
  docker compose run --rm quote-to-cash leafmesh config versions   # kept versions: which pass, which is in use
  docker compose run --rm quote-to-cash leafmesh config rollback   # back to the newest version that passes (saved as a new version)
  ```

  Or `leafmesh config export > config.yaml`, fix it by hand, then
  `leafmesh config import config.yaml` (it is checked before it is saved).

## Where the data store is set

From leafmesh 2.4.482 the store (Redis or Postgres) is set **only in `.env`** — never in `configs/config.yaml`. A `persistence:` block in the YAML is ignored with a warning on leafmesh 2.4.482–2.4.485; from 2.4.486 the agency refuses to start if that block differs from `.env`, and names each `.env` line to add. The project's `.env` sets the store explicitly (`LEAFMESH_STORE`, `LEAFMESH_AGENCY_NAME`, `REDIS_*`).

- Redis (default): `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`; optional `REDIS_DEFAULT_TTL`, `REDIS_SESSION_TTL`, `REDIS_SSL*`, `REDIS_CLUSTER_NODES`.
- Postgres instead: `LEAFMESH_STORE=postgres` plus `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (optional `POSTGRES_SSLMODE`).
- Or the whole server in one value: `REDIS_URL=redis://user:pw@host:6379/0` (`rediss://` turns TLS on) or `DATABASE_URL=postgresql://user:pw@host:5432/db`. The single names fill in what the URL leaves out.
- With Docker Compose the app reaches Redis as `redis` (the service name); compose sets that for you.
- Check it in Studio → **Infrastructure → Datastores**: it shows whether the store is reachable (never the address or password).

## This mesh's sign-in (leafmesh 2.4.497)

From leafmesh 2.4.497 each mesh signs in to LeafCraft with its own key, not
a key shared by every install.

- **First start.** The mesh makes a key pair and registers it with
  `LEAFMESH_LICENSE_KEY` and `LEAFMESH_ENV_TOKEN` from `.env` (copy the
  environment token from Studio — a placeholder such as `development` is
  refused). With both valid it works at once. If your organisation turned on
  "require approval", the first start stops and says so: approve it in
  Studio → **Keys → SDK access**, then start again. Organisation admins get an
  email for every new registration.
- **Where the key lives.** In the vault, in the store, encrypted with
  `LEAFMESH_VAULT_KEY`: it survives rebuilds and every copy of the app shares
  it. A new Redis volume, or a new vault key, makes a new key pair that
  registers again — revoke the old one in Studio.
- **Check or change it** (in Docker: `docker compose run --rm quote-to-cash leafmesh auth status`):
  - `leafmesh auth status` — credential id, key fingerprint, registration and
    mode, never a key; `--check` signs in now and reports the tokens.
  - `leafmesh auth register` — register now.
  - `leafmesh auth rotate` — a new key pair: once it is active the mesh
    switches to it and revokes the old one. A revoked or expired key is never
    revived; rotate instead.
- **Lost the environment token?** From 5 Dec 2026 Studio shows the licence
  key and environment token only once, when they are made (then only a hint).
  Rotate the environment token in Studio and put the new one in `.env`.
  Rotating it changes where the agency's data is kept in the store, so do it
  before the agency holds data.
- **An existing project whose `.env` says `LEAFMESH_ENV_TOKEN=development`.**
  2.4.497 needs the real token. The token also names where the agency's data
  sits in the store, so with the real token the agency starts on an empty
  store (vault, sessions, board) — the old data stays under the old name. Set
  the real token before you put data in the agency, or contact us to move it.

## Your vault key — back it up

`create-leafmesh` put a `LEAFMESH_VAULT_KEY` in your `.env` when it made this project. It is the master key that encrypts every connection and credential you store in the vault (in Redis / Postgres).

- **Back it up like a master password.** Lose it and every stored connection has to be entered again.
- **Never change or regenerate it** for an existing project — a new key locks the existing vault. To change it, use `leafmesh vault rotate-key`.
- Every copy of the app (every replica) must get the **same** value. Docker Compose passes it in from `.env` as an environment variable.
- Never commit `.env` (it is already in `.gitignore`).
