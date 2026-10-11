/* CV Studio page logic. Talks only to tools/ui.py on 127.0.0.1. All text goes in via textContent. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const main = $("#main");
const PAGE_LOADED = Date.now() / 1000;
const STATE_LABEL = { "jd only": "New", draft: "Draft", approved: "Approved", rendered: "Final", none: "Empty" };
const STATE_CLASS = { "jd only": "jd", draft: "draft", approved: "approved", rendered: "rendered", none: "jd" };
const KIND = {
  extract: { title: "Extractor", verb: "Drafting your CV", done: "Draft ready", agent: true },
  revise: { title: "Applying your answers", verb: "Applying your answers", done: "Answers applied", agent: true },
  preview: { title: "Preview", verb: "Rendering a preview", done: "Preview ready", agent: false },
  render: { title: "Final render", verb: "Rendering your final CV", done: "Final CV ready", agent: false },
  ask: { title: "Interviewer", verb: "Preparing your questions", done: "Your questions are ready", agent: true },
  next: { title: "Interview round", verb: "Recording your answers", done: "Answers recorded", agent: true },
  finish: { title: "Finishing the interview", verb: "Finishing the interview", done: "Interview finished", agent: true },
  curate: { title: "Curator", verb: "Updating your master CV", done: "Curator finished", agent: true },
  refresh: { title: "Ranking refresh", verb: "Re-ranking your master CV", done: "Ranking refreshed", agent: true },
  goals: { title: "Goals drafter", verb: "Drafting your goals", done: "Goals draft ready", agent: true },
};
const EXP_STATE = {
  stub: ["New", "jd"], interviewing: ["Interviewing", "running-static"], interviewed: ["To curate", "draft"],
  condensed: ["In CV", "rendered"], archived: ["Archived", "jd"], planned: ["Planned", "planned"],
  updated: ["Update to curate", "draft"],   // in the master CV, but the notes changed since
};
const CHANGE_RE = /^Change requested in (UI|chat)$/;
const MOD = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘↩" : "Ctrl+Enter";

let apps = [];
let active = {};
let current = null;      // slug
let detail = null;
const tab = {};          // slug -> tab name
const badges = {};       // slug -> Set(tab)
const seen = {};         // slug -> Set(question text), to animate only new cards
let poll = null;         // {jobId, slug, since, lines, view, timer}, where slug is the job key
let offline = false;
const SCOPES = ["apps", "exps", "master", "goals"];   // the sidebar tabs
let scope = SCOPES.includes(store0("cvs-scope")) ? store0("cvs-scope") : "apps";   // a stale stored value falls back to apps
const expPick = { status: store0("cvs-exp-status") || "", type: store0("cvs-exp-type") || "", year: store0("cvs-exp-year") || "", sort: store0("cvs-exp-sort") || "new" };
let exps = [];
let reviewPending = false;
let expDetail = null;
let masterData = null;

function store0(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
const isExpKey = (k) => typeof k === "string" && k.startsWith("exp:");
const expSlug = (k) => k.slice(4);

/* ---------- small helpers ---------- */

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(n.style, v);
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid);
  return n;
}

function svg(markup, cls = "") {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();  // static, author-written markup only
  const s = t.content.firstChild;
  if (cls) s.setAttribute("class", cls);
  return s;
}
const ICON = {
  check: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" class="ring"/><path d="M7 12.5l3.2 3.2L17.5 8.5" class="tick"/></svg>',
  cross: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" class="ring"/><path d="M8.5 8.5l7 7M15.5 8.5l-7 7" class="tick"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" class="ring"/><path d="M10 8.5v7M14 8.5v7" class="tick"/></svg>',
  close: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  file: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 1.5h5l3 3v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M9 1.5V4.5h3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5.5 8.5h5M5.5 11h3.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  pen: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10.5 2.5l3 3L6 13H3v-3z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  doc: '<svg viewBox="0 0 120 96" aria-hidden="true" class="illus"><rect x="30" y="10" width="52" height="68" rx="7" class="i-page"/><path d="M40 28h30M40 38h22M40 46h28M40 54h18" class="i-line"/><path d="M92 14c1.4 7.6 4.4 10.6 12 12-7.6 1.4-10.6 4.4-12 12-1.4-7.6-4.4-10.6-12-12 7.6-1.4 10.6-4.4 12-12z" class="i-spark"/><path d="M48 70h26" class="i-sign"/></svg>',
};

function hash(text) {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch (e) { /* private mode */ } },
};

function fmtTime(sec) {
  sec = Math.max(0, Math.round(sec));
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function announce(text) { $("#announce").textContent = text; }

/* ---------- network ---------- */

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-CV-UI": "1" }, body: JSON.stringify(body),
  };
  let res;
  try { res = await fetch(path, opts); }
  catch (e) { goOffline(); const err = new Error("CV Studio isn't running"); err.offline = true; throw err; }
  if (offline) backOnline();
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) { const err = new Error(data.error || res.statusText); err.data = data; err.status = res.status; throw err; }
  return data;
}

function goOffline() {
  if (offline) return;
  offline = true;
  $("#offline").hidden = false;
  setDocStatus("idle");
  const retry = async () => {
    try { await fetch("/api/ping"); backOnline(); }
    catch (e) { setTimeout(retry, 3000); }
  };
  setTimeout(retry, 3000);
}

async function backOnline() {
  if (!offline) return;
  offline = false;
  $("#offline").hidden = true;
  toast("Reconnected to CV Studio", { type: "ok" });
  await loadList().catch(() => {});
  if (current) reopen(current).catch(() => {});
}

/* ---------- what an agent said, readable ---------- */

const SAID = { "interview.md": "Interview record", "index.md": "Notes", "thin": "Still thin", "closes": "Closes", "tracker": "Added to your to-do list",
  "master-cv.md": "Master CV", "quantify?": "Needs numbers", "new tags": "New tags", "skipped": "Skipped", "open": "Question for you",
  "proposal": "Proposal", "changed": "Changed", "kept": "Kept", "not done": "Not done", "extraction.md": "Draft", "questions": "Questions" };

/** An agent's final message: its "label: value" lines as a short list (dropping the "none" ones), the full text under a toggle. */
function agentSaid(message) {
  const rows = [];
  for (const line of (message || "").split("\n")) {
    const m = line.match(/^\s*([A-Za-z.?\- ]{2,24}):\s*(.+)$/);
    if (m && !/^none\b/i.test(m[2].trim())) rows.push([SAID[m[1].trim().toLowerCase()] || m[1].trim(), m[2].trim()]);
  }
  const raw = el("details", { class: "raw-said" }, el("summary", { text: "Show exactly what the agent wrote" }), el("pre", { class: "said", text: message }));
  if (!rows.length) return el("div", {}, el("pre", { class: "said", text: message }));
  return el("div", {}, el("dl", { class: "said-table" }, ...rows.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", {}, inline(v))])), raw);
}

/* ---------- toasts, dialogs, busy buttons ---------- */

function toast(msg, { type = "info", action = null, sticky = type === "error" } = {}) {
  const t = el("div", { class: `toast ${type}`, role: type === "error" ? "alert" : "status" },
    type === "ok" ? svg(ICON.check, "t-icon") : type === "error" ? svg(ICON.cross, "t-icon") : null,
    el("span", { class: "t-msg", text: msg }),
    action ? el("button", { class: "t-action", type: "button", onclick: () => { action.fn(); close(); } }, action.label) : null,
    sticky ? el("button", { class: "t-close", type: "button", "aria-label": "Dismiss", onclick: () => close() }, svg(ICON.close)) : null);
  const close = () => { t.classList.remove("show"); setTimeout(() => t.remove(), 250); };
  $("#toasts").append(t);
  requestAnimationFrame(() => t.classList.add("show"));
  if (!sticky) setTimeout(close, 3600);
}

function confirmBox(title, body, yes) {
  return chooseBox(title, body, yes).then((v) => v === "yes");
}

/** Like confirmBox, with an optional second action: resolves "yes", "alt" or "no". */
function chooseBox(title, body, yes, alt = null) {
  const d = $("#confirm-dialog");
  $("#confirm-title").textContent = title;
  $("#confirm-body").textContent = body;
  $("#confirm-yes").textContent = yes;
  $("#confirm-alt").textContent = alt || "";
  $("#confirm-alt").hidden = !alt;
  d.returnValue = "";
  d.showModal();
  $("#confirm-yes").focus();   // Enter confirms. The form's first submit button is Cancel, so implicit submission would cancel
  return new Promise((resolve) => d.addEventListener("close", () => resolve(d.returnValue || "no"), { once: true }));
}

/** Run fn with btn showing a spinner and an -ing label. Ignores double clicks. Check on success, shake on failure. */
async function busy(btn, label, fn) {
  if (!btn || btn.dataset.busy) return;
  btn.dataset.busy = "1";
  const old = [...btn.childNodes];
  btn.style.minWidth = `${btn.offsetWidth}px`;
  btn.disabled = true;
  btn.replaceChildren(el("span", { class: "spinner small" }), el("span", { text: label }));
  try {
    const r = await fn();
    if (btn.isConnected) {
      btn.replaceChildren(svg(ICON.check, "btn-check"));
      await new Promise((ok) => setTimeout(ok, 450));
    }
    return r;
  } catch (e) {
    if (btn.isConnected) { btn.classList.remove("shake"); void btn.offsetWidth; btn.classList.add("shake"); }
    if (!e.offline) toast(e.message, { type: "error" });
    throw e;
  } finally {
    if (btn.isConnected) { btn.replaceChildren(...old); btn.disabled = false; delete btn.dataset.busy; btn.style.minWidth = ""; }
  }
}

/* ---------- tab title and favicon ---------- */

const favicon = { img: null, status: "idle" };
(() => { const i = new Image(); i.onload = () => { favicon.img = i; drawFavicon(); }; i.src = "/static/icon.png"; })();

function drawFavicon() {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  if (favicon.img) g.drawImage(favicon.img, 0, 0, 64, 64);
  const color = { working: "#0a84ff", done: "#30d158", failed: "#ff453a" }[favicon.status];
  if (color) {
    g.beginPath(); g.arc(50, 14, 13, 0, Math.PI * 2); g.fillStyle = "#fff"; g.fill();
    g.beginPath(); g.arc(50, 14, 10, 0, Math.PI * 2); g.fillStyle = color; g.fill();
  }
  try { $("#favicon").href = c.toDataURL("image/png"); } catch (e) { /* tainted canvas */ }
}

function setDocStatus(status, text = "") {
  const titles = { idle: "CV Studio", working: `⏳ ${text} · CV Studio`, done: `✓ ${text || "Done"} · CV Studio`, failed: `⚠ ${text || "Failed"} · CV Studio` };
  document.title = titles[status];
  if (favicon.status !== status) { favicon.status = status; drawFavicon(); }
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && (favicon.status === "done" || favicon.status === "failed")) setTimeout(() => setDocStatus("idle"), 1500);
});

/* ---------- sidebar ---------- */

async function loadList() {
  const [a, x, tr] = await Promise.all([api("/api/apps"), api("/api/exp"), api("/api/tracker")]);
  todoData = tr;
  const waiting = tr.items.filter((i) => i.section === tr.waiting).length;
  $("#todo-count").textContent = String(waiting);
  $("#todo-count").hidden = !waiting;
  apps = a.apps;
  active = a.active;
  exps = x.exps;
  reviewPending = x.review;
  goalsSummary = x.goals;
  renderList();
}

function pill(state, running) {
  if (running) return el("span", { class: "pill running" }, el("span", { class: "dot" }), "Working");
  return el("span", { class: `pill ${STATE_CLASS[state] || "jd"}` }, STATE_LABEL[state] || state);
}

function renderList() {
  renderScopeDots();
  if (scope === "exps") return renderExpList();
  if (scope === "master") return renderMasterNav();
  if (scope === "goals") return renderGoalsNav();
  renderAppList();
}

function renderAppList() {
  const nav = $("#app-list");
  nav.replaceChildren();
  if (!apps.length) nav.append(el("div", { class: "empty-list", text: "No applications yet." }));
  for (const a of apps) {
    const [company, ...role] = a.slug.slice(8).split("-");
    nav.append(el("button", { class: "app-item", type: "button", "aria-current": a.slug === current ? "true" : "false",
                               onclick: () => openApp(a.slug) },
      el("div", { class: "name" }, el("span", { text: a.company || company.toUpperCase() }), pill(a.state, active[a.slug])),
      el("div", { class: "role", text: a.role || role.join(" ") }),
      el("div", { class: "meta" }, el("span", { text: a.slug.slice(0, 7) }),
         a.unticked && a.state === "draft" ? el("span", { text: `· ${a.unticked} open question${a.unticked > 1 ? "s" : ""}` }) : null)));
  }
}

/* ---------- loading an application ---------- */

function skeletonMain() {
  return el("div", { class: "main-inner" },
    el("div", { class: "sk-head" }, el("div", { class: "sk w30 tall" }), el("div", { class: "sk w50" })),
    el("div", { class: "sk w60 seg" }),
    el("div", { class: "card" }, ...["w90", "w80", "w70", "w85"].map((w) => el("div", { class: `sk ${w}` }))));
}

async function openApp(slug, opts = {}) {
  if (scope !== "apps") setScope("apps", false);
  if (current !== slug) { parkPoll(); }
  const switching = current !== slug, prev = current;
  current = slug;
  setHash(slug);
  const slow = switching ? setTimeout(() => main.replaceChildren(skeletonMain()), 150) : null;
  try { detail = await api(`/api/apps/${encodeURIComponent(slug)}`); }
  catch (e) { return navFailed(prev, e); }
  finally { clearTimeout(slow); }
  if (current !== slug) return;
  if (opts.tab) tab[slug] = opts.tab;
  renderList();
  renderMain({ fade: switching });
  const job = detail.job;
  if (job && job.status === "running" && (!poll || poll.jobId !== job.id)) startPoll(job.id, slug);
  if (job && job.status === "running") store.set(`cvs-running:${slug}`, JSON.stringify({ id: job.id, kind: job.kind }));
  else checkInterrupted(slug, job);
}

async function checkInterrupted(slug, job) {
  const raw = store.get(`cvs-running:${slug}`);
  if (!raw) return;
  const was = JSON.parse(raw);
  if (job && job.id === was.id) { store.set(`cvs-running:${slug}`, ""); return; }
  try { await api(`/api/jobs/${was.id}?since=99999`); store.set(`cvs-running:${slug}`, ""); }
  catch (e) {
    if (e.status === 404 && current === slug) { interrupted[slug] = was; rerenderCurrent(); }
  }
}
const interrupted = {};

function defaultTab() {
  if (detail.state === "draft") return "questions";
  if (detail.state === "approved" || detail.state === "rendered") return "preview";
  return "overview";
}

function renderMain({ fade = false } = {}) {
  const d = detail;
  const running = d.job && d.job.status === "running";
  const ext = d.extraction;
  const t = tab[d.slug] || defaultTab();
  tab[d.slug] = t;
  (badges[d.slug] || new Set()).delete(t);

  const head = el("div", { class: "head" },
    el("div", { class: "head-text" },
      el("h1", { text: d.company }),
      el("div", { class: "sub" }, el("span", { text: d.role }), pill(d.state, running), el("code", { text: d.slug }))),
    el("div", { class: "actions" }, ...headerActions(d, running)));

  const tabs = [["overview", "Overview"]];
  if (ext) tabs.push(["questions", "Questions", ext.unticked]);
  tabs.push(["preview", "Preview"], ["log", "Activity"], ["files", "Files"]);
  const seg = el("div", { class: "segmented tabs", role: "tablist" },
    ...tabs.map(([k, label, n]) => el("button", { type: "button", role: "tab", "aria-selected": String(t === k),
      onclick: () => { tab[d.slug] = k; if (k === "preview") openApp(d.slug); else renderMain(); } },  // preview: re-read, it may be stale
      label, n ? el("span", { class: "count", text: String(n) }) : null,
      badges[d.slug] && badges[d.slug].has(k) ? el("span", { class: "badge-dot", "aria-label": "new" }) : null)));

  const body = { overview: viewOverview, questions: viewQuestions, preview: viewPreview, log: viewLog, files: viewFiles }[t]();
  const inner = el("div", { class: `main-inner${fade ? " enter" : ""}` }, head, flowStepper(d), runOrResult(d), seg, body);
  main.replaceChildren(inner);
  autogrowAll();
}

function flowStepper(d) {
  const steps = ["Job description", "Draft", "Vet", "Approve", "Final PDF"];
  const at = { "jd only": 1, draft: 2, approved: 4, rendered: 5 }[d.state] ?? 0;
  return el("ol", { class: "flow", "aria-label": "Progress" },
    ...steps.map((s, i) => el("li", { class: i < at ? "done" : i === at ? "now" : "", "aria-current": i === at ? "step" : null },
      el("span", { class: "flow-dot" }, i < at ? svg(ICON.check, "flow-check") : null), el("span", { text: s }))));
}

function headerActions(d, running) {
  const ext = d.extraction;
  const out = [];
  if (d.state === "jd only") {
    out.push(el("button", { class: "btn primary", disabled: running, title: "The extractor reads the job description and your master CV and drafts a tailored CV with questions for you. A few minutes.", onclick: (e) => runAction("extract", {}, e.currentTarget, "Starting…") }, "Draft my CV"));
  }
  if (d.state === "draft") {
    out.push(el("button", { class: "btn", disabled: running, onclick: (e) => runAction("preview", {}, e.currentTarget, "Rendering…", "preview") }, "Preview"));
    let why = null;
    if (running) why = "Wait for the current run to finish.";
    else if (ext.pending) why = "Some answers have not been applied yet.";
    else if (ext.unticked) why = `${ext.unticked} open question${ext.unticked > 1 ? "s" : ""} still need an answer.`;
    out.push(el("button", { class: "btn primary", disabled: !!why, title: why || "Approve this CV for rendering", onclick: approve }, "Approve"));
  }
  if (d.state === "approved") {
    out.push(el("button", { class: "btn", disabled: running, onclick: (e) => runAction("preview", {}, e.currentTarget, "Rendering…", "preview") }, "Preview"));
    out.push(el("button", { class: "btn primary", disabled: running, onclick: (e) => runAction("render", {}, e.currentTarget, "Rendering…", "preview") }, "Render final CV"));
  }
  if ((d.state === "approved" || d.state === "rendered") && !running) {
    out.push(el("button", { class: "text-btn", onclick: (e) => reopenApp(e.currentTarget) }, "Reopen to edit"));
  }
  if (d.state === "rendered" && d.final_pdf) {
    out.push(el("button", { class: "text-btn", disabled: running, onclick: rerender }, "Re-render"));
    out.push(el("a", { class: "btn green", href: fileUrl(d.final_pdf.name) + "&download=1", download: d.final_pdf.name }, "Download PDF"));
  }
  return out;
}

/* ---------- run panel and result card ---------- */

function runOrResult(d) {
  const job = d.job;
  if (job && job.status === "running") return runPanel(poll && poll.jobId === job.id && poll.view ? poll.view : job);
  if (interrupted[current]) return resultCard({ status: "interrupted", kind: interrupted[current].kind, id: interrupted[current].id });
  if (job && job.ended && !dismissed(job.id) && Date.now() / 1000 - job.ended < 1800) return resultCard(job);
  return null;
}

function progressRatio(elapsed, typ) {
  if (!typ) return null;
  const r = elapsed / typ;
  return r <= 1 ? 0.85 * r : 0.85 + 0.1 * (1 - Math.exp(-(r - 1) * 2));
}

