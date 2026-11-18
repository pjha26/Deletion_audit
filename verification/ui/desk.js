"use strict";

const byId = id => document.getElementById(id);
const esc = text => String(text ?? "").replace(/[&<>"']/g, ch => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[ch]);
const labels = {
  VERIFIED_IN_SCOPE: ["Verified in scope", "verified"],
  INCOMPLETE: ["Incomplete", "bad"],
  NEEDS_REVIEW: ["Needs review", "review"],
  unverified: ["Not checked yet", "neutral"]
};
const checkNames = {profile: "Primary profile", search: "Search copy", retention: "Retained audit record", sync: "Sync guard"};
const stamp = (text, color) => `<span class="status ${color}">${esc(text)}</span>`;
const badge = status => stamp(...(labels[status] ?? labels.unverified));
const dateTime = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit", month: "short", year: "numeric", hour: "2-digit",
  minute: "2-digit", second: "2-digit", timeZone: "UTC"
});
function stampTime(value, empty = "Time unavailable") {
  const time = Date.parse(value);
  return Number.isFinite(time) ? dateTime.format(time) + " UTC" : empty;
}
const caseHash = (id, run) => `#${encodeURIComponent(id)}${run ? "/" + run : ""}`;
let cases = [];
let fingerprint;
let busy = false;
let loading = false;
let rerenderPending = false;
let selectedCase;
let queueMatches;

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error((await response.json()).error);
  return response.json();
}

function showQueue(id) {
  const text = byId("search").value.toLowerCase().trim();
  const filter = byId("filter").value;
  const visible = cases.filter(c => c.id.toLowerCase().includes(text) && (
    filter === "all" || (filter === "review" ? (c.latest?.review.length || c.latest?.reappearances.length) :
      (c.latest?.status ?? "unverified") === filter)));
  const queue = byId("cases");
  const queueKey = JSON.stringify([id, visible.map(c => [c.id, c.latest?.status, c.latest?.reappearances.length])]);
  const count = `${visible.length.toLocaleString()} of ${cases.length.toLocaleString()}`;
  if (byId("case-count").textContent !== count) byId("case-count").textContent = count;
  if (queueMatches === queueKey) return;
  queueMatches = queueKey;
  const focusedHref = queue.contains(document.activeElement) ? document.activeElement.getAttribute("href") : null;
  const scroll = queue.scrollTop;
  queue.innerHTML = visible.length ? visible.map(c =>
    `<a href="${caseHash(c.id)}" aria-current="${c.id === id}">
      <strong>${esc(c.id)}</strong>
      <span class="case-state">${badge(c.latest?.status)}${c.latest?.reappearances.length ? '<span class="returned">Data returned</span>' : ""}</span></a>`).join("") :
    `<p class="empty">${cases.length ? "No cases match these filters." : "No cases registered."}</p>`;
  queue.scrollTop = scroll;
  if (focusedHref) Array.from(queue.querySelectorAll("a")).find(a => a.getAttribute("href") === focusedHref)?.focus({preventScroll: true});
}

function checkDetails(check, run) {
  const color = check.state === "unknown" ? "review" : check.state === check.expected ? "verified" : "bad";
  const result = {review: "Needs review", verified: "Meets policy", bad: "Action needed"}[color];
  return `<details class="check" data-check="${esc(check.id)}">
    <summary data-focus="check-${esc(check.id)}">
      <span class="check-source"><strong>${esc(checkNames[check.id] ?? check.id)}</strong>
      <span class="scope">${esc(check.system)} · ${esc(check.scope)}</span></span>
      <span class="check-result"><span class="observed">Observed <strong>${esc(check.state)}</strong></span>${stamp(result, color)}</span>
      <span class="chevron" aria-hidden="true"></span></summary>
    <dl><dt>Expected state</dt><dd>${esc(check.expected)}</dd>
      <dt>Observed at</dt><dd>${esc(stampTime(check.observed_at))}</dd>
      <dt>Evidence</dt><dd>Run ${run.id} / ${esc(check.id)}</dd>
      <dt>Result</dt><dd>${esc(check.reason)}</dd>
      <dt>Matches</dt><dd>${esc(check.matches ?? "Not counted")}</dd></dl></details>`;
}

