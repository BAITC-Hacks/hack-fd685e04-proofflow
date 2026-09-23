import { API, api } from "./lib/api.js";
import { state } from "./lib/state.js";
import { $, $$, escapeHtml, numeric, formatNumber, formatDate, rowKey } from "./lib/format.js";
import { renderDataQuality, urgencyMeta, chartSvg, breakdownMarkup } from "./lib/views.js";
import { i18n, t } from "./i18n.js";
import { renderWorkflow } from "./lib/workflow.js";
import { startIntro } from "./lib/intro.js";
import { roundedLineAmount, sumRoundedAmounts } from "./lib/money.js";

// Workflow orchestration and event bindings; calculations remain on the API.
function notify(message, kind = "success") {
  const region = $("#toast-region");
  if (!region) return;
  window.clearTimeout(state.toastTimer);
  region.innerHTML = `<div class="toast toast-${kind}"><span class="toast-mark" aria-hidden="true">${kind === "error" ? "!" : "✓"}</span><span>${escapeHtml(message)}</span></div>`;
  state.toastTimer = window.setTimeout(() => { region.innerHTML = ""; }, 4600);
}

function showAlert(message, kind = "error") {
  const region = $("#alert-region");
  if (!message) { region.innerHTML = ""; return; }
  region.innerHTML = `<div class="inline-alert inline-alert-${kind}" role="${kind === "error" ? "alert" : "status"}"><span class="alert-mark" aria-hidden="true">${kind === "error" ? "!" : "i"}</span><span>${escapeHtml(message)}</span><button class="icon-button alert-close" type="button" aria-label="${t("close")}">×</button></div>`;
}

function setBusy(busy, message = t("calculating")) {
  state.busy = busy;
  $("main").setAttribute("aria-busy", String(busy));
  $("#operation-status").hidden = !busy;
  $("#operation-message").textContent = message;
  const loading = $("#loading-state");
  loading.hidden = !busy;
  $("#loading-message").textContent = message;
  for (const selector of ["#demo-button", "#upload-button", "#choose-file-button", "#refresh-button", "#calculate-button", "#recalculate-settings", "#export-csv", "#export-xlsx", "#approve-button"]) {
    const button = $(selector);
    if (button) button.disabled = busy || (selector.startsWith("#export") && !state.result);
  }
  updateActionAvailability();
}

function syncCalculationControls() {
  $$("#supplier-groups [data-quantity]").forEach(input => { input.disabled = state.busy || Boolean(state.approval); });
  $$("#products-body input, #category-policies input, #category-policies button, #warehouse-filter, #category-filter, #supplier-filter, #review-days, #policy-review-days, #safety-days, #outlier-multiplier, #add-policy, #language-select").forEach(input => { input.disabled = state.busy; });
}

function uniqueValues(values) {
  return [...new Set((values || []).filter((value) => value !== null && value !== undefined && String(value).trim() !== "").map(String))]
    .sort((a, b) => a.localeCompare(b, "ru"));
}

function setSelectOptions(select, values, allLabel, selected = "") {
  const current = values.includes(selected) ? selected : "";
  select.innerHTML = `<option value="">${escapeHtml(allLabel)}</option>` + values.map((value) =>
    `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(value)}</option>`).join("");
}

function renderDataset() {
  const dataset = state.dataset;
  $("#source-label").textContent = dataset?.metadata?.synthetic === true
    ? t("synthetic")
    : (dataset ? (state.sourceLabel || t("loaded")) : t("noData"));
  $("#source-label").title = dataset?.as_of ? formatDate(dataset.as_of) : "";
  const badges = $("#dataset-badges");
  $("#editor-count").textContent = dataset?.products?.length ? `${formatNumber(dataset.products.length)} SKU` : "";
  renderDataQuality();
  if (!dataset) {
    badges.innerHTML = "";
    renderProducts();
    renderPolicies();
    setSelectOptions($("#warehouse-filter"), [], t("allWarehouses"));
    setSelectOptions($("#category-filter"), [], t("allCategories"));
    setSelectOptions($("#supplier-filter"), [], t("allSuppliers"));
    setSelectOptions($("#export-supplier"), [], t("allSuppliers"));
    $("#calculate-button").disabled = true;
    $("#recalculate-settings").disabled = true;
    return;
  }
  const products = Array.isArray(dataset.products) ? dataset.products : [];
  const metadata = dataset.metadata || {};
  const counts = metadata.record_counts || {};
  const tags = [
    `${formatNumber(products.length)} SKU`,
    `${formatNumber(counts.sales ?? dataset.sales?.length ?? 0)} ${t("sales")}`,
    `${formatNumber(counts.inbound ?? dataset.inbound?.length ?? 0)} ${t("inbound")}`,
  ];
  if (metadata.synthetic === true) tags.push(t("syntheticBadge"));
  badges.innerHTML = tags.map((tag, index) => `<span class="source-badge${index === tags.length - 1 && metadata.synthetic === true ? " synthetic-badge" : ""}">${escapeHtml(tag)}</span>`).join("");
  const warehouses = uniqueValues(products.map((item) => item.warehouse));
  const categories = uniqueValues(products.map((item) => item.category));
  const suppliers = uniqueValues(products.map((item) => item.supplier));
  setSelectOptions($("#warehouse-filter"), warehouses, t("allWarehouses"), $("#warehouse-filter").value);
  setSelectOptions($("#category-filter"), categories, t("allCategories"), $("#category-filter").value);
  setSelectOptions($("#supplier-filter"), suppliers, t("allSuppliers"), $("#supplier-filter").value);
  setSelectOptions($("#export-supplier"), suppliers, t("allSuppliers"), $("#export-supplier").value);
  renderPolicies();
  renderProducts();
  renderWarnings();
  $("#calculate-button").disabled = state.busy || products.length === 0;
  $("#recalculate-settings").disabled = state.busy || products.length === 0;
}

function filteredProductIndexes() {
  const products = state.dataset?.products || [];
  const query = state.productQuery.toLocaleLowerCase("ru");
  if (!query) return products.map((_, index) => index);
  const indexes = [];
  products.forEach((product, index) => {
    if ([product.sku, product.name, product.supplier, product.category, product.warehouse]
      .some((value) => String(value ?? "").toLocaleLowerCase("ru").includes(query))) indexes.push(index);
  });
  return indexes;
}

