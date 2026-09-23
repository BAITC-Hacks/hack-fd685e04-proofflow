# ProofFlow procurement — competition development

Official repository for team ProofFlow and the Электрокомплект replenishment task.
Read `docs/TEAM_MEMORY.md` for the user's persistent priorities and decisions;
official rules and the current task always take precedence.
Implement task-specific code here; do not copy the TransClaim application.
Root integrates and commits/pushes. Agents own disjoint files assigned by root.
Never commit raw partner archives, real client names, secrets, or runtime data.
Synthetic fixtures must be labelled. Orders are recommendations requiring an
explicit human approval; the application must never automatically send orders.
All quantities must be calculated deterministically. Explanations must reflect
actual calculation inputs. Test each requirement and document real limitations.
The first working increment is 2546b84 (7 passing unittest cases).

Use `docs/CONTRACT.md` for integration. Root owns server.py, application storage,
requirements, README and release integration. Communicate before editing files
assigned to another agent. Do not run git add/commit/push from a subagent.