function runPanel(v) {
  const k = KIND[v.kind] || { verb: v.kind, agent: false };
  const elapsed = (v.now || Date.now() / 1000) - v.started;
  const stop = k.agent ? el("button", { class: "text-btn danger", type: "button", id: "run-stop", onclick: (e) => stopJob(v, e.currentTarget) }, "Stop") : null;
  const panel = el("section", { class: "run", id: "run", "aria-label": `${k.verb} in progress` },
    el("div", { class: "run-head" },
      el("div", { class: "spinner" }),
      el("div", { class: "run-title" }, el("strong", { text: k.verb }), el("span", { class: "muted", id: "run-time" })),
      stop),
    el("div", { class: "bar", id: "run-bar" }, el("div", { class: "fill" })),
    v.stages && v.stages.length > 1 ? el("ol", { class: "stages", id: "run-stages" },
      ...v.stages.map((s, i) => el("li", {}, el("span", { class: "st-dot" }), el("span", { text: s })))) : null,
    el("div", { class: "latest mono", id: "run-latest" }),
    el("details", { class: "run-log" }, el("summary", { text: "Show full log" }), el("div", { class: "log mono", id: "log" })));
  requestAnimationFrame(() => updateRunPanel(v, elapsed));
  return panel;
}

function updateRunPanel(v, elapsed) {
  if (!$("#run")) return;
  const typ = v.typical;
  const slow = typ && elapsed > typ * 2;
  $("#run-time").textContent = typ
    ? ` ${fmtTime(elapsed)} · ${slow ? "taking longer than usual, still working" : `usually about ${fmtTime(typ)}`}`
    : ` ${fmtTime(elapsed)}${KIND[v.kind] && KIND[v.kind].agent ? " · usually 1 to 3 minutes" : ""}`;
  const bar = $("#run-bar"), r = progressRatio(elapsed, typ);
  bar.classList.toggle("indeterminate", r === null);
  if (r !== null) bar.firstChild.style.width = `${Math.round(r * 1000) / 10}%`;
  const stages = $("#run-stages");
  if (stages) {
    [...stages.children].forEach((li, i) => {
      const cls = i < v.stage ? "done" : i === v.stage ? "now" : "";
      if (li.className !== cls) {
        li.className = cls;
        if (cls === "now") announce(v.stages[i]);
        const dot = li.firstChild;
        dot.replaceChildren(cls === "done" ? svg(ICON.check, "st-check") : "");
      }
    });
  }
  const latest = $("#run-latest");
  if (latest && latest.textContent !== (v.latest || "Starting…")) latest.textContent = v.latest || "Starting…";
  const log = $("#log");
  if (log && poll && log.childElementCount < poll.lines.length) {
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
    for (const l of poll.lines.slice(log.childElementCount)) log.append(logLine(l));
    if (atBottom) log.scrollTop = log.scrollHeight;
  }
}

function dismissed(id) { return store.get(`cvs-dismissed:${id}`) === "1"; }

function nextStep(job) {
  const n = job.result && job.result.unticked;
  if (job.kind === "extract" || job.kind === "revise") {
    if (n) return { label: `Answer ${n} question${n > 1 ? "s" : ""} →`, fn: () => goTab("questions") };
    return { label: "Preview, then approve →", fn: () => goTab("preview") };
  }
  if (job.kind === "ask" || job.kind === "next") {
    const q = job.result && job.result.questions;
    return q ? { label: `Answer ${q} question${q > 1 ? "s" : ""} →`, fn: () => goTab("interview") } : { label: "Finish the interview →", fn: () => goTab("interview") };
  }
  if (job.kind === "finish" || job.kind === "curate" || job.kind === "refresh") {
    return job.result && job.result.review && reviewPending ? { label: "Review the change →", fn: () => goTab("changes") } : null;   // not once it was kept or undone
  }
  if (job.kind === "goals") return job.result && job.result.review ? { label: "Review the draft →", fn: () => goTab("review") } : null;
  if (job.kind === "preview") return { label: "See preview →", fn: () => goTab("preview") };
  if (job.kind === "render") return { label: "Open the final PDF →", fn: () => goTab("preview") };
  return null;
}

function retry(kind) {
  if (kind === "ask") return () => expAction("ask");
  if (kind === "next") return () => expAction("next", { mtime: expDetail.interview.mtime, answers: {}, other: "" });
  if (kind === "finish") return () => expAction("finish", { mtime: expDetail.interview.mtime, answers: {}, other: "" });
  if (kind === "curate") return () => expAction("curate");
  if (kind === "refresh") return () => masterAction("refresh");
  if (kind === "goals") return () => goalsPost("draft", { retry: true });
  if (kind === "extract") return () => runAction("extract");
  if (kind === "revise") return () => runAction("revise");
  if (kind === "preview") return () => runAction("preview", {}, null, null, "preview");
  if (kind === "render") return () => (detail.state === "rendered" ? rerender() : runAction("render", {}, null, null, "preview"));
  return null;
}

function resultCard(job) {
  const k = KIND[job.kind] || { title: job.kind, done: "Finished" };
  const close = el("button", { class: "icon-btn", type: "button", "aria-label": "Dismiss", onclick: () => {
    store.set(`cvs-dismissed:${job.id}`, "1"); delete interrupted[current]; store.set(`cvs-running:${current}`, "");
    const c = $("#result"); if (c) { c.classList.add("leave"); setTimeout(() => rerenderCurrent(), 200); }
  } }, svg(ICON.close));
  let icon, title, sub, body = [], actions = [];
  if (job.status === "done") {
    icon = svg(ICON.check, "res-icon ok");
    title = k.done;
    sub = `Finished in ${fmtTime(job.ended - job.started)}`;
    if (job.result && job.result.interviewer) body.push(agentSaid(job.result.interviewer));
    if (job.result && job.result.message) body.push(agentSaid(job.result.message));
    if (job.result && job.result.new_tags) body.push(el("div", { class: "banner warn" }, el("div", { class: "grow", text: `New tag added to CLAUDE.md: ${job.result.new_tags}. Keep it, or Undo the change to veto it.` })));
    if (job.result && job.result.dropped && job.result.dropped.length) {
      body.push(el("div", { class: "hint", text: `To fit one page, ${job.result.dropped.length} bullet${job.result.dropped.length > 1 ? "s were" : " was"} trimmed: ${job.result.dropped.map((x) => `${x.entry} (“${x.bullet.split(" ").slice(0, 6).join(" ")}…”)`).join("; ")}.` }));
    }
    const ns = nextStep(job);
    if (ns) actions.push(el("button", { class: "btn primary", type: "button", onclick: ns.fn }, ns.label));
  } else if (job.status === "stopped") {
    icon = svg(ICON.pause, "res-icon warn");
    title = `${k.title} stopped`;
    sub = job.result && job.result.rolled_back ? `Rolled back: ${job.result.rolled_back}.` : "Nothing was changed.";
    const r = retry(job.kind); if (r) actions.push(el("button", { class: "btn", type: "button", onclick: r }, "Run again"));
  } else if (job.status === "interrupted") {
    icon = svg(ICON.pause, "res-icon warn");
    title = "This run was interrupted";
    sub = "CV Studio restarted while it was running. Your files are as they were before the run, apart from anything it had already saved.";
    const r = retry(job.kind); if (r) actions.push(el("button", { class: "btn primary", type: "button", onclick: r }, "Retry"));
  } else {
    icon = svg(ICON.cross, "res-icon bad");
    title = `${k.title} failed`;
    sub = friendlyError(job.error) + (job.result && job.result.rolled_back ? ` Rolled back: ${job.result.rolled_back}.` : "");
    const r = retry(job.kind); if (r) actions.push(el("button", { class: "btn primary", type: "button", onclick: r }, "Retry"));
    actions.push(el("button", { class: "text-btn", type: "button", onclick: () => goTab("log") }, "Show details"));
  }
  return el("section", { class: `result ${job.status}`, id: "result", tabindex: "-1", "aria-label": title },
    el("div", { class: "res-head" }, icon, el("div", { class: "res-title" }, el("strong", { text: title }), el("span", { class: "muted", text: sub })), close),
    ...body, actions.length ? el("div", { class: "res-actions" }, ...actions) : null);
}

function friendlyError(err) {
  if (!err) return "Something went wrong.";
  if (/did not finish cleanly/.test(err)) return "The extractor stopped before finishing. Retry usually works; Show details has the log.";
  if (/without a result/.test(err)) return "Claude Code exited early (often a usage limit or a network blip). Try again in a minute.";
  if (/timed out/.test(err)) return "It took over 15 minutes and was stopped.";
  if (/refused/.test(err)) return err.replace(/^RuntimeError: /, "");
  return err.replace(/^\w+Error: /, "");
}

function goTab(t) {
  tab[current] = t;
  if (t === "preview" && detail && detail.slug === current) openApp(current);  // re-read: the preview may be older than the draft
  else rerenderCurrent();
  main.scrollTo({ top: 0, behavior: "smooth" });
}
function rerenderCurrent() { if (current === "master") renderMaster(); else if (current === "goals") renderGoals(); else if (isExpKey(current)) renderExp(); else renderMain(); }
/** Each page gets its own history entry, so the browser's Back button moves between pages instead of leaving. */
function setHash(key) {
  const h = key === "master" || key === "goals" || key === "todo" ? key : isExpKey(key) ? `exp/${expSlug(key)}` : key || "";
  $("#todo-btn").setAttribute("aria-current", String(key === "todo"));
  try { if (decodeURIComponent(location.hash.slice(1)) !== h) history.pushState(null, "", h ? `#${h}` : location.pathname); } catch (e) { /* sandbox */ }
}

/** A page that could not load because the server is down: stay where you were and say why. */
function navFailed(prev, e) {
  if (!e.offline) throw e;
  current = prev;
  setHash(prev);
  toast("CV Studio isn't running, so that page can't open yet. It reconnects by itself when the server is back.", { type: "error", sticky: false });
}

function reopen(key) { if (key === "todo") return openTodo(); if (key === "master") return openMaster(); if (key === "goals") return openGoals(); if (isExpKey(key)) return openExp(expSlug(key)); return openApp(key); }

/* ---------- views ---------- */

function emptyState(title, text, action) {
  return el("div", { class: "card empty" }, svg(ICON.doc), el("h3", { text: title }), el("p", { text }), action || null);
}

function viewOverview() {
  const d = detail;
  const running = d.job && d.job.status === "running";
  const ext = d.extraction;
  let next = null;
  if (d.state === "jd only" && !running) {
    next = emptyState("Ready to draft your CV",
      "The extractor reads this job description and your master CV, then drafts a tailored CV with questions for you. It runs on your Claude login and takes a few minutes.",
      el("button", { class: "btn primary", title: "The extractor reads the job description and your master CV and drafts a tailored CV with questions for you. A few minutes.", onclick: (e) => runAction("extract", {}, e.currentTarget, "Starting…") }, "Draft my CV"));
  } else if (d.state === "draft") {
    next = el("div", { class: "card next" }, el("h3", { text: ext.unticked ? `${ext.unticked} question${ext.unticked > 1 ? "s" : ""} for you` : "Ready to approve" }),
      el("p", { class: "muted", text: ext.unticked ? "Answer them in your own words. The extractor applies your answers and checks every citation again." : "Check the preview, then approve. Nothing changes the content after approval." }),
      el("button", { class: "btn primary", onclick: () => goTab(ext.unticked ? "questions" : "preview") }, ext.unticked ? "Answer questions →" : "See preview →"));
  } else if (d.state === "approved") {
    next = el("div", { class: "card next" }, el("h3", { text: "Approved" }), el("p", { class: "muted", text: "Render the final one-page PDF. It takes a few seconds." }),
      el("button", { class: "btn primary", disabled: running, onclick: (e) => runAction("render", {}, e.currentTarget, "Rendering…", "preview") }, "Render final CV"));
  } else if (d.state === "rendered" && d.final_pdf) {
    next = el("div", { class: "card next" }, el("h3", { text: "Your CV is ready" }), el("p", { class: "muted", text: "Review the PDF before you send it." }),
      el("div", { class: "row-actions" }, el("button", { class: "btn", onclick: () => goTab("preview") }, "Review"),
        el("a", { class: "btn green", href: fileUrl(d.final_pdf.name) + "&download=1", download: d.final_pdf.name }, "Download PDF")));
  }
  const jdCard = docCard("Job description", d.jd || "(no jd.md)", d.state === "jd only");
  if (!running && d.jd) jdCard.querySelector("summary").append(el("button", { type: "button", class: "text-btn",
    onclick: (e) => { e.preventDefault(); e.stopPropagation(); editJd(); } }, "Edit"));
  const editing = ext && draftEditing[d.slug] && d.state === "draft";
  return el("div", {}, editing ? null : next, ext ? (editing ? draftEditor(ext) : selectedCard(ext)) : null, jdCard, running ? null : manageCard(d));
}

const draftEditing = {};   // app slug -> true while Edit draft is open
const DRAFT_SECTIONS = ["Experience", "Projects", "Hackathons and case competitions", "Leadership & Co-Curricular Activities"];

/** Edit draft: your own changes to extraction.md, written by code. Every bullet keeps its citation. */
function draftEditor(ext) {
  const d = detail, ed = ext.editable;
  const list = el("div", { class: "draft-entries" });
  const bulletRow = (b = { text: "", source: "" }) => {
    const ta = el("textarea", { rows: "2", class: "b-text", "aria-label": "Bullet" }); ta.value = b.text;
    const src = el("input", { type: "text", class: "b-src", placeholder: "experiences/<slug>/index.md L12", "aria-label": "Source" }); src.value = b.source;
    const row = el("div", { class: "bullet-row" }, ta, el("label", { class: "b-meta1" }, "Source ", src),
      el("div", { class: "row-actions" },
        el("button", { type: "button", class: "text-btn", onclick: () => row.previousElementSibling && row.parentNode.insertBefore(row, row.previousElementSibling) }, "Up"),
        el("button", { type: "button", class: "text-btn", onclick: () => row.nextElementSibling && row.parentNode.insertBefore(row.nextElementSibling, row) }, "Down"),
        el("button", { type: "button", class: "text-btn danger", onclick: () => row.remove() }, "Remove")));
    return row;
  };
  for (const e of ed.entries) {
    const bullets = el("div", { class: "bullet-rows" }, ...e.bullets.map(bulletRow));
    const sec = el("select", { class: "e-section", "aria-label": "Section" }, ...DRAFT_SECTIONS.map((x) => el("option", { value: x, text: x })));
    sec.value = e.section;
    const card = el("div", { class: "card draft-entry", "data-line": e.line },
      el("div", { class: "card-head" }, el("h3", { text: e.heading }),
        el("div", { class: "row-actions" },
          el("button", { type: "button", class: "text-btn", onclick: () => card.previousElementSibling && list.insertBefore(card, card.previousElementSibling) }, "Up"),
          el("button", { type: "button", class: "text-btn", onclick: () => card.nextElementSibling && list.insertBefore(card.nextElementSibling, card) }, "Down"),
          el("button", { type: "button", class: "text-btn danger", onclick: () => { card.dataset.removed = "1"; card.hidden = true; } }, "Remove from this CV"))),
      el("label", { class: "inline-field" }, "Section ", sec), bullets,
      el("button", { type: "button", class: "text-btn", onclick: () => bullets.append(bulletRow()) }, "Add a bullet"));
    list.append(card);
  }
  const edu = el("textarea", { rows: String(Math.max(3, ed.education.length + 1)), class: "wide", "aria-label": "Education lines" }); edu.value = ed.education.join("\n");
  const skills = el("textarea", { rows: "2", class: "wide", "aria-label": "Skills line" }); skills.value = ed.skills;
  const save = el("button", { class: "btn primary", onclick: async (ev) => {
    const cards = [...list.children];
    const body = {
      mtime: ext.mtime,
      entries: cards.filter((c) => !c.dataset.removed).map((c) => ({ line: c.dataset.line, section: c.querySelector(".e-section").value,
        bullets: [...c.querySelectorAll(".bullet-row")].map((r) => ({ text: r.querySelector(".b-text").value, source: r.querySelector(".b-src").value })) })),
      removed: cards.filter((c) => c.dataset.removed).map((c) => c.dataset.line),
      education: edu.value.split("\n"), skills: skills.value };
    try {
      await busy(ev.currentTarget, "Saving…", () => api(`/api/apps/${encodeURIComponent(d.slug)}/edit-draft`, body));
      draftEditing[d.slug] = false;
      toast("Draft saved. The preview updates by itself.", { type: "ok" });
      await openApp(d.slug);
    } catch (e) { if (e.status === 409) openApp(d.slug); }
  } }, "Save draft");
  return el("div", {},
    el("div", { class: "card next" }, el("h3", { text: "Edit draft" }),
      el("p", { class: "muted", text: "Reorder, move, remove or reword anything. Every bullet keeps its source line, and a new bullet needs one. The style rules are checked when you save. If the page runs over, the renderer drops the last bullet of the lowest-scored entry first, so put what you'd cut last." })),
    list,
    el("div", { class: "card" }, el("h3", { text: "Education" }), el("p", { class: "hint", text: "One line each. Keep the (source: …) on lines that have one." }), edu),
    el("div", { class: "card" }, el("h3", { text: "Skills line" }), skills),
    el("div", { class: "footer-bar" }, el("div", { class: "footer-info" }),
      el("div", { class: "row-actions" }, el("button", { class: "text-btn", onclick: () => { draftEditing[d.slug] = false; renderMain(); } }, "Cancel"), save)));
}

function editJd() {
  const d = detail;
  const body = (d.jd || "").split("\n\n").slice(2).join("\n\n");
  formDialog("Edit job description", d.state === "jd only" ? "" : "The draft was made from the current text. After editing, Re-extract to start over from the new one.", [
    { name: "jd", label: "Job description", type: "textarea", rows: "14", value: body, required: true },
  ], "Save", async (v) => {
    const r = await api(`/api/apps/${encodeURIComponent(d.slug)}/edit-jd`, v);
    toast(r.stale ? "Saved. Re-extract (bottom of Overview) to redo the draft from it." : "Saved", { type: "ok" });
    await openApp(d.slug);
  });
}

/** Start over, or delete: the two things you'd otherwise do by hand in the folder. */
function manageCard(d) {
  const acts = [];
  if (d.state === "draft" || d.state === "approved") acts.push(el("button", { class: "btn", onclick: async (e) => {
    const btn = e.currentTarget;
    const ok = await confirmBox("Re-extract from scratch?", "The current draft and its previews move to drafts/ (nothing is lost), then the extractor starts over from the job description and your master CV. A few minutes.", "Re-extract");
    if (!ok) return;
    try {
      const r = await busy(btn, "Starting…", () => api(`/api/apps/${encodeURIComponent(d.slug)}/reextract`, {}));
      store.set(`cvs-running:${d.slug}`, JSON.stringify({ id: r.job, kind: "extract" }));
      await openApp(d.slug); startPoll(r.job, d.slug); loadList();
    } catch (err) { /* toast shown */ }
  } }, "Re-extract"));
  acts.push(el("button", { class: "text-btn danger", onclick: async (e) => {
    const btn = e.currentTarget;
    const ok = await confirmBox(`Delete ${d.company}, ${d.role}?`, "The folder moves to tools/trash/, so you can still get it back by hand. Its tracker rows are removed.", "Delete");
    if (!ok) return;
    try {
      const r = await busy(btn, "Deleting…", () => api(`/api/apps/${encodeURIComponent(d.slug)}/delete`, {}));
      toast(`Deleted. It's in ${r.trash} if you need it back.`, { type: "ok" });
      current = null; await loadList();
      if (apps[0]) openApp(apps[0].slug); else main.replaceChildren(el("div", { class: "main-inner enter" }, emptyState("No applications yet", "Paste a job description to draft your first tailored CV.")));
    } catch (err) { /* toast shown */ }
  } }, "Delete application"));
  return el("div", { class: "card" }, el("h3", { text: "Manage this application" }), el("div", { class: "row-actions" }, ...acts));
}

async function reopenApp(btn) {
  const ok = await confirmBox("Reopen for editing?", "It goes back to a draft you can edit and approve again. The final PDF moves to drafts/, so nothing is lost.", "Reopen");
  if (!ok) return;
  try { await busy(btn, "Reopening…", () => api(`/api/apps/${encodeURIComponent(detail.slug)}/reopen`, {})); tab[detail.slug] = "overview"; await openApp(detail.slug); loadList(); }
  catch (e) { /* toast shown */ }
}

