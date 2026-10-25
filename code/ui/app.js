"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const enc = value => encodeURIComponent(String(value));
const labels = {INCOMPLETE:"Incomplete", COMPLETE:"Complete", NOT_APPLICABLE:"No deletion", UNRUN:"Not audited"};
const systems = {account_service:"Account service", search_service:"Search index", analytics_platform:"Analytics", support_platform:"Support desk", backup_service:"Backup vault", integration_service:"Sync connectors", security_service:"Security ledger", identity_service:"Account reference", object_storage:"Object storage", legal_service:"Legal holds", marketing_platform:"Audience profiles", email_delivery_service:"Delivery logs", cache_service:"Profile cache"};
const actions = {REPORT_REMAINING_RECORD:"A record remains", REPORT_EXPOSED_PII:"Identifiers remain exposed", REPORT_ACTIVE_DATA_FLOW:"An active process can recreate data", REPORT_RESTORE_RISK:"A restore path remains open", DISABLE_DATA_FLOW:"Disable the data flow", BLOCK_RESTORE:"Block restoration of the subject's data", DELETE_RECORD:"Delete the record", REDACT_RECORD:"Redact prohibited identifiers", ANONYMIZE_RECORD:"Anonymize the record", VERIFY_RECORD_ABSENT:"Verify the record is absent", VERIFY_RECORD_PRESENT:"Verify the retained record is available", VERIFY_RECORD_REDACTED:"Verify prohibited identifiers are removed", VERIFY_RECORD_ANONYMIZED:"Verify the record is irreversibly unlinked", VERIFY_DATA_FLOW_DISABLED:"Verify the data flow is disabled", VERIFY_RESTORE_BLOCKED:"Verify restoration is blocked"};
const states = {PRESENT:"Record present", ABSENT:"Record absent", EXPOSED:"Identifiers exposed", ACTIVE:"Recreation risk", DISABLED:"Flow disabled", BLOCKED:"Restore blocked", REDACTED:"Identifiers redacted", ANONYMIZED:"Unlinked from subject"};
const state = {summary:null, selected:null, detail:null, view:"cases", filter:"all", tab:"trace", resource:null, showExcluded:false, jobTimer:null, caseToken:0};

function date(value, withTime = false) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const d = parsed.toLocaleDateString("en-GB", {day:"2-digit", month:"short", year:withTime ? undefined : "numeric", timeZone:"UTC"});
  return withTime ? `${d} · ${parsed.toLocaleTimeString("en-GB", {hour:"2-digit",minute:"2-digit",timeZone:"UTC"})} UTC` : d;
}
function percent(value) { return `${((value || 0) * 100).toFixed(1)}%`; }
function friendly(system) { return systems[system] || system.replaceAll("_", " "); }
function shortIdentifier(value) { return /^[a-f0-9]{64}$/i.test(value) ? `${value.slice(0, 10)}…${value.slice(-6)} · hash` : value; }
function sourceButton(id) { return id ? `<button class="source-button" data-source="${esc(id)}">${esc(id)} ↗</button>` : '<span class="muted">Planned check</span>'; }
function steps() { return state.detail?.prediction?.steps || []; }
function resources() { return state.detail?.trace?.resources || []; }
function remediationSet() { return new Set(steps().filter(s => s.phase === "REMEDIATION").map(s => `${s.system_id}/${s.resource_id}`)); }
function risky(resource) { return remediationSet().has(`${resource.system}/${resource.resource}`); }

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}
let toastTimer;
function toast(message) {
  const box = $("#toast"); box.textContent = message; box.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => box.hidden = true, 6500);
}

async function loadSummary(keepCase = true) {
  state.summary = await api("/api/summary");
  const s = state.summary;
  $("#corpus-stats").innerHTML = [
    [s.counts.INCOMPLETE || 0, "OPEN", "Require remediation", "red"],
    [s.counts.COMPLETE || 0, "CLEAR", "Corpus verdict", "green"],
    [s.review_required, "REVIEW", "Evidence limitations", ""],
    [s.evidence_files, "SOURCES", "Local evidence files", ""]
  ].map(([n, label, note, color]) => `<div class="stat ${color}"><span>${label}</span><strong>${n}</strong><em>${note}</em></div>`).join("");
  $("#last-run").textContent = s.last_run ? `LAST RUN ${date(s.last_run, true).toUpperCase()}` : "NO AUDIT RUN YET";
  renderQueue();
  const id = keepCase && state.selected && s.cases.some(c => c.case_id === state.selected) ? state.selected : s.cases[0]?.case_id;
  if (id) await selectCase(id);
  else $("#dossier").innerHTML = '<div class="empty-state">No requests are available. Place the participant dataset alongside code/.</div>';
  if (s.job.state === "running") pollJob();
}