function renderProducts() {
  const products = state.dataset?.products || [];
  const indexes = filteredProductIndexes();
  const pageSize = 25;
  const pageCount = Math.max(1, Math.ceil(indexes.length / pageSize));
  state.productPage = Math.min(state.productPage, pageCount - 1);
  const pageIndexes = indexes.slice(state.productPage * pageSize, (state.productPage + 1) * pageSize);
  $("#products-empty").hidden = products.length > 0 && indexes.length > 0;
  $("#products-empty").textContent = t(products.length ? "noMatches" : "loadForCalc");
  $("#products-table-wrap").hidden = !pageIndexes.length;
  $("#products-pager").hidden = !pageIndexes.length || pageCount === 1;
  $("#product-range").textContent = products.length ? `${formatNumber(indexes.length)} ${t("of")} ${formatNumber(products.length)}` : "—";
  $("#products-page-label").textContent = `${state.productPage + 1} / ${pageCount}`;
  $("#products-prev").disabled = state.productPage === 0;
  $("#products-next").disabled = state.productPage >= pageCount - 1;
  $("#products-body").innerHTML = pageIndexes.map((index) => {
    const product = products[index];
    const input = (field, value, min, step, label) => {
      const marker = product.provenance?.[field] ?? state.dataset?.metadata?.field_provenance?.[field] ?? state.dataset?.metadata?.provenance?.[field];
      const uncertain = state.dataset?.metadata?.synthetic !== true && ["on_hand", "lead_days"].includes(field) && !["observed", "assumed"].includes(marker);
      return `<label class="visually-hidden" for="product-${field}-${index}">${escapeHtml(label)} · ${escapeHtml(product.sku)}</label><input id="product-${field}-${index}" class="product-input${uncertain ? " unconfirmed-input" : ""}" type="number" min="${min}" step="${step}" value="${escapeHtml(value)}" data-product-index="${index}" data-product-field="${field}"${uncertain ? ` aria-describedby="input-note-${field}-${index}"` : ""}>${uncertain ? `<small class="product-input-note" id="input-note-${field}-${index}">${t("missing")}</small>` : ""}`;
    };
    return `<tr><td><div class="product-cell"><strong>${escapeHtml(product.sku)}</strong><span>${escapeHtml(product.name || t("noName"))}</span></div></td>
      <td><div class="product-cell"><strong>${escapeHtml(product.supplier || t("noSupplier"))}</strong><label class="visually-hidden" for="product-category-${index}">${t("category")} · ${escapeHtml(product.sku)}</label><input id="product-category-${index}" class="product-input product-text-input" value="${escapeHtml(product.category || "")}" data-product-index="${index}" data-product-field="category" placeholder="${t("category")}"></div></td>
      <td>${escapeHtml(product.warehouse || "—")}</td><td>${input("on_hand", product.on_hand ?? 0, 0, "any", t("stock"))}</td>
      <td>${input("lead_days", product.lead_days ?? 0, 0, 1, t("lead"))}</td>
      <td>${input("moq", product.moq ?? 0, 0, "any", t("moq"))}</td>
      <td>${input("growth", product.growth ?? 0, -1, 0.01, t("growthAdjustment"))}</td></tr>`;
  }).join("");
  syncCalculationControls();
}

function renderWarnings() {
  const datasetWarnings = state.dataset?.metadata?.warnings || [];
  const runWarnings = state.result?.warnings || [];
  const all = [...new Set([...datasetWarnings, ...runWarnings].filter(Boolean).map(String))];
  const panel = $("#warning-panel");
  panel.hidden = all.length === 0;
  $("#warning-count").textContent = formatNumber(all.length);
  $("#warning-list").innerHTML = all.slice(0, 12).map((warning) => `<li>${escapeHtml(warning)}</li>`).join("") +
    (all.length > 12 ? `<li>${t("extraWarnings")}: ${formatNumber(all.length - 12)}</li>` : "");
}

function initializeSettings() {
  const settings = state.dataset?.settings || {};
  const reviewDays = settings.review_days ?? 14;
  const safetyDays = settings.safety_days ?? 7;
  const outlier = settings.outlier_multiplier ?? 4;
  $("#review-days").value = reviewDays;
  $("#policy-review-days").value = reviewDays;
  $("#safety-days").value = safetyDays;
  $("#outlier-multiplier").value = outlier;
}

function policyRows() {
  const policies = state.dataset?.category_policies || {};
  const categories = uniqueValues([
    ...(state.dataset?.products || []).map((item) => item.category),
    ...Object.keys(policies),
  ]);
  const defaults = state.dataset?.settings || {};
  return categories.map((category) => ({
    category,
    growth: policies[category]?.growth ?? 0,
    safetyDays: policies[category]?.safety_days ?? defaults.safety_days ?? 7,
  }));
}

function renderPolicies() {
  const container = $("#category-policies");
  if (!container) return;
  const policies = policyRows();
  if (!state.dataset) {
    container.innerHTML = `<p class="muted-copy">${t("loadForCalc")}</p>`;
    return;
  }
  if (!policies.length) {
    container.innerHTML = `<p class="muted-copy">${t("noPolicies")}</p>`;
    return;
  }
  container.innerHTML = `<div class="category-policy-table"><div class="policy-table-head"><span>${t("category")}</span><span>${t("growthAdjustment")}</span><span>${t("safety")}</span><span></span></div>${policies.map((policy) => `
    <div class="policy-row" data-policy-category="${escapeHtml(policy.category)}">
      <strong>${escapeHtml(policy.category)}</strong>
      <label><span class="visually-hidden">${t("growthAdjustment")} · ${escapeHtml(policy.category)}</span><div class="number-with-unit"><input type="number" step="0.01" min="-1" max="10" data-policy-field="growth" value="${escapeHtml(policy.growth)}"><span>${t("fraction")}</span></div></label>
      <label><span class="visually-hidden">${t("safety")} · ${escapeHtml(policy.category)}</span><div class="number-with-unit"><input type="number" step="1" min="0" data-policy-field="safety_days" value="${escapeHtml(policy.safetyDays)}"><span>${t("days")}</span></div></label>
      <button class="icon-button remove-policy" type="button" data-remove-policy="${escapeHtml(policy.category)}" aria-label="${t("removePolicy")} ${escapeHtml(policy.category)}">×</button>
    </div>`).join("")}</div>`;
  syncCalculationControls();
}

