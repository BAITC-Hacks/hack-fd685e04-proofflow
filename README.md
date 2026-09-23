# ProofFlow — replenishment for Электрокомплект

Competition repository for the ProofFlow team. Task: calculate explainable supplier
order recommendations from sales, inventory and inbound receipts.

First-hour increment: executable deterministic baseline, isolated spike handling,
growth, stock/inbound subtraction, pack rounding and human-review status.

Run with Python 3.11+ (no dependencies for this increment):

```sh
python procurement.py
python -m unittest discover -s tests -v
```

The demo uses explicitly synthetic data. No TransClaim product code or partner
raw data has been copied. The program never sends orders to suppliers.

Methodology: daily median/MAD-based provisional spike replacement; cleaned mean
demand times lead time plus review period, minus available stock and confirmed
inbound within that horizon, clamped to zero and rounded up to pack size.

Still in development: full seasonal/trend estimation, stockout compensation,
client-level spike detection, category inputs, dated receipts, Excel import,
supplier-grouped dashboard, editing/approval and export. This first increment
does not claim complete compliance with all task requirements.