function showCase(c, selected) {
  const run = c.runs.find(item => String(item.id) === selected) ?? c.runs[0];
  const sameCase = selectedCase === c.id;
  const open = new Set(sameCase ? Array.from(byId("case-body").querySelectorAll("details[open]"),
    el => el.dataset.check) : []);
  const focus = sameCase && byId("case-header").parentElement.contains(document.activeElement)
    ? document.activeElement.dataset.focus : null;
  const historyScroll = sameCase ? document.querySelector(".timeline ol")?.scrollTop ?? 0 : 0;
  selectedCase = c.id;
  const historical = run && run.id !== c.runs[0].id;
  byId("case-header").innerHTML = `<div class="case-head"><div><h2 id="case-title" tabindex="-1" data-focus="case-title">${esc(c.id)}</h2>
    <p class="verdict">${badge(run?.status)}
    ${run ? `<span class="time">${historical ? "Historical run" : "Last checked"} · ${esc(stampTime(run.collected_at))}</span>` : ""}</p></div>
    <div class="actions">${run ? `<a class="button" data-focus="report" href="/api/cases/${encodeURIComponent(c.id)}/reports/${run.id}" download>Download report</a>` : ""}
    <button class="button primary" id="run" data-focus="run" type="button" aria-disabled="${busy}">${busy ? "Checking sources…" : "Run verification"}</button></div></div>`;
  byId("run").addEventListener("click", () => runCase(c.id));
  if (!run) {
    byId("case-body").innerHTML = '<p class="empty">Run verification to collect the first set of observations.</p>';
    if (focus === "run") byId("run").focus();
    return;
  }
  const recurrence = run.reappearances.map(e =>
    `<p><strong>${esc(checkNames[e.check] ?? e.check)} returned.</strong>
      <a data-focus="absent-${e.previous_run}-${esc(e.check)}" href="${caseHash(c.id, e.previous_run)}">Run ${e.previous_run}</a> found it absent at ${esc(stampTime(e.absent_at))}.
      <a data-focus="present-${e.present_run ?? run.id}-${esc(e.check)}" href="${caseHash(c.id, e.present_run ?? run.id)}">Run ${e.present_run ?? run.id}</a>
      found it present at ${esc(stampTime(e.present_at))}.</p>`).join("");
  const review = run.review.length ? `<p><strong>Evidence needs review.</strong>
    Open the ${esc(run.review.map(id => checkNames[id]).join(", "))} check for details.</p>` : "";
  const followUp = run.guidance.length ? `<section class="followup"><h2>Proposed follow-up</h2>
    <ul>${run.guidance.map(text => `<li>${esc(text)}</li>`).join("")}</ul></section>` : "";
  byId("case-body").innerHTML = `${recurrence ? `<div class="alert">${recurrence}</div>` : ""}
    ${review ? `<div class="alert review-alert">${review}</div>` : ""}
    <div class="details-grid"><section class="evidence"><h2>Checks and evidence</h2>
      <p class="coverage">${run.checks.filter(c => c.state !== "unknown").length} of ${run.checks.length} checks conclusive
      <span>Policy · ${esc(run.policy)}</span></p>
      <div class="check-list">${run.checks.map(check => checkDetails(check, run)).join("")}</div>${followUp}</section>
      <section class="timeline" aria-label="Run history"><div class="timeline-head"><h2>Run history</h2>
      ${historical ? `<a data-focus="latest" href="${caseHash(c.id)}">Latest run</a>` : ""}</div>
      <p class="coverage">Next recheck · ${esc(stampTime(c.next_due, "Not scheduled"))}</p>
      <ol>${c.runs.map(item => `<li><a data-focus="run-${item.id}" href="${caseHash(c.id, item.id)}" aria-current="${item.id === run.id}">
        <span class="run-label"><strong>Run ${item.id}</strong><span>${esc(item.trigger)}</span></span>
        ${badge(item.status)}<span class="time">${esc(stampTime(item.collected_at))}</span></a></li>`).join("")}</ol>
      </section></div>`;
  for (const detail of byId("case-body").querySelectorAll("details")) {
    detail.open = open.has(detail.dataset.check);
  }
  document.querySelector(".timeline ol").scrollTop = historyScroll;
  if (focus) (byId("case-detail").querySelector(`[data-focus="${CSS.escape(focus)}"]`) ??
    byId("case-title")).focus({preventScroll: true});
}

async function refresh(force = false) {
  if (loading) {
    rerenderPending ||= force;
    return;
  }
  loading = true;
  try {
    const next = await api("/api/cases");
    const key = JSON.stringify(next) + location.hash;
    if (!force && key === fingerprint) {
      byId("connection").textContent = "";
      return;
    }
    cases = next;
    const [id, run] = location.hash.slice(1).split("/");
    const chosen = cases.find(c => encodeURIComponent(c.id) === id) ?? cases[0];
    showQueue(chosen?.id);
    if (!chosen) {
      selectedCase = null;
      byId("case-header").textContent = "";
      byId("case-body").innerHTML = '<p class="empty">Register a verified account using the command line to start a case.</p>';
    } else {
      const detailUrl = `/api/cases/${encodeURIComponent(chosen.id)}`;
      showCase(await api(id === encodeURIComponent(chosen.id) && run ? detailUrl + "?run=" + encodeURIComponent(run)
        : detailUrl), run);
    }
    byId("connection").textContent = "";
    fingerprint = key;
  } catch (error) {
    const connection = byId("connection");
    const message = selectedCase ? "Could not refresh. Showing the last loaded run." :
      "The desk could not load. Check that the local server is running.";
    if (connection.textContent !== message) connection.textContent = message;
  } finally {
    loading = false;
    if (rerenderPending) {
      rerenderPending = false;
      refresh(true);
    }
  }
}

async function runCase(id) {
  if (busy) return;
  busy = true;
  byId("run").setAttribute("aria-disabled", "true");
  byId("run").textContent = "Checking sources…";
  const notice = byId("notice");
  notice.dataset.state = "working";
  notice.textContent = "Checking the configured sources…";
  try {
    await api(`/api/cases/${encodeURIComponent(id)}/run`, {method: "POST", headers: {"X-Ghost-Local": "1"}});
    if (location.hash.split("/")[0] === caseHash(id)) history.replaceState(null, "", caseHash(id));
    notice.dataset.state = "success";
    notice.textContent = "New observations saved.";
  } catch (error) {
    notice.dataset.state = "error";
    notice.textContent = error.message || "Could not complete the check.";
  } finally {
    busy = false;
    await refresh(true);
  }
}

function filterQueue() {
  showQueue(selectedCase);
}
byId("search").addEventListener("input", filterQueue);
byId("filter").addEventListener("change", filterQueue);
byId("skip-case").addEventListener("click", () => (byId("case-title") ?? byId("case-detail")).focus());
window.addEventListener("hashchange", () => refresh(true));
setInterval(() => refresh(), 3000);
refresh();