function renderQueue() {
  if (!state.summary) return;
  const search = $("#case-search").value.toLocaleLowerCase().trim();
  const cases = state.summary.cases.filter(c =>
    (!search || `${c.case_id} ${c.name} ${c.email}`.toLocaleLowerCase().includes(search)) &&
    (state.filter === "all" || (state.filter === "review" ? c.review_required : c.status === state.filter)));
  $("#case-count").textContent = `${cases.length}/${state.summary.cases.length}`;
  $("#case-list").innerHTML = cases.length ? cases.map(c => `<button class="case-row ${c.case_id === state.selected ? "selected" : ""}" data-case="${esc(c.case_id)}" aria-pressed="${c.case_id === state.selected}">
    <span class="case-row-top"><span class="case-number">${esc(c.case_id.toUpperCase().replace("_", " / "))}</span><span class="case-indicator"><i class="status-dot ${esc(c.status)}"></i>${esc(labels[c.status])}</span></span>
    <strong>${esc(c.name)}</strong><span class="case-row-email">${esc(c.email)}</span>
    <span class="case-row-footer"><span>${c.resources} records${c.review_required ? " · review" : ""}</span><span class="${c.risks ? "risk" : ""}">${c.risks ? `${c.risks} recreation ${c.risks === 1 ? "path" : "paths"} ↗` : `${c.findings} findings`}</span></span>
  </button>`).join("") : '<p class="no-matches">No cases match this search and filter. Try a name, email or case ID.</p>';
}

async function selectCase(caseId) {
  const token = ++state.caseToken;
  $("#dossier").classList.add("loading-dossier");
  try {
    const detail = await api(`/api/case/${enc(caseId)}`);
    if (token !== state.caseToken) return;
    state.selected = caseId; state.detail = detail;
    state.resource = resources().find(risky)?.resource || resources()[0]?.resource || null;
    renderQueue(); renderDossier();
    document.title = `${detail.user.name} — Ghost Protocol`;
  } catch (error) { toast(error.message); }
  finally { if (token === state.caseToken) $("#dossier").classList.remove("loading-dossier"); }
}

function renderDossier() {
  const d = state.detail; if (!d) return;
  const status = d.prediction?.deletion_status || "UNRUN";
  const findings = steps().filter(s => s.phase === "FINDING").length;
  const evidence = [...new Set(resources().map(r => r.evidence))];
  const review = d.review;
  $("#dossier").innerHTML = `<header class="dossier-top">
    <div class="dossier-kicker"><span class="case-tag">${esc(d.request.case_id.toUpperCase().replace("_", " / "))}</span><span>AUDIT CUTOFF</span><span>${esc(date(d.request.audit_at, true).toUpperCase())}</span></div>
    <div class="person-line"><div><h2 class="person-name">${esc(d.user.name)}</h2><p class="email-line">${esc(d.request.email)} <span>↳ ${esc(d.trace.user_id || "request subject")}</span></p></div><div class="stamp ${esc(status)}" aria-label="Audit prediction: ${esc(labels[status])}">${esc(status === "NOT_APPLICABLE" ? "NO DELETION" : status)}</div></div>
    <blockquote class="request-text">${esc(d.request.request_text)}</blockquote>
    ${status === "NOT_APPLICABLE" ? '<div class="review-strip clear">✓ This request does not authorize deletion. No remediation or deletion verification is proposed.</div>' : review.required ? `<div class="review-strip"><span>△</span><span><strong>Review required.</strong> ${esc(review.reasons[0] || "The evidence has unresolved limitations.")} <button class="source-button" data-tab="decision">Read decision notes ↗</button></span></div>` : `<div class="review-strip clear">✓ ${findings ? `${findings} supported ${findings === 1 ? "finding" : "findings"}. The ordered plan is ready for review.` : "The discovered resources meet the supplied policy in the available evidence."}</div>`}
  </header>
  <div class="dossier-tabs" role="tablist" aria-label="Investigation sections">
    ${[["trace","Trace map",resources().length],["remediation","Remediation",steps().length],["evidence","Evidence",evidence.length],["decision","Decision ledger",""]].map(([id,title,count]) => `<button class="tab ${state.tab === id ? "active" : ""}" data-tab="${id}" role="tab" aria-selected="${state.tab === id}" id="tab-${id}" aria-controls="case-panel">${title}${count !== "" ? `<span class="tab-count">${count}</span>` : ""}</button>`).join("")}
  </div><div id="case-panel" class="tab-panel" role="tabpanel" aria-labelledby="tab-${state.tab}"></div>`;
  renderPanel();
}

