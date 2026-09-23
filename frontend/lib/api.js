import { t } from "../i18n.js";

export const API = "/api";

export async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180_000);
  try {
    const response = await fetch(`${API}${path}`, { ...options, signal: options.signal || controller.signal });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("json") ? await response.json() : await response.text();
    if (!response.ok) {
      let message = typeof payload === "object" && payload
        ? (payload.detail || payload.message || payload.error)
        : payload;
      if (Array.isArray(message)) message = message.map(item => `${(item.loc || []).join(".")}: ${item.msg || t("validation")}`).join("; ");
      throw new Error(message || `${t("requestError")} (${response.status})`);
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") throw new Error(t("requestTimeout"));
    if (error instanceof TypeError) throw new Error(t("serviceOffline"));
    throw error;
  } finally { clearTimeout(timeout); }
}