function readNumber(selector, label, { minimum = 0, maximum = Number.MAX_SAFE_INTEGER } = {}) {
  const input = $(selector);
  const value = Number(input.value);
  if (!input.value.trim() || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${t("validation")}: ${label} (${formatNumber(minimum, 2)}–${formatNumber(maximum, 2)})`);
  }
  return value;
}

function collectSettings() {
  const review = readNumber("#review-days", t("horizon"));
  const policyReview = readNumber("#policy-review-days", t("review"));
  const settings = {
    locale: i18n.locale,
    review_days: policyReview,
    safety_days: readNumber("#safety-days", t("safety")),
    outlier_multiplier: readNumber("#outlier-multiplier", t("threshold"), { minimum: 1 }),
  };
  // The quick-access horizon and the detailed setting are two views of the same contract field.
  if (review !== policyReview) {
    $("#policy-review-days").value = review;
    settings.review_days = review;
  }
  return settings;
}

function collectPolicies() {
  const policies = {};
  $$(".policy-row").forEach((row) => {
    const category = row.dataset.policyCategory;
    const growth = Number($("[data-policy-field='growth']", row).value);
    const safetyDays = Number($("[data-policy-field='safety_days']", row).value);
    if (!category || !Number.isFinite(growth) || growth < -1 || growth > 10 || !Number.isFinite(safetyDays) || safetyDays < 0) {
      throw new Error(t("policiesInvalid"));
    }
    policies[category] = { growth, safety_days: safetyDays };
  });
  return policies;
}

function activeFilters() {
  return {
    warehouse: $("#warehouse-filter").value || null,
    category: $("#category-filter").value || null,
    supplier: $("#supplier-filter").value || null,
  };
}

function syncHorizonInputs(source) {
  const value = source.value;
  if (source.id === "review-days") $("#policy-review-days").value = value;
  else if (source.id === "policy-review-days") $("#review-days").value = value;
}

async function calculate() {
  if (state.busy) return;
  if (!state.dataset) { showAlert(t("emptyHelp")); return; }
  showAlert("");
  let settings;
  let categoryPolicies;
  try {
    settings = collectSettings();
    categoryPolicies = collectPolicies();
  } catch (error) {
    showAlert(error.message);
    return;
  }
  setBusy(true, t("calculating"));
  const inputRevision = state.inputRevision;
  try {
    const result = await api("/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset: state.dataset, settings, category_policies: categoryPolicies, filters: activeFilters() }),
    });
    if (inputRevision !== state.inputRevision) {
      showAlert(t("staleCalculation"), "info");
      return;
    }
    state.result = result;
    state.exported = false;
    state.approvalOpen = false;
    state.edits = new Map();
    state.approval = result.approval || null;
    state.rowsByKey = new Map((result.rows || []).map((row) => [rowKey(row), row]));
    renderResult();
    renderWarnings();
    const rows = result.rows?.length || 0;
    notify(t(rows ? "calculationReady" : "emptyFilters"), rows ? "success" : "info");
  } catch (error) {
    showAlert(error.message || t("requestError"));
  } finally {
    setBusy(false);
    if (state.result) updateActionAvailability();
  }
}

async function loadDatasetResponse(response) {
  state.inputRevision += 1;
  state.dataset = response.dataset || null;
  state.sourceLabel = response.source_label || state.dataset?.metadata?.source_label || "Загруженные данные";
  state.result = null;
  state.exported = false;
  state.approvalOpen = false;
  state.edits = new Map();
  state.approval = null;
  state.rowsByKey.clear();
  state.supplierPages.clear();
  state.productPage = 0;
  state.productQuery = "";
  state.orderQuery = "";
  $("#order-search").value = "";
  $("#product-search").value = "";
  initializeSettings();
  renderDataset();
  renderResult();
  renderWarnings();
}

async function loadDemo() {
  if (state.busy) return;
  showAlert("");
  setBusy(true, t("demoLoading"));
  try {
    await loadDatasetResponse(await api("/demo", { method: "POST" }));
    notify(t("demoLoaded"), "success");
  } catch (error) {
    showAlert(error.message || t("requestError"));
  } finally { setBusy(false); }
}

async function importFiles(files) {
  if (state.busy) return;
  const selected = [...(files || [])];
  if (!selected.length) return;
  const body = new FormData();
  selected.forEach((file) => body.append("files", file, file.name));
  showAlert("");
  setBusy(true, `${t("loading")} ${formatNumber(selected.length)}`);
  try {
    await loadDatasetResponse(await api("/import", { method: "POST", body }));
    notify(t("uploadDone"), "success");
  } catch (error) {
    showAlert(error.message || t("requestError"));
  } finally {
    setBusy(false);
    $("#file-input").value = "";
  }
}

async function refreshService() {
  if (state.busy) return;
  showAlert("");
  setBusy(true, t("loading"));
  try {
    await checkHealth();
    await loadDatasetResponse(await api("/dataset"));
    notify(t("refreshDone"), "success");
  } catch (error) {
    showAlert(error.message || t("requestError"));
  } finally { setBusy(false); }
}

function checkHealth() {
  return api("/health").then((health) => {
    $("#api-indicator").classList.add("online");
    $("#api-indicator").classList.remove("offline");
    $("#api-status").textContent = t("serviceReady");
    $("#api-version").textContent = health.version ? `API v${health.version}` : t("local");
  }).catch((error) => {
    $("#api-indicator").classList.remove("online");
    $("#api-indicator").classList.add("offline");
    $("#api-status").textContent = t("serviceOffline");
    $("#api-version").textContent = t("serviceOffline");
    throw error;
  });
}

function currentQuantity(row) {
  const key = rowKey(row);
  if (state.edits.has(key)) return state.edits.get(key);
  if (state.approval?.quantities && key in state.approval.quantities) return Number(state.approval.quantities[key]);
  return numeric(row.recommended_quantity);
}

function lineAmount(row, quantity = currentQuantity(row)) {
  if (!priceKnown(row)) return 0;
  return roundedLineAmount(quantity, numeric(row.unit_price));
}

function priceKnown(row) {
  return row.price_known !== false && row.unit_price !== null && row.unit_price !== undefined && row.unit_price !== "" && Number.isFinite(Number(row.unit_price));
}

function unpricedCount(rows = resultRows()) {
  return rows.filter(row => currentQuantity(row) > 0 && !priceKnown(row)).length;
}

function displayedTotal(rows, amount) {
  const ordered = rows.filter(row => currentQuantity(row) > 0);
  if (ordered.length && ordered.every(row => !priceKnown(row))) return t("noPrice");
  return unpricedCount(rows) ? `${formatNumber(amount, 2)} *` : formatNumber(amount, 2);
}

function renderBudget() {
  const count = state.edits.size || state.approval ? unpricedCount() : Math.max(unpricedCount(), numeric(state.result?.summary?.unpriced_order_lines));
  setMetric("#metric-total", displayedTotal(resultRows(), state.totalAmount));
  $(".metric-highlight .metric-foot").textContent = count || (state.result?.summary?.total_amount_complete === false && !state.edits.size && !state.approval)
    ? `${t("partialAmount")}: ${formatNumber(count)} ${t("unpriced")}` : t("amountHelp");
}

function resultRows() {
  return Array.isArray(state.result?.rows) ? state.result.rows : [];
}

function visibleResultRows() {
  const query = state.orderQuery.toLocaleLowerCase(i18n.locale);
  return query ? resultRows().filter(row => [row.sku, row.name, row.supplier, row.warehouse, row.category, urgencyMeta(row.urgency).label].some(value => String(value ?? "").toLocaleLowerCase(i18n.locale).includes(query))) : resultRows();
}

function resultTotals() {
  const rows = resultRows();
  return sumRoundedAmounts(rows.map(row => lineAmount(row)));
}

function setMetric(id, value) { $(id).textContent = value; }

function renderSummary() {
  const result = state.result;
  renderSignals();
  $(".metric-highlight .metric-top span").textContent = t(state.approval ? "approved" : "draft");
  if (!result) {
    setMetric("#metric-items", "—");
    setMetric("#metric-suppliers", "—");
    setMetric("#metric-total", "—");
    setMetric("#metric-critical", "—");
    $("#metric-items-foot").textContent = t(state.dataset ? "runForFilters" : "loadForCalc");
    return;
  }
  const summary = result.summary || {};
  const rows = resultRows();
  setMetric("#metric-items", formatNumber(state.orderLineCount));
  setMetric("#metric-suppliers", formatNumber(summary.suppliers ?? uniqueValues(rows.map((row) => row.supplier)).length));
  renderBudget();
  setMetric("#metric-critical", formatNumber(summary.critical_items ?? rows.filter((row) => row.urgency === "critical").length));
  $("#metric-items-foot").textContent = `${formatNumber(summary.items ?? rows.length)} ${t("rows")}`;
}

function renderSignals() {
  const region = $("#decision-signals");
  region.hidden = !state.result;
  if (!state.result) { region.innerHTML = ""; return; }
  const rows = resultRows();
  const counts = [
    ["shield-check", "signalSpikes", rows.filter(row => numeric(row.excluded_quantity) > 0).length],
    ["chart-line-up", "signalStockout", rows.filter(row => numeric(row.lost_demand) > 0).length],
    ["warning-circle", "signalMissing", state.result.source_synthetic === false ? rows.filter(row => ["on_hand", "lead_days"].some(field => !["observed", "assumed"].includes(row.input_provenance?.[field]))).length : 0],
  ];
  region.innerHTML = `<span class="signal-title">${t("signalsHelp")}</span>${counts.map(([icon, label, count]) => `<div class="signal-item"><span class="ph-icon" style="--icon:url('/static/assets/icons/${icon}-duotone.svg')" aria-hidden="true"></span><strong>${formatNumber(count)}</strong><span>${t(label)}</span></div>`).join("")}`;
}

async function explainRow(key) {
  const row = state.rowsByKey.get(key);
  if (!row) return;
  $("#explain-title").textContent = row.name || row.sku || t("sku");
  $("#explain-meta").textContent = [row.sku, row.supplier, row.warehouse].filter(Boolean).join(" · ");
  $("#explain-content").innerHTML = `<div class="loading-state"><span class="spinner" aria-hidden="true"></span><span>${t("loading")}</span></div>`;
  $("#explain-dialog").showModal();
  let detail;
  try {
    const query = new URLSearchParams({ sku: String(row.sku), warehouse: String(row.warehouse) });
    detail = await api(`/runs/${encodeURIComponent(state.result.run_id)}/item?${query}`);
  } catch (error) {
    $("#explain-content").innerHTML = `<p class="inline-alert inline-alert-error">${escapeHtml(error.message || t("requestError"))}</p>`;
    return;
  }
  const warnings = Array.isArray(detail.warnings) ? detail.warnings : [];
  const excluded = Array.isArray(detail.excluded_events) ? detail.excluded_events : [];
  const demand = detail.daily_demand;
  $("#explain-content").innerHTML = `
    <div class="explain-kpis">
      <div><span>${t("dailyDemand")}</span><strong>${escapeHtml(formatNumber(demand, 2))}<small> ${escapeHtml(detail.unit || t("unit"))}</small></strong></div>
      <div><span>${t("coverage")}</span><strong>${escapeHtml(formatNumber(detail.coverage_days, 1))}<small> ${t("daysShort")}</small></strong></div>
      <div><span>${t("excluded")}</span><strong>${escapeHtml(formatNumber(detail.excluded_quantity ?? 0))}</strong></div>
    </div>
    <section class="explain-section"><div class="explain-section-head"><h3>${t("demandChart")}</h3><div class="chart-legend"><span><i class="legend-history"></i>${t("history")}</span><span><i class="legend-forecast"></i>${t("forecast")}</span></div></div>${chartSvg(detail.history, detail.forecast, detail.name || detail.sku || t("demandChart"))}</section>
    <section class="explain-section"><h3>${t("logic")}</h3><p class="explanation-text">${escapeHtml(detail.explanation || t("noExplanation"))}</p>${breakdownMarkup(detail)}</section>
    ${excluded.length ? `<section class="explain-section"><h3>${t("excludedEvents")}</h3><ul class="event-list">${excluded.map((event) => `<li>${escapeHtml(typeof event === "object" ? JSON.stringify(event) : event)}</li>`).join("")}</ul></section>` : ""}
    ${warnings.length ? `<section class="explain-section warning-list"><h3>${t("warnings")}</h3><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></section>` : ""}`;
}

function renderGroup(supplier, rows) {
  const priority = { critical: 0, high: 1, normal: 2, covered: 3 };
  rows = [...rows].sort((a, b) => (priority[a.urgency] ?? 2) - (priority[b.urgency] ?? 2) || String(a.sku).localeCompare(String(b.sku)));
  const total = sumRoundedAmounts(rows.map(row => lineAmount(row)));
  const hasLines = rows.filter((row) => currentQuantity(row) > 0).length;
  const pageSize = 30;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(state.supplierPages.get(supplier) || 0, pageCount - 1);
  const visibleRows = rows.slice(page * pageSize, (page + 1) * pageSize);
  return `<article class="supplier-card panel" data-supplier-card="${escapeHtml(supplier)}">
    <header class="supplier-card-head">
      <div class="supplier-title"><span class="supplier-avatar" aria-hidden="true">${escapeHtml((supplier || "?").trim().slice(0, 1).toUpperCase())}</span><div><h3>${escapeHtml(supplier || t("noSupplier"))}</h3><p><span data-supplier-count>${formatNumber(hasLines)}</span> ${t("orderLines")} <span class="footer-separator">·</span> ${formatNumber(rows.length)} ${t("rows")}</p></div></div>
      <div class="supplier-total"><span>${t(unpricedCount(rows) ? "partialAmount" : (state.orderQuery ? "viewTotal" : (state.approval ? "approved" : "draft")))}</span><strong data-supplier-total>${escapeHtml(displayedTotal(rows, total))}</strong></div>
    </header>
    <div class="table-scroll"><table class="order-table"><thead><tr><th scope="col">${t("sku")}</th><th scope="col">${t("category")}</th><th scope="col">${t("warehouse")}</th><th scope="col">${t("status")}</th><th scope="col" class="numeric-cell">${t("orderQty")}</th><th scope="col" class="numeric-cell">${t("amount")}</th><th scope="col"><span class="visually-hidden">${t("explanation")}</span></th></tr></thead><tbody>
    ${visibleRows.map((row) => {
      const key = rowKey(row), urgency = urgencyMeta(row.urgency), quantity = currentQuantity(row);
      const amount = lineAmount(row, quantity);
      return `<tr data-row="${escapeHtml(key)}">
        <td><div class="product-cell"><strong>${escapeHtml(row.sku || "—")}</strong><span>${escapeHtml(row.name || t("noName"))}</span></div></td>
        <td><span class="category-chip">${escapeHtml(row.category || t("noCategory"))}</span></td>
        <td class="warehouse-cell">${escapeHtml(row.warehouse || "—")}</td>
        <td><span class="urgency urgency-${urgency.key}"><i aria-hidden="true"></i>${escapeHtml(urgency.label)}</span>${row.coverage_days !== null && row.coverage_days !== undefined ? `<small class="coverage-hint">${t("coveredDays")} ${formatNumber(row.coverage_days, 1)} ${t("daysShort")}</small>` : ""}</td>
        <td class="numeric-cell qty-cell" data-label="${t("orderQty")}"><label class="visually-hidden" for="qty-${escapeHtml(key)}">${t("orderQty")} · ${escapeHtml(row.sku || row.name)}</label><div class="qty-input-wrap"><input id="qty-${escapeHtml(key)}" class="qty-input${state.edits.has(key) ? " edited-quantity" : ""}" type="number" min="0" step="any" inputmode="decimal" value="${escapeHtml(quantity)}" data-quantity="${escapeHtml(key)}" ${state.approval ? "disabled" : ""}><span>${escapeHtml(row.unit || t("unit"))}</span></div></td>
        <td class="numeric-cell amount-cell" data-label="${t("amount")}" data-amount>${escapeHtml(priceKnown(row) ? formatNumber(amount, 2) : t("noPrice"))}</td>
        <td><button class="details-button" type="button" data-explain="${escapeHtml(key)}" aria-label="${t("explanation")} · ${escapeHtml(row.sku || row.name)}"><span class="ph-icon" style="--icon:url('/static/assets/icons/info-regular.svg')" aria-hidden="true"></span><span class="mobile-details-label">${t("explanation")}</span></button></td>
      </tr>`;
    }).join("")}</tbody></table></div>
    ${pageCount > 1 ? `<div class="supplier-pager"><button class="button button-quiet button-small" type="button" data-supplier-page="${escapeHtml(supplier)}" data-page="${page - 1}" ${page === 0 ? "disabled" : ""}>${t("back")}</button><span>${page + 1} / ${pageCount} · ${formatNumber(rows.length)} ${t("rows")}</span><button class="button button-quiet button-small" type="button" data-supplier-page="${escapeHtml(supplier)}" data-page="${page + 1}" ${page >= pageCount - 1 ? "disabled" : ""}>${t("next")}</button></div>` : ""}
    <div class="supplier-card-foot"><span>${t("quantityHelp")}${unpricedCount(rows) ? ` · ${formatNumber(unpricedCount(rows))} ${t("unpriced")}` : ""}</span><strong>${t("total")}: <span data-supplier-total>${escapeHtml(displayedTotal(rows, total))}</span></strong></div>
  </article>`;
}

function renderResult() {
  const result = state.result;
  document.body.dataset.stage = result ? "results" : state.dataset ? "ready" : "empty";
  const groups = $("#supplier-groups");
  const empty = $("#orders-empty");
  $("#order-search").disabled = !result || state.busy;
  $("#order-view-count").textContent = result ? `${formatNumber(visibleResultRows().length)} ${t("of")} ${formatNumber(resultRows().length)}` : "";
  if (!result) {
    renderSummary();
    groups.innerHTML = "";
    empty.hidden = false;
    empty.innerHTML = state.dataset
      ? `<div class="empty-art" aria-hidden="true">▤ ↗</div><h3>${t("readyTitle")}</h3><p>${t("readyHelp")}</p>`
      : `<div class="onboarding-icon" aria-hidden="true"><span class="ph-icon" style="--icon:url('/static/assets/icons/package-duotone.svg')"></span></div><h3>${t("onboardingTitle")}</h3><p>${t("onboardingHelp")}</p><div class="onboarding-actions"><button class="button button-primary" type="button" data-action="demo">${t("demo")}</button><button class="button button-outline" type="button" data-action="upload">${t("upload")}</button></div><small>${t("onboardingNote")}</small>`;
    $("#orders-caption").textContent = t(state.dataset ? "readyHelp" : "emptyHelp");
    $("#run-stamp").textContent = t("notCalculated");
    updateActionAvailability();
    return;
  }
  const rows = resultRows();
  state.totalAmount = sumRoundedAmounts(rows.map(row => lineAmount(row)));
  state.orderLineCount = 0;
  state.supplierTotals.clear();
  state.supplierLineCounts.clear();
  rows.forEach((row) => {
    const supplier = row.supplier || t("noSupplier");
    const quantity = currentQuantity(row);
    state.supplierTotals.set(supplier, sumRoundedAmounts([state.supplierTotals.get(supplier) || 0, lineAmount(row, quantity)]));
    if (quantity > 0) {
      state.orderLineCount += 1;
      state.supplierLineCounts.set(supplier, (state.supplierLineCounts.get(supplier) || 0) + 1);
    }
  });
  renderSummary();
  const visibleRows = visibleResultRows();
  if (!visibleRows.length) {
    groups.innerHTML = "";
    empty.hidden = false;
    empty.innerHTML = `<div class="empty-art" aria-hidden="true">⌕</div><h3>${t(state.orderQuery ? "noMatches" : "emptyFilters")}</h3><p>${t(state.orderQuery ? "searchViewHelp" : "changeFilters")}</p>`;
  } else {
    empty.hidden = true;
    const grouped = new Map();
    visibleRows.forEach((row) => {
      const supplier = row.supplier || t("noSupplier");
      if (!grouped.has(supplier)) grouped.set(supplier, []);
      grouped.get(supplier).push(row);
    });
    groups.innerHTML = [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b, "ru"))
      .map(([supplier, supplierRows]) => renderGroup(supplier, supplierRows)).join("");
  }
  const createdAt = result.created_at || result.as_of;
  $("#run-stamp").textContent = createdAt ? `${t("sample")} · ${formatDate(createdAt, Boolean(result.created_at))}` : t("calculationReady");
  const filters = result.filters || activeFilters();
  const applied = Object.entries(filters).filter(([, value]) => value).map(([key, value]) => {
    const labels = { warehouse: t("warehouse"), category: t("category"), supplier: t("supplier") };
    return `${labels[key] || key}: ${value}`;
  });
  $("#orders-caption").textContent = `${formatNumber(rows.length)} ${t("rows")} · ${applied.length ? `${t("filters")}: ${applied.join("; ")}` : t("noFilters")} · ${t(state.approval ? "approved" : "draft")}`;
  updateActionAvailability();
}

function updateActionAvailability() {
  renderWorkflow();
  syncCalculationControls();
  const hasRun = Boolean(state.result?.run_id);
  const unsavedEdits = state.edits.size > 0 && !state.approval;
  $("#edits-notice").hidden = !unsavedEdits;
  $("#edits-count").textContent = t("editsPending").replace("{count}", formatNumber(state.edits.size));
  $("#reset-quantities").disabled = state.busy;
  $("#export-csv").disabled = state.busy || !hasRun || unsavedEdits;
  $("#export-xlsx").disabled = state.busy || !hasRun || unsavedEdits;
  $("#decision-report").disabled = state.busy || !hasRun || unsavedEdits;
  $("#order-search").disabled = state.busy || !hasRun;
  for (const id of ["#export-csv", "#export-xlsx"]) {
    $(id).title = unsavedEdits ? t("approveBeforeExport") : t("exportTitle");
  }
  $("#calculate-button").disabled = state.busy || !state.dataset?.products?.length;
  $("#recalculate-settings").disabled = state.busy || !state.dataset?.products?.length;
  $("#approve-button").disabled = state.busy || !hasRun || Boolean(state.approval) || !resultRows().length;
}

function invalidateResult() {
  state.inputRevision += 1;
  if (!state.result) return;
  state.result = null;
  state.exported = false;
  state.approvalOpen = false;
  state.approval = null;
  state.edits.clear();
  state.rowsByKey.clear();
  state.supplierPages.clear();
  renderResult();
  renderWarnings();
}

function updateTotalsAfterEdit(row, before, after) {
  const supplier = row.supplier || t("noSupplier");
  const amountDelta = sumRoundedAmounts([lineAmount(row, after), -lineAmount(row, before)]);
  const lineDelta = Number(after > 0) - Number(before > 0);
  state.totalAmount = sumRoundedAmounts([state.totalAmount, amountDelta]);
  state.orderLineCount += lineDelta;
  state.supplierTotals.set(supplier, sumRoundedAmounts([state.supplierTotals.get(supplier) || 0, amountDelta]));
  state.supplierLineCounts.set(supplier, (state.supplierLineCounts.get(supplier) || 0) + lineDelta);
  renderBudget();
  setMetric("#metric-items", formatNumber(state.orderLineCount));
  const card = $$(".supplier-card").find((node) => node.dataset.supplierCard === supplier);
  if (card) {
    const visibleRows = visibleResultRows().filter(item => (item.supplier || t("noSupplier")) === supplier);
    $$('[data-supplier-total]', card).forEach((el) => { el.textContent = displayedTotal(visibleRows, sumRoundedAmounts(visibleRows.map(item => lineAmount(item)))); });
    $("[data-supplier-count]", card).textContent = formatNumber(visibleRows.filter(item => currentQuantity(item) > 0).length);
  }
}

function openApproval() {
  if (state.busy) return;
  if (!state.result?.run_id || !resultRows().length) { notify(t("runForFilters"), "error"); return; }
  const rows = resultRows();
  const filters = state.result.filters || {};
  const applied = Object.entries(filters).filter(([, value]) => value).map(([key, value]) => `${key}: ${value}`);
  $("#approval-preview").innerHTML = `<div><span>${t("runItems")}</span><strong>${formatNumber(rows.length)}</strong></div><div><span>${t("suppliers")}</span><strong>${formatNumber(uniqueValues(rows.map(row => row.supplier)).length)}</strong></div><div><span>${t(unpricedCount() ? "partialAmount" : "draft")}</span><strong>${displayedTotal(rows, resultTotals())}</strong></div><p>${t("approvalScope")}${applied.length ? ` (${escapeHtml(applied.join("; "))})` : ""}</p>`;
  const missing = state.result.source_synthetic === false && rows.some(row => currentQuantity(row) > 0 && ["on_hand", "lead_days"].some(field => !["observed", "assumed"].includes(row.input_provenance?.[field])));
  $("#missing-inputs-label").hidden = !missing;
  $("#acknowledge-missing-inputs").checked = false;
  $("#acknowledge-missing-inputs").required = missing;
  $("#reviewer-name").value = "";
  $("#approval-error").hidden = true;
  $("#approval-error").textContent = "";
  state.approvalOpen = true;
  renderWorkflow();
  $("#approval-dialog").showModal();
}

async function submitApproval(event) {
  event.preventDefault();
  if (!state.result?.run_id || state.approval || state.busy) return;
  const runId = state.result.run_id;
  const revision = state.inputRevision;
  const reviewer = $("#reviewer-name").value.trim();
  if (!reviewer) { $("#reviewer-name").focus(); return; }
  const quantities = Object.fromEntries(resultRows().map((row) => [rowKey(row), currentQuantity(row)]));
  const button = $("#confirm-approval");
  $("#approval-error").hidden = true;
  button.disabled = true;
  button.textContent = t("saving");
  setBusy(true, t("saving"));
  try {
    const approval = await api(`/runs/${encodeURIComponent(runId)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantities, reviewer, acknowledge_missing_inputs: !$("#missing-inputs-label").hidden && $("#acknowledge-missing-inputs").checked }),
    });
    if (state.result?.run_id !== runId || state.inputRevision !== revision) return;
    state.approval = approval;
    $("#approval-dialog").close();
    renderResult();
    notify(t("approvedMessage"), "success");
  } catch (error) {
    if (state.result?.run_id !== runId || state.inputRevision !== revision) return;
    $("#approval-error").textContent = error.message || t("requestError");
    $("#approval-error").hidden = false;
  } finally {
    setBusy(false);
    button.disabled = false;
    button.textContent = t("confirm");
  }
}