function renderPanel() {
  const panel = $("#case-panel"); if (!panel) return;
  if (state.detail.prediction?.deletion_status === "NOT_APPLICABLE" && state.tab !== "decision") {
    panel.innerHTML = '<div class="not-applicable"><p class="eyebrow">AUTHORIZATION BOUNDARY</p><h3>A request to keep, not erase.</h3><p>The request was classified as a non-deletion action. The audit proposes an empty action list and does not perform a deletion investigation for this subject.</p></div>';
    return;
  }
  if (state.tab === "trace") renderTrace(panel);
  if (state.tab === "remediation") renderRemediation(panel);
  if (state.tab === "evidence") renderCaseEvidence(panel);
  if (state.tab === "decision") renderDecision(panel);
}

function graph() {
  const grouped = new Map();
  resources().forEach(r => grouped.set(r.system, [...(grouped.get(r.system) || []), r]));
  const groups = [...grouped.entries()].sort((a,b) => Number(b[1].some(risky)) - Number(a[1].some(risky)) || a[0].localeCompare(b[0]));
  if (!groups.length) return '<div class="map-empty">No linked record observations are available.</div>';
  const rows = Math.ceil(groups.length / 2), height = Math.max(290, rows * 82 + 20), cy = height / 2;
  const selected = resources().find(r => r.resource === state.resource);
  let edges = "", nodes = "";
  groups.forEach(([system, records], i) => {
    const right = i >= rows, row = right ? i-rows : i;
    const x = right ? 490 : 20, y = 18 + row * (height-80) / Math.max(rows-1,1), endX = right ? x : x+205;
    const bad = records.filter(risky).length, active = selected?.system === system;
    edges += `<path class="map-edge ${bad ? "risky" : ""}" d="M${right ? 390 : 310},${cy} C${right ? 450 : 250},${cy} ${right ? 440 : 270},${y+29} ${endX},${y+29}"/>`;
    nodes += `<g class="map-node ${bad ? "risky" : ""} ${active ? "active" : ""}" data-system="${esc(system)}" tabindex="0" role="button" aria-label="Inspect ${esc(friendly(system))}, ${records.length} records${bad ? `, ${bad} require remediation` : ""}"><rect x="${x}" y="${y}" width="205" height="59" rx="2"/><circle class="node-state" cx="${x+13}" cy="${y+19}" r="2.7"/><text x="${x+23}" y="${y+22}">${esc(friendly(system))}</text><text class="node-subtitle" x="${x+13}" y="${y+43}">${records.length} ${records.length === 1 ? "record" : "records"} · ${bad ? `${bad} need treatment` : "policy met in evidence"}</text><text class="node-count" x="${x+184}" y="${y+23}" text-anchor="end">${String(records.length).padStart(2,"0")}</text></g>`;
  });
  return `<svg viewBox="0 0 720 ${height}" aria-label="Subject-to-system evidence links"><title>Evidence-linked resource map for ${esc(state.detail.user.name)}</title>${edges}<g class="map-subject"><circle cx="350" cy="${cy}" r="40"/><text x="350" y="${cy-6}" class="subject-title">Subject</text><text x="350" y="${cy+12}">${esc(state.detail.trace.user_id || "identity")}</text></g>${nodes}</svg><div class="mobile-system-list"><p class="section-label">${esc(state.detail.trace.user_id)} → LINKED SYSTEMS</p>${groups.map(([system,records])=>`<button data-system="${esc(system)}" class="mobile-system ${selected?.system===system ? "selected" : ""}"><span><i class="status-dot ${records.some(risky)?"INCOMPLETE":"COMPLETE"}"></i>${esc(friendly(system))}</span><span>${records.length} ${records.length===1?"record":"records"} ↗</span></button>`).join("")}</div>`;
}

