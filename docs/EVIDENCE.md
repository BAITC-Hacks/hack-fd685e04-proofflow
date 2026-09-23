# Decision evidence report

`evidence.build_evidence(run)` builds a local JSON report from one saved
calculation and its optional approval. It preserves the distinction between
the original recommendation and the manager's final quantities. It does not
place or send an order.

The report contains source label and synthetic flag, calculation locale,
allowlisted settings and filters, warning counts, line-level quantity changes,
supplier totals, and reconciliation against the original stored summary,
supplier groups and known-price line amounts. A reconciliation can be `pass`,
`fail`, or `partial` when original comparison fields were not recorded.
After approval, stored summaries remain recommendation summaries; approved
totals are calculated separately. A malformed approval with missing/extra
positions or duplicate warehouse/SKU rows is rejected.

All quantities and monetary amounts are decimal strings. Line amounts use
decimal multiplication with half-up rounding to cents before aggregation,
matching the export policy. Missing prices are `null`, never an asserted zero;
`known_amount` excludes unknown-price positions, with their counts and
quantities reported separately. An explicitly known zero price is valid.
No currency conversion is performed; the contract does not identify currency,
so `currency` is null. Quantity sums may include different units and are only
reconciliation figures, not interchangeable physical inventory.

Customer identifiers, raw excluded events, history and reviewer names are not
included. Only event counts are reported. The report is a decision summary,
not a replacement for the locally retained source records or methodology.

`fingerprint_sha256` hashes UTF-8 JSON of the entire report except that field,
using sorted object keys, compact separators and unescaped Unicode. It detects
changes if compared to a separately retained trusted fingerprint. It is not a
signature, immutable ledger, proof of authorship or proof that input data is
true: someone able to alter a report can recompute its fingerprint.

Verification: `python -m pytest tests/test_evidence.py -q`.
