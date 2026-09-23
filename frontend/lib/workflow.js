import { state } from "./state.js";
import { $ } from "./format.js";
import { t } from "../i18n.js";

// UI progress is distinct from supplier order transmission (never automatic).
export function workflowPosition(snapshot) {
  if (snapshot.exported && snapshot.approval) return 6;
  if (snapshot.approval) return 5;
  if (snapshot.result && snapshot.approvalOpen) return 4;
  if (snapshot.result) return 3;
  if (snapshot.dataset) return 1;
  return 0;
}

export function renderWorkflow() {
  const keys = ["stepData", "stepCalculate", "stepRecommendations", "stepReview", "stepApprove", "stepExport"];
  const position = workflowPosition(state);
  const list = $("#workflow-steps");
  list.setAttribute("aria-label", t("workflow"));
  list.innerHTML = keys.map((key, index) => `<li class="workflow-step ${index < position ? "complete" : index === position ? "current" : "pending"}"${index === position ? ' aria-current="step"' : ""}><span class="step-number" aria-hidden="true">${index < position ? '<span class="ph-icon" style="--icon:url(\'/static/assets/icons/check-circle-regular.svg\')"></span>' : index + 1}</span><span>${t(key)}</span></li>`).join("");
}