function renderTrace(panel) {
  panel.innerHTML = `<div class="section-bar"><h3 class="section-label">01 / SUBJECT-TO-RECORD LINKS</h3><div class="map-legend"><span class="legend-key"><i class="legend-box red"></i>Requires treatment</span><span class="legend-key"><i class="legend-box green"></i>Policy met in evidence</span></div></div>
    <div class="trace-layout"><div class="trace-canvas">${graph()}</div><aside id="trace-inspector" class="trace-inspector" aria-live="polite"></aside></div>
    <div class="map-footnote"><span>Links represent identifier associations, not assumed replication routes.</span><span>SELECT A SYSTEM TO INSPECT ↗</span></div>
    <div class="identity-strip"><h3 class="section-label">IDENTITY TRAIL</h3><div><div class="identifiers">${(state.detail.trace.identifiers || []).map(id => `<span class="identifier ${id === state.detail.user.email?.toLowerCase() ? "current" : ""}" title="${esc(id)}">${esc(shortIdentifier(id))}</span>`).join("")}</div><p class="identity-note">Current and historical identifiers recovered from the supplied records. Names alone do not establish a match.</p></div></div>
    <section class="timeline-section"><div class="timeline-heading"><h3 class="section-label">02 / OBSERVATION TIMELINE</h3><label class="checkbox"><input id="show-excluded" type="checkbox" ${state.showExcluded ? "checked" : ""}>Show observations after cutoff</label></div><div id="timeline" class="timeline"></div></section>`;
  renderInspector(); renderTimeline();
}

function renderInspector() {
  const target = $("#trace-inspector"); if (!target) return;
  const r = resources().find(item => item.resource === state.resource) || resources()[0];
  if (!r) {target.innerHTML = '<p class="inspector-description">No selected resource.</p>'; return;}
  const sameSystem = resources().filter(item => item.system === r.system);
  const rule = state.detail.rules.find(item => item.data_category === r.category);
  const required = r.category === "DATA_FLOW" ? "Disable the process before treating downstream records." : r.category === "BACKUP_ARCHIVE" ? "Preserve the archive and block restoration of the subject's data." : `${rule?.required_action || "Review"} · ${rule?.condition || "Inspect the supplied policy."}`;
  target.innerHTML = `${sameSystem.length > 1 ? `<select id="resource-select" class="resource-select" aria-label="Select record in ${esc(friendly(r.system))}">${sameSystem.map(item => `<option value="${esc(item.resource)}" ${item.resource === r.resource ? "selected" : ""}>${esc(item.resource)}</option>`).join("")}</select>` : ""}
    <div><p class="inspector-label">SELECTED OBSERVATION</p><h3>${esc(friendly(r.system))}</h3><p class="resource-code">${esc(r.resource)}</p><span class="inspector-status ${risky(r) ? "" : "safe"}"><i class="status-dot ${risky(r) ? "INCOMPLETE" : "COMPLETE"}"></i>${esc(states[r.state] || r.state)}</span></div>
    <div><div class="inspector-divider"></div><p class="inspector-description">${esc(required)}</p>${sourceButton(r.evidence)}<time class="inspector-time">Observed ${esc(date(r.time,true))}<br>${esc(r.location)}</time></div>`;
}

function renderTimeline() {
  const timeline = $("#timeline"); if (!timeline) return;
  const events = (state.detail.trace.timeline || []).filter(event => state.showExcluded || event.included);
  timeline.innerHTML = events.length ? events.map(event => `<div class="timeline-event ${event.included ? "" : "excluded"}"><time datetime="${esc(event.time)}">${esc(date(event.time,true))}</time><i class="event-dot"></i><span class="event-resource">${esc(event.resource_id)} ${event.included ? "" : "· EXCLUDED"}</span><span class="event-state">${esc(event.state)}</span></div>`).join("") : '<p class="no-matches">No observation timeline is available. Run the current audit to generate provenance.</p>';
}

