# Integration contract — 23 September 2026

## Canonical input

JSON object: `as_of` (ISO date), `products`, `sales`, `stockouts`, `inbound`,
`category_policies`, `settings`, `metadata`.

- products: sku, name, supplier, category, warehouse, unit, on_hand,
  lead_days, moq (default 0), pack_size (default 1), unit_price (default 0),
  growth (default 0; fractional forward uplift).
- sales: date (ISO date), sku, warehouse, quantity, client_id (anonymous ID only),
  price (optional). Repeated transactions can be aggregated per day and client.
- stockouts: sku, warehouse, start (inclusive ISO date), end (inclusive ISO date).
- inbound: sku, warehouse, quantity, eta (ISO date).
- category_policies: category -> {growth: fractional uplift, safety_days: days}.
- settings: review_days=14, safety_days=7, outlier_multiplier=4; explicit editable
  engineering defaults, not task mandated numbers.
  `locale` is `ru` (default), `kk`, or `en`; it changes engine text only.
- metadata: source_label, synthetic (bool), warnings (list of strings).

Daily input is canonical. If partner inputs are monthly totals, preserve their
aggregation and explicitly disclose any daily allocation assumptions in metadata;
never pretend monthly rows contain real client-level transactions or stockout dates.
Importer should communicate alternative requirements to root before diverging.

## Calculation engine

`engine.py`: `calculate(dataset: dict) -> dict`, no persistence/network/UI.
Return: {as_of, rows, summary, warnings, methodology}.
Each row: sku, name, supplier, category, warehouse, unit, on_hand,
inbound_quantity, lead_days, recommended_quantity, unit_price, amount,
daily_demand, raw_daily_demand, lost_demand, excluded_quantity, excluded_events,
seasonality_factor, trend_factor, growth_factor, coverage_days,
stockout_date (ISO or null), urgency (critical/high/normal/covered),
explanation (string), breakdown (dict), history (list), forecast (list),
warnings (list). Additional explanatory fields are welcome.
Summary: items, suppliers, order_lines, total_amount, critical_items.

## Import

`importer.py`: `import_files(paths: list[str]) -> dict` returns canonical dataset.
Allow JSON/CSV templates plus partner XLSX/ZIP structures if feasible; inspect
schemas before making mappings. Return clear errors for unsupported layouts.
Raw partner files remain local under ignored private_data. No outbound network.

## HTTP API and UI (root implements API, frontend agent implements static UI)

- GET /api/health -> {status, version}
- GET /api/dataset -> {dataset: preview, source_label}
- POST /api/demo -> {dataset: preview, source_label}
- POST /api/import (multipart files) -> {dataset: preview, source_label}
- The preview has `_preview: true`, `_data_ref`, products, settings,
  category_policies and metadata including record_counts. It omits potentially
  large sales/stockout/inbound arrays; those remain in local server storage.
- POST /api/calculate -> body {dataset?: canonical, settings?: object,
  category_policies?: object, filters?: {warehouse?, category?, supplier?}}
  -> calculation result plus run_id. Sending an edited preview in `dataset`
  merges only its products/settings/category_policies onto the matching stored
  dataset, with `_data_ref` guarding against stale edits.
- `supplier_groups` contains supplier/order_lines/total_amount summaries. The
  UI groups the compact `rows` by supplier; rows are not duplicated in groups.
- GET /api/runs/{run_id} -> stored result, decisions.
- GET /api/runs/{run_id}/item?sku=...&warehouse=... -> detailed history,
  forecast and diagnostic fields for one item; list rows stay compact.
- POST /api/runs/{run_id}/approve -> {quantities: {row_key: quantity},
  reviewer: string, acknowledge_missing_inputs?: boolean}; validates quantities
  and records approval; never sends orders. Real runs with unconfirmed stock
  or lead times require explicit acknowledgement, saved with the approval.
  row_key = warehouse + '::' + sku. Return {approval_id, status, approved_at}.
- GET /api/runs/{run_id}/export?format=csv|xlsx -> attachment of visible calculated
  rows, optional supplier query, clearly marks draft versus approved quantities.

Rows include `price_known` and `input_provenance`. Unknown prices/amounts are
blank in exports. `summary.total_amount_complete=false` and
`summary.unpriced_order_lines` distinguish an incomplete budget from a real
zero-value order.

Static frontend in frontend/index.html, app.js, styles.css served at /.
Russian procurement workbench: upload/demo, filters, calculation settings,
supplier groups, explainable rows, editable quantities, approve, export, charts.
Use native browser APIs and local assets; no CDN dependency, no external fonts.
Show task value and real calculations. Errors/loading/empty state must work.