const signed = (n) => (n > 0 ? `+${n}` : String(n));

/** The entries the extractor kept, each with its score out of 10, its why line and the four-part breakdown.
    A draft written before the extractor broke scores down has no score: line, so the card shows the recency term computed here. */
function selectedCard(ext) {
  const entries = ext.entries || [];
  if (!entries.length) return null;
  const rows = entries.map((e) => {
    const b = e.breakdown;
    const parts = b ? `tags ${b.tags} · relevance ${b.relevance} · goals ${signed(b.goals)} · recency ${signed(b.recency)}`
      : `No breakdown in this draft. Recency against the JD date (${ext.jd_date}): ${signed(e.recency)}.`;
    return el("div", { class: "sel-row" },
      el("div", { class: "sel-head" }, el("span", { class: "sel-title", text: e.heading }),
        e.score !== null ? el("span", { class: "score-pill", text: `${e.score}/10` }) : null),
      e.why ? el("div", { class: "muted", text: e.why }) : null,
      el("div", { class: `hint${b ? "" : " sel-nobreak"}`, text: parts }));
  });
  const canEdit = detail.state === "draft" && !(detail.job && detail.job.status === "running");
  return el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", { text: "Selected entries" }),
      el("div", { class: "row-actions" }, el("span", { class: "muted", text: `${entries.length} on the CV` }),
        canEdit ? el("button", { class: "text-btn", onclick: () => { draftEditing[detail.slug] = true; renderMain(); } }, "Edit draft") : null)),
    el("p", { class: "hint", text: "Scored from the master CV: tags and keywords (up to 6), direct relevance (up to 3), your goals (+1 to -1) and recency (+1 to -1). Ties go to the more recent entry." }),
    ...rows);
}

function draftKey(slug, key) { return `cvs-draft:${slug}:${key}`; }

function viewQuestions() {
  const d = detail, ext = d.extraction;
  if (!ext) return emptyState("No draft yet", "Run the extractor first.");
  const running = d.job && d.job.status === "running";
  const applying = running && d.job.kind === "revise";
  const editable = d.state === "draft" && !running;
  const qs = ext.questions;
  const known = seen[d.slug] || (seen[d.slug] = new Set());
  const fresh = known.size > 0;
  const wrap = el("div", { class: "questions" });
  if (d.state === "draft" && ext.pending && !running) {
    wrap.append(el("div", { class: "banner warn" }, el("div", { class: "grow", text: `${ext.pending} answer${ext.pending > 1 ? "s are" : " is"} saved but not applied yet.` }),
      el("button", { class: "btn primary", onclick: (e) => runAction("revise", {}, e.currentTarget, "Applying…") }, "Apply now")));
  }
  const card = el("div", { class: "card" });
  if (!qs.length) card.append(el("div", { class: "muted", text: "No open questions." }));
  let stagger = 0;
  for (const q of qs) {
    const isChange = CHANGE_RE.test(q.text);
    const openQ = !q.ticked && !q.answers.length;
    const pending = !q.ticked && q.answers.length;
    const isNew = fresh && !known.has(q.text);
    known.add(q.text);
    const trail = [];
    if (!isChange) for (const a of q.answers) trail.push(["You", a, pending]);
    else for (const a of q.answers.slice(0, -1)) trail.push(["You", a, false]);
    for (const a of q.decisions) trail.push([isChange ? "Done" : "Extractor", a, false]);
    const tag = pending ? el("span", { class: `tag ${applying ? "applying" : "waiting"}`, text: applying ? "applying…" : "not applied yet" }) : null;
    const node = el("div", { class: `q${q.ticked ? " done" : ""}${isChange ? " change" : ""}${isNew ? " appear" : ""}`, style: isNew ? { "--i": stagger++ } : null },
      el("div", { class: "num" }, q.ticked ? svg(ICON.check, "num-check") : isChange ? svg(ICON.pen) : String(q.index + 1)),
      isChange
        ? el("div", { class: "text" }, el("span", { class: "kicker", text: "Your change" }), el("span", { text: q.answers[q.answers.length - 1] || "" }), tag)
        : el("div", { class: "text" }, el("span", { text: q.text })),
      trail.length || (!isChange && tag) ? el("div", { class: "trail" },
        ...trail.map(([who, txt, p]) => el("div", { class: p ? "pending" : "" }, el("b", { text: who.toUpperCase() }), el("span", {}, txt, p ? tag.cloneNode(true) : null)))) : null,
      openQ && editable ? el("textarea", { "data-q": String(q.index), "data-key": hash(q.text), rows: "1", placeholder: "Your answer, in your own words (leave blank to skip)",
                                           "aria-label": `Answer to question ${q.index + 1}` }) : null,
      openQ && editable && !isChange ? el("button", { class: "text-btn skip", title: "Tick it without changing the draft or running the extractor",
        onclick: (e) => dismissQuestion(q.index, e.currentTarget) }, "Dismiss, no change needed") : null);
    card.append(node);
  }
  wrap.append(card);
  if (editable) {
    wrap.append(el("div", { class: "card other" }, el("h3", { text: "Other changes" }),
      el("div", { class: "hint", text: "Anything else to change on this CV, e.g. \"drop the oldest project\" or \"lead with the dashboard bullet\"." }),
      el("textarea", { "data-q": "other", "data-key": "other", rows: "2", placeholder: "Optional", "aria-label": "Other changes" })));
    const counter = el("span", { class: "hint", id: "answered" });
    const saved = el("span", { class: "hint saved", id: "draft-saved", text: "Saved in this browser" });
    wrap.append(el("div", { class: "footer-bar" },
      el("div", { class: "footer-info" }, counter, el("span", { class: "hint kbd", text: `${MOD} to apply` }), saved),
      el("button", { class: "btn primary", id: "apply-btn", onclick: (e) => submitAnswers(e.currentTarget) }, "Apply my answers")));
    for (const ta of wrap.querySelectorAll("textarea[data-key]")) {
      ta.value = store.get(draftKey(d.slug, ta.dataset.key)) || "";
      ta.addEventListener("input", () => onDraftInput(ta));
      ta.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); submitAnswers($("#apply-btn")); } });
    }
    requestAnimationFrame(updateCounter);
  }
  return wrap;
}

async function dismissQuestion(index, btn) {
  try { await busy(btn, "Dismissing…", () => api(`/api/apps/${encodeURIComponent(detail.slug)}/dismiss`, { index, mtime: detail.extraction.mtime })); await openApp(detail.slug); loadList(); }
  catch (e) { if (e.status === 409) openApp(detail.slug); }
}

let savedTimer = null;
function onDraftInput(ta) {
  autogrow(ta);
  store.set(draftKey(current, ta.dataset.key), ta.value.trim() ? ta.value : "");
  updateCounter();
  const s = $("#draft-saved");
  if (s) { s.classList.add("show"); clearTimeout(savedTimer); savedTimer = setTimeout(() => s.classList.remove("show"), 1200); }
}

function updateCounter() {
  const boxes = [...main.querySelectorAll("textarea[data-q]")].filter((t) => t.dataset.q !== "other");
  const c = $("#answered");
  if (c) c.textContent = boxes.length ? `${boxes.filter((t) => t.value.trim()).length} of ${boxes.length} answered` : "";
}

function autogrow(ta) { ta.style.height = "auto"; ta.style.height = `${Math.min(ta.scrollHeight + 2, 420)}px`; }
function autogrowAll() { main.querySelectorAll("textarea").forEach(autogrow); }

function fileUrl(name, v) {
  return `/files/${encodeURIComponent(detail.slug)}/${name.split("/").map(encodeURIComponent).join("/")}?v=${v || Date.now()}`;
}

function a4Skeleton(label) {
  return el("div", { class: "pdf-frame" }, el("div", { class: "a4 sk-page" },
    el("div", { class: "sk w50 tall center" }), el("div", { class: "sk w70 thin center" }),
    ...["w30", "w90", "w85", "w80", "w30", "w90", "w75", "w85", "w70", "w30", "w90", "w80"].map((w) => el("div", { class: `sk ${w}` })),
    label ? el("div", { class: "a4-label" }, el("span", { class: "spinner small" }), el("span", { text: label })) : null));
}

const autoPreviewed = {};  // app slug -> the extraction.md mtime a preview was auto-started for (a refused render never loops)

function viewPreview() {
  const d = detail;
  const running = d.job && d.job.status === "running";
  const updating = d.preview_pdf ? "Updating the preview with your latest changes…" : "Rendering your CV…";
  if (running && (d.job.kind === "preview" || d.job.kind === "render")) return a4Skeleton(d.job.kind === "render" ? "Rendering your final CV…" : updating);
  const f = d.state === "rendered" ? d.final_pdf : d.preview_pdf;
  const can = d.state === "draft" || d.state === "approved";
  if (can && !running && d.extraction && (!f || d.preview_stale) && autoPreviewed[d.slug] !== d.extraction.mtime) {
    autoPreviewed[d.slug] = d.extraction.mtime;
    setTimeout(() => runAction("preview", {}, null, null, "preview"), 0);
    return a4Skeleton(updating);
  }
  if (!f) {
    return emptyState("No preview yet", can ? "Render a preview to see the real page before you approve." : "Run the extractor first.",
      can ? el("button", { class: "btn primary", disabled: running, onclick: (e) => runAction("preview", {}, e.currentTarget, "Rendering…", "preview") }, "Make a preview") : null);
  }
  const url = fileUrl(f.name, f.v);
  const frame = el("iframe", { src: url, title: "CV PDF", class: "loading", onload: (e) => { e.currentTarget.classList.remove("loading"); const s = e.currentTarget.previousSibling; if (s) s.remove(); } });
  return el("div", { class: "pdf-frame" },
    el("div", { class: "pdf-bar" },
      el("span", { class: "muted", text: d.state === "rendered" ? `Final · ${f.name}` : `Preview · ${f.name}` },
        d.state !== "rendered" && d.preview_stale ? el("span", { class: "tag waiting", text: "Older than your latest changes" }) : null),
      el("div", { class: "actions" },
        d.state !== "rendered" ? el("button", { class: "text-btn", disabled: running, onclick: (e) => runAction("preview", {}, e.currentTarget, "Rendering…", "preview") }, "Refresh preview") : null,
        el("a", { class: "text-btn", href: url, target: "_blank", rel: "noopener" }, "Open in new tab"))),
    el("div", { class: "pdf-stack" }, el("div", { class: "a4 sk-page under" }, ...["w50", "w70", "w30", "w90", "w85", "w80", "w30", "w90"].map((w) => el("div", { class: `sk ${w}` }))), frame));
}

function viewLog() {
  const job = detail.job;
  if (!job) return emptyState("Nothing has run yet", "Activity from the extractor and renders appears here.");
  const wrap = el("div", {});
  const r = job.result || {};
  if (job.status !== "running" && r.message) wrap.append(el("div", { class: "card" }, el("h3", { text: "The extractor said" }), agentSaid(r.message)));
  if (r.diff) {
    const diff = el("div", { class: "diff mono" });
    for (const line of r.diff.split("\n")) {
      const cls = line.startsWith("@@") ? "hunk" : line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : "";
      diff.append(el("div", { class: cls, text: line || " " }));
    }
    wrap.append(el("div", { class: "card" }, el("details", { open: true }, el("summary", { text: "What changed in extraction.md" }), diff)));
  }
  if (r.problems) wrap.append(el("div", { class: "card" }, el("h3", { text: "Why the render was refused" }), ...r.problems.map((p) => el("div", { class: "mono", text: `• ${p}` }))));
  if (job.status === "running") return el("div", {}, wrap, el("p", { class: "hint", text: "The live log is in the panel above (Show full log)." }));
  const log = el("div", { class: "log mono" });
  wrap.append(el("div", { class: "card" }, el("h3", { text: `${(KIND[job.kind] || {}).title || job.kind}: ${job.status}` }), log));
  api(`/api/jobs/${job.id}?since=0`).then((v) => { for (const l of v.lines) log.append(logLine(l)); }).catch(() => log.append(el("div", { class: "hint", text: "The full log is gone (CV Studio restarted since)." })));
  return wrap;
}

function logLine(l) {
  return el("div", { class: l.kind }, el("span", { class: "ts", text: fmtTime(l.t) }), el("span", { text: l.text }));
}

function viewFiles() {
  const d = detail;
  const links = [];
  if (d.final_pdf) links.push(["Final PDF", d.final_pdf.name]);
  if (d.preview_pdf) links.push(["Preview PDF", d.preview_pdf.name]);
  return el("div", {},
    links.length ? el("div", { class: "card" }, el("h3", { text: "Rendered" }), el("div", { class: "files-list" },
      ...links.map(([label, name]) => el("a", { href: fileUrl(name), target: "_blank", rel: "noopener" }, label)))) : null,
    d.extraction ? docCard("extraction.md", d.extraction.raw, false) : null,
    docCard("jd.md", d.jd || "", false),
    d.drafts.length ? el("div", { class: "card" }, el("h3", { text: "drafts/" }), el("div", { class: "files-list" },
      ...d.drafts.map((n) => el("a", { href: fileUrl(`drafts/${n}`), target: "_blank", rel: "noopener" }, n)))) : null);
}

/* ---------- markdown (small, safe: builds DOM nodes, never innerHTML) ---------- */

let docMode = store.get("cvs-doc-mode") || "formatted";

function docCard(title, text, open) {
  const body = el("div", {});
  const seg = el("div", { class: "segmented small doc-toggle", role: "radiogroup", "aria-label": "View as" });
  const show = (mode) => {
    body.replaceChildren(mode === "source" ? el("pre", { text }) : markdown(text));
    seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.v === mode)));
  };
  for (const [v, label] of [["formatted", "Formatted"], ["source", "Source"]]) {
    seg.append(el("button", { type: "button", role: "radio", "data-v": v, onclick: (ev) => {
      ev.preventDefault(); docMode = v; store.set("cvs-doc-mode", v); show(v);
    } }, label));
  }
  show(docMode);
  return el("div", { class: "card" }, el("details", { open }, el("summary", {}, el("span", { text: title }), seg), body));
}

function inline(text) {
  const frag = document.createDocumentFragment();
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\((https?:\/\/[^)\s]+)\))|(https?:\/\/[^\s)<>]+[^\s)<>.,;:!?])|(\*[^*\s][^*]*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) frag.append(text.slice(last, m.index));
    const t = m[0];
    if (m[1]) frag.append(el("code", { text: t.slice(1, -1) }));
    else if (m[2]) frag.append(el("strong", {}, inline(t.slice(2, -2))));
    else if (m[3]) frag.append(el("a", { href: m[4], target: "_blank", rel: "noopener noreferrer", text: t.slice(1, t.indexOf("](")) }));
    else if (m[5]) frag.append(el("a", { href: t, target: "_blank", rel: "noopener noreferrer", text: t }));
    else if (m[6]) frag.append(el("em", {}, inline(t.slice(1, -1))));
    last = m.index + t.length;
  }
  if (last < text.length) frag.append(text.slice(last));
  return frag;
}

function markdown(src) {
  const root = el("div", { class: "md" });
  const lines = src.replace(/\r\n?/g, "\n").replace(/<!--[\s\S]*?-->/g, "").split("\n");
  let para = [], list = null;
  const flushPara = () => { if (para.length) { root.append(el("p", {}, inline(para.join(" ")))); para = []; } };
  for (const line of lines) {
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    const ul = line.match(/^\s*[-*•]\s+(.*)$/);
    const ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    const task = ul && ul[1].match(/^\[( |x|X)\]\s+(.*)$/);
    if (!line.trim()) { flushPara(); list = null; continue; }
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { flushPara(); list = null; root.append(el("hr")); continue; }
    if (h) { flushPara(); list = null; root.append(el(`h${Math.min(h[1].length + 1, 6)}`, {}, inline(h[2]))); continue; }
    if (ul || ol) {
      flushPara();
      const tag = ul ? "ul" : "ol";
      if (!list || list.tagName.toLowerCase() !== tag) { list = el(tag); root.append(list); }
      const li = el("li", {});
      if (task) { li.className = "task"; li.append(el("span", { class: "box", text: task[1] === " " ? "○" : "✓" }), inline(task[2])); }
      else li.append(inline(ul ? ul[1] : ol[2]));
      list.append(li);
      continue;
    }
    if (/^\s{2,}\S/.test(line) && list && list.lastChild) { list.lastChild.append(el("br"), inline(line.trim())); continue; }
    if (/^>\s?/.test(line)) { flushPara(); list = null; root.append(el("blockquote", {}, inline(line.replace(/^>\s?/, "")))); continue; }
    list = null;
    para.push(line.trim());
  }
  flushPara();
  return root;
}

/* ---------- actions ---------- */

async function runAction(verb, body = {}, btn = null, label = null, thenTab = null) {
  const go = async () => {
    const r = await api(`/api/apps/${encodeURIComponent(current)}/${verb}`, body);
    if (thenTab) tab[current] = thenTab;
    delete interrupted[current];
    await openApp(current);
    if (r.job) { store.set(`cvs-running:${current}`, JSON.stringify({ id: r.job, kind: verb === "answers" ? "revise" : verb })); startPoll(r.job, current); }
    loadList();
    return r;
  };
  try {
    return btn ? await busy(btn, label || "Working…", go) : await go();
  } catch (e) {
    if (e.data && e.data.confirm === "rerender") return rerender();
    if (!btn && !e.offline) toast(e.message, { type: "error" });
    if (e.status === 409) openApp(current);
  }
}

async function submitAnswers(btn) {
  const boxes = [...main.querySelectorAll("textarea[data-q]")];
  const answers = {};
  let other = "";
  for (const ta of boxes) {
    if (!ta.value.trim()) continue;
    if (ta.dataset.q === "other") other = ta.value.trim(); else answers[ta.dataset.q] = ta.value;
  }
  if (!Object.keys(answers).length && !other) { toast("Type at least one answer first."); return; }
  const slug = current;
  try {
    const r = await busy(btn, "Applying…", () => api(`/api/apps/${encodeURIComponent(slug)}/answers`, { mtime: detail.extraction.mtime, answers, other }));
    for (const ta of boxes) { store.set(draftKey(slug, ta.dataset.key), ""); ta.value = ""; }   // the stale-answer fix
    if (r.skipped && r.skipped.length) toast(r.skipped.length > 1 ? `${r.skipped.length} answers were skipped: those questions were already answered.` : "1 answer was skipped: that question was already answered.");
    store.set(`cvs-running:${slug}`, JSON.stringify({ id: r.job, kind: "revise" }));
    await openApp(slug);
    startPoll(r.job, slug);
    loadList();
  } catch (e) {
    if (e.status === 409) openApp(slug);
  }
}

async function approve(e) {
  const btn = e.currentTarget;
  let stale = detail.preview_stale;
  try { stale = (await api(`/api/apps/${encodeURIComponent(current)}`)).preview_stale; } catch (err) { /* keep what the page knows */ }
  if (stale) {
    const v = await chooseBox("Your preview is older than your latest changes",
      "Update it to check the real page before you sign off. Approving is your sign-off: nothing changes the content after it.",
      "Update preview", "Approve anyway");
    if (v === "yes") return runAction("preview", {}, null, null, "preview");
    if (v !== "alt") return;
  } else {
    const ok = await confirmBox("Approve this CV?",
      "This is your sign-off: nothing changes the content after approval. Then you can render the final PDF.", "Approve");
    if (!ok) return;
  }
  try {
    await busy(btn, "Approving…", () => api(`/api/apps/${encodeURIComponent(current)}/approve`, { mtime: detail.extraction.mtime }));
    toast("Approved. Render the final CV when ready.", { type: "ok" });
    tab[current] = "overview";
    await openApp(current);
    loadList();
  } catch (err) { openApp(current); }
}

async function rerender() {
  const ok = await confirmBox("Render again?", "The current PDF and cv.html move to drafts/ with a version number, then the final CV is rendered again from the approved extraction.", "Re-render");
  if (ok) runAction("render", { confirm_rerender: true }, null, null, "preview");
}

