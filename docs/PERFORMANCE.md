# Performance and security evidence

This is a measured engineering note, **not** a promise of a contest score or a
production-service SLA. The partner's raw files and any customer identifiers
must remain local and outside Git.

## Repeatable synthetic scale check

Run from this repository in the installed virtual environment:

```powershell
$env:PROOFFLOW_PERF_BENCH = '1'
.\.venv\Scripts\python.exe -m pytest -q -s tests\test_security_performance.py -k 250k
```

On 23 September 2026, one local Windows/Python 3.14 run of
`engine.calculate` processed **250,000 synthetic transaction rows, 2,500
products, 25 suppliers** in **2.065 seconds**. The test validates output
counts; it does not impose a machine-dependent time limit. Input generation,
JSON parsing, partner-file import, SQLite persistence, HTTP transfer and
browser rendering are **not** included in that number. The synthetic shape is
100 consecutive daily sales per product, and therefore does not represent
every partner-data skew. Run `python scripts/benchmark.py <local files>` for
end-to-end import-plus-calculation timing after the importer is integrated; do
not print or commit raw partner records.

The calculation groups transactions by `(warehouse, sku)`, then processes each
product. Result persistence keeps heavy per-product chart details in separate
SQLite rows while the run list returns compact summaries. The UI preview omits
the complete sales archive. These choices limit repeated browser transfers,
but total memory and first import time still need measurement against the
actual supplied spreadsheets.

## Checks executed

`python -m pytest -q tests/test_security_performance.py`: **4 passed**, plus
one opt-in benchmark test skipped by default (9 formula-injection and quantity
subcases). The tests verify:

- CSV and XLSX escape text beginning with `=`, `+`, `-`, `@`, including leading
  whitespace. XLSX cells remain strings rather than formulas.
- Approval rejects a negative or excessive quantity, unknown position, and
  nonnumeric `NaN` payload. Recommendations remain unchanged after a manual
  approved quantity; export stays marked draft before human approval.
- Top-level unknown fields are rejected and a cross-origin write with an
  explicit foreign `Origin` receives HTTP 403.

## Security limitations / required deployment posture

1. **Single-user local application, no authentication.** `server.py` binds to
   `127.0.0.1` by default. `Dockerfile` instead binds `0.0.0.0`; exposing its
   port on a LAN or the internet would make all imported sales and approvals
   reachable without authentication. Bind Docker's published port to localhost
   (e.g. `-p 127.0.0.1:8000:8000`) and never expose it publicly without an
   authentication and access-control layer. Docker build/run was not verified
   on this host.
2. **Origin is defense in depth, not authentication.** Foreign explicit
   `Origin` is blocked, but requests with no `Origin` are accepted. A remote
   process that can reach the service can read or write; DNS rebinding and
   proxy/network exposure need host-header validation or a stronger trust
   boundary. Do not claim a production-ready CSRF defense.
3. **Computational input limits are incomplete.** Upload bytes are capped at
   80 MiB, but `/api/calculate` accepts arbitrary JSON and engine settings such
   as review/lead/safety days have no safe upper bound. A deliberately huge
   horizon or historical span can consume CPU/memory. Apply size/horizon limits
   before any network-facing deployment.
4. **Privacy depends on import normalization.** The API accepts canonical
   `client_id` values and excluded-event details may echo them. Actual
   partner-source import must map only anonymous or pseudonymized IDs; never
   expose raw client names or send source records to external AI services.
5. **ZIP parsing is pending audit.** Once `importer.py` is integrated, verify
   archive member count, decompressed-size and compression-ratio limits,
   path traversal rejection, nested ZIP policy and workbook parser behavior.
   An 80 MiB compressed-file limit alone does not prevent ZIP bombs.

The two locally provided partner archives were inspected by metadata only,
without printing source rows: each has 7 members, the largest member
compression ratio is about 1.2:1, and no absolute or `..` member path was
observed. This does **not** prove that the general upload parser rejects a
malicious archive; that separate parser audit remains necessary.

The calculation outputs drafts; no supplier-send endpoint is present. Human
approval is required before the export is labelled approved, and even an
approved export is a file for controlled manual handling, not transmission.
