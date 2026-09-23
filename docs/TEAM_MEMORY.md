# ProofFlow — working memory for this hackathon

This file records the team's decisions and the user's recurring requests; it is
not a substitute for the current official task, rules or judging rubric.

- Team: **ProofFlow**, three registered human participants, all checked in and
  physically at the venue per the captain's confirmation at 16:00 UTC+5.
  One teammate owns frontend work/commits; Codex and its subagents are tools,
  not registered team members.
- Official competition repository: `BAITC-Hacks/hack-fd685e04-proofflow`.
  Develop and push the competition solution here. The older TransClaim project
  is prior work, not the submission or a source of ready-made core functionality.
- Task: Электрокомплект supplier replenishment recommendations from sales,
  on-hand inventory, expected receipts, category policy and demand changes.
  Deliver a usable, fast, explainable workflow, not a decorative prototype.
- Required behaviors: seasonality and sustained growth; compensation for demand
  hidden by stockouts; isolation of one-off unusually large/customer orders;
  supplier-grouped purchase lines and per-item explanations. Test that changing
  each relevant input actually changes output in the expected direction.
- User prioritizes correctness, optimization, performance and production-minded
  implementation. Inspect real partner materials and state missing fields or
  assumptions explicitly; never fabricate client identities, stockout dates,
  lead times, results, scores or legal claims.
- Keep the user informed about the project's actual features, architecture,
  measured progress and remaining gaps. Backend/data logic takes priority;
  resume dedicated frontend work only after the functional base is integrated
  and verified. This sequencing was explicitly requested at ~14:35 UTC+5.
- The user additionally prioritizes low resource/token consumption, high
  throughput, integration-friendly APIs, meaningful AI rather than decorative
  claims, a polished frontend and a compelling competitive demo. Differentiate
  with measured performance, evidence/assumption labels and scenario comparison
  if time permits after all mandatory criteria are tested. Do not send partner
  source data to an external generative service without authorization.
- Workflow: import or synthetic demo → inspect data and warnings → configure
  policy/lead time → calculate → review/edit quantities → human approval → export.
  No automatic supplier dispatch or unnecessary admin panel.
- Keep partner data, credentials and private runtime data local and out of Git.
  A clean evaluator run must not require the participant's private AI credits.
- Prove progress each hour and push early enough to confirm remote state.
  The first working commit `2546b84` reached the remote at about 14:00:06
  UTC+5 on 23 September 2026; do not describe it as before 14:00.
- Final delivery requires a verified README, tests, realistic end-to-end demo,
  security/privacy checks, official-repo push and submission through the event
  platform before the organizer's freeze. A Git push alone is not submission.
- At 15:19 UTC+5 the user requested a fully working project by 17:00, leaving
  approximately one hour for adversarial checks and platform submission before
  the provisional 18:00 freeze. Reassign freed agent capacity to concrete
  independent tasks; root alone integrates and pushes.
- Aim to satisfy every current criterion. **Do not promise 100/100**: the actual
  score belongs to the judges, and this file cannot override the official rubric.

Decision hierarchy: latest organizer notice and task-specific rubric → task
statement → current participation rules → repository instructions → this memory.