async function stopJob(v, btn) {
  const k = KIND[v.kind] || { title: v.kind };
  const ok = await confirmBox(`Stop ${k.title.toLowerCase()}?`,
    v.kind === "revise" ? "The draft goes back to exactly how it was before this run. Your answers are kept, so you can apply them again." :
    v.kind === "goals" ? "The draft is thrown away. goals.md was never touched, so there is nothing to roll back." :
    ["ask", "next"].includes(v.kind) ? "Your notes and the interview record go back to how they were before this run. Your typed answers are kept." :
    ["finish", "curate", "refresh"].includes(v.kind) ? "Your master CV and notes go back to how they were before this run. Nothing from it is kept." :
    "The half-written draft is removed. Your job description is kept, so you can run it again.", "Stop");
  if (!ok) return;
  try { await busy(btn, "Stopping…", () => api(`/api/jobs/${v.id}/stop`, {})); } catch (e) { /* toast shown */ }
}

/* ---------- job polling ---------- */

function stopPoll() { if (poll) clearTimeout(poll.timer); poll = null; }

/** Leaving a page while its run goes on: keep watching that run in the background, so its finish still shows. */
const parked = new Map();   // job id -> slug
function parkPoll() {
  if (poll) parked.set(poll.jobId, poll.slug);
  stopPoll();
  if (parked.size && !parkPoll.timer) parkPoll.timer = setTimeout(watchParked, 2500);
}

async function watchParked() {
  parkPoll.timer = null;
  for (const [id, slug] of [...parked]) {
    if (poll && poll.jobId === id) { parked.delete(id); continue; }   // its page is open again
    let v;
    try { v = await api(`/api/jobs/${id}?since=1000000`); }
    catch (e) { if (e.status === 404) parked.delete(id); continue; }
    if (v.status === "running") continue;
    parked.delete(id);
    await jobEnded(slug, v);
  }
  if (parked.size && !parkPoll.timer) parkPoll.timer = setTimeout(watchParked, 2500);
}

function startPoll(jobId, slug) {
  stopPoll();
  parked.delete(jobId);
  poll = { jobId, slug, since: 0, lines: [], view: null, timer: null };
  tick();
}

async function tick() {
  const p = poll;
  if (!p) return;
  let v;
  try { v = await api(`/api/jobs/${p.jobId}?since=${p.since}`); }
  catch (e) {
    if (poll !== p) return;
    if (e.status === 404) { stopPoll(); interrupted[p.slug] = JSON.parse(store.get(`cvs-running:${p.slug}`) || "{}"); if (current === p.slug) reopen(p.slug); setDocStatus("failed", "Interrupted"); return; }
    p.timer = setTimeout(tick, 3000); return;
  }
  if (poll !== p) return;
  p.since = v.next;
  p.lines.push(...v.lines);
  p.view = v;
  const elapsed = v.now - v.started;
  if (v.status === "running") {
    if (current === p.slug) updateRunPanel(v, elapsed);
    setDocStatus("working", fmtTime(elapsed));
    p.timer = setTimeout(tick, 1000);
    return;
  }
  stopPoll();
  await jobEnded(p.slug, v);
}

/** A run ended, seen by its page or by the background watcher: badges, the tab title, a toast or the result card. */
async function jobEnded(slug, v) {
  const p = { slug };
  store.set(`cvs-running:${p.slug}`, "");
  const k = KIND[v.kind] || { done: "Done", title: v.kind };
  const b = badges[p.slug] || (badges[p.slug] = new Set());
  if (v.status === "done") {
    setDocStatus("done", k.done);
    const news = { extract: "questions", revise: "questions", preview: "preview", render: "preview", ask: "interview", next: "interview",
                   finish: v.result && v.result.review ? "changes" : "overview", curate: "changes", refresh: "changes",
                   goals: v.result && v.result.review ? "review" : "goals" }[v.kind] || "overview";
    b.add(news);
    if (current === p.slug && tab[p.slug] === "log") tab[p.slug] = news;
  } else if (v.status === "failed") {
    setDocStatus("failed", `${k.title} failed`);
    b.add("log");
  } else {
    setDocStatus("idle");
  }
  await loadList().catch(() => {});
  if (current === p.slug) {
    await reopen(p.slug).catch(() => {});
    const card = $("#result");
    if (card) { card.focus({ preventScroll: true }); card.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  } else if (v.status === "done") {
    toast(`${k.done} · ${v.label || v.slug}`, { type: "ok", action: { label: "View", fn: () => reopen(p.slug) } });
  } else if (v.status === "failed") {
    toast(`${k.title} failed · ${v.label || v.slug}`, { type: "error", action: { label: "View", fn: () => reopen(p.slug) } });
  }
}

/* ---------- new application ---------- */

function setupNew() {
  const d = $("#new-dialog"), form = $("#new-form"), msg = $("#new-msg"), submit = $("#new-submit");
  let confirmSimilar = false;
  $("#new-btn").addEventListener("click", () => {
    if (scope === "exps") return openNewExp();
    form.reset(); msg.replaceChildren(); confirmSimilar = false; submit.textContent = "Create and extract"; d.showModal();
  });
  $("#new-cancel").addEventListener("click", () => d.close());
  form.addEventListener("input", () => { if (confirmSimilar) { confirmSimilar = false; submit.textContent = "Create and extract"; msg.replaceChildren(); } });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    body.confirm_similar = confirmSimilar;
    try {
      const r = await busy(submit, "Creating…", () => api("/api/apps", body));
      d.close();
      current = r.slug;
      tab[r.slug] = "overview";
      await loadList();
      await runAction("extract");
    } catch (e) {
      msg.replaceChildren(e.message + ". ");
      if (e.data && e.data.existing) {
        msg.append(el("button", { type: "button", class: "text-btn", onclick: () => { d.close(); openApp(e.data.existing); } }, "Open it"));
      } else if (e.data && e.data.similar) {
        msg.append(`Existing: ${e.data.similar.join(", ")}. `);
        confirmSimilar = true;
        submit.textContent = "Create anyway";
      }
    }
  });
}

/* ---------- theme, settings, quit ---------- */

function setupTheme() {
  const seg = $("#theme");
  const apply = (v) => {
    document.documentElement.dataset.theme = v;
    seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.v === v)));
  };
  apply(document.documentElement.dataset.theme || "system");
  seg.addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    apply(b.dataset.v);
    store.set("cvs-theme", b.dataset.v);
  });
}

function setupSettings() {
  const d = $("#settings-dialog"), n = $("#set-notify"), s = $("#set-sound");
  $("#todo-btn").addEventListener("click", () => openTodo());
  $("#offline-retry").addEventListener("click", async () => { try { await fetch("/api/ping"); backOnline(); } catch (e) { toast("Still not running. Open the CV Studio app, then try again.", { type: "error", sticky: false }); } });
  $("#settings-btn").addEventListener("click", async () => {
    try { const p = await api("/api/settings"); n.checked = p.notify; s.checked = p.sound; s.disabled = !p.notify; } catch (e) { return; }
    d.showModal();
  });
  const save = async (extra = {}) => {
    s.disabled = !n.checked;
    try { await api("/api/settings", { notify: n.checked, sound: s.checked, ...extra }); } catch (e) { /* toast shown */ }
  };
  n.addEventListener("change", () => save());
  s.addEventListener("change", () => save());
  $("#set-test").addEventListener("click", (e) => busy(e.currentTarget, "Sending…", () => save({ test: true })));
}

function setupQuit() {
  $("#quit").addEventListener("click", async () => {
    const running = Object.keys(active).length;
    const ok = await confirmBox("Quit CV Studio?",
      running ? "A run is still going and will be stopped. Your files are safe; you can run it again later." : "The local server stops. Open CV Studio again from the app icon whenever you need it.",
      "Quit");
    if (!ok) return;
    try { await api("/api/quit", {}); } catch (e) { /* already gone */ }
    stopPoll();
    clearInterval(finishStart.timer);
    setDocStatus("idle");
    document.body.replaceChildren(el("div", { class: "stopped" }, el("div", {},
      svg(ICON.doc), el("h1", { text: "CV Studio has stopped" }), el("p", { text: "You can close this tab. Open the CV Studio app to start again." }))));
  });
}

/* =====================================================================
   Experiences and the master CV
   ===================================================================== */

const SCOPE_LABELS = {   // scope -> [new button label (null hides it), list label]
  apps: ["New application", "Applications"], exps: ["New experience", "Experiences"], master: [null, "Sections"], goals: [null, "On this page"],
};

function setScope(v, open = true) {
  scope = v;
  store.set("cvs-scope", v);
  $("#scope").querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.v === v)));
  const [newLabel, listLabel] = SCOPE_LABELS[v];
  $("#new-btn").hidden = !newLabel;
  $("#new-label").textContent = newLabel || "";
  $("#list-label").textContent = listLabel;
  $("#exp-tools").hidden = v !== "exps";
  renderList();
  if (!open) return;
  if (v === "master" && current !== "master") openMaster();
  if (v === "goals" && current !== "goals") openGoals();
  if (v === "exps" && !isExpKey(current)) openFirstExp();
  if (v === "apps" && !apps.some((a) => a.slug === current) && apps[0]) openApp((apps.find((a) => a.state === "draft") || apps[0]).slug);
}

function setupScope() {
  $("#scope").addEventListener("click", (ev) => { const b = ev.target.closest("button"); if (b && b.dataset.v !== scope) setScope(b.dataset.v); });
  for (const k of ["status", "type", "year", "sort"]) {
    $(`#xf-${k}`).addEventListener("change", (ev) => { expPick[k] = ev.target.value; store.set(`cvs-exp-${k}`, ev.target.value); renderExpList(); });
  }
  setScope(scope, false);
}

/** A dot on the Master CV tab while a review waits, the curator works or the ranking is older than the goals, and on Goals while a draft waits or the drafter runs. */
function renderScopeDots() {
  const gs = goalsSummary || {};
  const dots = {
    master: reviewPending ? "A master CV change is waiting for your review" : active.master ? "The curator is working" : gs.needs_refresh ? "Your goals changed: refresh the ranking" : "",
    goals: gs.running ? "The goals drafter is working" : gs.proposal ? "A goals draft is waiting for your review" : "",
  };
  for (const [k, why] of Object.entries(dots)) {
    const b = $(`#scope button[data-v="${k}"]`);
    b.querySelector(".scope-dot").hidden = !why;
    if (why) b.title = why; else b.removeAttribute("title");
  }
}

/* ---------- experiences list and its filter ---------- */

/** The Status menu. In Progress goes by dates (still going on today), so it overlaps In CV and Not in CV yet. */
const EXP_STATUS = [["", "Any status"], ["incv", "In CV"], ["progress", "In Progress"], ["planned", "Planned"],
                    ["archived", "Archived"], ["notyet", "Not in CV yet"]];

function expMatches(x, f) {
  const st = expState(x);
  if (f === "incv") return st === "condensed";
  if (f === "progress") return x.phase === "ongoing" && st !== "planned";
  if (f === "planned") return st === "planned" || x.phase === "planned";
  if (f === "archived") return st === "archived";
  if (f === "notyet") return ["stub", "interviewing", "interviewed", "updated"].includes(st);
  return true;
}

const EXP_TYPES = { work: "Work", internship: "Internship", project: "Project", leadership: "Leadership", education: "Education", "self-study": "Self-study", sport: "Sport" };

/** The calendar years an experience spans, an open end counting up to this year. */
function expYears(x) {
  if (!x.start) return [];
  const from = +x.start.slice(0, 4), to = x.end === "present" ? new Date().getFullYear() : +(x.end || x.start).slice(0, 4);
  return Array.from({ length: Math.max(0, to - from) + 1 }, (_, i) => from + i);
}

/** The Type and Year menus narrow the list and the counts in the Status menu. */
function expPicked(x) {
  return (!expPick.type || x.type === expPick.type) && (!expPick.year || expYears(x).includes(+expPick.year));
}

/** Newest first sorts by end (ongoing first, undated last), oldest first by start. */
function expSorter(sort) {
  const end = (x) => (x.end === "present" ? "9999" : x.end || "");
  if (sort === "az") return (a, b) => a.title.localeCompare(b.title);
  if (sort === "old") return (a, b) => (a.start || "9999").localeCompare(b.start || "9999") || a.title.localeCompare(b.title);
  return (a, b) => end(b).localeCompare(end(a)) || (b.start || "").localeCompare(a.start || "") || a.title.localeCompare(b.title);
}

function fillSelect(sel, options, value) {
  sel.replaceChildren(...options.map(([v, label]) => el("option", { value: v, text: label })));
  sel.value = options.some(([v]) => v === value) ? value : options[0][0];
  return sel.value;
}

/** Status shows a count per option. Type and Year list only what the experiences have. A stored choice that no longer exists resets to any. */
function renderExpTools() {
  if (!exps.length) return;   // before the list loads there are no options yet, and a stored choice would be lost
  const n = (f) => exps.filter((x) => expPicked(x) && expMatches(x, f)).length;
  expPick.status = fillSelect($("#xf-status"), EXP_STATUS.map(([v, label]) => [v, v ? `${label} (${n(v)})` : `${label} (${n("")})`]), expPick.status);
  const types = [...new Set(exps.map((x) => x.type).filter(Boolean))].sort((a, b) => Object.keys(EXP_TYPES).indexOf(a) - Object.keys(EXP_TYPES).indexOf(b));
  expPick.type = fillSelect($("#xf-type"), [["", "All types"], ...types.map((t) => [t, EXP_TYPES[t] || t])], expPick.type);
  const years = [...new Set(exps.flatMap(expYears))].sort((a, b) => b - a);
  expPick.year = fillSelect($("#xf-year"), [["", "Any year"], ...years.map((y) => [String(y), String(y)])], expPick.year);
  $("#xf-sort").value = ["new", "old", "az"].includes(expPick.sort) ? expPick.sort : "new";
  expPick.sort = $("#xf-sort").value;
}

/** The first experience that needs attention, else the first in the list. */
function openFirstExp() {
  const first = exps.find((x) => ["stub", "interviewing", "interviewed"].includes(expState(x))) || exps[0];
  if (first) return openExp(first.slug);
  current = null;
  main.replaceChildren(el("div", { class: "main-inner enter" }, emptyState("No experiences yet", "Add a role, project, competition or activity. A short interview turns it into master CV material.",
    el("button", { class: "btn primary", onclick: () => openNewExp() }, "New experience"))));
}

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The notes' dates, or the span the server read from the master CV heading when the notes still say TODO. */
function expDates(x) {
  if (/\d{4}|present|planned|AY\d/i.test(x.dates || "")) return cleanDates(x.dates);
  const m = (v) => (v === "present" ? "Present" : v ? `${MON[+v.slice(5, 7) - 1]} ${v.slice(0, 4)}` : "");
  return x.start ? [m(x.start), x.end !== x.start ? m(x.end) : ""].filter(Boolean).join(" - ") : "";
}

