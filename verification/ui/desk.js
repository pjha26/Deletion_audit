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
const stampTime = time => time ? new Intl.DateTimeFormat("en-GB", {
  day: "2-digit", month: "short", year: "numeric", hour: "2-digit",
  minute: "2-digit", second: "2-digit", timeZone: "UTC"
}).format(new Date(time)) + " UTC" : "Not scheduled";
const caseHash = (id, run) => `#${encodeURIComponent(id)}${run ? "/" + run : ""}`;
let cases = [];
let fingerprint;
let busy = false;
let loading = false;
let rerenderPending = false;

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
  const focusedHref = queue.contains(document.activeElement) ? document.activeElement.getAttribute("href") : null;
  byId("case-count").textContent = `${visible.length} of ${cases.length}`;
  queue.innerHTML = visible.length ? visible.map(c =>
    `<a href="${caseHash(c.id)}" aria-current="${c.id === id}">
      <strong>${esc(c.id)}</strong>${badge(c.latest?.status)}</a>`).join("") :
    `<p class="empty">${cases.length ? "No cases match these filters." : "No cases registered."}</p>`;
  if (focusedHref) Array.from(queue.querySelectorAll("a")).find(a => a.getAttribute("href") === focusedHref)?.focus();
}

function checkDetails(check, run) {
  const color = check.state === "unknown" ? "review" : check.state === check.expected ? "verified" : "bad";
  return `<details class="check" data-check="${esc(check.id)}">
    <summary><strong>${esc(checkNames[check.id])}</strong>${stamp(check.state, color)}
    <div class="scope">${esc(check.system)} · ${esc(check.scope)}</div></summary>
    <dl><dt>Expected</dt><dd>${esc(check.expected)}</dd>
      <dt>Observed</dt><dd>${esc(stampTime(check.observed_at))}</dd>
      <dt>Evidence</dt><dd>Run ${run.id} / ${esc(check.id)}</dd>
      <dt>Result</dt><dd>${esc(check.reason)}</dd>
      <dt>Matches</dt><dd>${esc(check.matches ?? "Not counted")}</dd></dl></details>`;
}

function showCase(c, selected) {
  const run = c.runs.find(item => String(item.id) === selected) ?? c.runs[0];
  const open = new Set(Array.from(byId("case-body").querySelectorAll("details[open]"), el => el.dataset.check));
  byId("case-header").innerHTML = `<div class="case-head"><div><h2>${esc(c.id)}</h2>
    <p>${badge(run?.status)} <span class="time">${run ? esc(stampTime(run.collected_at)) : ""}</span></p></div>
    <div class="actions"><button class="button primary" id="run" type="button">Run verification</button>
    ${run ? `<a class="button" href="/api/cases/${encodeURIComponent(c.id)}/reports/${run.id}" download>Download report</a>` : ""}</div></div>`;
  byId("run").addEventListener("click", () => runCase(c.id));
  byId("run").disabled = busy;
  if (!run) {
    byId("case-body").innerHTML = '<p class="empty">Run verification to collect the first set of observations.</p>';
    return;
  }
  const recurrence = run.reappearances.map(e =>
    `<p><strong>${esc(checkNames[e.check])} returned.</strong>
      <a href="${caseHash(c.id, e.previous_run)}">Run ${e.previous_run}</a> found it absent at ${esc(stampTime(e.absent_at))}.
      <a href="${caseHash(c.id, e.present_run ?? run.id)}">Run ${e.present_run ?? run.id}</a>
      found it present at ${esc(stampTime(e.present_at))}.</p>`).join("");
  const review = run.review.length ? `<p><strong>Evidence needs review.</strong>
    Open the ${esc(run.review.map(id => checkNames[id]).join(", "))} check for details.</p>` : "";
  const followUp = run.guidance.length ? `<section class="followup"><h2>Proposed follow-up</h2>
    <ul>${run.guidance.map(text => `<li>${esc(text)}</li>`).join("")}</ul></section>` : "";
  byId("case-body").innerHTML = `${recurrence || review ? `<div class="alert">${recurrence}${review}</div>` : ""}
    <div class="details-grid"><section><h2>Checks and evidence</h2>
      <p class="coverage">${run.checks.filter(c => c.state !== "unknown").length} of ${run.checks.length} conclusive checks
      · ${esc(run.policy)}</p>${run.checks.map(check => checkDetails(check, run)).join("")}${followUp}</section>
      <section class="timeline"><h2>Run history</h2>
      <p class="coverage">Next recheck · ${esc(stampTime(c.next_due))}</p>
      <ol>${c.runs.map(item => `<li><a href="${caseHash(c.id, item.id)}" aria-current="${item.id === run.id}">
        <strong>Run ${item.id} · ${esc(item.trigger)}</strong> ${badge(item.status)}
        <span class="time">${esc(stampTime(item.collected_at))}</span></a></li>`).join("")}</ol>
      </section></div>`;
  for (const detail of byId("case-body").querySelectorAll("details")) {
    detail.open = open.has(detail.dataset.check);
  }
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
    if (!force && key === fingerprint) return;
    cases = next;
    const [id, run] = location.hash.slice(1).split("/");
    const chosen = cases.find(c => encodeURIComponent(c.id) === id) ?? cases[0];
    showQueue(chosen?.id);
    if (!chosen) {
      byId("case-header").textContent = "";
      byId("case-body").innerHTML = '<p class="empty">Register a verified account using the command line to start a case.</p>';
    } else {
      const focused = document.activeElement.id === "run";
      const detailUrl = `/api/cases/${encodeURIComponent(chosen.id)}`;
      showCase(await api(id === encodeURIComponent(chosen.id) && run ? detailUrl + "?run=" + encodeURIComponent(run)
        : detailUrl), run);
      if (focused) byId("run")?.focus();
    }
    fingerprint = key;
  } catch (error) {
    byId("notice").textContent = error.message || "The verification desk could not load.";
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
  byId("run").disabled = true;
  byId("notice").textContent = "Checking the configured sources…";
  try {
    await api(`/api/cases/${encodeURIComponent(id)}/run`, {method: "POST", headers: {"X-Ghost-Local": "1"}});
    if (location.hash.split("/")[0] === caseHash(id)) history.replaceState(null, "", caseHash(id));
    byId("notice").textContent = "New observations saved.";
  } catch (error) {
    byId("notice").textContent = error.message || "Could not complete the check.";
  } finally {
    busy = false;
    await refresh(true);
  }
}

function filterQueue() {
  showQueue(document.querySelector("#cases a[aria-current=true]")?.getAttribute("href")?.slice(1) ??
            byId("case-header").querySelector("h2")?.textContent);
}
byId("search").addEventListener("input", filterQueue);
byId("filter").addEventListener("change", filterQueue);
window.addEventListener("hashchange", () => refresh(true));
setInterval(() => refresh(), 3000);
refresh();
