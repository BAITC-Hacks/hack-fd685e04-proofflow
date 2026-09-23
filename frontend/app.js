(() => {
  "use strict";

  const API = "/api";
  const i18n = window.ProofFlowI18n;
  const t = (key) => i18n.t(key);
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = {
    dataset: null,
    sourceLabel: "Данные ещё не загружены",
    result: null,
    edits: new Map(),
    approval: null,
    busy: false,
    rowsByKey: new Map(),
    toastTimer: null,
    productPage: 0,
    productQuery: "",
    supplierPages: new Map(),
    supplierTotals: new Map(),
    supplierLineCounts: new Map(),
    totalAmount: 0,
    orderLineCount: 0,
  };

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  function numeric(value, fallback = 0) {
    const parsed = typeof value === "number" ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function formatNumber(value, digits = 0) {
    if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "—";
    return new Intl.NumberFormat(i18n.locale === "en" ? "en-GB" : `${i18n.locale}-KZ`, { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(Number(value));
  }

  function formatDate(value, includeTime = false) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat(i18n.locale === "en" ? "en-GB" : `${i18n.locale}-KZ`, includeTime
      ? { dateStyle: "medium", timeStyle: "short" }
      : { day: "numeric", month: "short", year: "numeric" }).format(date);
  }

  function rowKey(row) {
    return `${row.warehouse ?? ""}::${row.sku ?? ""}`;
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, options);
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("json") ? await response.json() : await response.text();
    if (!response.ok) {
      const message = typeof payload === "object" && payload
        ? (payload.detail || payload.message || payload.error)
        : payload;
      throw new Error(message || `Ошибка сервера (${response.status})`);
    }
    return payload;
  }

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
    region.innerHTML = `<div class="inline-alert inline-alert-${kind}" role="${kind === "error" ? "alert" : "status"}"><span class="alert-mark" aria-hidden="true">${kind === "error" ? "!" : "i"}</span><span>${escapeHtml(message)}</span><button class="icon-button alert-close" type="button" aria-label="Скрыть сообщение">×</button></div>`;
  }

  function setBusy(busy, message = t("calculating")) {
    state.busy = busy;
    const loading = $("#loading-state");
    loading.hidden = !busy;
    $("#loading-message").textContent = message;
    for (const selector of ["#demo-button", "#upload-button", "#refresh-button", "#calculate-button", "#recalculate-settings", "#export-csv", "#export-xlsx", "#approve-button"]) {
      const button = $(selector);
      if (button) button.disabled = busy || (selector.startsWith("#export") && !state.result);
    }
    updateActionAvailability();
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
      : (dataset ? t("loaded") : t("noData"));
    const badges = $("#dataset-badges");
    if (!dataset) {
      badges.innerHTML = "";
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
    $("#product-range").textContent = products.length ? `${formatNumber(indexes.length)} из ${formatNumber(products.length)}` : "—";
    $("#products-page-label").textContent = `${state.productPage + 1} / ${pageCount}`;
    $("#products-prev").disabled = state.productPage === 0;
    $("#products-next").disabled = state.productPage >= pageCount - 1;
    $("#products-body").innerHTML = pageIndexes.map((index) => {
      const product = products[index];
      const input = (field, value, min, step, label) => `<label class="visually-hidden" for="product-${field}-${index}">${escapeHtml(label)} для ${escapeHtml(product.sku)}</label><input id="product-${field}-${index}" class="product-input" type="number" min="${min}" step="${step}" value="${escapeHtml(value)}" data-product-index="${index}" data-product-field="${field}">`;
      return `<tr><td><div class="product-cell"><strong>${escapeHtml(product.sku)}</strong><span>${escapeHtml(product.name || "Без наименования")}</span></div></td>
        <td><div class="product-cell"><strong>${escapeHtml(product.supplier || "Поставщик не задан")}</strong><label class="visually-hidden" for="product-category-${index}">Категория для ${escapeHtml(product.sku)}</label><input id="product-category-${index}" class="product-input product-text-input" value="${escapeHtml(product.category || "")}" data-product-index="${index}" data-product-field="category" placeholder="Категория"></div></td>
        <td>${escapeHtml(product.warehouse || "—")}</td><td>${input("on_hand", product.on_hand ?? 0, 0, "any", "Остаток")}</td>
        <td>${input("lead_days", product.lead_days ?? 0, 0, 1, "Срок поставки")}</td>
        <td>${input("moq", product.moq ?? 0, 0, "any", "Минимальная партия")}</td>
        <td>${input("growth", product.growth ?? 0, -1, 0.01, "Поправка роста")}</td></tr>`;
    }).join("");
  }

  function renderWarnings() {
    const datasetWarnings = state.dataset?.metadata?.warnings || [];
    const runWarnings = state.result?.warnings || [];
    const all = [...new Set([...datasetWarnings, ...runWarnings].filter(Boolean).map(String))];
    const panel = $("#warning-panel");
    panel.hidden = all.length === 0;
    $("#warning-list").innerHTML = all.slice(0, 12).map((warning) => `<li>${escapeHtml(warning)}</li>`).join("") +
      (all.length > 12 ? `<li>Ещё ${formatNumber(all.length - 12)} предупреждений в детальных позициях.</li>` : "");
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
      container.innerHTML = '<p class="muted-copy">Загрузите данные, чтобы настроить политики категорий.</p>';
      return;
    }
    if (!policies.length) {
      container.innerHTML = '<p class="muted-copy">В наборе нет категорий для настройки.</p>';
      return;
    }
    container.innerHTML = `<div class="category-policy-table"><div class="policy-table-head"><span>КАТЕГОРИЯ</span><span>ПОПРАВКА РОСТА</span><span>СТРАХОВОЙ ЗАПАС</span><span></span></div>${policies.map((policy) => `
      <div class="policy-row" data-policy-category="${escapeHtml(policy.category)}">
        <strong>${escapeHtml(policy.category)}</strong>
        <label><span class="visually-hidden">Поправка роста для ${escapeHtml(policy.category)}</span><div class="number-with-unit"><input type="number" step="0.01" min="-1" max="10" data-policy-field="growth" value="${escapeHtml(policy.growth)}"><span>доля</span></div></label>
        <label><span class="visually-hidden">Страховой запас для ${escapeHtml(policy.category)}</span><div class="number-with-unit"><input type="number" step="1" min="0" data-policy-field="safety_days" value="${escapeHtml(policy.safetyDays)}"><span>дней</span></div></label>
        <button class="icon-button remove-policy" type="button" data-remove-policy="${escapeHtml(policy.category)}" aria-label="Удалить политику ${escapeHtml(policy.category)}">×</button>
      </div>`).join("")}</div>`;
  }

  function readNumber(selector, label, { minimum = 0, maximum = Number.MAX_SAFE_INTEGER } = {}) {
    const input = $(selector);
    const value = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(value) || value < minimum || value > maximum) {
      throw new Error(`Проверьте параметр «${label}»: значение должно быть от ${formatNumber(minimum, 2)} до ${formatNumber(maximum, 2)}.`);
    }
    return value;
  }

  function collectSettings() {
    const review = readNumber("#review-days", "горизонт заказа");
    const policyReview = readNumber("#policy-review-days", "период пересмотра");
    const settings = {
      locale: i18n.locale,
      review_days: policyReview,
      safety_days: readNumber("#safety-days", "страховой запас"),
      outlier_multiplier: readNumber("#outlier-multiplier", "порог всплеска", { minimum: 1 }),
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
        throw new Error("Проверьте настройки категорий: поправка роста должна быть от −1 до 10, запас — неотрицательным числом.");
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
    if (!state.dataset) { showAlert("Сначала откройте демо-данные или загрузите файлы."); return; }
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
    setBusy(true, "Расчёт потребности по выбранным фильтрам…");
    try {
      const result = await api("/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset: state.dataset, settings, category_policies: categoryPolicies, filters: activeFilters() }),
      });
      state.result = result;
      state.edits = new Map();
      state.approval = result.approval || null;
      state.rowsByKey = new Map((result.rows || []).map((row) => [rowKey(row), row]));
      renderResult();
      renderWarnings();
      const rows = result.rows?.length || 0;
      notify(t(rows ? "calculationReady" : "emptyFilters"), rows ? "success" : "info");
    } catch (error) {
      showAlert(error.message || "Не удалось выполнить расчёт.");
    } finally {
      setBusy(false);
      if (state.result) updateActionAvailability();
    }
  }

  async function loadDatasetResponse(response) {
    state.dataset = response.dataset || null;
    state.sourceLabel = response.source_label || state.dataset?.metadata?.source_label || "Загруженные данные";
    state.result = null;
    state.edits = new Map();
    state.approval = null;
    state.rowsByKey.clear();
    state.supplierPages.clear();
    state.productPage = 0;
    state.productQuery = "";
    $("#product-search").value = "";
    initializeSettings();
    renderDataset();
    renderResult();
    renderWarnings();
  }

  async function loadDemo() {
    showAlert("");
    setBusy(true, "Загружаем синтетический демонстрационный набор…");
    try {
      await loadDatasetResponse(await api("/demo", { method: "POST" }));
      notify("Синтетические данные загружены. Запустите расчёт, чтобы сформировать рекомендации.", "success");
    } catch (error) {
      showAlert(error.message || "Не удалось загрузить демонстрационный набор.");
    } finally { setBusy(false); }
  }

  async function importFiles(files) {
    const selected = [...(files || [])];
    if (!selected.length) return;
    const body = new FormData();
    selected.forEach((file) => body.append("files", file, file.name));
    showAlert("");
    setBusy(true, `Загружаем ${formatNumber(selected.length)} файл(а)…`);
    try {
      await loadDatasetResponse(await api("/import", { method: "POST", body }));
      notify("Файлы приняты. Проверьте источник и параметры, затем выполните расчёт.", "success");
    } catch (error) {
      showAlert(error.message || "Не удалось импортировать файлы.");
    } finally {
      setBusy(false);
      $("#file-input").value = "";
    }
  }

  async function refreshService() {
    showAlert("");
    setBusy(true, "Проверяем сервис и обновляем исходные данные…");
    try {
      await checkHealth();
      await loadDatasetResponse(await api("/dataset"));
      notify("Сервис доступен, состояние источника обновлено.", "success");
    } catch (error) {
      showAlert(error.message || "Не удалось обновить состояние сервиса.");
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
      $("#api-version").textContent = "Проверьте локальный сервер";
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
    return numeric(row.unit_price) * quantity;
  }

  function priceKnown(row) {
    return row.price_known !== false && row.unit_price !== null && row.unit_price !== undefined && Number.isFinite(Number(row.unit_price));
  }

  function unpricedCount(rows = resultRows()) {
    return rows.filter(row => currentQuantity(row) > 0 && !priceKnown(row)).length;
  }

  function displayedTotal(rows, amount) {
    return unpricedCount(rows) ? `${formatNumber(amount, 2)} *` : formatNumber(amount, 2);
  }

  function renderBudget() {
    const count = unpricedCount();
    setMetric("#metric-total", displayedTotal(resultRows(), state.totalAmount));
    $(".metric-highlight .metric-foot").textContent = count
      ? `${t("partialAmount")}: ${formatNumber(count)} ${t("unpriced")}` : t("amountHelp");
  }

  function resultRows() {
    return Array.isArray(state.result?.rows) ? state.result.rows : [];
  }

  function resultTotals() {
    const rows = resultRows();
    return rows.reduce((total, row) => total + lineAmount(row), 0);
  }

  function setMetric(id, value) { $(id).textContent = value; }

  function urgencyMeta(value) {
    const key = String(value || "normal").toLowerCase();
    return { key: ["critical", "high", "normal", "covered"].includes(key) ? key : "normal", label: t(["critical", "high", "normal", "covered"].includes(key) ? key : "normal") };
  }

  function renderSummary() {
    const result = state.result;
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

  function seriesPoints(series, monthly = false) {
    if (!Array.isArray(series)) return [];
    return series.map((point, index) => {
      if (typeof point === "number") return Number.isFinite(point) ? { date: String(index + 1), value: point } : null;
      if (!point || typeof point !== "object") return null;
      const value = [point.demand, point.adjusted_demand, point.quantity, point.sales, point.value, point.actual, point.forecast]
        .find((candidate) => candidate !== null && candidate !== undefined && Number.isFinite(Number(candidate)));
      if (value === undefined) return null;
      const days = monthly && Number(point.days) > 0 ? Number(point.days) : 1;
      return { date: String(point.period ?? point.date ?? point.day ?? index + 1), value: Number(value) / days };
    }).filter(Boolean);
  }

  function chartSvg(historyInput, forecastInput, label) {
    const history = seriesPoints(historyInput, true);
    const forecast = seriesPoints(forecastInput);
    if (!history.length && !forecast.length) {
      return '<div class="chart-empty">Для этой позиции история и прогноз не переданы сервисом.</div>';
    }
    const all = [...history, ...forecast];
    const width = 720, height = 208, left = 42, right = 14, top = 14, bottom = 34;
    const plotWidth = width - left - right, plotHeight = height - top - bottom;
    const values = all.map((point) => point.value);
    let min = Math.min(0, ...values), max = Math.max(0, ...values);
    if (min === max) max = min + 1;
    const pad = (max - min) * 0.12;
    min -= pad; max += pad;
    const y = (value) => top + ((max - value) / (max - min)) * plotHeight;
    const x = (index) => left + (all.length <= 1 ? plotWidth / 2 : (index / (all.length - 1)) * plotWidth);
    const historyPath = history.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
    const forecastPath = forecast.map((point, index) => {
      const absoluteIndex = history.length + index;
      return `${index ? "L" : "M"}${x(absoluteIndex).toFixed(1)},${y(point.value).toFixed(1)}`;
    }).join(" ");
    const splitX = history.length ? x(Math.max(0, history.length - 1)) : left;
    const grid = [0, 0.5, 1].map((fraction) => {
      const gy = top + fraction * plotHeight;
      const labelValue = max - fraction * (max - min);
      return `<line x1="${left}" y1="${gy}" x2="${width - right}" y2="${gy}" class="chart-grid"/><text x="${left - 8}" y="${gy + 4}" text-anchor="end" class="chart-axis">${escapeHtml(formatNumber(labelValue, 1))}</text>`;
    }).join("");
    const forecastCircles = forecast.map((point, index) => `<circle cx="${x(history.length + index)}" cy="${y(point.value)}" r="3.2" class="chart-point forecast-point"><title>${escapeHtml(point.date)}: ${escapeHtml(formatNumber(point.value, 2))}</title></circle>`).join("");
    const historyCircles = history.map((point, index) => `<circle cx="${x(index)}" cy="${y(point.value)}" r="2.5" class="chart-point history-point"><title>${escapeHtml(point.date)}: ${escapeHtml(formatNumber(point.value, 2))}</title></circle>`).join("");
    const dateLabel = (point) => point ? escapeHtml(point.date) : "";
    return `<svg class="history-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}: история и прогноз спроса">
      <title>${escapeHtml(label)} — история и прогноз</title>${grid}
      ${history.length ? `<path d="${historyPath}" class="chart-line history-line"/>` : ""}
      ${forecast.length ? `<path d="${forecastPath}" class="chart-line forecast-line"/>` : ""}
      ${historyCircles}${forecastCircles}${history.length && forecast.length ? `<line x1="${splitX}" y1="${top}" x2="${splitX}" y2="${top + plotHeight}" class="chart-split"/>` : ""}
      <text x="${left}" y="${height - 8}" class="chart-axis">${dateLabel(all[0])}</text>
      <text x="${width - right}" y="${height - 8}" text-anchor="end" class="chart-axis">${dateLabel(all.at(-1))}</text>
    </svg>`;
  }

  function breakdownMarkup(row) {
    const breakdown = row.breakdown && typeof row.breakdown === "object" ? row.breakdown : {};
    const entries = Object.entries(breakdown);
    if (!entries.length) return '<p class="muted-copy">Детальная разбивка не передана расчётным сервисом.</p>';
    return `<dl class="breakdown-list">${entries.map(([key, value]) => `<div><dt>${escapeHtml(key.replaceAll("_", " "))}</dt><dd>${escapeHtml(typeof value === "object" ? JSON.stringify(value) : value)}</dd></div>`).join("")}</dl>`;
  }

  async function explainRow(key) {
    const row = state.rowsByKey.get(key);
    if (!row) return;
    $("#explain-title").textContent = row.name || row.sku || "Позиция";
    $("#explain-meta").textContent = [row.sku, row.supplier, row.warehouse].filter(Boolean).join(" · ");
    $("#explain-content").innerHTML = '<div class="loading-state"><span class="spinner" aria-hidden="true"></span><span>Загружаем расчёт позиции…</span></div>';
    $("#explain-dialog").showModal();
    let detail;
    try {
      const query = new URLSearchParams({ sku: String(row.sku), warehouse: String(row.warehouse) });
      detail = await api(`/runs/${encodeURIComponent(state.result.run_id)}/item?${query}`);
    } catch (error) {
      $("#explain-content").innerHTML = `<p class="inline-alert inline-alert-error">${escapeHtml(error.message || "Детали недоступны.")}</p>`;
      return;
    }
    const warnings = Array.isArray(detail.warnings) ? detail.warnings : [];
    const excluded = Array.isArray(detail.excluded_events) ? detail.excluded_events : [];
    const demand = detail.daily_demand;
    $("#explain-content").innerHTML = `
      <div class="explain-kpis">
        <div><span>СРЕДНИЙ СПРОС / ДЕНЬ</span><strong>${escapeHtml(formatNumber(demand, 2))}<small> ${escapeHtml(detail.unit || "ед.")}</small></strong></div>
        <div><span>ПОКРЫТИЕ</span><strong>${escapeHtml(formatNumber(detail.coverage_days, 1))}<small> дн.</small></strong></div>
        <div><span>ИСКЛЮЧЕНО ВСПЛЕСКОВ</span><strong>${escapeHtml(formatNumber(detail.excluded_quantity ?? 0))}</strong></div>
      </div>
      <section class="explain-section"><div class="explain-section-head"><h3>Спрос, единиц в день</h3><div class="chart-legend"><span><i class="legend-history"></i>История: среднее за месяц</span><span><i class="legend-forecast"></i>Прогноз: по дням</span></div></div>${chartSvg(detail.history, detail.forecast, detail.name || detail.sku || "Спрос")}</section>
      <section class="explain-section"><h3>Логика рекомендации</h3><p class="explanation-text">${escapeHtml(detail.explanation || "Текстовое пояснение не передано сервисом.")}</p>${breakdownMarkup(detail)}</section>
      ${excluded.length ? `<section class="explain-section"><h3>События, исключённые из базового спроса</h3><ul class="event-list">${excluded.map((event) => `<li>${escapeHtml(typeof event === "object" ? JSON.stringify(event) : event)}</li>`).join("")}</ul></section>` : ""}
      ${warnings.length ? `<section class="explain-section warning-list"><h3>Ограничения и предупреждения</h3><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></section>` : ""}`;
  }

  function renderGroup(supplier, rows) {
    const total = rows.reduce((sum, row) => sum + lineAmount(row), 0);
    const hasLines = state.supplierLineCounts.get(supplier) ?? rows.filter((row) => currentQuantity(row) > 0).length;
    const pageSize = 30;
    const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
    const page = Math.min(state.supplierPages.get(supplier) || 0, pageCount - 1);
    const visibleRows = rows.slice(page * pageSize, (page + 1) * pageSize);
    return `<article class="supplier-card panel" data-supplier-card="${escapeHtml(supplier)}">
      <header class="supplier-card-head">
        <div class="supplier-title"><span class="supplier-avatar" aria-hidden="true">${escapeHtml((supplier || "?").trim().slice(0, 1).toUpperCase())}</span><div><h3>${escapeHtml(supplier || "Поставщик не указан")}</h3><p><span data-supplier-count>${formatNumber(hasLines)}</span> строк к заказу <span class="footer-separator">·</span> ${formatNumber(rows.length)} позиций</p></div></div>
        <div class="supplier-total"><span>${t(unpricedCount(rows) ? "partialAmount" : (state.approval ? "approved" : "draft"))}</span><strong data-supplier-total>${escapeHtml(displayedTotal(rows, total))}</strong></div>
      </header>
      <div class="table-scroll"><table class="order-table"><thead><tr><th scope="col">${t("sku")}</th><th scope="col">${t("category")}</th><th scope="col">${t("warehouse")}</th><th scope="col">${t("status")}</th><th scope="col" class="numeric-cell">${t("orderQty")}</th><th scope="col" class="numeric-cell">${t("amount")}</th><th scope="col"><span class="visually-hidden">${t("explanation")}</span></th></tr></thead><tbody>
      ${visibleRows.map((row) => {
        const key = rowKey(row), urgency = urgencyMeta(row.urgency), quantity = currentQuantity(row);
        const amount = lineAmount(row, quantity);
        return `<tr data-row="${escapeHtml(key)}">
          <td><div class="product-cell"><strong>${escapeHtml(row.sku || "—")}</strong><span>${escapeHtml(row.name || "Наименование не указано")}</span></div></td>
          <td><span class="category-chip">${escapeHtml(row.category || "Без категории")}</span></td>
          <td class="warehouse-cell">${escapeHtml(row.warehouse || "—")}</td>
          <td><span class="urgency urgency-${urgency.key}"><i aria-hidden="true"></i>${escapeHtml(urgency.label)}</span></td>
          <td class="numeric-cell qty-cell"><label class="visually-hidden" for="qty-${escapeHtml(key)}">Количество для ${escapeHtml(row.sku || row.name)}</label><div class="qty-input-wrap"><input id="qty-${escapeHtml(key)}" class="qty-input" type="number" min="0" step="any" inputmode="decimal" value="${escapeHtml(quantity)}" data-quantity="${escapeHtml(key)}" ${state.approval ? "disabled" : ""}><span>${escapeHtml(row.unit || "ед.")}</span></div></td>
          <td class="numeric-cell amount-cell" data-amount>${escapeHtml(priceKnown(row) ? formatNumber(amount, 2) : t("noPrice"))}</td>
          <td><button class="details-button" type="button" data-explain="${escapeHtml(key)}" aria-label="Пояснить расчёт для ${escapeHtml(row.sku || row.name)}">i</button></td>
        </tr>`;
      }).join("")}</tbody></table></div>
      ${pageCount > 1 ? `<div class="supplier-pager"><button class="button button-quiet button-small" type="button" data-supplier-page="${escapeHtml(supplier)}" data-page="${page - 1}" ${page === 0 ? "disabled" : ""}>← Назад</button><span>${page + 1} / ${pageCount} · ${formatNumber(rows.length)} позиций</span><button class="button button-quiet button-small" type="button" data-supplier-page="${escapeHtml(supplier)}" data-page="${page + 1}" ${page >= pageCount - 1 ? "disabled" : ""}>Далее →</button></div>` : ""}
      <div class="supplier-card-foot"><span>${t("quantityHelp")}${unpricedCount(rows) ? ` · ${formatNumber(unpricedCount(rows))} ${t("unpriced")}` : ""}</span><strong>${t("total")}: <span data-supplier-total>${escapeHtml(displayedTotal(rows, total))}</span></strong></div>
    </article>`;
  }

  function renderResult() {
    const result = state.result;
    const groups = $("#supplier-groups");
    const empty = $("#orders-empty");
    if (!result) {
      renderSummary();
      groups.innerHTML = "";
      empty.hidden = false;
      empty.innerHTML = state.dataset
        ? `<div class="empty-art" aria-hidden="true">▤ ↗</div><h3>${t("readyTitle")}</h3><p>${t("readyHelp")}</p>`
        : `<div class="empty-art" aria-hidden="true">▤ ↗</div><h3>${t("emptyTitle")}</h3><p>${t("emptyHelp")}</p><button class="button button-outline" type="button" data-action="demo">${t("demo")}</button>`;
      $("#orders-caption").textContent = t(state.dataset ? "readyHelp" : "emptyHelp");
      $("#run-stamp").textContent = t("notCalculated");
      updateActionAvailability();
      return;
    }
    const rows = resultRows();
    state.totalAmount = 0;
    state.orderLineCount = 0;
    state.supplierTotals.clear();
    state.supplierLineCounts.clear();
    rows.forEach((row) => {
      const supplier = row.supplier || "Поставщик не указан";
      const quantity = currentQuantity(row);
      state.totalAmount += lineAmount(row, quantity);
      state.supplierTotals.set(supplier, (state.supplierTotals.get(supplier) || 0) + lineAmount(row, quantity));
      if (quantity > 0) {
        state.orderLineCount += 1;
        state.supplierLineCounts.set(supplier, (state.supplierLineCounts.get(supplier) || 0) + 1);
      }
    });
    renderSummary();
    if (!rows.length) {
      groups.innerHTML = "";
      empty.hidden = false;
      empty.innerHTML = `<div class="empty-art" aria-hidden="true">⌕</div><h3>${t("emptyFilters")}</h3><p>${t("changeFilters")}</p>`;
    } else {
      empty.hidden = true;
      const grouped = new Map();
      rows.forEach((row) => {
        const supplier = row.supplier || "Поставщик не указан";
        if (!grouped.has(supplier)) grouped.set(supplier, []);
        grouped.get(supplier).push(row);
      });
      groups.innerHTML = [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b, "ru"))
        .map(([supplier, supplierRows]) => renderGroup(supplier, supplierRows)).join("");
    }
    const createdAt = result.created_at || result.as_of;
    $("#run-stamp").textContent = createdAt ? `Расчёт · ${formatDate(createdAt, Boolean(result.created_at))}` : "Расчёт готов";
    const filters = result.filters || activeFilters();
    const applied = Object.entries(filters).filter(([, value]) => value).map(([key, value]) => {
      const labels = { warehouse: "склад", category: "категория", supplier: "поставщик" };
      return `${labels[key] || key}: ${value}`;
    });
    $("#orders-caption").textContent = `${formatNumber(rows.length)} строк · ${applied.length ? `фильтр: ${applied.join("; ")}` : "без фильтров"}${state.approval ? " · утверждено менеджером" : " · черновик на проверке"}`;
    updateActionAvailability();
  }

  function updateActionAvailability() {
    const hasRun = Boolean(state.result?.run_id);
    const unsavedEdits = state.edits.size > 0 && !state.approval;
    $("#export-csv").disabled = state.busy || !hasRun || unsavedEdits;
    $("#export-xlsx").disabled = state.busy || !hasRun || unsavedEdits;
    for (const id of ["#export-csv", "#export-xlsx"]) {
      $(id).title = unsavedEdits ? "Сначала утвердите изменения количества, иначе экспорт не включит их" : "Экспорт текущего расчёта";
    }
    $("#calculate-button").disabled = state.busy || !state.dataset?.products?.length;
    $("#recalculate-settings").disabled = state.busy || !state.dataset?.products?.length;
    $("#approve-button").disabled = state.busy || !hasRun || Boolean(state.approval) || !resultRows().length;
  }

  function invalidateResult() {
    if (!state.result) return;
    state.result = null;
    state.approval = null;
    state.edits.clear();
    state.rowsByKey.clear();
    state.supplierPages.clear();
    renderResult();
    renderWarnings();
  }

  function updateTotalsAfterEdit(row, before, after) {
    const supplier = row.supplier || "Поставщик не указан";
    const amountDelta = lineAmount(row, after) - lineAmount(row, before);
    const lineDelta = Number(after > 0) - Number(before > 0);
    state.totalAmount += amountDelta;
    state.orderLineCount += lineDelta;
    state.supplierTotals.set(supplier, (state.supplierTotals.get(supplier) || 0) + amountDelta);
    state.supplierLineCounts.set(supplier, (state.supplierLineCounts.get(supplier) || 0) + lineDelta);
    renderBudget();
    setMetric("#metric-items", formatNumber(state.orderLineCount));
    const card = $$(".supplier-card").find((node) => node.dataset.supplierCard === supplier);
    if (card) {
      $$('[data-supplier-total]', card).forEach((el) => { el.textContent = displayedTotal(resultRows().filter(item => (item.supplier || "Поставщик не указан") === supplier), state.supplierTotals.get(supplier)); });
      $("[data-supplier-count]", card).textContent = formatNumber(state.supplierLineCounts.get(supplier));
    }
  }

  function openApproval() {
    if (!state.result?.run_id || !resultRows().length) { notify("Сначала выполните расчёт с позициями.", "error"); return; }
    const rows = resultRows();
    const filters = state.result.filters || {};
    const applied = Object.entries(filters).filter(([, value]) => value).map(([key, value]) => `${key}: ${value}`);
    $("#approval-preview").innerHTML = `<div><span>${t("orderItems")}</span><strong>${formatNumber(rows.length)}</strong></div><div><span>${t("suppliers")}</span><strong>${formatNumber(uniqueValues(rows.map(row => row.supplier)).length)}</strong></div><div><span>${t(unpricedCount() ? "partialAmount" : "draft")}</span><strong>${displayedTotal(rows, resultTotals())}</strong></div><p>${t("approvalScope")}${applied.length ? ` (${escapeHtml(applied.join("; "))})` : ""}</p>`;
    const missing = state.result.source_synthetic === false && rows.some(row => currentQuantity(row) > 0 && ["on_hand", "lead_days"].some(field => !["observed", "assumed"].includes(row.input_provenance?.[field])));
    $("#missing-inputs-label").hidden = !missing;
    $("#acknowledge-missing-inputs").checked = false;
    $("#acknowledge-missing-inputs").required = missing;
    $("#reviewer-name").value = "";
    $("#approval-dialog").showModal();
  }

  async function submitApproval(event) {
    event.preventDefault();
    if (!state.result?.run_id || state.approval) return;
    const reviewer = $("#reviewer-name").value.trim();
    if (!reviewer) { $("#reviewer-name").focus(); return; }
    const quantities = Object.fromEntries(resultRows().map((row) => [rowKey(row), currentQuantity(row)]));
    const button = $("#confirm-approval");
    button.disabled = true;
    button.textContent = t("saving");
    try {
      state.approval = await api(`/runs/${encodeURIComponent(state.result.run_id)}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quantities, reviewer, acknowledge_missing_inputs: !$("#missing-inputs-label").hidden && $("#acknowledge-missing-inputs").checked }),
      });
      $("#approval-dialog").close();
      renderResult();
      notify(t("approvedMessage"), "success");
    } catch (error) {
      showAlert(error.message || "Не удалось подтвердить рекомендации.");
    } finally {
      button.disabled = false;
      button.textContent = t("confirm");
    }
  }

  async function exportRun(format) {
    if (!state.result?.run_id) return;
    const supplier = $("#export-supplier").value;
    const query = new URLSearchParams({ format });
    if (supplier) query.set("supplier", supplier);
    showAlert("");
    try {
      const response = await fetch(`${API}/runs/${encodeURIComponent(state.result.run_id)}/export?${query}`);
      if (!response.ok) {
        const type = response.headers.get("content-type") || "";
        const payload = type.includes("json") ? await response.json() : await response.text();
        throw new Error(payload?.detail || payload || `Ошибка выгрузки (${response.status})`);
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
      notify(`${format.toUpperCase()} выгружен${supplier ? ` для ${supplier}` : ""}.`, "success");
    } catch (error) { showAlert(error.message || "Не удалось выгрузить расчёт."); }
  }

  function addPolicyRow() {
    if (!state.dataset) { notify("Сначала загрузите данные.", "error"); return; }
    const category = window.prompt("Название категории из справочника:");
    if (!category || !category.trim()) return;
    const normalized = category.trim();
    if (policyRows().some((item) => item.category.toLocaleLowerCase() === normalized.toLocaleLowerCase())) {
      notify("Политика для этой категории уже отображается.", "info");
      return;
    }
    state.dataset.category_policies = { ...(state.dataset.category_policies || {}), [normalized]: { growth: 0, safety_days: numeric(state.dataset.settings?.safety_days, 0) } };
    renderPolicies();
    invalidateResult();
    notify(`Добавлена политика категории «${normalized}». Она будет применена после пересчёта.`, "success");
  }

  function bindEvents() {
    $("#language-select").addEventListener("change", event => {
      // Save in-progress category settings before rebuilding translated views.
      if (state.dataset) state.dataset.category_policies = collectPolicies();
      i18n.setLocale(event.target.value);
      renderDataset();
      renderResult();
      if (state.result) notify(t("localeRecalculate"), "info");
    });
    $("#theme-toggle").addEventListener("click", () => { i18n.toggleTheme(); renderSummary(); });
    $("#demo-button").addEventListener("click", loadDemo);
    $("#upload-button").addEventListener("click", () => $("#file-input").click());
    $("#choose-file-button").addEventListener("click", () => $("#file-input").click());
    $("#orders-empty").addEventListener("click", (event) => { if (event.target.closest("[data-action='demo']")) loadDemo(); });
    $("#file-input").addEventListener("change", (event) => importFiles(event.target.files));
    $("#refresh-button").addEventListener("click", refreshService);
    $("#calculate-button").addEventListener("click", calculate);
    $("#recalculate-settings").addEventListener("click", calculate);
    $("#product-search").addEventListener("input", (event) => {
      state.productQuery = event.target.value.trim();
      state.productPage = 0;
      renderProducts();
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
          notify("Проверьте числовое значение товара: допустимы конечные неотрицательные числа, рост от −1.", "error");
          return;
        }
      }
      product[field] = value;
      if (["on_hand", "lead_days"].includes(field)) product.provenance = { ...(product.provenance || {}), [field]: "assumed" };
      invalidateResult();
      notify("Параметр товара изменён. Выполните новый расчёт.", "info");
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
      notify(`Политика «${category}» исключена из следующего расчёта.`, "info");
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
      if (!input || state.approval) return;
      const quantity = Number(input.value);
      if (!input.value.trim() || !Number.isFinite(quantity) || quantity < 0 || quantity > 1e12) return;
      const key = input.dataset.quantity;
      const row = state.rowsByKey.get(key);
      if (!row) return;
      const before = currentQuantity(row);
      if (quantity === numeric(row.recommended_quantity)) state.edits.delete(key);
      else state.edits.set(key, quantity);
      const tableRow = input.closest("tr");
      if (tableRow) $("[data-amount]", tableRow).textContent = priceKnown(row) ? formatNumber(lineAmount(row, quantity), 2) : t("noPrice");
      updateTotalsAfterEdit(row, before, quantity);
      updateActionAvailability();
    });
    $("#supplier-groups").addEventListener("change", (event) => {
      const input = event.target.closest("[data-quantity]");
      if (!input || state.approval) return;
      const quantity = Number(input.value);
      if (!input.value.trim() || !Number.isFinite(quantity) || quantity < 0 || quantity > 1e12) {
        input.value = currentQuantity(state.rowsByKey.get(input.dataset.quantity));
        notify("Количество должно быть числом от 0 до 10¹².", "error");
      }
    });
    $("#export-csv").addEventListener("click", () => exportRun("csv"));
    $("#export-xlsx").addEventListener("click", () => exportRun("xlsx"));
    $("#approve-button").addEventListener("click", openApproval);
    $("#supplier-filter").addEventListener("change", () => {
      const supplier = $("#supplier-filter").value;
      $("#export-supplier").value = supplier;
    });
    $("#approval-form").addEventListener("submit", submitApproval);
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
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "enter" && !state.busy) calculate();
    });
  }

  async function init() {
    i18n.apply();
    bindEvents();
    initializeSettings();
    renderDataset();
    renderResult();
    try {
      await checkHealth();
      const response = await api("/dataset");
      await loadDatasetResponse(response);
      if (!state.dataset) showAlert("Сервис готов. Откройте демо или загрузите данные для начала работы.", "info");
    } catch (error) {
      showAlert(`Не удалось подключиться к локальному API. ${error.message || "Запустите сервис и нажмите «Обновить»."}`);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