function cleanDates(d) { return (d || "").replace(/\s*\((?:[A-Z][\w'-]*, \d{4}-\d{2}-\d{2}|planned|in progress)[^)]*\)\s*$/i, "").replace(/ – /g, " - "); }

/** One CV label per item. A curated or archived entry that has not started yet reads Planned. */
function expState(x) {
  if (x.interviewing) return "interviewing";
  if (x.phase === "planned" && (x.archived || x.status === "condensed")) return "planned";
  if (x.archived) return "archived";
  if (x.status === "interviewed" && x.in_master) return "updated";
  return x.status in EXP_STATE ? x.status : "stub";
}

/** "Data Analyst Intern (Part-Time)" -> "DAI": initials of the title's main words, else its first word. */
function shortTitle(t) {
  const words = (t || "").replace(/\(.*$/, "").split(/[\s,]+/).filter((w) => /^[A-Z]/.test(w));
  const ini = words.map((w) => w[0]).join("");
  return ini.length >= 2 && ini.length <= 4 ? ini : words[0] || t;
}

const EXP_HELP = { stub: "New: not interviewed yet", interviewing: "An interview is open", interviewed: "Interviewed, not in your CV yet. Click Update CV entry",
  updated: "In your CV, but the notes or details changed since. Click Update CV entry so the CV catches up", condensed: "In your master CV",
  archived: "Archived: kept, but no tailored CV picks it", planned: "Planned: hasn't started, so it stays off CVs until it's done" };

function expPill(x, running) {
  if (running) return el("span", { class: "pill running" }, el("span", { class: "dot" }), "Working");
  const parent = x.part_of && exps.find((p) => p.slug === x.part_of);
  if (parent && expState(x) === "condensed") return el("span", { class: "pill rendered", title: `Merged into ${parent.title} on your CV` }, `Part of ${shortTitle(parent.title)}`);
  const st = expState(x), [label, cls] = EXP_STATE[st];
  return el("span", { class: `pill ${cls}`, title: EXP_HELP[st] || "" }, label);
}

const EXP_EMPTY = { "": "No experiences yet.", incv: "Nothing is in your CV yet.", progress: "Nothing is in progress.", planned: "Nothing planned.", archived: "Nothing archived.", notyet: "Everything is in your CV." };

function renderExpList() {
  const nav = $("#app-list");
  nav.replaceChildren();
  renderExpTools();
  const shown = exps.filter((x) => expPicked(x) && expMatches(x, expPick.status)).sort(expSorter(expPick.sort));
  if (!shown.length && (expPick.type || expPick.year) && exps.some((x) => expMatches(x, expPick.status))) {
    nav.append(el("div", { class: "empty-list" }, "Nothing matches these filters. ",
      el("button", { class: "text-btn", type: "button", onclick: () => { for (const k of ["type", "year"]) { expPick[k] = ""; store.set(`cvs-exp-${k}`, ""); } renderExpList(); } }, "Clear filters")));
  } else if (!shown.length) nav.append(el("div", { class: "empty-list", text: EXP_EMPTY[expPick.status] }));
  const groups = [["Experience", (x) => x.section === "Experience"], ["Projects", (x) => x.section === "Projects"],
                  ["Hackathons and case competitions", (x) => (x.section || "").startsWith("Hackathons")],
                  ["Leadership & Co-Curricular Activities", (x) => (x.section || "").startsWith("Leadership")],
                  ["Education and other", () => true]];
  if (!expPick.status) groups.unshift(["Needs you", (x) => ["stub", "interviewing", "interviewed", "updated"].includes(expState(x))]);
  const placed = new Set();
  const item = (x, child) => el("button", { class: `app-item${child ? " exp-child" : ""}`, type: "button", "aria-current": String(current === `exp:${x.slug}`), onclick: () => openExp(x.slug) },
    el("div", { class: "name" }, el("span", { text: x.title, title: x.title }), expPill(x, active[`exp:${x.slug}`])),
    el("div", { class: "role", text: [x.organisation, expDates(x)].filter(Boolean).join(" · "), title: [x.organisation, expDates(x)].filter(Boolean).join(" · ") }),
    x.phase === "ongoing" && expState(x) !== "planned" ? el("div", { class: "exp-now", text: "In Progress", title: "Its dates say you're still doing it" }) : null);
  // an experience merged into another entry (style rule 7) sits right under it, unless a filter hid the parent
  const children = (p) => shown.filter((x) => x.part_of === p.slug);
  const nested = new Set(shown.filter((x) => x.part_of && shown.some((p) => p.slug === x.part_of)).map((x) => x.slug));
  for (const [name, test] of groups) {
    const items = shown.filter((x) => !placed.has(x.slug) && !nested.has(x.slug) && test(x));
    if (!items.length) continue;
    nav.append(el("div", { class: "group-label", text: name, title: name === "Needs you" ? "Not interviewed yet, mid-interview, or not in your CV yet" : "" }));
    for (const x of items) {
      placed.add(x.slug);
      nav.append(item(x, false));
      for (const c of children(x)) { placed.add(c.slug); nav.append(item(c, true)); }
    }
  }
}

/* ---------- sidebar for the Master CV and Goals tabs ---------- */

const MASTER_SECTIONS = ["Experience", "Projects", "Hackathons and case competitions", "Leadership & Co-Curricular Activities", "Education", "Skills", "Archive"];

/** The master CV's sections with entry counts. A click jumps to that section on the page. */
function renderMasterNav() {
  const nav = $("#app-list");
  nav.replaceChildren();
  for (const name of MASTER_SECTIONS) {
    const n = name === "Archive" ? exps.filter((x) => x.archived).length : exps.filter((x) => x.section === name).length;
    nav.append(el("button", { class: "app-item nav-item", type: "button", onclick: () => jumpToSection(name) },
      el("div", { class: "name" }, el("span", { text: name === "Archive" ? "Archived" : name }),
        name === "Skills" ? null : el("span", { class: "hint", text: `${n} ${n === 1 ? "entry" : "entries"}` }))));
  }
}

async function jumpToSection(name) {
  if (current !== "master") await openMaster({ tab: "cv" });
  else if (tab.master !== "cv") { tab.master = "cv"; renderMaster(); }
  const h = [...main.querySelectorAll(".md h3")].find((x) => x.textContent.trim() === name);
  if (h) h.scrollIntoView({ behavior: "smooth", block: "start" });
}

/** The Goals page's own tabs, so the sidebar switches them like the other tabs' lists open pages. */
function renderGoalsNav() {
  const nav = $("#app-list");
  nav.replaceChildren();
  const gs = goalsSummary || {};
  const rows = [["goals", "Goals"], ["review", "Review draft", gs.proposal], ["history", "History"], ["log", "Activity"]];
  for (const [k, label, flag] of rows) {
    nav.append(el("button", { class: "app-item nav-item", type: "button", "aria-current": String(current === "goals" && tab.goals === k),
                              onclick: () => { tab.goals = k; if (current === "goals") renderGoals(); else openGoals({ tab: k }); } },
      el("div", { class: "name" }, el("span", { text: label }), flag ? el("span", { class: "pill draft" }, el("span", { class: "dot" }), "Review") : null)));
  }
}

async function openExp(slug, opts = {}) {
  if (scope !== "exps") setScope("exps", false);
  const key = `exp:${slug}`;
  const switching = current !== key;
  if (switching) parkPoll();
  const prev = current;
  current = key;
  setHash(key);
  const slow = switching ? setTimeout(() => main.replaceChildren(skeletonMain()), 150) : null;
  try { expDetail = await api(`/api/exp/${encodeURIComponent(slug)}`); }
  catch (e) { clearTimeout(slow); if (e.offline) return navFailed(prev, e); if (e.status === 404) { toast("That experience no longer exists.", { type: "error" }); return openMaster(); } throw e; }
  clearTimeout(slow);
  if (current !== key) return;
  if (opts.tab) tab[key] = opts.tab;
  renderList();
  renderExp({ fade: switching });
  const job = expDetail.job;
  if (job && job.status === "running" && (!poll || poll.jobId !== job.id)) startPoll(job.id, key);
  if (job && job.status === "running") store.set(`cvs-running:${key}`, JSON.stringify({ id: job.id, kind: job.kind }));
  else checkInterrupted(key, job);
}

function expDefaultTab(d) {
  if (d.interview.open) return "interview";
  if (d.review) return "changes";
  return "overview";
}

function renderExp({ fade = false } = {}) {
  const d = expDetail, key = current, f = d.front;
  const running = d.job && d.job.status === "running";
  const t = tab[key] || expDefaultTab(d);
  tab[key] = t;
  (badges[key] || new Set()).delete(t);
  const listed = exps.find((x) => x.slug === d.slug) || {};   // the date phase comes from the list
  const state = expState({ ...listed, interviewing: d.interview.open, status: f.status || "stub",
                           in_master: !!d.master_entry, archived: !!(d.master_entry && d.master_entry.archived) });
  const [label, cls] = EXP_STATE[state] || EXP_STATE.stub;
  const actions = [];
  if (!d.interview.open && !running) {
    if (f.status === "stub") actions.push(el("button", { class: "btn primary", onclick: (e) => startInterview(e.currentTarget) }, "Start interview"));
    else {
      if (f.status === "interviewed") actions.push(el("button", { class: "btn primary", title: "The curator writes this experience's master CV entry from your notes. About 2 minutes, then you Keep or Undo.", onclick: (e) => expAction("curate", {}, e.currentTarget, "Starting…") }, "Update CV entry"));
      actions.push(el("button", { class: f.status === "interviewed" ? "btn" : "btn primary", onclick: () => openUpdate() }, "Update"));
    }
  }
  if (!running) {
    const more = [el("button", { class: "text-btn", onclick: () => editDetails() }, "Edit details")];
    if (d.own_entry && !d.review) more.push(d.master_entry && d.master_entry.archived
      ? el("button", { class: "text-btn", onclick: () => unarchiveEntry() }, "Move back to CV")
      : el("button", { class: "text-btn", onclick: () => archiveEntry() }, "Archive"));
    actions.unshift(...more);
  }
  const head = el("div", { class: "head" },
    el("div", { class: "head-text" }, el("h1", { text: f.title || d.slug }),
      el("div", { class: "sub" }, el("span", { text: [f.organisation, cleanDates(f.dates)].filter(Boolean).join(" · ") }),
        running ? el("span", { class: "pill running" }, el("span", { class: "dot" }), "Working") : el("span", { class: `pill ${cls}` }, label),
        el("code", { text: d.slug }))),
    el("div", { class: "actions" }, ...actions));
  const at = d.review ? 3 : d.interview.open ? 1 : f.status === "condensed" ? 4 : f.status === "interviewed" ? 2 : 1;   // the loop step, whatever the label says
  const flow = el("ol", { class: "flow", "aria-label": "Progress" },
    ...["Notes", "Interview", "Curate", "Review"].map((s, i) => el("li", { class: i < at ? "done" : i === at ? "now" : "", "aria-current": i === at ? "step" : null },
      el("span", { class: "flow-dot" }, i < at ? svg(ICON.check, "flow-check") : null), el("span", { text: s }))));
  const openQs = d.interview.open && d.interview.open.rounds.length ? d.interview.open.rounds.at(-1).questions.filter((q) => !q.ticked && !q.answers.length).length : 0;
  const tabs = [["overview", "Overview"], ["interview", "Interview", openQs], ["log", "Activity"], ["changes", "Changes", d.review ? "•" : 0]];
  const seg = el("div", { class: "segmented tabs", role: "tablist" },
    ...tabs.map(([k, lab, n]) => el("button", { type: "button", role: "tab", "aria-selected": String(t === k), onclick: () => { tab[key] = k; renderExp(); } },
      lab, n ? el("span", { class: "count", text: String(n) }) : null,
      badges[key] && badges[key].has(k) ? el("span", { class: "badge-dot" }) : null)));
  const body = { overview: expOverview, interview: expInterview, log: () => viewActivity(d.job), changes: () => viewChanges(d.review) }[t]();
  main.replaceChildren(el("div", { class: `main-inner${fade ? " enter" : ""}` }, head, flow, runOrResult(d), seg, body));
  autogrowAll();
}

function expOverview() {
  const d = expDetail;
  const m = d.master_entry;
  const inCv = m ? el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", { text: "In your master CV" }), el("span", { class: "muted", text: m.section })),
      el("div", { class: "entry-preview" }, el("div", { class: "ep-title", text: m.heading }),
        el("ul", {}, ...m.bullets.filter((b) => !b.startsWith("Stack:")).map((b) => el("li", {}, inline(b)))),
        m.bullets.find((b) => b.startsWith("Stack:")) ? el("div", { class: "hint", text: m.bullets.find((b) => b.startsWith("Stack:")) }) : null),
      el("div", { class: "chips" }, ...m.tags.map((x) => el("span", { class: "chip", text: x }))),
      entryControls(d))
    : el("div", { class: "card next" }, el("h3", { text: "Not in your master CV yet" }),
      el("p", { class: "muted", text: d.front.status === "stub" ? "Start the interview. When you finish, the curator writes the entry and you review it." : "Click Update CV entry and the curator writes it from your notes." }));
  const tracker = d.tracker.length ? el("div", { class: "card" }, el("h3", { text: "Waiting on you" }),
    ...d.tracker.map((r) => el("div", { class: "track-row" }, el("div", { class: "grow" },
      el("div", { class: "hint", text: r.section }), el("div", { text: r.cells.filter((c) => c !== d.slug).join(" · ") })),
      el("div", { class: "row-actions" },
        el("button", { class: "text-btn", onclick: () => answerRow(r.line, r.cells.filter((c) => c !== d.slug).at(-1)) }, "Answer"),
        el("button", { class: "text-btn", onclick: (e) => resolveRow(r.line, e.currentTarget) }, "Resolved"))))) : null;
  return el("div", {}, m && bulletsEditing[d.slug] && d.own_entry ? bulletsCard(d) : inCv, documentsCard(d), tracker, notesCard(d));
}

const notesEditing = {};   // slug -> true while the notes editor is open
const bulletsEditing = {}; // slug -> true while the bullet editor is open

/** Your own edits to this experience's CV entry: code makes them, you Keep or Undo, and the curator keeps them (pin:). */
function entryControls(d) {
  const running = d.job && d.job.status === "running";
  if (!d.own_entry || running) return null;
  if (d.review) return el("p", { class: "hint", text: "Keep or Undo the waiting change (Changes tab) before editing this entry again." });
  const go = (verb, body, btn, label) => entryEdit(verb, body, btn, label);
  return el("div", { class: "row-actions entry-tools" },
    el("button", { class: "text-btn", onclick: (e) => go("entry-move", { step: -1 }, e.currentTarget, "Moving…") }, "Move up"),
    el("button", { class: "text-btn", onclick: (e) => go("entry-move", { step: 1 }, e.currentTarget, "Moving…") }, "Move down"),
    el("button", { class: "text-btn", onclick: () => editTags(d) }, "Edit tags"),
    el("button", { class: "text-btn", onclick: () => { bulletsEditing[d.slug] = true; renderExp(); } }, "Edit bullets"));
}

async function entryEdit(verb, body, btn, label) {
  const slug = expDetail.slug;
  const go = async () => {
    await api(`/api/exp/${encodeURIComponent(slug)}/${verb}`, body);
    tab[current] = "changes";
    toast("Saved as a change to review. Keep or Undo it on the Changes tab.", { type: "ok" });
    await loadList(); await openExp(slug);
  };
  if (btn) { try { await busy(btn, label, go); } catch (e) { /* toast shown */ } } else await go();
}

function editTags(d) {
  formDialog("Edit tags", "Job descriptions are matched against these. Pick from the vocabulary in CLAUDE.md.", [
    { name: "tags", label: "Tags", type: "checks", value: d.master_entry.tags, options: d.vocab.map((g) => [g.group, g.tags]) },
  ], "Save tags", (v) => entryEdit("entry-tags", { tags: v.tags }));
}

/** Edit bullets: every new or changed bullet names the lines of your notes it rests on, or adds a new note line. */
function bulletsCard(d) {
  const notes = d.index.split("\n");
  const old = d.master_entry.bullets;
  const rows = el("div", { class: "bullet-rows" });
  const addRow = (text = "") => {
    const ta = el("textarea", { rows: "2", class: "b-text", "aria-label": "Bullet" }); ta.value = text;
    const src = el("input", { type: "text", class: "b-src", placeholder: "e.g. 12, 15", "aria-label": "Rests on note lines" });
    const note = el("input", { type: "text", class: "b-note", placeholder: "Optional: a new fact, like the number for a (quantify?)", "aria-label": "New note line" });
    const row = el("div", { class: "bullet-row" }, ta,
      el("div", { class: "b-meta" }, el("label", {}, "Rests on note lines ", src), el("label", {}, "or add to your notes ", note)),
      el("div", { class: "row-actions" },
        el("button", { type: "button", class: "text-btn", onclick: () => row.previousElementSibling && row.parentNode.insertBefore(row, row.previousElementSibling) }, "Up"),
        el("button", { type: "button", class: "text-btn", onclick: () => row.nextElementSibling && row.parentNode.insertBefore(row.nextElementSibling, row) }, "Down"),
        el("button", { type: "button", class: "text-btn danger", onclick: () => row.remove() }, "Remove")));
    const stack = [...rows.children].find((r) => r.querySelector(".b-text").value.startsWith("Stack:"));
    if (stack && !text) rows.insertBefore(row, stack); else rows.append(row);   // a new bullet goes above the Stack line
  };
  old.forEach((b) => addRow(b));
  const save = el("button", { class: "btn primary", onclick: async (e) => {
    const bullets = [...rows.querySelectorAll(".bullet-row")].map((r) => ({
      text: r.querySelector(".b-text").value,
      sources: r.querySelector(".b-src").value.split(/[^0-9]+/).filter(Boolean).map(Number),
      note: r.querySelector(".b-note").value }));
    try { await busy(e.currentTarget, "Saving…", async () => { await entryEdit("entry-bullets", { bullets }); bulletsEditing[d.slug] = false; }); }
    catch (err) { /* toast shown */ }
  } }, "Save bullets");
  const ref = el("details", { class: "notes-ref" }, el("summary", { text: "Your notes, with line numbers" }),
    el("ol", { class: "numbered" }, ...notes.map((l, i) => el("li", { value: String(i + 1), class: l.startsWith("- ") ? "" : "muted", text: l || " " }))));
  return el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", { text: "Edit bullets" })),
    el("p", { class: "hint", text: "Rewrite, reorder, remove or add bullets. A new or changed bullet must name the lines of your notes it rests on, or add the fact to your notes here. The style rules are checked on save, then you Keep or Undo the change, and the curator keeps your bullets from then on." }),
    ref, rows,
    el("div", { class: "row-actions" }, el("button", { type: "button", class: "text-btn", onclick: () => addRow("") }, "Add a bullet"), save,
      el("button", { class: "text-btn", onclick: () => { bulletsEditing[d.slug] = false; renderExp(); } }, "Cancel")));
}

/** Your notes, editable. Saving an entry already in the CV marks it Update to curate, so the CV catches up. */
function notesCard(d) {
  if (!notesEditing[d.slug]) {
    const card = docCard("Notes (index.md)", d.index, false);
    card.querySelector("summary").append(el("button", { type: "button", class: "text-btn",
      onclick: (e) => { e.preventDefault(); e.stopPropagation(); notesEditing[d.slug] = true; renderExp(); } }, "Edit notes"));
    return card;
  }
  const ta = el("textarea", { class: "notes-edit", spellcheck: "true", "aria-label": "Notes (index.md)" });
  ta.value = store.get(`cvs-notes:${d.slug}`) || d.index;
  ta.addEventListener("input", () => store.set(`cvs-notes:${d.slug}`, ta.value));
  const save = el("button", { class: "btn primary", onclick: async (e) => {
    try {
      const r = await busy(e.currentTarget, "Saving…", () => api(`/api/exp/${encodeURIComponent(d.slug)}/notes`, { text: ta.value, index_mtime: d.index_mtime }));
      store.set(`cvs-notes:${d.slug}`, ""); notesEditing[d.slug] = false;
      toast(r.unchanged ? "Nothing changed" : d.master_entry ? "Notes saved. Run the curator when you want your CV to catch up." : "Notes saved", { type: "ok" });
      await openExp(d.slug); loadList();
    } catch (err) { /* toast shown */ }
  } }, "Save notes");
  return el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", { text: "Edit your notes" })),
    el("p", { class: "hint", text: "These are your own words, so edit freely. Keep the block between the --- lines as it is (use Edit details for title, organisation, dates and type). Drafts that cite these lines may need re-extracting after a big edit." }),
    ta, el("div", { class: "row-actions" }, save,
      el("button", { class: "text-btn", onclick: () => { store.set(`cvs-notes:${d.slug}`, ""); notesEditing[d.slug] = false; renderExp(); } }, "Cancel")));
}

/** A small form in a dialog. onSubmit gets the values; if it throws, the message shows and the dialog stays open. */
function formDialog(title, intro, fields, yes, onSubmit) {
  const d = el("dialog", { class: "form-dialog" });
  const inputs = {};
  const msg = el("p", { class: "form-msg", role: "alert" });
  const submit = el("button", { type: "submit", class: "btn primary" }, yes);
  const form = el("form", {}, el("h2", { text: title }), intro ? el("p", { class: "muted", text: intro }) : null,
    ...fields.map((f) => {
      if (f.type === "checks") {   // grouped checkboxes: [[group, [values]]]
        const box = el("div", { class: "checks" }, ...f.options.map(([g, vals]) => el("fieldset", {}, el("legend", { text: g }),
          ...vals.map((v) => el("label", { class: "check" }, el("input", { type: "checkbox", value: v, ...(f.value.includes(v) ? { checked: "" } : {}) }), v)))));
        inputs[f.name] = { get value() { return [...box.querySelectorAll("input:checked")].map((c) => c.value); } };
        return el("div", { class: "field" }, el("div", { class: "hint", text: f.label }), box);
      }
      const inp = f.type === "select" ? el("select", { name: f.name }, ...f.options.map(([v, l]) => el("option", { value: v, text: l })))
        : f.type === "textarea" ? el("textarea", { name: f.name, rows: f.rows || "3" }) : el("input", { name: f.name, type: "text", autocomplete: "off" });
      inp.value = f.value || "";
      if (f.required) inp.required = true;
      inputs[f.name] = inp;
      return el("label", {}, f.label, inp, f.hint ? el("span", { class: "hint", text: f.hint }) : null);
    }),
    msg, el("div", { class: "dialog-actions" }, el("button", { type: "button", class: "text-btn", onclick: () => d.close() }, "Cancel"), submit));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const values = Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, v.value]));
    try { await busy(submit, "Saving…", () => onSubmit(values)); d.close(); }
    catch (e) { msg.textContent = e.message; }
  });
  d.append(form);
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  const first = form.querySelector("input, select, textarea");
  if (first) first.focus();
}

const TYPE_SECTION = { work: "Experience", internship: "Experience", project: "Projects", leadership: "Leadership & Co-Curricular Activities",
                       sport: "Leadership & Co-Curricular Activities", education: "Education", "self-study": "Education" };

function editDetails() {
  const d = expDetail, f = d.front;
  formDialog("Edit details", "Saved straight away, no agent run. If this experience is in your CV, it then reads Update to curate until the curator updates the heading.", [
    { name: "title", label: "Title", value: f.title, required: true },
    { name: "organisation", label: "Organisation", value: f.organisation, required: true },
    { name: "dates", label: "Dates", value: f.dates, required: true, hint: "Like May 2026 - Aug 2026, Sep 2026 - Present or AY24/25. Dates that haven't started yet, or the word Planned, make it Planned." },
    { name: "type", label: "Type", type: "select", value: f.type, options: (d.types || []).map((t) => [t, t[0].toUpperCase() + t.slice(1)]) },
  ], "Save details", async (v) => {
    await api(`/api/exp/${encodeURIComponent(d.slug)}/details`, { ...v, index_mtime: d.index_mtime });
    toast("Details saved", { type: "ok" });
    await loadList(); await openExp(d.slug);
  });
}

function archiveEntry() {
  const d = expDetail;
  formDialog("Archive this entry?", "It moves to the Archive section of your master CV, so no tailored CV picks it. Nothing is deleted, and you can move it back any time. You review the change before it's kept.", [
    { name: "reason", label: "Why", type: "textarea", rows: "2", required: true, hint: "A few words, kept with the entry. For example: older work, a newer project shows the same skills." },
  ], "Archive", async (v) => {
    await api(`/api/exp/${encodeURIComponent(d.slug)}/archive`, v);
    tab[current] = "changes";
    toast("Moved to Archive. Keep or Undo it on the Changes tab.", { type: "ok" });
    await loadList(); await openExp(d.slug);
  });
}

function unarchiveEntry() {
  const d = expDetail;
  const options = (d.sections || []).filter((x) => x !== "Archive").map((x) => [x, x]);
  formDialog("Move back to your CV", "It leaves the Archive and joins this section, at the end. You review the change before it's kept.", [
    { name: "section", label: "Section", type: "select", options, value: TYPE_SECTION[d.front.type] || (options[0] || [""])[0] },
  ], "Move back", async (v) => {
    await api(`/api/exp/${encodeURIComponent(d.slug)}/unarchive`, v);
    tab[current] = "changes";
    toast("Moved back. Keep or Undo it on the Changes tab.", { type: "ok" });
    await loadList(); await openExp(d.slug);
  });
}

