import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";

const appSource = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const approvalSource = appSource.slice(appSource.indexOf("async function submitApproval("), appSource.indexOf("async function exportRun("));

function approvalHarness() {
  let finish;
  const request = new Promise(resolve => { finish = resolve; });
  const nodes = new Map();
  const state = { result: { run_id: "run-A" }, inputRevision: 0, approval: null, busy: false };
  const context = vm.createContext({
    state,
    $(selector) {
      if (!nodes.has(selector)) nodes.set(selector, { value: "Manager", hidden: true, checked: false, close() {}, focus() {} });
      return nodes.get(selector);
    },
    t: key => key,
    api: () => request,
    resultRows: () => [],
    rowKey: row => row.sku,
    currentQuantity: () => 1,
    setBusy: value => { state.busy = value; },
    renderResult() {}, notify() {},
  });
  vm.runInContext(approvalSource, context);
  return { state, finish, submit: () => context.submitApproval({ preventDefault() {} }) };
}

test("approval locks mutations and applies only to its original run", async () => {
  const harness = approvalHarness();
  const pending = harness.submit();
  assert.equal(harness.state.busy, true);
  harness.state.result = { run_id: "run-B" };
  harness.finish({ approval_id: "approval-A" });
  await pending;
  assert.equal(harness.state.approval, null);
  assert.equal(harness.state.busy, false);
});

test("changed input revision discards an in-flight approval response", async () => {
  const harness = approvalHarness();
  const pending = harness.submit();
  harness.state.inputRevision += 1;
  harness.finish({ approval_id: "approval-A" });
  await pending;
  assert.equal(harness.state.approval, null);
  assert.equal(harness.state.busy, false);
});

test("matching approval response is applied and releases the busy lock", async () => {
  const harness = approvalHarness();
  const pending = harness.submit();
  harness.finish({ approval_id: "approval-A" });
  await pending;
  assert.equal(harness.state.approval.approval_id, "approval-A");
  assert.equal(harness.state.busy, false);
});
