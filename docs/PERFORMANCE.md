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
every partner-data skew.

## Local partner-file import and calculation

On 23 September 2026, `scripts/benchmark.py` was run against the two provided
local partner directories, after the document-spike handling update. The
aggregate-only report showed **3,588 SKU**, **248,467 positive sales rows**,
**313 inbound rows**, **161 suggested order lines**, **527 warnings** and
**858 excluded one-off events**. Of these, **517 SKU** require manual review
of document-linked exclusions; a document number is not a customer ID.

| Stage | One local run |
| --- | ---: |
| XLSX import and normalization | 16.319 s |
| Deterministic calculation | 7.580 s |
| Total | 23.899 s |

The timing excludes SQLite persistence, HTTP upload/response and browser
rendering. It is a **single workstation observation**, not an SLA or a
cross-platform benchmark. Missing client IDs, exact stockout periods and
confirmed supplier lead times limit what this real-data run can prove. The
warnings and event flags are work for the purchasing manager, not evidence
that all 161 lines are production-ready. Reproduce locally with
`.\.venv\Scripts\python.exe scripts/benchmark.py <IEK-dir> <Systeme-dir>`;
never print or commit source rows.

The calculation groups transactions by `(warehouse, sku)`, then processes each
product. Result persistence keeps heavy per-product chart details in separate
SQLite rows while the run list returns compact summaries. The UI preview omits
the complete sales archive. These choices limit repeated browser transfers,
but the benchmark above does not measure peak memory or full HTTP/UI latency.

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
2. **Origin and Host checks are defense in depth, not authentication.** Foreign
   explicit `Origin` is blocked for writes, and the HTTP middleware accepts only
   localhost/TestClient Host names. Requests without `Origin` are accepted, so
   a process that can reach a deliberately exposed service is still a risk.
   These checks do not make a network-facing deployment safe; use a stronger
   trust boundary before exposing the service. Do not claim a production-ready
   CSRF defense.
3. **Computational limits are bounded, not a public-service guarantee.** HTTP
   upload totals are capped at 80 MiB. The engine enforces a 730-day planning
   horizon, up to 50,000 products, 2 million sales, 100,000 stockout records,
   2 million inbound rows and bounded history/stockout expansion. A direct
   JSON request can still consume substantial CPU/memory within those limits;
   add authentication, per-user quotas and request-body limits before any
   network-facing deployment.
4. **Raw identifiers are pseudonymized at the HTTP and importer boundaries.**
   Incoming `client_id` and `event_id` values are replaced with per-operation
   HMAC tokens before storage, calculation and detail response; the key is not
   persisted. This is not a substitute for source anonymization or access
   control. `engine.calculate` called directly by another Python program is a
   lower-level function and expects anonymized identifiers from its caller.
   Never upload client names or partner source rows to an external AI service.
5. **Archive bounds exist, but require hostile-file review before public use.**
   The ZIP adapter limits member count, individual/aggregate expanded bytes,
   compression ratio and selected workbooks, and writes selected basenames
   under a temporary directory. XLSX internal expanded size is also bounded.
   Parser resource exhaustion and unusual archive encodings still merit
   adversarial tests; a local pilot should not imply arbitrary untrusted
   upload safety.

The two locally provided partner archives were inspected by metadata only,
without printing source rows: each has 7 members, the largest member
compression ratio is about 1.2:1, and no absolute or `..` member path was
observed. That does **not** prove the general upload parser is safe against
every malicious archive.

The calculation outputs drafts; no supplier-send endpoint is present. Human
approval is required before the export is labelled approved, and even an
approved export is a file for controlled manual handling, not transmission.