function answerRow(line, question) {
  formDialog("Answer", question, [
    { name: "text", label: "Your answer", type: "textarea", rows: "3", required: true, hint: "Goes into this experience's notes with your name and today's date, so the curator can use it. The row then leaves the to-do list." },
  ], "Save answer", async (v) => {
    const r = await api("/api/tracker/answer", { line, text: v.text });
    toast("Added to your notes. Run the curator when you want your CV to catch up.", { type: "ok" });
    await loadList(); if (current === "todo") openTodo(); else await openExp(r.slug);
  });
}

async function resolveRow(line, btn) {
  const ok = await confirmBox("Mark as resolved?", "This removes the row from tracker.md (git keeps the history).", "Resolve");
  if (!ok) return;
  try { await busy(btn, "Saving…", () => api(`/api/exp/${encodeURIComponent(expDetail.slug)}/tracker-resolve`, { line })); toast("Removed from the tracker", { type: "ok" }); openExp(expDetail.slug); }
  catch (e) { /* toast shown */ }
}

/* ---------- documents (artifacts) ---------- */

const ALLOWED = [".md", ".txt", ".csv", ".tsv", ".json", ".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"];
const MAX_MB = 25;

function documentsCard(d) {
  const list = el("div", { class: "doc-list", id: "doc-list" },
    ...d.artifacts.map((a) => el("div", { class: "doc-line" },
      el("a", { class: "doc-row", href: `/files/exp/${encodeURIComponent(d.slug)}/artifacts/${encodeURIComponent(a.name)}`, target: "_blank", rel: "noopener" },
        svg(ICON.file, "mini-doc"), el("span", { class: "grow", text: a.name }), el("span", { class: "hint", text: fmtSize(a.size) })),
      el("button", { class: "text-btn", "aria-label": `Remove ${a.name}`, onclick: (e) => removeDoc(a.name, e.currentTarget) }, "Remove"))));
  const input = el("input", { type: "file", multiple: true, accept: ALLOWED.join(","), hidden: true, onchange: (e) => { uploadFiles([...e.target.files]); e.target.value = ""; } });
  const zone = el("div", { class: "drop", tabindex: "0", role: "button", "aria-label": "Add documents",
    onclick: () => input.click(), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } },
    ondragenter: (e) => { e.preventDefault(); zone.classList.add("over"); }, ondragover: (e) => { e.preventDefault(); zone.classList.add("over"); },
    ondragleave: () => zone.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); zone.classList.remove("over"); uploadFiles([...e.dataTransfer.files]); } },
    el("div", { class: "drop-icon", text: "＋" }), el("div", {}, el("strong", { text: "Drop documents here" }), " or click to choose"),
    el("div", { class: "hint", text: "Journals, READMEs, notes, slides as PDF, screenshots. Up to 25 MB each. The interviewer reads them and skips questions they answer." }), input);
  return el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", { text: "Documents" }), el("span", { class: "muted", text: `${d.artifacts.length} in artifacts/` })), zone, el("div", { id: "uploads" }), list);
}

async function removeDoc(name, btn) {
  const ok = await confirmBox(`Remove ${name}?`, "The file is deleted from this experience's documents. Notes already taken from it stay in your notes.", "Remove");
  if (!ok) return;
  try { await busy(btn, "Removing…", () => api(`/api/exp/${encodeURIComponent(expDetail.slug)}/doc-remove`, { name })); toast("Removed", { type: "ok" }); openExp(expDetail.slug); }
  catch (e) { /* toast shown */ }
}

function fmtSize(n) { return n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`; }

function uploadFiles(files) {
  const slug = expDetail.slug, box = $("#uploads");
  let pending = files.length;
  const done = () => { if (--pending === 0) setTimeout(() => current === `exp:${slug}` && openExp(slug), 700); };
  for (const f of files) {
    const ext = (f.name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
    const bar = el("div", { class: "bar" }, el("div", { class: "fill" }));
    const status = el("span", { class: "hint", text: "Waiting…" });
    const row = el("div", { class: "up-row" }, svg(ICON.file, "mini-doc"), el("div", { class: "grow" }, el("div", { class: "up-name", text: f.name }), bar), status);
    box && box.append(row);
    const fail = (msg) => { row.classList.add("bad"); status.textContent = msg; bar.remove(); done(); };
    if (!ALLOWED.includes(ext)) { fail([".docx", ".doc", ".pptx", ".ppt", ".key", ".pages", ".xlsx", ".numbers"].includes(ext) ? `${ext} can't be read. Export it to PDF.` : `${ext || "This type"} can't be read.`); continue; }
    if (f.size > MAX_MB * 1048576) { fail(`Too large: ${Math.round(f.size / 1048576)} MB, limit ${MAX_MB} MB`); continue; }
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/exp/${encodeURIComponent(slug)}/upload`);
    xhr.setRequestHeader("X-CV-UI", "1");
    xhr.setRequestHeader("X-File-Name", encodeURIComponent(f.name));
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) { bar.firstChild.style.width = `${Math.round((e.loaded / e.total) * 100)}%`; status.textContent = `${Math.round((e.loaded / e.total) * 100)}%`; } };
    xhr.onload = () => {
      let data = {}; try { data = JSON.parse(xhr.responseText); } catch (e) { /* empty */ }
      if (xhr.status === 200) { bar.firstChild.style.width = "100%"; row.classList.add("ok"); status.replaceChildren(svg(ICON.check, "btn-check"), ` Saved as ${data.name}`); done(); }
      else fail(data.error || `Upload failed (${xhr.status})`);
    };
    xhr.onerror = () => fail("Upload failed: CV Studio isn't reachable");
    status.textContent = "Uploading…";
    xhr.send(f);
  }
}

function setupDropGuard() {  // dropping a file outside a drop zone must not navigate away from the page
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => { if (!e.target.closest || !e.target.closest(".drop")) e.preventDefault(); });
}

/* ---------- interview ---------- */

function expInterview() {
  const d = expDetail, iv = d.interview, key = current;
  const running = d.job && d.job.status === "running";
  const wrap = el("div", { class: "questions" });
  const past = iv.sessions.filter((x) => x.status !== "open").reverse();
  if (!iv.open) {
    wrap.append(d.front.status === "stub"
      ? emptyState("Start the interview", "3 to 5 tailored questions at a time, in your own words. Usually 1 or 2 rounds. Drop any documents in Overview first and the interviewer will use them.",
          el("button", { class: "btn primary", disabled: running, onclick: (e) => startInterview(e.currentTarget) }, "Start interview"))
      : emptyState("No interview open", "Use Update when something changed: a result came in, you finished it, or you have new numbers.",
          el("button", { class: "btn primary", disabled: running, onclick: () => openUpdate() }, "Update this experience")));
  } else {
    const o = iv.open;
    const rounds = o.rounds;
    const cur = rounds.at(-1);
    const lastRes = d.job && d.job.status !== "running" ? d.job.result || {} : {};
    wrap.append(el("div", { class: "round-head" },
      el("div", {}, el("strong", { text: o.kind === "update" ? "Update interview" : "Interview" }), el("span", { class: "muted", text: ` · started ${o.date}` })),
      el("div", { class: "round-dots", "aria-label": `Round ${rounds.length || 1} of up to ${iv.max_rounds}` },
        ...Array.from({ length: iv.max_rounds }, (_, i) => el("span", { class: i < rounds.length - 1 ? "done" : i === rounds.length - 1 ? "now" : "" })),
        el("span", { class: "hint", text: `Round ${rounds.length || 1} of up to ${iv.max_rounds}` }),
        running ? null : el("button", { class: "text-btn", onclick: (e) => cancelInterview(e.currentTarget) }, "Cancel interview"))));
    if (o.note) wrap.append(el("div", { class: "note-card" }, el("span", { class: "kicker", text: "What changed" }), el("span", { text: o.note })));
    if (!rounds.length && running) {
      wrap.append(el("div", { class: "card round" }, el("div", { class: "round-label", text: "Round 1" }),
        ...[0, 1, 2].map(() => el("div", { class: "q" }, el("div", { class: "num" }), el("div", {}, el("div", { class: "sk w90" }), el("div", { class: "sk w60 thin" })))),
        el("div", { class: "hint center-hint", text: "Preparing questions tailored to your notes and documents…" })));
    }
    if (!rounds.length && !running) {
      wrap.append(el("div", { class: "banner warn" }, el("div", { class: "grow", text: "The first questions didn't arrive (the run was stopped or failed)." }),
        el("button", { class: "btn primary", onclick: (e) => expAction("ask", {}, e.currentTarget, "Asking…") }, "Ask again")));
    }
    for (const r of rounds.slice(0, -1)) wrap.append(roundCard(r, false, false));
    if (cur) {
      if (iv.pending && !running) wrap.append(el("div", { class: "banner warn" }, el("div", { class: "grow", text: `${iv.pending} answer${iv.pending > 1 ? "s are" : " is"} saved but not recorded yet (the last run did not finish).` }),
        el("button", { class: "btn primary", onclick: () => retry("next")() }, "Record now")));
      if (lastRes.thin && !/^none/i.test(lastRes.thin) && !running) wrap.append(el("div", { class: "hint thin" }, el("strong", { text: "Still thin: " }), lastRes.thin));
      wrap.append(roundCard(cur, !running, running));
      if (!running) {
        wrap.append(el("div", { class: "card other" }, el("h3", { text: "Anything else" }),
          el("div", { class: "hint", text: "Anything the questions missed that a recruiter should know." }),
          el("textarea", { "data-q": "other", "data-key": "other", rows: "2", placeholder: "Optional", "aria-label": "Anything else" })));
        const canNext = rounds.length < iv.max_rounds && !lastRes.nothing_more;
        const counter = el("span", { class: "hint", id: "answered" });
        wrap.append(el("div", { class: "footer-bar" },
          el("div", { class: "footer-info" }, counter, el("span", { class: "hint kbd", text: `${MOD} next round` }), el("span", { class: "hint saved", id: "draft-saved", text: "Saved in this browser" })),
          el("div", { class: "row-actions" },
            canNext ? el("button", { class: "btn", id: "next-btn", onclick: (e) => submitRound("next", e.currentTarget) }, "Next round") : null,
            el("button", { class: "btn primary", id: "finish-btn", onclick: (e) => submitRound("finish", e.currentTarget) }, "Finish"))));
      }
    }
    wireDrafts(wrap, key, () => submitRound($("#next-btn") ? "next" : "finish", $("#next-btn") || $("#finish-btn")));
  }
  if (past.length) {
    wrap.append(el("div", { class: "card" }, el("h3", { text: "Earlier interviews" }),
      ...past.map((x) => el("details", { class: "past" }, el("summary", { text: `${x.date} · ${x.kind === "update" ? "Update" : "First interview"}${x.note ? ` · ${x.note}` : ""}` }),
        ...x.rounds.map((r) => roundCard(r, false, false, true))))));
  }
  return wrap;
}

function roundCard(r, editable, applying, bare = false) {
  const card = el("div", { class: bare ? "round bare" : "card round" }, el("div", { class: "round-label", text: `Round ${r.n}` }));
  for (const q of r.questions) {
    const isNote = q.text === "Also noted in CV Studio";
    const openQ = !q.ticked && !q.answers.length;
    const pending = !q.ticked && q.answers.length;
    const tag = pending ? el("span", { class: `tag ${applying ? "applying" : "waiting"}`, text: applying ? "recording…" : "not recorded yet" }) : null;
    const text = q.text.replace(/^\d+\.\s*/, "");
    const node = el("div", { class: `q${q.ticked ? " done" : ""}${isNote ? " change" : ""}` },
      el("div", { class: "num" }, q.ticked ? svg(ICON.check, "num-check") : isNote ? svg(ICON.pen) : String(q.index + 1)),
      isNote ? el("div", { class: "text" }, el("span", { class: "kicker", text: "You added" }), el("span", { text: q.answers.at(-1) || "" }), tag)
             : el("div", { class: "text" }, el("span", { text })),
      (!isNote && q.answers.length) || q.outcomes.length ? el("div", { class: "trail" },
        ...(isNote ? [] : q.answers.map((a) => el("div", {}, el("b", { text: "YOU" }), el("span", {}, a, tag ? tag.cloneNode(true) : null)))),
        ...q.outcomes.map((o) => el("div", {}, el("b", { text: "NOTE" }), el("span", { text: o })))) : null,
      openQ && editable ? el("textarea", { "data-q": String(q.index), "data-key": hash(q.text), rows: "1", placeholder: "Your answer, in your own words (leave blank to skip)", "aria-label": `Answer to question ${q.index + 1}` }) : null,
      openQ && editable && !isNote ? el("button", { class: "text-btn skip", onclick: (e) => skipQuestion(q.index, e.currentTarget) }, "Skip this question") : null);
    card.append(node);
  }
  return card;
}

function wireDrafts(wrap, key, submit) {
  for (const ta of wrap.querySelectorAll("textarea[data-key]")) {
    ta.value = store.get(draftKey(key, ta.dataset.key)) || "";
    ta.addEventListener("input", () => onDraftInput(ta));
    ta.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); submit(); } });
  }
  requestAnimationFrame(updateCounter);
}

async function submitRound(verb, btn) {
  const boxes = [...main.querySelectorAll("textarea[data-q]")];
  const answers = {};
  let other = "";
  for (const ta of boxes) {
    if (!ta.value.trim()) continue;
    if (ta.dataset.q === "other") other = ta.value.trim(); else answers[ta.dataset.q] = ta.value;
  }
  if (verb === "next" && !Object.keys(answers).length && !other) { toast("Type at least one answer first, or click Finish."); return; }
  if (verb === "finish") {
    const o = expDetail.interview.open;
    const anything = Object.keys(answers).length || other || o.rounds.some((r) => r.questions.some((q) => q.answers.length || (q.ticked && !q.outcomes.some((x) => /^skipped/.test(x)))));
    if (!anything) {   // finishing with nothing said would mark it interviewed and run the curator on old notes
      const v = await chooseBox("Nothing answered yet", "Finishing now marks this experience interviewed and asks the curator to write its CV entry from the notes it already has. If you just want to stop, close the interview instead.", "Finish anyway", "Close the interview");
      if (v === "alt") return cancelInterview(btn, false);
      if (v !== "yes") return;
    }
    const unanswered = boxes.filter((t) => t.dataset.q !== "other" && !t.value.trim()).length;
    const ok = await confirmBox("Finish the interview?",
      `Your answers are recorded in your notes${unanswered ? `, ${unanswered} unanswered question${unanswered > 1 ? "s go" : " goes"} to Open questions` : ""}, the experience is marked interviewed, and the curator updates your master CV. About 2 to 4 minutes. You review the change before it's kept.`,
      "Finish");
    if (!ok) return;
  }
  const key = current;
  try {
    const r = await busy(btn, verb === "next" ? "Sending…" : "Finishing…",
      () => api(`/api/exp/${encodeURIComponent(expSlug(key))}/${verb}`, { mtime: expDetail.interview.mtime, answers, other }));
    for (const ta of boxes) { store.set(draftKey(key, ta.dataset.key), ""); ta.value = ""; }
    if (r.skipped && r.skipped.length) toast(r.skipped.length > 1 ? `${r.skipped.length} answers were skipped: those questions were already answered.` : "1 answer was skipped: that question was already answered.");
    store.set(`cvs-running:${key}`, JSON.stringify({ id: r.job, kind: verb }));
    await openExp(expSlug(key));
    startPoll(r.job, key);
    loadList();
  } catch (e) { if (e.status === 409) openExp(expSlug(key)); }
}

async function skipQuestion(index, btn) {
  try { await busy(btn, "Skipping…", () => api(`/api/exp/${encodeURIComponent(expDetail.slug)}/skip`, { index, mtime: expDetail.interview.mtime })); openExp(expDetail.slug); }
  catch (e) { if (e.status === 409) openExp(expDetail.slug); }
}

async function cancelInterview(btn, ask = true) {
  const ok = !ask || await confirmBox("Cancel this interview?", "The interview closes without running the curator. Answers already recorded stay in your notes. Unanswered questions are dropped.", "Cancel interview");
  if (!ok) return;
  try { await busy(btn, "Closing…", () => api(`/api/exp/${encodeURIComponent(expDetail.slug)}/cancel`, {})); tab[current] = "overview"; await openExp(expDetail.slug); loadList(); }
  catch (e) { /* toast shown */ }
}

async function startInterview(btn) {
  await expAction("start", {}, btn, "Starting…", "interview");
}

async function expAction(verb, body = {}, btn = null, label = null, thenTab = null) {
  const key = current, slug = expSlug(key);
  const go = async () => {
    const r = await api(`/api/exp/${encodeURIComponent(slug)}/${verb}`, body);
    if (thenTab) tab[key] = thenTab;
    delete interrupted[key];
    await openExp(slug);
    if (r.job) { store.set(`cvs-running:${key}`, JSON.stringify({ id: r.job, kind: verb === "start" ? "ask" : verb })); startPoll(r.job, key); }
    loadList();
    return r;
  };
  try { return btn ? await busy(btn, label || "Working…", go) : await go(); }
  catch (e) { if (!btn && !e.offline) toast(e.message, { type: "error" }); if (e.status === 409) openExp(slug); }
}

/* ---------- dialogs: new experience, update ---------- */

function openNewExp() {
  const d = $("#exp-dialog"), form = $("#exp-form");
  form.reset(); $("#exp-msg").replaceChildren(); $("#exp-slug").dataset.touched = "";
  d.showModal();
}

function slugify(t) { return t.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""); }

function setupExpDialogs() {
  const d = $("#exp-dialog"), form = $("#exp-form"), msg = $("#exp-msg"), submit = $("#exp-submit"), slugIn = $("#exp-slug");
  $("#exp-type").replaceChildren(...["project", "work", "internship", "leadership", "education", "self-study", "sport"].map((v) => el("option", { value: v, text: v[0].toUpperCase() + v.slice(1) })));
  form.title.addEventListener("input", () => { if (!slugIn.dataset.touched) slugIn.value = slugify(form.title.value); });
  slugIn.addEventListener("input", () => { slugIn.dataset.touched = "1"; });
  $("#exp-cancel").addEventListener("click", () => d.close());
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    try {
      const r = await busy(submit, "Creating…", () => api("/api/exp", body));
      d.close();
      current = `exp:${r.slug}`;
      tab[current] = "interview";
      await loadList();
      await openExp(r.slug);
      toast("Experience created. Drop any documents in Overview while the first questions are prepared.", { type: "ok" });
      await expAction("start", {}, null, null, "interview");
    } catch (e) { msg.textContent = e.message; }
  });
  const ud = $("#update-dialog"), uf = $("#update-form"), um = $("#update-msg"), us = $("#update-submit");
  $("#update-cancel").addEventListener("click", () => ud.close());
  uf.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const note = uf.note.value.trim();
    if (!note) return;
    try {
      await busy(us, "Starting…", async () => {
        const key = current;
        const r = await api(`/api/exp/${encodeURIComponent(expSlug(key))}/start`, { note });
        ud.close();
        tab[key] = "interview";
        store.set(`cvs-running:${key}`, JSON.stringify({ id: r.job, kind: "ask" }));
        await openExp(expSlug(key));
        startPoll(r.job, key);
        loadList();
      });
    } catch (e) { um.textContent = e.message; }
  });
}

function openUpdate() {
  const ud = $("#update-dialog");
  $("#update-form").reset(); $("#update-msg").textContent = "";
  $("#update-title").textContent = expDetail.front.title || expDetail.slug;
  ud.showModal();
}

/* ---------- activity (generic) ---------- */