async function exportRun(format) {
  if (!state.result?.run_id || state.busy) return;
  const runId = state.result.run_id;
  const supplier = $("#export-supplier").value;
  const query = new URLSearchParams({ format });
  if (supplier) query.set("supplier", supplier);
  showAlert("");
  try {
    const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/export?${query}`);
    if (!response.ok) {
      const type = response.headers.get("content-type") || "";
      const payload = type.includes("json") ? await response.json() : await response.text();
      throw new Error(payload?.detail || payload || `${t("requestError")} (${response.status})`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `proofflow.${format}`;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    if (state.result?.run_id === runId) state.exported = true;
    renderWorkflow();
    notify(`${t("exported")}: ${format.toUpperCase()}${supplier ? ` · ${supplier}` : ""}.`, "success");
  } catch (error) { showAlert(error.message || t("requestError")); }
}

async function downloadDecisionReport() {
  if (!state.result?.run_id) return;
  try {
    const response = await fetch(`${API}/runs/${encodeURIComponent(state.result.run_id)}/evidence`);
    if (!response.ok) throw new Error(t("requestError"));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `proofflow-decision-${state.result.run_id}.json`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify(t("reportSaved"));
  } catch (error) { showAlert(error.message || t("requestError")); }
}

function addPolicyRow() {
  if (!state.dataset) { notify(t("loadForCalc"), "error"); return; }
  const category = window.prompt(t("categoryPrompt"));
  if (!category || !category.trim()) return;
  const normalized = category.trim();
  if (policyRows().some((item) => item.category.toLocaleLowerCase() === normalized.toLocaleLowerCase())) {
    notify(t("existingPolicy"), "info");
    return;
  }
  state.dataset.category_policies = { ...(state.dataset.category_policies || {}), [normalized]: { growth: 0, safety_days: numeric(state.dataset.settings?.safety_days, 0) } };
  renderPolicies();
  invalidateResult();
  notify(`${normalized}: ${t("changed")}`, "success");
}

function bindEvents() {
  $("#language-select").addEventListener("change", event => {
    // Save in-progress category settings before rebuilding translated views.
    try {
      if (state.dataset) state.dataset.category_policies = collectPolicies();
    } catch (error) { event.target.value = i18n.locale; showAlert(error.message); return; }
    i18n.setLocale(event.target.value);
    showAlert("");
    $("#api-status").textContent = t($("#api-indicator").classList.contains("online") ? "serviceReady" : "serviceOffline");
    renderDataset();
    renderResult();
    ["#explain-dialog", "#approval-dialog"].forEach(selector => { if ($(selector).open) $(selector).close(); });
    if (state.result) notify(t("localeRecalculate"), "info");
  });
  $("#theme-toggle").addEventListener("click", () => { i18n.toggleTheme(); renderSummary(); });
  $("#demo-button").addEventListener("click", loadDemo);
  $("#upload-button").addEventListener("click", () => $("#file-input").click());
  $("#choose-file-button").addEventListener("click", () => $("#file-input").click());
  $("#orders-empty").addEventListener("click", (event) => {
    if (state.busy) return;
    if (event.target.closest("[data-action='demo']")) loadDemo();
    if (event.target.closest("[data-action='upload']")) $("#file-input").click();
  });
  $("#file-input").addEventListener("change", (event) => importFiles(event.target.files));
  $("#refresh-button").addEventListener("click", refreshService);
  $("#calculate-button").addEventListener("click", calculate);
  $("#recalculate-settings").addEventListener("click", calculate);
  $("#product-search").addEventListener("input", (event) => {
    state.productQuery = event.target.value.trim();
    state.productPage = 0;
    renderProducts();
  });
  $("#order-search").addEventListener("input", event => {
    state.orderQuery = event.target.value.trim();
    state.supplierPages.clear();
    renderResult();
  });
  $("#reset-quantities").addEventListener("click", () => {
    if (state.approval || state.busy) return;
    state.edits.clear();
    state.exported = false;
    renderResult();
    notify(t("editsReset"), "info");
  });
  $("#products-prev").addEventListener("click", () => { state.productPage -= 1; renderProducts(); });
  $("#products-next").addEventListener("click", () => { state.productPage += 1; renderProducts(); });
  $("#products-body").addEventListener("change", (event) => {
    const input = event.target.closest("[data-product-index]");
    if (!input || !state.dataset) return;
    const index = Number(input.dataset.productIndex), field = input.dataset.productField;
    const product = state.dataset.products[index];
    if (!product || !["on_hand", "lead_days", "moq", "growth", "category"].includes(field)) return;
    let value = input.value.trim();
    if (field !== "category") {
      value = Number(value);
      const min = field === "growth" ? -1 : 0;
      if (!input.value.trim() || !Number.isFinite(value) || value < min || value > 1e12 || (field === "lead_days" && !Number.isInteger(value))) {
        input.value = product[field] ?? 0;
        notify(t("invalidProduct"), "error");
        return;
      }
    }
    product[field] = value;
    if (["on_hand", "lead_days"].includes(field)) product.provenance = { ...(product.provenance || {}), [field]: "assumed" };
    input.classList.remove("unconfirmed-input");
    const note = document.getElementById(`input-note-${field}-${index}`);
    if (note) note.textContent = t("assumed");
    renderDataQuality();
    invalidateResult();
    notify(t("changed"), "info");
  });
  $("#review-days").addEventListener("change", (event) => syncHorizonInputs(event.target));
  $("#policy-review-days").addEventListener("change", (event) => syncHorizonInputs(event.target));
  ["#review-days", "#policy-review-days", "#safety-days", "#outlier-multiplier", "#warehouse-filter", "#category-filter", "#supplier-filter"].forEach((selector) => {
    $(selector).addEventListener("change", invalidateResult);
  });
  $("#add-policy").addEventListener("click", addPolicyRow);
  $("#category-policies").addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-policy]");
    if (!button) return;
    const category = button.dataset.removePolicy;
    const policies = { ...(state.dataset?.category_policies || {}) };
    delete policies[category];
    if (state.dataset) state.dataset.category_policies = policies;
    renderPolicies();
    invalidateResult();
    notify(`${category}: ${t("changed")}`, "info");
  });
  $("#category-policies").addEventListener("change", (event) => {
    if (event.target.closest("[data-policy-field]")) invalidateResult();
  });
  $("#supplier-groups").addEventListener("click", (event) => {
    const pager = event.target.closest("[data-supplier-page]");
    if (pager) {
      state.supplierPages.set(pager.dataset.supplierPage, Number(pager.dataset.page));
      renderResult();
      return;
    }
    const button = event.target.closest("[data-explain]");
    if (button) explainRow(button.dataset.explain);
  });
  $("#supplier-groups").addEventListener("input", (event) => {
    const input = event.target.closest("[data-quantity]");
    if (!input || state.approval || state.busy) return;
    const quantity = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(quantity) || quantity < 0 || quantity > 1e12) return;
    const key = input.dataset.quantity;
    const row = state.rowsByKey.get(key);
    if (!row) return;
    const before = currentQuantity(row);
    if (quantity === numeric(row.recommended_quantity)) state.edits.delete(key);
    else state.edits.set(key, quantity);
    input.classList.toggle("edited-quantity", state.edits.has(key));
    const tableRow = input.closest("tr");
    if (tableRow) $("[data-amount]", tableRow).textContent = priceKnown(row) ? formatNumber(lineAmount(row, quantity), 2) : t("noPrice");
    updateTotalsAfterEdit(row, before, quantity);
    updateActionAvailability();
  });
  $("#supplier-groups").addEventListener("change", (event) => {
    const input = event.target.closest("[data-quantity]");
    if (!input || state.approval || state.busy) return;
    const quantity = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(quantity) || quantity < 0 || quantity > 1e12) {
      input.value = currentQuantity(state.rowsByKey.get(input.dataset.quantity));
      notify(t("invalidQuantity"), "error");
    }
  });
  $("#export-csv").addEventListener("click", () => exportRun("csv"));
  $("#export-xlsx").addEventListener("click", () => exportRun("xlsx"));
  $("#decision-report").addEventListener("click", downloadDecisionReport);
  $("#approve-button").addEventListener("click", openApproval);
  $("#supplier-filter").addEventListener("change", () => {
    const supplier = $("#supplier-filter").value;
    $("#export-supplier").value = supplier;
  });
  $("#approval-form").addEventListener("submit", submitApproval);
  $("#approval-dialog").addEventListener("close", () => { state.approvalOpen = false; renderWorkflow(); });
  $$('[data-close]').forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.close}`).close()));
  ["#explain-dialog", "#approval-dialog"].forEach((selector) => {
    const dialog = $(selector);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });
  $("#alert-region").addEventListener("click", (event) => {
    if (event.target.closest(".alert-close")) showAlert("");
  });
  $$(".nav-link").forEach((link) => link.addEventListener("click", () => {
    $$(".nav-link").forEach((item) => item.classList.toggle("active", item === link));
    $$(".nav-link").forEach(item => item.setAttribute("aria-current", item === link ? "location" : "false"));
    if (link.getAttribute("href") === "#data-workbench") $("#product-details").open = true;
    if (link.getAttribute("href") === "#policies") $("#policy-details").open = true;
  }));
  const sourceStrip = $("#data-source");
  ["dragenter", "dragover"].forEach((name) => sourceStrip.addEventListener(name, (event) => {
    event.preventDefault(); sourceStrip.classList.add("drag-over");
  }));
  ["dragleave", "drop"].forEach((name) => sourceStrip.addEventListener(name, (event) => {
    event.preventDefault(); sourceStrip.classList.remove("drag-over");
  }));
  sourceStrip.addEventListener("drop", (event) => importFiles(event.dataTransfer?.files));
  window.addEventListener("keydown", (event) => {
    if (document.querySelector("dialog[open]") || $(".app-shell").inert) return;
    if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) && !$("#order-search").disabled) {
      event.preventDefault();
      $("#order-search").focus();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "enter" && !state.busy) calculate();
  });
}

async function init() {
  i18n.apply();
  startIntro();
  bindEvents();
  initializeSettings();
  renderDataset();
  renderResult();
  setBusy(true, t("loading"));
  try {
    await checkHealth();
    const response = await api("/dataset");
    await loadDatasetResponse(response);
  } catch (error) {
    showAlert(`${t("requestError")} ${error.message || ""}`);
  } finally { setBusy(false); }
}

document.addEventListener("DOMContentLoaded", init);
