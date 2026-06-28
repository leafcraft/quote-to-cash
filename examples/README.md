# quote-to-cash — example scenarios

Four realistic scenarios that exercise the major paths through this mesh.

## How to run

```bash
python examples/run_examples.py                 # all scenarios
python examples/run_examples.py 01_             # one scenario (substring match)
```

## Scenario map

- **01_rfq_standard** — `rep_initiated` — Sales rep files a standard RFQ — line items, target close. Routes through cost calc → discount policy (tier-1) → deal-desk approval.
- **02_steep_discount_finance** — `rep_initiated` — Rep proposes 28% discount — triggers tier-3 path → finance_approver_human. Requires rationale.
- **03_competitor_price_change** — `competitor_price_change` — Competitor cut prices — discount tier matrix is refreshed.
- **04_renewal_uplift_bundle** — `renewal_uplift_bundle` — Renewal up for quote — bundle_recommender proposes adding a complementary product + tier bump.

## Audit trail

Every scenario appends one hash-chained entry to the template's
`logs/<audit>.jsonl` file. Tail it during a run to see the
ledger build up across scenarios.