function viewActivity(job) {
  if (!job) return emptyState("Nothing has run yet", "Interviewer and curator runs appear here, with what they said.");
  const wrap = el("div", {});
  const r = job.result || {};
  const who = { ask: "The interviewer", next: "The interviewer", finish: "The curator", curate: "The curator", refresh: "The curator",
                goals: "The goals drafter" }[job.kind] || "It";
  if (job.status !== "running") {
    if (r.interviewer) wrap.append(el("div", { class: "card" }, el("h3", { text: "The interviewer said" }), agentSaid(r.interviewer)));
    if (r.message) wrap.append(el("div", { class: "card" }, el("h3", { text: `${who} said` }), agentSaid(r.message)));
  }
  if (job.status === "running") return el("div", {}, el("p", { class: "hint", text: "The live log is in the panel above (Show full log)." }));
  const log = el("div", { class: "log mono" });
  wrap.append(el("div", { class: "card" }, el("h3", { text: `${(KIND[job.kind] || {}).title || job.kind}: ${job.status}` }), log));
  api(`/api/jobs/${job.id}?since=0`).then((v) => { for (const l of v.lines) log.append(logLine(l)); }).catch(() => log.append(el("div", { class: "hint", text: "The full log is gone (CV Studio restarted since)." })));
  return wrap;
}

/* ---------- changes: Keep / Undo ---------- */

function wordDiff(a, b) {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
  const n = A.length, m = B.length;
  if (n * m > 40000) return null;
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const del = el("div", { class: "del" }), add = el("div", { class: "add" });
  let i = 0, j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && A[i] === B[j]) { del.append(A[i]); add.append(B[j]); i++; j++; }
    else if (j < m && (i === n || L[i][j + 1] >= L[i + 1][j])) { add.append(el("mark", { text: B[j++] })); }
    else { del.append(el("mark", { text: A[i++] })); }
  }
  return [del, add];
}

function renderDiff(text) {
  const box = el("div", { class: "diff mono" });
  const lines = text.split("\n").filter((l) => !l.startsWith("+++") && !l.startsWith("---"));
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (l.startsWith("@@")) { box.append(el("div", { class: "hunk", text: "⋯" })); continue; }
    if (l.startsWith("-") && lines[i + 1] && lines[i + 1].startsWith("+")) {
      const pair = wordDiff(l.slice(1), lines[i + 1].slice(1));
      if (pair) { box.append(...pair); i++; continue; }
    }
    const cls = l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "ctx";
    box.append(el("div", { class: cls, text: (cls === "ctx" ? l.slice(1) : l.slice(1)) || " " }));
  }
  return box;
}

function viewChanges(review) {
  if (!review) return emptyState("No changes waiting for review", "When the curator updates your master CV, the change shows here with Keep and Undo.");
  const diffs = review.diffs || {};
  const order = ["master/master-cv.md", "CLAUDE.md", ...Object.keys(diffs).filter((k) => k.endsWith("index.md")), "tracker.md"];
  const tagLines = (diffs["CLAUDE.md"] || "").split("\n").filter((l) => l.startsWith("+") && !l.startsWith("+++"));
  const label = { "master/master-cv.md": "Master CV", "CLAUDE.md": "CLAUDE.md (tag vocabulary)", "tracker.md": "Tracker" };
  return el("div", {},
    el("div", { class: "card review-head" }, el("div", { class: "grow" }, el("h3", { text: "Review the change to your master CV" }),
      el("p", { class: "muted", text: `${(KIND[review.kind] || {}).title || review.kind} · ${review.label || review.slugs.join(", ")} · ${review.when}. Keep it, or Undo to put everything back (your interview notes stay).` })),
      el("div", { class: "row-actions" }, el("button", { class: "text-btn danger", onclick: (e) => masterAction("undo", e.currentTarget) }, "Undo"),
        el("button", { class: "btn primary", onclick: (e) => masterAction("keep", e.currentTarget) }, "Keep"))),
    tagLines.length ? el("div", { class: "banner warn" }, el("div", { class: "grow" }, el("strong", { text: "New tag added. " }), "The curator extended the tag vocabulary in CLAUDE.md. Undo vetoes it.")) : null,
    ...order.filter((k) => diffs[k]).map((k) => el("div", { class: "card" }, el("details", { open: !k.endsWith("tracker.md") && !k.endsWith("index.md") },
      el("summary", { text: label[k] || k }), renderDiff(diffs[k])))));
}

async function masterAction(verb, btn = null) {
  if (verb === "undo") {
    const ok = await confirmBox("Undo this change?", "Your master CV, CLAUDE.md and tracker go back to how they were before the curator ran, and the entry's status goes back too. Your interview notes stay.", "Undo");
    if (!ok) return;
  }
  if (verb === "refresh") {
    const ok = await confirmBox("Refresh the ranking?", "The curator re-reads goals.md and re-orders entries and bullets, and may move entries to or from Archive. No facts are rewritten. About 2 minutes, and you review the change.", "Refresh");
    if (!ok) return;
  }
  const label = { keep: "Keeping…", undo: "Undoing…", refresh: "Starting…" }[verb];
  const go = async () => {
    const r = await api(`/api/master/${verb}`, {});
    if (verb === "keep") toast("Kept. Your master CV is updated.", { type: "ok" });
    if (verb === "undo") toast(r.refused && r.refused.length ? `Undone, except ${r.refused.join(", ")} (changed since)` : "Undone. Everything is back as it was.", { type: r.refused && r.refused.length ? "info" : "ok" });
    if (r.job) { store.set("cvs-running:master", JSON.stringify({ id: r.job, kind: "refresh" })); }
    await loadList();
    if (r.job) { await openMaster(); startPoll(r.job, "master"); } else await reopen(current);
    return r;
  };
  try { return btn ? await busy(btn, label, go) : await go(); }
  catch (e) { if (!btn && !e.offline) toast(e.message, { type: "error" }); }
}

/** Every kept change saved the version before it. Restore brings one back as a change you Keep or Undo. */
function masterHistory(m) {
  if (!m.history.length) return emptyState("No saved versions yet", "Each time you keep a change to your master CV, the version before it is saved here.");
  return el("div", { class: "card" }, el("h3", { text: "Saved versions" }),
    el("p", { class: "hint", text: "Each is your master CV just before the change named. Restore shows you the difference first, then you Keep or Undo." }),
    ...m.history.map((h) => el("div", { class: "track-row" }, el("div", { class: "grow" }, el("div", { text: `Before: ${h.label || "a change"}` }), el("div", { class: "hint", text: h.when })),
      el("button", { class: "text-btn", disabled: !!m.review, onclick: async (e) => {
        const btn = e.currentTarget;
        const ok = await confirmBox("Restore this version?", "Your master CV goes back to how it was before that change. You see the difference and Keep or Undo it.", "Restore");
        if (!ok) return;
        try { await busy(btn, "Restoring…", () => api("/api/master/restore", { name: h.name })); tab.master = "changes"; await loadList(); openMaster(); }
        catch (err) { /* toast shown */ }
      } }, "Restore"))));
}

/* ---------- to-do list (tracker.md) ---------- */

let todoData = null;
const todoEdit = {};   // row text -> "edit" while its editor is open

/** Everything outstanding, from tracker.md. The agents add rows; here you answer, edit, resolve or add them. */
async function openTodo() {
  if (current !== "todo") parkPoll();
  const prev = current;
  current = "todo";
  setHash("todo");
  try { todoData = await api("/api/tracker"); } catch (e) { return navFailed(prev, e); }
  if (current !== "todo") return;
  renderTodo();
}

function renderTodo() {
  const d = todoData;
  const label = (sec) => (sec === d.waiting ? "Waiting on you" : sec);
  const add = el("div", { class: "card" }, el("h3", { text: "Add an item" }),
    el("p", { class: "hint", text: "Anything you want to remember: a fact to add later, a result to wait for, a question for yourself." }),
    el("div", { class: "row-actions" }, el("button", { class: "btn", onclick: () => addTodo() }, "Add an item")));
  const order = [d.waiting, "Waiting on a date or event", "Applications", "Skill gaps surfaced by applications", "Interview prep only (never on a CV)"];
  const cards = order.map((sec) => {
    const rows = d.items.filter((i) => i.section === sec);
    if (!rows.length) return null;
    return el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", { text: label(sec) }), el("span", { class: "muted", text: `${rows.length}` })),
      ...rows.map((r) => todoRow(r)));
  });
  main.replaceChildren(el("div", { class: "main-inner enter" },
    el("div", { class: "head" }, el("div", { class: "head-text" }, el("h1", { text: "To-do list" }),
      el("div", { class: "sub" }, el("span", { text: "Everything outstanding, kept in tracker.md. Agents add rows as they work. Answer, edit or resolve them here." })))),
    ...cards.filter(Boolean), add));
}

function todoRow(r) {
  const d = todoData;
  const header = r.header || r.cells.map(() => "");
  const exp = r.section === "Waiting on a date or event" ? r.cells[1] : r.cells[0];
  const answerable = r.kind === "row" && (r.section === d.waiting || r.section === "Waiting on a date or event") && d.titles[exp];
  if (todoEdit[r.line]) {
    const inputs = r.cells.map((c) => { const t = el("textarea", { rows: c.length > 80 ? "3" : "1" }); t.value = c; return t; });
    return el("div", { class: "todo-row" },
      ...inputs.map((t, i) => el("label", { class: "todo-cells" }, el("span", { class: "k", text: header[i] || "" }), t)),
      el("div", { class: "row-actions" },
        el("button", { class: "btn primary", onclick: async (e) => {
          try { await busy(e.currentTarget, "Saving…", () => api("/api/tracker/edit", { line: r.line, cells: inputs.map((t) => t.value) })); delete todoEdit[r.line]; await loadList(); openTodo(); }
          catch (err) { if (err.status === 400) openTodo(); }
        } }, "Save"),
        el("button", { class: "text-btn", onclick: () => { delete todoEdit[r.line]; renderTodo(); } }, "Cancel")));
  }
  return el("div", { class: "todo-row" },
    el("div", { class: "todo-cells" }, ...r.cells.map((c, i) => el("div", {},
      header[i] ? el("div", { class: "k", text: header[i] }) : null,
      i === (r.section === "Waiting on a date or event" ? 1 : 0) && d.titles[c]
        ? el("a", { href: `#exp/${encodeURIComponent(c)}`, text: d.titles[c] }) : el("div", {}, inline(c))))),
    el("div", { class: "row-actions" },
      answerable ? el("button", { class: "btn", onclick: () => answerRow(r.line, r.cells.at(-1)) }, "Answer") : null,
      el("button", { class: "text-btn", onclick: () => { todoEdit[r.line] = "edit"; renderTodo(); } }, "Edit"),
      el("button", { class: "text-btn", onclick: async (e) => {
        const btn = e.currentTarget;   // gone once the confirm dialog's await returns
        const ok = await confirmBox("Mark as resolved?", "The row leaves the to-do list (git keeps the history).", "Resolve");
        if (!ok) return;
        try { await busy(btn, "Saving…", () => api("/api/tracker/resolve", { line: r.line })); await loadList(); openTodo(); } catch (err) { /* toast shown */ }
      } }, "Resolved")));
}

function addTodo() {
  const d = todoData;
  formDialog("Add an item", "", [
    { name: "entry", label: "About", required: true, hint: `An experience's folder name (${Object.keys(d.titles).slice(0, 2).join(", ")}…), or anything else, like (master CV).` },
    { name: "text", label: "What to do, or what closes it", type: "textarea", rows: "2", required: true },
    { name: "when", label: "When (optional)", hint: "Leave empty for Waiting on you. Fill in, like After 12 Nov 2026, for Waiting on a date or event." },
  ], "Add", async (v) => {
    await api("/api/tracker/add", v);
    toast("Added", { type: "ok" });
    await loadList(); openTodo();
  });
}

/* ---------- master CV page ---------- */

async function openMaster(opts = {}) {
  if (scope !== "master") setScope("master", false);
  const switching = current !== "master";
  if (switching) parkPoll();
  const prev = current;
  current = "master";
  setHash("master");
  const slow = switching ? setTimeout(() => main.replaceChildren(skeletonMain()), 150) : null;
  try { masterData = await api("/api/master"); } catch (e) { return navFailed(prev, e); } finally { clearTimeout(slow); }
  if (current !== "master") return;
  if (opts.tab) tab.master = opts.tab;
  renderList();
  renderMaster({ fade: switching });
  const job = masterData.job;
  if (job && job.status === "running" && (!poll || poll.jobId !== job.id)) startPoll(job.id, "master");
  else checkInterrupted("master", job);
}

function renderMaster({ fade = false } = {}) {
  const m = masterData;
  const running = m.job && m.job.status === "running";
  const t = tab.master || (m.review ? "changes" : "cv");
  tab.master = t;
  (badges.master || new Set()).delete(t);
  const inCv = m.experiences.filter((x) => x.in_master && !x.archived).length;
  const head = el("div", { class: "head" },
    el("div", { class: "head-text" }, el("h1", { text: "Master CV" }),
      el("div", { class: "sub" }, el("span", { text: `${inCv} entries · ${m.experiences.filter((x) => x.archived).length} archived · ${m.experiences.length} experiences` }),
        m.review ? el("span", { class: "pill draft" }, "Review waiting") : null)),
    el("div", { class: "actions" },
      el("button", { class: "btn", disabled: running || !!m.review || !m.experiences.some((x) => x.in_master),
        title: m.review ? "Keep or Undo the waiting change first" : !m.experiences.some((x) => x.in_master) ? "Add an experience first: there's nothing to rank yet" : "Re-rank after editing goals.md",
        onclick: (e) => masterAction("refresh", e.currentTarget) }, "Refresh ranking"),
      el("button", { class: "btn primary", onclick: () => openNewExp() }, "New experience")));
  const tabs = [["cv", "CV"], ["tags", "Tags"], ["history", "History"], ["log", "Activity"], ["changes", "Changes", m.review ? "•" : 0]];
  const seg = el("div", { class: "segmented tabs", role: "tablist" },
    ...tabs.map(([k, lab, n]) => el("button", { type: "button", role: "tab", "aria-selected": String(t === k), onclick: () => { tab.master = k; renderMaster(); } },
      lab, n ? el("span", { class: "count", text: String(n) }) : null, badges.master && badges.master.has(k) ? el("span", { class: "badge-dot" }) : null)));
  const body = {
    cv: () => docCard("master-cv.md", m.raw, true),
    tags: () => el("div", { class: "card" }, el("h3", { text: "Tag vocabulary" }), el("p", { class: "muted", text: "From CLAUDE.md. The curator adds tags only when none fits, and you can veto each one." }),
      ...m.tags.map((g) => el("div", { class: "tag-group" }, el("div", { class: "hint", text: g.group }), el("div", { class: "chips" }, ...g.tags.map((x) => el("span", { class: "chip", text: x })))))),
    log: () => viewActivity(m.job),
    changes: () => viewChanges(m.review),
    history: () => masterHistory(m),
  }[t]();
  const stale = m.goals && m.goals.needs_refresh && !m.review && !running
    ? el("div", { class: "banner warn", role: "status" }, el("div", { class: "grow", text: `Your goals changed ${m.goals.last_updated ? `on ${m.goals.last_updated}` : "recently"} and the ranking hasn't been refreshed.` }),
        el("button", { class: "btn primary", onclick: (e) => masterAction("refresh", e.currentTarget) }, "Refresh ranking"))
    : null;
  main.replaceChildren(el("div", { class: `main-inner${fade ? " enter" : ""}` }, head, stale, runOrResult(m), seg, body));
}

/* ---------- career goals (master/goals.md) ---------- */
// goals.md is the user's: the drafter only writes a proposal, and only their Save click (server code) writes the file.

let goalsData = null;
let goalsSummary = null;   // sidebar: {last_updated, proposal, needs_refresh, running}
let goalsEdit = null;      // {text, source: "manual" | "ai-edited", restored}
let goalsReview = null;    // manual path after Review changes: {text, diff, problems, stale, source}
let goalsSaved = null;     // the banner after a save: {drafts}
const GOALS_DRAFT = "cvs-goals-draft";

function dismissGoalsResult() {  // its "Review the draft" button is moot once the draft is saved or discarded
  if (goalsData && goalsData.job && goalsData.job.status !== "running") store.set(`cvs-dismissed:${goalsData.job.id}`, "1");
}

async function openGoals(opts = {}) {
  if (scope !== "goals") setScope("goals", false);
  const switching = current !== "goals";
  if (switching) parkPoll();
  const prev = current;
  current = "goals";
  setHash("goals");
  const slow = switching ? setTimeout(() => main.replaceChildren(skeletonMain()), 150) : null;
  try { goalsData = await api("/api/goals"); } catch (e) { return navFailed(prev, e); } finally { clearTimeout(slow); }
  if (current !== "goals") return;
  if (opts.tab) tab.goals = opts.tab;
  renderList();
  renderGoals({ fade: switching });
  const job = goalsData.job;
  if (job && job.status === "running" && (!poll || poll.jobId !== job.id)) startPoll(job.id, "goals");
  else checkInterrupted("goals", job);
}

function goalsTabDefault(d) { return d.proposal ? "review" : "goals"; }

function renderGoals({ fade = false } = {}) {
  const d = goalsData;
  const running = d.job && d.job.status === "running";
  const t = tab.goals || goalsTabDefault(d);
  tab.goals = t;
  (badges.goals || new Set()).delete(t);
  if (scope === "goals") renderGoalsNav();  // the sidebar mirrors the page's tabs
  const actions = [];
  if (!running && !goalsEdit && !goalsReview) {
    if (d.proposal) actions.push(el("button", { class: "btn primary", onclick: () => goTab("review") }, "Review draft →"));
    else {
      actions.push(el("button", { class: "btn", onclick: () => startGoalsEdit("manual") }, "Edit"));
      actions.push(el("button", { class: "btn primary", onclick: () => openGoalsDialog("draft") }, "Rewrite with AI"));
    }
  }
  const head = el("div", { class: "head" },
    el("div", { class: "head-text" }, el("h1", { text: "Career goals" }),
      el("div", { class: "sub" }, el("span", { text: `master/goals.md · last updated ${d.last_updated || "unknown"} · read by the curator, extractor and interviewer` }),
        running ? el("span", { class: "pill running" }, el("span", { class: "dot" }), "Working")
          : d.proposal ? el("span", { class: "pill draft" }, "Draft waiting") : null)),
    el("div", { class: "actions" }, ...actions));
  const tabs = [["goals", "Goals"], ["review", "Review", d.proposal ? "•" : 0], ["history", "History"], ["log", "Activity"]];
  const seg = el("div", { class: "segmented tabs", role: "tablist" },
    ...tabs.map(([k, lab, n]) => el("button", { type: "button", role: "tab", "aria-selected": String(t === k), onclick: () => { tab.goals = k; renderGoals(); } },
      lab, n ? el("span", { class: "count", text: String(n) }) : null, badges.goals && badges.goals.has(k) ? el("span", { class: "badge-dot" }) : null)));
  const body = { goals: goalsMain, review: goalsAiReview, history: goalsHistory, log: () => viewActivity(d.job) }[t]();
  const resolved = d.job && d.job.status === "done" && d.job.result && d.job.result.review && !d.proposal;  // saved or discarded since
  main.replaceChildren(el("div", { class: `main-inner${fade ? " enter" : ""}` }, head, resolved ? null : runOrResult(d), seg, body));
  autogrowAll();
  if (t === "goals" && goalsEdit && !goalsReview) { const ta = $("#goals-editor"); if (ta && !ta.dataset.focused) { ta.dataset.focused = "1"; ta.focus({ preventScroll: true }); } }
}

function refreshButton(label = "Refresh ranking →") {
  const blocked = goalsData.review_pending;
  return el("button", { class: "btn primary", disabled: blocked, title: blocked ? "Keep or Undo the waiting master CV change first" : "",
    onclick: (e) => masterAction("refresh", e.currentTarget) }, label);
}

