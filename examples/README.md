# quote-to-cash — example scenarios

Four realistic scenarios that exercise the major paths through the pod —
from an RFQ all the way to cash.

## How to run

```bash
python examples/run_examples.py                 # all scenarios
python examples/run_examples.py 01_             # one scenario (substring match)
```

> Needs Tier 1 in `.env` (license + model keys + Redis) — the whole LLM
> chain runs day-0 against the seeded price book / invoice store, no
> connector required.

## Scenario map

- **01_rfq_rep_selfapprove** — `rep_initiated` — a small, healthy, low-discount
  deal. Cass prices it from the price book; the approval matrix routes it to the
  sales rep's own self-approval tier → drafter → issuer.
- **02_rfq_deep_discount_cfo** — `rfq_email` — a large deal with a deep discount
  ask. The pricing floor recomputes a below-floor margin / >30% discount, so the
  matrix FORCES the CFO tier deterministically — the model cannot dodge it.
- **03_quote_accepted_invoice** — `quote_accepted` — the customer accepted; billing
  raises the invoice. The atomic claim means one billing copy wins the single job.
- **04_dunning_sweep** — `dunning_sweep` — the overdue backlog. Billing fans out
  across `instances`; each copy atomically claims a DISJOINT batch and duns it.
  Severely overdue accounts escalate to the RevOps Lead.

## Audit trail

Every scenario appends hash-chained entries to `logs/qtc_audit.jsonl`. Tail it
during a run to watch the ledger build up. On an approved deal the issuer also
renders the real quote artifact to `out/<quote_id>.pdf` (or `.md`).
