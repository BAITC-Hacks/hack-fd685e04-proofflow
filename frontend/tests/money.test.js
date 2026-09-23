import assert from "node:assert/strict";
import test from "node:test";
import { lineMoneyCents, roundedLineAmount, sumRoundedAmounts } from "../lib/money.js";
import { workflowPosition } from "../lib/workflow.js";

test("HALF_UP rounds each line before calculating the purchase total", () => {
  const rows = [roundedLineAmount(1, 2.675), roundedLineAmount(1, 2.675)];
  assert.deepEqual(rows, [2.68, 2.68]);
  assert.equal(sumRoundedAmounts(rows), 5.36);
});

test("decimal quantities, exact ties and scientific prices match Decimal semantics", () => {
  assert.equal(roundedLineAmount(1, 1.005), 1.01);
  assert.equal(roundedLineAmount(0.1, 0.05), 0.01);
  assert.equal(roundedLineAmount(1000, 1e-5), 0.01);
  assert.equal(lineMoneyCents("123456789", "0.001"), 12345679n);
});

test("quantity edits add and subtract rounded monetary amounts", () => {
  assert.equal(sumRoundedAmounts([5.36, -2.68]), 2.68);
  assert.equal(sumRoundedAmounts(Array(100).fill(0.01)), 1);
  assert.throws(() => lineMoneyCents("not money", 1), RangeError);
});

test("exporting a draft cannot imply a manager approved it", () => {
  assert.equal(workflowPosition({ dataset: {}, result: {}, exported: true }), 3);
  assert.equal(workflowPosition({ approval: {}, exported: true }), 6);
  assert.equal(workflowPosition({ result: {}, approvalOpen: true }), 4);
});
