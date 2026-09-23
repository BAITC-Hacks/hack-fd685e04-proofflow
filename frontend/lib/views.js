import { state } from "./state.js";
import { $, escapeHtml, numeric, formatNumber } from "./format.js";
import { t } from "../i18n.js";

// Focused view builders. Data/ordering decisions are not made in the browser.
export function renderDataQuality() {
  const region = $("#data-quality");
  const coverage = state.dataset?.quality?.field_coverage;
  region.hidden = !coverage;
  if (!coverage) { region.innerHTML = ""; return; }
  const fields = { on_hand: "stock", lead_days: "lead", unit_price: "amount" };
  region.innerHTML = `<div class="quality-heading">${t("quality")}</div><div class="quality-grid">${Object.entries(fields).map(([field, label]) => {
    const counters = { observed: 0, assumed: 0, unknown: 0, missing: 0 };
    (state.dataset.products || []).forEach(product => {
      let marker = product[field] === null || product[field] === undefined || product[field] === "" ? "missing" :
        state.dataset.metadata?.synthetic === true ? "assumed" :
        product.provenance?.[field] ?? state.dataset.metadata?.field_provenance?.[field] ?? state.dataset.metadata?.provenance?.[field] ?? "unknown";
      if (!(marker in counters)) marker = "unknown";
      counters[marker] += 1;
    });
    return `<div class="quality-card"><strong>${t(label)}</strong><div class="quality-counts"><span><b>${formatNumber(counters.observed ?? 0)}</b>${t("observed")}</span><span><b>${formatNumber(counters.assumed ?? 0)}</b>${t("assumed")}</span><span><b>${formatNumber(numeric(counters.unknown) + numeric(counters.missing))}</b>${t("missing")}</span></div></div>`;
  }).join("")}</div><p class="quality-help">${t("qualityHelp")}</p>`;
}


export function urgencyMeta(value) {
  const key = String(value || "normal").toLowerCase();
  return { key: ["critical", "high", "normal", "covered"].includes(key) ? key : "normal", label: t(["critical", "high", "normal", "covered"].includes(key) ? key : "normal") };
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


export function chartSvg(historyInput, forecastInput, label) {
  const history = seriesPoints(historyInput, true);
  const forecast = seriesPoints(forecastInput);
  if (!history.length && !forecast.length) {
    return `<div class="chart-empty">${t("noChart")}</div>`;
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
  return `<svg class="history-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}: ${t("demandChart")}">
    <title>${escapeHtml(label)} — ${t("demandChart")}</title>${grid}
    ${history.length ? `<path d="${historyPath}" class="chart-line history-line"/>` : ""}
    ${forecast.length ? `<path d="${forecastPath}" class="chart-line forecast-line"/>` : ""}
    ${historyCircles}${forecastCircles}${history.length && forecast.length ? `<line x1="${splitX}" y1="${top}" x2="${splitX}" y2="${top + plotHeight}" class="chart-split"/>` : ""}
    <text x="${left}" y="${height - 8}" class="chart-axis">${dateLabel(all[0])}</text>
    <text x="${width - right}" y="${height - 8}" text-anchor="end" class="chart-axis">${dateLabel(all.at(-1))}</text>
  </svg>`;
}


export function breakdownMarkup(row) {
  const breakdown = row.breakdown && typeof row.breakdown === "object" ? row.breakdown : {};
  const entries = Object.entries(breakdown);
  if (!entries.length) return `<p class="muted-copy">${t("noBreakdown")}</p>`;
  const scalar = entries.filter(([, value]) => value === null || typeof value !== "object");
  const nested = entries.filter(([, value]) => value !== null && typeof value === "object");
  const details = scalar.map(([key, value]) => {
    const display = typeof value === "number" ? key.endsWith("_growth") ? `${formatNumber(value * 100, 1)} %` : formatNumber(value, 3) : value;
    return `<div><dt>${escapeHtml(t(key))}</dt><dd>${escapeHtml(display)}</dd></div>`;
  }).join("");
  return `<dl class="breakdown-list">${details}</dl>${nested.length ? `<details class="advanced-breakdown"><summary>${t("calculationDetails")}</summary>${nested.map(([key, value]) => `<section><h4>${escapeHtml(t(key))}</h4><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></section>`).join("")}</details>` : ""}`;
}
