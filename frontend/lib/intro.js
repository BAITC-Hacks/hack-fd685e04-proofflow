import { t } from "../i18n.js";

// A short entrance animation, never a claim about data import/calculation progress.
export function startIntro() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  try { if (sessionStorage.getItem("proofflow.introSeen") === "1") return; } catch { /* Private sessions can still render the application. */ }
  const overlay = document.querySelector("#workspace-intro");
  const shell = document.querySelector(".app-shell");
  const skip = document.querySelector("#skip-intro");
  document.querySelector("#intro-caption").textContent = t("planning");
  document.querySelector("#intro-hint").textContent = t("introHint");
  skip.textContent = t("skip");
  overlay.hidden = false;
  shell.inert = true;
  skip.focus({ preventScroll: true });
  const start = performance.now();
  let frame;
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    cancelAnimationFrame(frame);
    shell.inert = false;
    overlay.hidden = true;
    document.querySelector("#page-title").focus({ preventScroll: true });
    skip.removeEventListener("click", finish);
    document.removeEventListener("keydown", escape);
    try { sessionStorage.setItem("proofflow.introSeen", "1"); } catch { /* No persistence is required. */ }
  };
  const escape = event => { if (event.key === "Escape") finish(); };
  skip.addEventListener("click", finish);
  document.addEventListener("keydown", escape);
  const animate = now => {
    if (finished) return;
    const fraction = Math.min(1, (now - start) / 850);
    const value = Math.min(100, Math.floor(1 + fraction * 99));
    document.querySelector("#intro-counter").textContent = String(value);
    document.querySelector("#intro-progress").style.transform = `scaleX(${fraction})`;
    if (fraction < 1) frame = requestAnimationFrame(animate);
    else window.setTimeout(finish, 100);
  };
  frame = requestAnimationFrame(animate);
}