function renderRemediation(panel) {
  const all = steps(), complete = state.detail.prediction?.deletion_status === "COMPLETE";
  panel.innerHTML = `<p class="ledger-intro">${complete ? "These checks cite observations supporting the discovered resources' compliant state. Read review notes before treating the result as complete proof." : "A proposed sequence of findings, remediation and final checks. These are instructions for completing the deletion; no production actions have been executed."}</p>`;
  ["FINDING","REMEDIATION","VERIFICATION"].forEach((phase,index) => {
    const items = all.filter(step => step.phase === phase); if (!items.length) return;
    panel.insertAdjacentHTML("beforeend", `<section class="phase-section"><div class="phase-heading"><span class="phase-number">0${index+1}</span><h3>${{FINDING:"What remains",REMEDIATION:"Close the paths. Treat the records.",VERIFICATION:complete ? "Evidence-backed checks" : "Checks that must pass"}[phase]}</h3><span class="muted">${items.length} ${items.length === 1 ? "step" : "steps"}</span></div>${items.map(step => `<div class="step-row"><span class="step-no">${String(step.step_no).padStart(2,"0")}</span><div class="step-main"><strong>${esc(actions[step.operation] || step.operation)}</strong><span>${esc(friendly(step.system_id))} / ${esc(step.resource_id)} → ${esc(step.state)}</span></div><div class="step-proof">${step.evidence_id ? sourceButton(step.evidence_id) : `<span>${phase === "REMEDIATION" ? "PROPOSED ACTION" : "FUTURE CHECK"}</span>`}</div></div>`).join("")}</section>`);
  });
  const retained = all.filter(s => s.operation === "VERIFY_RECORD_PRESENT");
  if (retained.length) panel.insertAdjacentHTML("beforeend", `<p class="retained-note">Preservation is part of completion: ${retained.map(r => esc(r.resource_id)).join(", ")} must remain available under the supplied policy.</p>`);
  if (!all.length) panel.insertAdjacentHTML("beforeend", '<div class="empty-state">No proposed steps are available.</div>');
}

function fileCard(file, compact = false) {
  const kind = file.file_path?.split(".").pop() || "event", filename = file.file_path?.split("/").pop() || file.file_id;
  return `<button class="evidence-item" data-source="${esc(file.file_id)}"><span class="file-kind ${esc(kind)}">${esc(kind.toUpperCase())}</span><span><strong>${esc(filename)}</strong><span class="file-id">${esc(file.file_id)} · ${esc(file.origin || "source event")}</span><small>${esc(date(file.captured_at,true))}${file.coverage?.read ? " · parsed" : ""}${!compact && file.coverage?.low_confidence_lines ? ` · ${file.coverage.low_confidence_lines} OCR lines need review` : ""}</small></span></button>`;
}
async function renderCaseEvidence(panel) {
  panel.innerHTML = '<p class="ledger-intro">Original local artifacts cited by the selected resource observations. Open a source to inspect the underlying record.</p><div class="evidence-list" id="case-evidence-list"></div>';
  const token = state.caseToken;
  try {
    const files = await api("/api/evidence"); if (token !== state.caseToken || state.tab !== "evidence") return;
    const ids = new Set(resources().map(r => r.evidence));
    $("#case-evidence-list").innerHTML = files.filter(f => ids.has(f.file_id)).map(f => fileCard(f,true)).join("") || '<p class="empty-state">No file citations in this case.</p>';
  } catch (error) {toast(error.message);}
}

