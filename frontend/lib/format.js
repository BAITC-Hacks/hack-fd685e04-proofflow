import { i18n } from "../i18n.js";

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);

export function numeric(value, fallback = 0) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat(i18n.locale === "en" ? "en-GB" : `${i18n.locale}-KZ`, { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(Number(value));
}

export function formatDate(value, includeTime = false) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(i18n.locale === "en" ? "en-GB" : `${i18n.locale}-KZ`, includeTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { day: "numeric", month: "short", year: "numeric" }).format(date);
}

export function rowKey(row) {
  return `${row.warehouse ?? ""}::${row.sku ?? ""}`;
}
