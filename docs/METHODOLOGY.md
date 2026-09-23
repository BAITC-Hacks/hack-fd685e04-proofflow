# ProofFlow calculation methodology (provisional)

This is the reproducible calculation policy implemented by `engine.calculate`.
It is a task-specific deterministic prototype, not an approved purchasing
policy. Settings and heuristic thresholds are visible/editable. All generated
orders are drafts for human approval; nothing is sent to suppliers.

## Inputs and data boundaries

The engine takes the canonical JSON shape in `CONTRACT.md`. Dates are ISO
calendar dates. Sales are aggregated to SKU + warehouse + day; client IDs must
be anonymous identifiers. `as_of` is the inventory snapshot date. Sales dated
after it, unknown SKU rows, past inbound receipts, and future stockouts are
reported as warnings rather than silently influencing the forecast. Malformed
dates, non-finite/negative quantities, duplicate SKU/warehouse products and
invalid horizons fail validation. Daily history begins at the first supplied
sale; missing dates within that interval are zero sales.

Monthly partner totals cannot reveal actual transaction dates, client identity,
or stockout intervals. The importer must preserve monthly grain and disclose
any allocation assumption; client-spike and exact stockout compensation are
not claimed as observed facts when source fields do not support them.

## Demand cleaning, lost sales, seasonality and trend

1. A provisional global candidate threshold is
   `max(median * outlier_multiplier, median + 6 * MAD, median + 1 unit)` over
   in-stock daily totals. This only flags candidates; it does not itself remove
   demand.
2. A day is excluded as an isolated client/order spike only when it exceeds
   that threshold, one known anonymous `client_id` or opaque `event_id`
   accounts for at least `spike_client_share`, this customer's/order event's
   quantity is itself unusually high relative to its own other observed
   events, adjacent dates are not also elevated, and no repeated same-month
   peak is observed. The day is replaced with its local seven-day-neighbor
   median; the removed volume and event are returned. An `event_id` is **not**
   called a customer identity. A day with only anonymous aggregate totals,
   multi-day elevated run, or non-dominant single order is retained. These
   conservative rules avoid deleting sustained growth, but can miss genuine
   one-offs; tune only with business validation.
3. Explicit inclusive stockout intervals are censored. Lost demand per day is
   `max(0, same-weekday median of available non-stockout demand - observed
   sales)`. At least three reference dates are required by default; otherwise
   the in-stock global median is used and a warning is emitted. No interval
   means no imputation. This is an estimate, not recorded lost sales.
4. Weekday and month-of-year indices are ratios of historical mean demand to
   the overall in-stock positive-day mean, then normalized. Weekday indices
   require at least 3 observations; month indices require the configurable
   `seasonality_min_observations` (10 by default). Insufficient groups default
   to 1.0, and no positive history yields neutral indices with a warning.
5. A least-squares linear slope over the latest `trend_window_days` (90 by
   default) of adjusted daily history supplies an average projected trend
   multiplier. It is bounded to 0.5–2.0; fewer than 8 usable dates gives 1.0.
   This is a transparent heuristic, not a statistical confidence interval.
6. Forward growth is multiplicative:
   `(1 + product.growth) * (1 + category_policy.growth)`. It is kept separate
   from observed trend. Category policy may also set `safety_days`; otherwise
   the global setting is used.

## Order, inbound, coverage and urgency

For each forecast day from `as_of + 1`, the engine multiplies the fitted demand
level by trend, seasonal date index, and forward growth. Planning horizon is
`lead_days + review_days + safety_days` (at least one day). Recommended units:

```text
net_need = max over every forecast day t of
           max(0, cumulative demand through t - on_hand
                  - cumulative inbound quantity whose ETA <= t)
rounded_order = ceil(max(net_need, MOQ) / pack_size) * pack_size
```

Zero net need remains zero (it does not trigger MOQ). The maximum dated
shortfall prevents a large *late* receipt from hiding an earlier stockout,
which the simple end-horizon balance would miss. Every inbound receipt is
added to simulated inventory on its ETA; late receipts are never credited
before arrival. This draft quantity assumes the new order arrives according
to `lead_days`; if projected depletion is sooner, an emergency action may
still be necessary. `stockout_date` is the first simulated day inventory becomes
negative without a new order. `critical` means that day falls on/before the
supplier lead-time boundary; `high` means later within the simulated horizon;
otherwise a positive order is `normal`, and a zero order is `covered`. This is
an urgency heuristic, not an automatic expedite order.

## Response fields and explanations

`history` is aggregated to the most recent 36 calendar months per item to
bound UI/SQLite size. Its entries expose month-start `date`, `period`, `days`,
`quantity` (adjusted monthly total), `raw_quantity`, `adjusted_quantity`,
`lost_demand`, `excluded_quantity`, and stockout/exclusion flags. Detailed
calculation still uses the full in-memory daily history. `forecast` entries
expose `date`, `quantity` and `demand` (same
forecast units) plus the applied seasonal factor. `lost_demand` at row level is
the cumulative imputed units over the history; `excluded_quantity` is the
cumulative anomaly volume removed. `inbound_quantity` counts receipts arriving
by the end of this row's planning horizon. Explanations and breakdowns carry
the actual inputs, component factors, dates and rounding that produced the
recommendation. `supplier_groups` contains compact supplier subtotals only;
each SKU appears once in `rows`, avoiding duplicated response payloads.
Missing supplier is visibly grouped as `UNASSIGNED`.

## Provisional defaults

`review_days=14`, `safety_days=7`, `outlier_multiplier=4`,
`spike_client_share=0.60`, `stockout_min_reference_days=3`,
`seasonality_min_observations=10`, and `trend_window_days=90` are explicit
engineering defaults from `engine.DEFAULT_SETTINGS`, not requirements stated
by the task owner. Validate lead times, order calendar, service levels,
substitutions, returns, MOQ enforcement, and seasonal treatment with
Электрокомплект before operational use.
