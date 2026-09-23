# ProofFlow implementation and verification plan

Task source: https://docs.google.com/document/d/1Z4faOPlT1t6NMCuJSKKB8-vkZ2LVzGMR0PO9rtZgSnM/edit

1. First working increment: 2546b84, committed 23 September 2026 14:00:01 UTC+5;
   remote confirmed at approximately 14:00:06. Seven baseline tests passed.
   This timestamp is recorded accurately, not represented as before 14:00.
   Second-hour backend checkpoint: new task-specific algorithm, synthetic
   fixtures, local API/storage/exports and 26 passing baseline/API/engine
   tests at 14:48 UTC+5. Import and frontend integration are still in progress;
   this checkpoint must not be described as the final product.
2. Full calculation engine, partner import and purchasing workbench in parallel.
3. Integrate upload -> filter -> calculate -> explain -> adjust -> approve -> export.
4. Verify each must-have independently, including seasonal versus flat series,
   sustained trend, stockout compensation, isolated client spikes, and inbound ETA.
5. Verify actual IEK/Systeme import locally and document missing source fields.
6. Test clean install, API, runtime UI, exports, persisted approvals, invalid input.
7. Prepare README, methodology, sample templates and repeatable demo.
8. Final verified commit and remote confirmation before official freeze.

Internal push targets: 14:50, 15:50, 16:50 and 17:40 (UTC+5), contingent on
confirmed official schedule. Each checkpoint includes a real tested increment.

No automated supplier sending. Partner files remain local. Any synthetic examples
and reconstructed monthly data must be identified as such. Main functionality
is written during the competition in this repository.