function renderDecision(panel) {
  const d = state.detail, method = d.trace.intent || {}, review = d.review;
  const links = d.trace.linkage || [];
  const unique = [...new Map(links.map(link => [`${link.resource_id}/${link.basis}/${link.evidence_id}`, link])).values()];
  panel.innerHTML = `<div class="decision-grid"><section class="decision-block"><h3>Authorization</h3><p><strong>${method.authorized ? "Deletion requested" : "No deletion authorized"}</strong> · ${esc(method.method?.replaceAll("_"," ") || "not available")}</p><p>Local character-ngram intent model. The score (${esc(method.score ?? "—")}) is not calibrated probability.</p><p>Reported workflow claim: <strong>${esc(d.request.reported_status)}</strong>. This claim does not prove the current state.</p></section>
    <section class="decision-block"><h3>Scope & uncertainty</h3><p><strong>${review.required ? "Review required" : "No generated review warnings"}</strong></p><p>${esc(review.scope || "Authorization assessment only")}. ${resources().length} linked record observations. ${review.excluded_observations || 0} later observations excluded from the verdict.</p>${review.reasons?.length ? `<ul class="review-list">${review.reasons.map(reason => `<li>${esc(reason)}</li>`).join("")}</ul>` : '<p>Absence of a warning is not an organization-wide deletion certificate.</p>'}</section></div>
    <section class="decision-block"><h3>How the records were linked</h3><p>Exact identifier and explicit catalog links are stronger than a workflow-time candidate. Every proposed action should be reviewed against its source.</p>${unique.length ? unique.map(link => `<div class="link-row"><strong>${esc(link.resource_id)}</strong><span class="basis ${link.basis === "workflow_time" ? "weak" : ""}">${esc(link.basis.replaceAll("_"," "))}</span><div>${(link.identifiers || []).map(id => esc(shortIdentifier(id))).join(" · ") || esc(link.location)}</div>${link.evidence_id ? sourceButton(link.evidence_id) : ""}</div>`).join("") : '<p class="muted">No deletion-resource investigation was performed.</p>'}</section>
    ${d.identity_history.length && method.authorized ? `<section class="decision-block"><h3>Historical identifier changes</h3>${d.identity_history.map(item => `<div class="link-row">${esc(date(item.event_time,true))} · ${esc(item.field_name)}<div>${esc(shortIdentifier(item.old_value))} → ${esc(shortIdentifier(item.new_value))}</div>${sourceButton(item.audit_id)}</div>`).join("")}</section>` : ""}`;
}

async function switchView(view) {
  state.view = ["cases","evidence","evaluation"].includes(view) ? view : "cases";
  $$(".view").forEach(section => section.hidden = section.id !== `${state.view}-view`);
  $$(".nav-button").forEach(button => {button.classList.toggle("active",button.dataset.view === state.view); button.setAttribute("aria-pressed",String(button.dataset.view === state.view));});
  if (location.hash !== `#${state.view}`) history.replaceState(null,"",`#${state.view}`);
  if (state.view === "evidence") await renderLibrary();
  if (state.view === "evaluation") await renderEvaluation();
}

async function renderLibrary() {
  const target = $("#evidence-view"); target.innerHTML = '<div class="empty-state">Opening the evidence library…</div>';
  try {
    const files = await api("/api/evidence");
    const kinds = files.reduce((acc,f) => {const kind = f.file_path.split(".").pop().toUpperCase();acc[kind]=(acc[kind]||0)+1;return acc;},{});
    target.innerHTML = `<div class="view-title"><div><p class="eyebrow muted">THE SOURCE OF RECORD</p><h2>Evidence, not assurances.</h2><p>Every supplied artifact, with its original capture time and extraction coverage.</p></div><span class="mono muted">${files.length} LOCAL FILES</span></div><div class="catalog-toolbar"><label class="search"><input id="evidence-search" type="search" placeholder="Find a filename, source or evidence ID…" aria-label="Search evidence"></label><span class="mono">${Object.entries(kinds).map(([k,v]) => `${v} ${k}`).join(" / ")}</span></div><div id="catalog-grid" class="catalog-grid"></div>`;
    const render = () => {const query = $("#evidence-search").value.toLowerCase(); const visible = files.filter(file => `${file.file_id} ${file.file_path} ${file.origin}`.toLowerCase().includes(query));$("#catalog-grid").innerHTML = visible.map(file => fileCard(file)).join("") || '<p class="empty-state">No evidence matches this search.</p>';};
    $("#evidence-search").addEventListener("input",render);render();
  } catch(error) {target.innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;}
}

