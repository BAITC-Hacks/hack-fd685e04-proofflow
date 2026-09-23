# ProofFlow — development rules

This is the official competition repository for team ProofFlow's supplier
replenishment solution. The task statement and organizer rules take priority
over this file. See `README.md` for the product and `docs/CONTRACT.md` for the
data/API contract.

- Build and verify the core procurement functionality in this repository.
  Disclose third-party and pre-existing components; do not present an earlier
  product as hackathon work.
- Never commit partner source files, personal data, credentials, runtime
  databases, or private exports. Keep synthetic fixtures clearly labelled.
- Orders remain recommendations until a responsible person reviews and
  approves them. Never send or place supplier orders automatically.
- Keep quantities deterministic and explanations traceable to actual inputs.
  Unknown stock, lead time, customer ID, price, and stockout dates are unknown,
  not observed zeros.
- Run the relevant tests and `scripts/preflight.py` before release. Root
  coordinates integration and performs commit/push; contributors work in
  disjoint areas and report changes before integration.