function goalsMain() {
  const d = goalsData;
  if (goalsReview) return goalsManualReview();
  if (goalsEdit) return goalsEditor();
  const out = [];
  if (goalsSaved) {
    out.push(el("div", { class: "card next", role: "status" }, el("h3", { text: "Saved" }),
      el("p", { class: "muted", text: "goals.md is updated and the previous version is kept in History. Refresh the ranking so the curator re-orders your master CV against the new goals. About 2 minutes, and you review the change." }),
      goalsSaved.drafts && goalsSaved.drafts.length ? el("p", { class: "hint", text: `${goalsSaved.drafts.length === 1 ? "1 draft application was" : `${goalsSaved.drafts.length} draft applications were`} scored against your old goals: ${goalsSaved.drafts.map((x) => x.label).join("; ")}. To re-rank one, add "Re-rank against my updated goals" under Other changes on its Questions tab.` }) : null,
      el("div", { class: "row-actions" }, refreshButton(), el("button", { class: "text-btn", onclick: () => { goalsSaved = null; renderGoals(); } }, "Not now"))));
  } else if (d.needs_refresh) {
    out.push(el("div", { class: "card next" }, el("h3", { text: "Your ranking is older than your goals" }),
      el("p", { class: "muted", text: `Your goals changed ${d.last_updated ? `on ${d.last_updated}` : "recently"}. Refresh the ranking so the curator re-orders your master CV against them. About 2 minutes, and you review the change.` }),
      refreshButton()));
  }
  if (d.unfinished && d.unfinished.length) {
    out.push(el("div", { class: "banner warn" }, el("div", { class: "grow", text: `Your note is saved but the draft did not finish: “${d.unfinished.at(-1).text}”` }),
      el("button", { class: "text-btn", onclick: (e) => goalsPost("discard", {}, e.currentTarget, "Discarding…") }, "Discard"),
      el("button", { class: "btn primary", onclick: (e) => goalsPost("draft", { retry: true }, e.currentTarget, "Starting…") }, "Retry")));
  }
  if (!(d.raw || "").trim()) {  // a missing or empty goals.md: say what to write instead of showing a blank card
    out.push(el("div", { class: "card next" }, el("h3", { text: "Your goals are empty" }),
      el("p", { class: "muted", text: "Write a few honest lines: the roles you're aiming for in order, what to lead with and what to play down. The curator ranks your master CV by this file." }),
      el("div", { class: "row-actions" }, el("button", { class: "btn primary", onclick: () => startGoalsEdit("manual") }, "Write my goals"))));
    return el("div", {}, ...out);
  }
  out.push(docCard("goals.md", d.raw, true));
  return el("div", {}, ...out);
}

/* the manual editor */

function startGoalsEdit(source, text = null) {
  let restored = false;
  if (text === null) {
    const saved = store.get(GOALS_DRAFT);
    if (saved && saved !== goalsData.raw) { text = saved; restored = true; }
    else text = goalsData.raw;
  } else store.set(GOALS_DRAFT, text);
  goalsEdit = { text, source, restored };
  goalsReview = null; goalsSaved = null;
  tab.goals = "goals";
  renderGoals();
}

function linesChanged(a, b) {
  const A = a.split("\n"), B = b.split("\n");
  const count = (xs) => xs.reduce((m, x) => m.set(x, (m.get(x) || 0) + 1), new Map());
  const ca = count(A), cb = count(B);
  let added = 0, removed = 0;
  for (const [x, k] of cb) added += Math.max(0, k - (ca.get(x) || 0));
  for (const [x, k] of ca) removed += Math.max(0, k - (cb.get(x) || 0));
  return Math.max(added, removed);  // a reworded line counts once, not as one removed plus one added
}

function goalsEditor() {
  const ed = goalsEdit;
  const status = el("span", { class: "hint", id: "goals-changed" });
  const review = el("button", { class: "btn primary", id: "goals-review", onclick: (e) => reviewGoalsEdit(e.currentTarget) }, "Review changes");
  const update = () => {
    const n = linesChanged(goalsData.raw, ed.text);
    status.textContent = `Editing goals.md · ${n ? `${n} line${n > 1 ? "s" : ""} changed` : "no changes yet"}`;
    review.disabled = !n;
  };
  const ta = el("textarea", { class: "editor mono", id: "goals-editor", spellcheck: "true", "aria-label": "goals.md source", rows: "24" });
  ta.value = ed.text;
  ta.addEventListener("input", () => {
    ed.text = ta.value;
    store.set(GOALS_DRAFT, ta.value === goalsData.raw ? "" : ta.value);
    update();
    const s = $("#draft-saved");
    if (s) { s.classList.add("show"); clearTimeout(savedTimer); savedTimer = setTimeout(() => s.classList.remove("show"), 1200); }
  });
  ta.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); if (!review.disabled) review.click(); } });
  requestAnimationFrame(update);
  return el("div", {},
    ed.restored ? el("div", { class: "banner warn" }, el("div", { class: "grow", text: "Your unsaved edits from earlier are back." }),
      el("button", { class: "text-btn", onclick: () => { store.set(GOALS_DRAFT, ""); startGoalsEdit(ed.source); } }, "Discard them")) : null,
    el("div", { class: "card" },
      el("div", { class: "card-head" }, el("h3", { text: ed.source === "ai-edited" ? "Editing the AI draft" : "Edit goals.md" }),
        el("span", { class: "hint", text: "Markdown" })),
      el("p", { class: "hint", text: "Keep the headings and the <!-- hints -->: the curator and extractor look for Target roles, What to lead with and What to demote." }),
      ta),
    el("div", { class: "footer-bar" },
      el("div", { class: "footer-info" }, status, el("span", { class: "hint kbd", text: `${MOD} review` }), el("span", { class: "hint saved", id: "draft-saved", text: "Saved in this browser" })),
      el("div", { class: "row-actions" }, el("button", { class: "text-btn", onclick: cancelGoalsEdit }, "Cancel"), review)));
}

async function cancelGoalsEdit() {
  if (goalsEdit && goalsEdit.text !== goalsData.raw) {
    const ok = await confirmBox("Discard your edits?", "goals.md stays as it is.", "Discard");
    if (!ok) return;
  }
  store.set(GOALS_DRAFT, "");
  goalsEdit = null; goalsReview = null;
  renderGoals();
}

async function reviewGoalsEdit(btn) {
  try {
    const r = await busy(btn, "Checking…", () => api("/api/goals/preview", { text: goalsEdit.text, mtime: goalsData.mtime }));
    goalsReview = { ...r, text: goalsEdit.text, source: goalsEdit.source };
    renderGoals();
    main.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) { /* toast shown */ }
}

function diffCard(diff, text) {
  return el("div", { class: "card", role: "region", "aria-label": "Changes to goals.md" },
    el("details", { open: true }, el("summary", { text: "Changes to goals.md" }), renderDiff(diff)),
    el("details", {}, el("summary", { text: "Show the whole new version" }), markdown(text)));
}

function goalsManualReview() {
  const r = goalsReview;
  const note = el("input", { type: "text", id: "goals-note", placeholder: "Optional, e.g. analytics engineering first now", "aria-label": "What changed (optional)" });
  const save = el("button", { class: "btn primary", disabled: !!(r.problems && r.problems.length), onclick: (e) => saveGoals(e.currentTarget, r.source, r.text, note.value) }, "Save");
  return el("div", {},
    el("div", { class: "card review-head" }, el("div", { class: "grow" }, el("h3", { text: r.source === "ai-edited" ? "Review the AI draft with your edits" : "Review your edits" }),
      el("p", { class: "muted", text: "Nothing is saved until you click Save. A copy of the current goals.md is kept in History." })),
      el("div", { class: "row-actions" }, el("button", { class: "btn", onclick: () => { goalsReview = null; renderGoals(); } }, "Back to editing"), save)),
    r.problems && r.problems.length ? el("div", { class: "banner error", role: "status" }, el("div", { class: "grow", text: `Can't save yet: ${r.problems.join("; ")}.` })) : null,
    r.stale ? el("div", { class: "banner warn", role: "status" }, el("div", { class: "grow", text: "goals.md changed on disk since you opened it (maybe in VS Code or chat). Reload to start from the new version; your edits are kept as a draft." }),
      el("button", { class: "btn", onclick: () => location.reload() }, "Reload")) : null,
    r.source === "manual" ? el("div", { class: "card" }, el("label", {}, "What changed? (optional, goes in goals-log.md)", note)) : null,
    diffCard(r.diff, r.text));
}

async function saveGoals(btn, source, text, note = "") {
  const ok = await confirmBox("Save these goals?", "goals.md is replaced with this version and a copy of the current file is kept, so you can restore it from History. Then refresh the ranking so the curator re-ranks your master CV.", "Save");
  if (!ok) return;
  try {
    const r = await busy(btn, "Saving…", () => api("/api/goals/save", { source, text, note, mtime: goalsData.mtime }));
    store.set(GOALS_DRAFT, "");
    dismissGoalsResult();
    goalsEdit = null; goalsReview = null; goalsSaved = { drafts: r.drafts };
    toast("Goals saved", { type: "ok", action: { label: "History", fn: () => goTab("history") } });
    await loadList();
    await openGoals({ tab: "goals" });
  } catch (e) {  // busy() already showed the error. A 409 means goals.md changed, so show the banner with Reload
    if (e.status === 409) { if (goalsReview) { goalsReview.stale = true; renderGoals(); } else openGoals(); }
  }
}

/* the AI path */

function goalsAiReview() {
  const d = goalsData, p = d.proposal;
  const running = d.job && d.job.status === "running";
  if (!p) return emptyState("No draft waiting", "Rewrite with AI drafts a new version from your note. You review it here before anything is saved.",
    running ? null : el("button", { class: "btn primary", onclick: () => openGoalsDialog("draft") }, "Rewrite with AI"));
  const list = (text) => (text || "").split(/;\s+/).filter((x) => x && !/^none$/i.test(x));
  const when = p.when ? new Date(p.when * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  return el("div", {},
    el("div", { class: "card review-head" }, el("div", { class: "grow" }, el("h3", { text: "Review the new goals" }),
      el("p", { class: "muted", text: `Drafted ${when} from your note. Nothing is saved until you accept it.` })),
      el("div", { class: "row-actions" },
        el("button", { class: "text-btn danger", disabled: running, onclick: (e) => discardGoalsDraft(e.currentTarget) }, "Discard"),
        // a stale draft was made from an older goals.md: editing it by hand would undo the newer file, so start from the file
        el("button", { class: "btn", disabled: running, onclick: () => (p.stale ? startGoalsEdit("manual", goalsData.raw) : startGoalsEdit("ai-edited", p.text)) }, p.stale ? "Edit the current file" : "Edit by hand"),
        el("button", { class: "btn", disabled: running, onclick: () => openGoalsDialog("revise") }, "Revise"),
        el("button", { class: "btn primary", disabled: running || p.stale, title: p.stale ? "goals.md changed after this draft was made" : "", onclick: (e) => saveGoals(e.currentTarget, "ai", "") }, "Accept and save"))),
    p.stale ? el("div", { class: "banner warn", role: "status" }, el("div", { class: "grow", text: "goals.md changed after this draft was made, so Accept is off. Revise drafts again from the current file. Or edit the current file yourself, and copy from this draft as you go." })) : null,
    p.new_terms && p.new_terms.length ? el("div", { class: "banner warn", role: "status" }, el("div", { class: "grow" },
      el("strong", { text: "Names or numbers that are in neither your goals nor your note: " }), el("span", { class: "terms" }, ...p.new_terms.map((x) => el("span", { class: "chip warn", text: x }))),
      el("div", { class: "hint", text: "Check they are yours before saving. This check is cautious, so a reworded sentence can trip it." }))) : null,
    el("div", { class: "card" }, el("h3", { text: p.notes.length > 1 ? "Your notes" : "Your note" }),
      ...p.notes.map((n, i) => el("div", { class: "goals-note" }, el("span", { class: "kicker", text: `${i ? `Revision ${i}` : "Note"} · ${n.date}` }), el("div", { text: n.text })))),
    el("div", { class: "card" }, el("h3", { text: "What the drafter changed" }),
      list(p.changed).length ? el("ul", { class: "plain-list" }, ...list(p.changed).map((x) => el("li", { text: x }))) : el("p", { class: "muted", text: "No summary." }),
      p.kept && !/^none$/i.test(p.kept) ? el("p", { class: "hint", text: `Left as they were: ${p.kept}` }) : null,
      p.not_done && !/^none$/i.test(p.not_done) ? el("div", { class: "banner warn" }, el("div", { class: "grow" }, el("strong", { text: "Not done: " }), p.not_done)) : null,
      p.open && !/^none$/i.test(p.open) ? el("p", {}, el("strong", { text: "Question for you: " }), p.open) : null),
    diffCard(p.diff, p.text));
}

async function discardGoalsDraft(btn) {
  const ok = await confirmBox("Discard this draft?", "Nothing was saved to goals.md, so nothing changes.", "Discard");
  if (ok) goalsPost("discard", {}, btn, "Discarding…");
}

async function goalsPost(verb, body, btn = null, label = null) {
  const go = async () => {
    const r = await api(`/api/goals/${verb}`, body);
    delete interrupted.goals;
    if (r.job) { store.set("cvs-running:goals", JSON.stringify({ id: r.job, kind: "goals" })); tab.goals = "goals"; }
    if (verb === "discard") { tab.goals = "goals"; dismissGoalsResult(); toast("Draft discarded. goals.md is unchanged.", { type: "ok" }); }
    await openGoals();
    if (r.job) startPoll(r.job, "goals");
    loadList();
    return r;
  };
  try { return btn ? await busy(btn, label || "Working…", go) : await go(); }
  catch (e) { if (!btn && !e.offline) toast(e.message, { type: "error" }); if (e.status === 409) openGoals(); }
}

function openGoalsDialog(mode) {
  const d = $("#goals-dialog"), form = $("#goals-form");
  form.reset(); $("#goals-msg").replaceChildren();
  form.dataset.mode = mode;
  $("#goals-dialog-title").textContent = mode === "revise" ? "Ask for another revision" : "Rewrite your goals with AI";
  $("#goals-dialog-text").textContent = mode === "revise"
    ? "Say what should change in this draft. The drafter revises it from your goals and all your notes so far. About a minute."
    : "Say what changed in your direction, in your own words. The drafter rewrites goals.md from what it already says plus your note, never adding targets, companies, dates or preferences you did not give. You review the change before anything is saved. About a minute.";
  $("#goals-note-label").firstChild.textContent = mode === "revise" ? "What should change?" : "What changed?";
  $("#goals-submit").textContent = mode === "revise" ? "Revise the draft" : "Draft the rewrite";
  d.showModal();
}

function setupGoalsDialog() {
  const d = $("#goals-dialog"), form = $("#goals-form"), msg = $("#goals-msg"), submit = $("#goals-submit");
  $("#goals-cancel").addEventListener("click", () => d.close());
  form.note.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); form.requestSubmit(); } });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const note = form.note.value.trim();
    if (!note) { msg.textContent = "Say what changed first."; return; }
    try {
      const mode = form.dataset.mode;
      const r = await busy(submit, mode === "revise" ? "Revising…" : "Starting…", () => api(`/api/goals/${mode}`, { note }));
      d.close();
      store.set("cvs-running:goals", JSON.stringify({ id: r.job, kind: "goals" }));
      tab.goals = "goals";
      await openGoals();
      startPoll(r.job, "goals");
      loadList();
    } catch (e) { msg.textContent = e.message; }
  });
}

/* history */

function goalsHistory() {
  const d = goalsData;
  const rows = d.backups.map((b) => {
    const box = el("div", { class: "ver-view" });
    const view = el("details", { class: "ver-details", ontoggle: (e) => {
      if (!e.currentTarget.open || box.childNodes.length) return;
      box.append(el("div", { class: "hint", text: "Loading…" }));
      api(`/api/goals/backup/${encodeURIComponent(b.name)}`).then((r) => box.replaceChildren(markdown(r.text))).catch(() => box.replaceChildren(el("div", { class: "hint", text: "That version is not there any more." })));
    } }, el("summary", { text: `${b.when} · ${fmtSize(b.size)}` }), box);
    return el("div", { class: "ver-row" }, el("div", { class: "grow" }, view),
      el("button", { class: "text-btn", onclick: (e) => restoreGoals(e.currentTarget, b) }, "Restore"));
  });
  return el("div", {},
    el("div", { class: "card" }, el("h3", { text: "Saved versions" }),
      el("p", { class: "muted", text: "A copy of goals.md is kept before every save or restore (the last 20)." }),
      ...(rows.length ? rows : [el("p", { class: "hint", text: "No saved versions yet. Every save keeps a copy here." })])),
    d.log ? docCard("goals-log.md", d.log, true) : el("div", { class: "card" }, el("h3", { text: "goals-log.md" }),
      el("p", { class: "hint", text: "No changes yet. Each save records the date, how it was made and your note, word for word." })));
}

async function restoreGoals(btn, b) {
  const ok = await confirmBox("Restore this version?", `The current goals.md is backed up first, then replaced by the version from ${b.when}. Refresh the ranking afterwards.`, "Restore");
  if (!ok) return;
  try {
    const r = await busy(btn, "Restoring…", () => api("/api/goals/restore", { name: b.name, mtime: goalsData.mtime }));
    goalsSaved = { drafts: r.drafts };
    toast(`Restored the version from ${b.when}`, { type: "ok" });
    await loadList();
    await openGoals({ tab: "goals" });
  } catch (e) { if (e.status === 409) openGoals(); }  // busy() showed the error. Re-read so a retry works
}

window.addEventListener("beforeunload", (ev) => {
  if (goalsEdit && goalsData && goalsEdit.text !== goalsData.raw && current === "goals") { ev.preventDefault(); ev.returnValue = ""; }
});

/* ---------- start ---------- */

async function start() {
  setupTheme();
  setupScope();
  setupNew();
  setupExpDialogs();
  setupGoalsDialog();
  setupDropGuard();
  setupSettings();
  setupQuit();
  try { await loadList(); } catch (e) { main.replaceChildren(el("div", { class: "main-inner" }, emptyState("Can't reach CV Studio", "Open the CV Studio app again; this page reconnects by itself."))); return; }
  const want = decodeURIComponent(location.hash.slice(1));
  if (want === "todo") return finishStart(openTodo());
  if (want === "master") return finishStart(openMaster());
  if (want === "goals") return finishStart(openGoals());
  if (want.startsWith("exp/")) return finishStart(openExp(want.slice(4)));
  if (!apps.some((a) => a.slug === want)) {
    if (scope === "master") return finishStart(openMaster());
    if (scope === "goals") return finishStart(openGoals());
    if (scope === "exps") return finishStart(openFirstExp());
  }
  if (want && !apps.some((a) => a.slug === want)) toast(`There's no application called ${want}. Showing another one.`);
  const first = apps.find((a) => a.slug === want) || apps.find((a) => active[a.slug]) || apps.find((a) => a.state === "draft") || apps[0];
  if (first) openApp(first.slug);
  else main.replaceChildren(el("div", { class: "main-inner enter" }, (exps.some((x) => x.in_master)
    ? emptyState("No applications yet", "Paste a job description to draft your first tailored CV.",
        el("button", { class: "btn primary", onclick: () => $("#new-btn").click() }, "New application"))
    : emptyState("Start with your experiences", "A tailored CV is picked from your master CV, which is empty for now. Add an experience on the Experiences tab, answer a few questions about it, and come back with a job description.",
        el("button", { class: "btn primary", onclick: () => setScope("exps") }, "Add an experience")))));
  finishStart();
}

function finishStart(p) {
  if (finishStart.done) return p;
  finishStart.done = true;
  window.addEventListener("hashchange", () => {
    const h = decodeURIComponent(location.hash.slice(1));
    if (h === "todo" && current !== "todo") openTodo();
    else if (h === "master" && current !== "master") openMaster();
    else if (h === "goals" && current !== "goals") openGoals();
    else if (h.startsWith("exp/") && current !== `exp:${h.slice(4)}`) openExp(h.slice(4));
    else if (h && h !== current && apps.some((a) => a.slug === h)) openApp(h);
  });
  finishStart.timer = setInterval(() => { if (!document.hidden && !offline) loadList().catch(() => {}); }, 8000);
  return p;
}

start();