async function renderEvaluation() {
  const target = $("#evaluation-view"); target.innerHTML = '<div class="empty-state">Opening measured evaluation…</div>';
  try {
    const result = await api("/api/evaluation"), m = result.metrics, usage = state.summary.usage;
    target.innerHTML = `<div class="view-title"><div><p class="eyebrow muted">QUALITY / WITH THE LIMITS IN VIEW</p><h2>Show the work. Count the misses.</h2><p>Public samples used during development. Hidden-set accuracy is unknown.</p></div><button class="button" id="run-evaluation">↻ Run evaluation</button></div>
      <div class="evaluation-metrics">${[["STATUS ACCURACY",m.status_accuracy,"Final classification",false],["EXACT CASE MATCH",m.exact_case_accuracy,"Status, every step and citation",true],["STEP RECALL",m.step_recall,"Expected steps recovered",false],["FIELD ACCURACY",m.field_accuracy,"Seven required step fields",false]].map(([label,n,note,bad]) => `<div class="evaluation-metric"><p class="section-label">${label}</p><strong class="metric-number ${bad ? "caution" : ""}">${percent(n)}</strong><p>${note}</p></div>`).join("")}</div>
      <div class="evaluation-split"><section><div class="section-bar"><h3 class="section-label">CASE-LEVEL DIFFERENCES / ${(m.differences || []).length}</h3><span class="last-run-label">${m.cases || 0} PUBLIC SAMPLES</span></div><table class="comparison-table"><thead><tr><th>CASE</th><th>EXPECTED → ACTUAL</th><th>MISSING</th><th>EXTRA</th></tr></thead><tbody>${(m.differences || []).map(diff => `<tr><td>${esc(diff.case_id)}</td><td>${esc(labels[diff.expected_status] || diff.expected_status)} → ${esc(labels[diff.actual_status] || diff.actual_status)}</td><td class="error-count">${diff.missing_steps.length}</td><td>${diff.extra_steps.length}</td></tr>`).join("") || '<tr><td colspan="4">No differences have been recorded.</td></tr>'}</tbody></table></section>
      <aside><div class="method-note"><p class="eyebrow">SMALL MODELS. EXPLICIT RULES.</p><h3>Local by design.</h3><p>A multilingual statistical intent model and neural OCR extract facts. Deterministic code applies policy, preserves retained records and orders the plan. No LLM runs in the submitted pipeline.</p><dl><div><dt>Requests processed</dt><dd>${usage.requests || 0}</dd></div><div><dt>Paid API cost</dt><dd>$${Number(usage.api_cost_usd || 0).toFixed(2)}</dd></div><div><dt>LLM calls</dt><dd>${usage.llm_calls || 0}</dd></div><div><dt>Step precision</dt><dd>${percent(m.step_precision)}</dd></div><div><dt>Sequence match</dt><dd>${percent(m.sequence_accuracy)}</dd></div><div><dt>Review required</dt><dd>${state.summary.review_required}</dd></div></dl></div><details class="report-details"><summary>Read the source-backed failure audit ↗</summary><pre id="failure-audit-text"></pre></details></aside></div>`;
    $("#failure-audit-text").textContent = result.failure_audit || "No failure audit has been generated.";
    $("#run-evaluation").addEventListener("click",() => startJob("evaluate"));
  } catch(error) {target.innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;}
}

let sourceToken = 0;
async function openSource(id) {
  const token = ++sourceToken, dialog = $("#source-dialog");
  $("#source-title").textContent = id;
  $("#source-body").innerHTML = '<div class="empty-state">Reading original local evidence…</div>';
  if (!dialog.open) dialog.showModal();
  try {
    const source = await api(`/api/source/${enc(id)}`); if (token !== sourceToken) return;
    $("#source-title").textContent = source.file_path?.split("/").pop() || id;
    $("#source-body").innerHTML = `<div class="source-meta"><span>${esc(id)}</span><span>${esc(source.origin || "Structured source event")}</span><span>CAPTURED ${esc(date(source.captured_at,true))}</span>${source.coverage?.low_confidence_lines ? `<span>${source.coverage.low_confidence_lines} OCR LINES BELOW 0.85 CONFIDENCE</span>` : ""}</div><div class="source-content" id="source-content"></div>`;
    const content = $("#source-content");
    if (["png","jpg","jpeg"].includes(source.kind)) {const img = document.createElement("img");img.src=`/api/evidence/${enc(id)}`;img.alt=`Original evidence ${id}`;content.append(img);}
    else if (source.kind === "pdf") {const frame = document.createElement("iframe");frame.src=`/api/evidence/${enc(id)}`;frame.title=`Original PDF ${id}`;content.append(frame);}
    else {const pre = document.createElement("pre");pre.textContent=source.content || "No extracted content.";content.append(pre);}
    if (source.kind !== "event") {const link=document.createElement("a");link.href=`/api/evidence/${enc(id)}`;link.target="_blank";link.rel="noopener";link.className="source-original";link.textContent="Open original artifact ↗";content.append(link);}
  } catch(error) {$("#source-body").innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;}
}

async function startJob(action) {
  try {
    await api(action === "evaluate" ? "/api/evaluate" : "/api/run", {method:"POST",headers:{"X-Audit-Local":"1"},body:"{}"});
    pollJob();
  } catch(error) {toast(error.message);}
}
async function pollJob() {
  clearTimeout(state.jobTimer);
  try {
    const job = await api("/api/status"), running = job.state === "running";
    $("#run-audit").disabled = running; if ($("#run-evaluation")) $("#run-evaluation").disabled = running;
    $("#run-state").classList.toggle("running",running);
    $("#run-state").innerHTML = `<i></i> ${running ? "AUDIT RUNNING" : "CORPUS LOADED"}`;
    const message = $("#job-message");message.hidden=job.state === "idle";message.textContent=job.message;message.classList.toggle("error",job.state === "error");
    if (running) state.jobTimer = setTimeout(pollJob,850);
    else if (job.state === "done") {await loadSummary();if (state.view === "evaluation") await renderEvaluation(); if(state.view === "evidence") await renderLibrary();}
  } catch(error) {toast(error.message);}
}

document.addEventListener("click", event => {
  const source = event.target.closest("[data-source]"); if (source) return void openSource(source.dataset.source);
  const row = event.target.closest("[data-case]"); if (row) return void selectCase(row.dataset.case);
  const filter = event.target.closest("[data-filter]"); if (filter) {state.filter=filter.dataset.filter;$$("[data-filter]").forEach(button => button.classList.toggle("selected",button===filter));renderQueue();return;}
  const view = event.target.closest("[data-view]"); if (view) return void switchView(view.dataset.view);
  const tab = event.target.closest("[data-tab]"); if (tab) {state.tab=tab.dataset.tab;renderDossier();return;}
  const system = event.target.closest("[data-system]"); if(system) {state.resource=resources().find(r => r.system===system.dataset.system && risky(r))?.resource || resources().find(r => r.system===system.dataset.system)?.resource;renderPanel();}
});
document.addEventListener("keydown", event => {
  if (event.key==="/" && !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName) && !$("#source-dialog").open) {event.preventDefault();switchView("cases");$("#case-search").focus();}
  if (["Enter"," "].includes(event.key) && event.target.matches("[data-system]")) {event.preventDefault();event.target.dispatchEvent(new MouseEvent("click",{bubbles:true}));}
  if (["ArrowLeft","ArrowRight"].includes(event.key) && event.target.matches('[role="tab"]')) {event.preventDefault();const tabs=$$('[role="tab"]');const i=(tabs.indexOf(event.target)+(event.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;state.tab=tabs[i].dataset.tab;renderDossier();$(`#tab-${state.tab}`).focus();}
});
document.addEventListener("change",event => {
  if(event.target.id==="resource-select") {state.resource=event.target.value;renderPanel();}
  if(event.target.id==="show-excluded") {state.showExcluded=event.target.checked;renderTimeline();}
});
$("#case-search").addEventListener("input",renderQueue);
$("#close-source").addEventListener("click",()=>$("#source-dialog").close());
$("#source-dialog").addEventListener("click",event=>{if(event.target===$("#source-dialog")){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
$("#run-audit").addEventListener("click",()=>startJob("run"));
window.addEventListener("hashchange",()=>switchView(location.hash.slice(1)));
loadSummary().then(()=>switchView(location.hash.slice(1)||"cases")).catch(error=>{$("#dossier").innerHTML=`<div class="empty-state">Could not load the local audit. ${esc(error.message)}<br>Start the desk with: python code/ui.py</div>`;});
