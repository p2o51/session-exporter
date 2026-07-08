"use strict";

/* ── state ──────────────────────────────────────────────────────────────── */
const state = {
  all: [],
  index: new Map(),            // key -> session
  sources: [],
  enabledSources: new Set(),   // active source filters
  selectedProjects: new Set(), // empty => all projects
  selected: new Set(),         // keys of selected sessions
  query: "",
  projQuery: "",
  dateFrom: "",
  dateTo: "",
  sort: "updated",
  filtered: [],
};

const SOURCE_LABEL = { claude: "Claude Code", codex: "Codex", cursor: "Cursor" };
const key = (s) => `${s.source}::${s.id}`;
const $ = (id) => document.getElementById(id);

/* ── formatting ─────────────────────────────────────────────────────────── */
function humanTokens(n) {
  n = Number(n) || 0;
  if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e11 ? 0 : 1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e5 ? 0 : 1) + "k";
  return String(n);
}
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  const now = new Date();
  const base = `${MONTHS[d.getMonth()]} ${d.getDate()}`;
  return d.getFullYear() === now.getFullYear() ? base : `${base} '${String(d.getFullYear()).slice(2)}`;
}
function fmtPct(x) { return x == null ? null : `${(x * 100).toFixed(x >= 0.995 ? 0 : 1)}%`; }
function fmtUSD(x) {
  if (x == null) return "—";
  if (x >= 1000) return "$" + (x / 1000).toFixed(x >= 100000 ? 0 : 1) + "k";
  if (x >= 1) return "$" + x.toFixed(2);
  if (x <= 0) return "$0";
  if (x < 0.01) return "<$0.01";
  return "$" + x.toFixed(2);
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ── boot: poll until the background scan is ready ───────────────────────── */
async function boot() {
  wireStaticEvents();
  const sub = $("loadingSub");
  const hints = [
    "Reading Claude Code, Codex & Cursor history…",
    "Aggregating token usage…",
    "Codex keeps large rollout files — hang tight…",
  ];
  let tries = 0;
  while (true) {
    let payload;
    try {
      const res = await fetch("/api/sessions");
      payload = await res.json();
    } catch (e) {
      sub.textContent = "Waiting for the server…";
      await sleep(600); continue;
    }
    if (payload.status === "ready") { setData(payload); break; }
    if (payload.status === "error") { sub.textContent = "Error: " + payload.error; return; }
    sub.textContent = hints[Math.min(tries >> 1, hints.length - 1)];
    tries++;
    await sleep(700);
  }
  const el = $("loading");
  el.classList.add("hide");
  setTimeout(() => (el.hidden = true), 400);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function setData(payload) {
  state.all = payload.sessions || [];
  state.sources = payload.sources || [];
  state.enabledSources = new Set(state.sources);
  state.index = new Map(state.all.map((s) => [key(s), s]));
  buildSourceChips();
  buildProjectList();
  render();
}

/* ── filter builders ────────────────────────────────────────────────────── */
function buildSourceChips() {
  const counts = {};
  for (const s of state.all) counts[s.source] = (counts[s.source] || 0) + 1;
  const box = $("sourceFilters");
  box.innerHTML = "";
  for (const src of state.sources) {
    const on = state.enabledSources.has(src);
    const chip = document.createElement("div");
    chip.className = "chip" + (on ? "" : " off");
    chip.innerHTML = `<span class="dot ${src}"></span><span class="name">${SOURCE_LABEL[src] || src}</span><span class="n">${counts[src] || 0}</span>`;
    chip.onclick = () => {
      if (state.enabledSources.has(src)) state.enabledSources.delete(src);
      else state.enabledSources.add(src);
      chip.classList.toggle("off");
      render();
    };
    box.appendChild(chip);
  }
}

function projectsWithCounts() {
  const m = new Map(); // path -> {name, n}
  for (const s of state.all) {
    if (!state.enabledSources.has(s.source)) continue;
    const path = s.project_path || "";
    const name = s.project || (path ? path.split("/").pop() : "(no project)");
    const e = m.get(path) || { path, name, n: 0 };
    e.n++; m.set(path, e);
  }
  return [...m.values()].sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
}

function buildProjectList() {
  const list = projectsWithCounts();
  const q = state.projQuery.toLowerCase();
  const shown = q ? list.filter((p) => p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)) : list;
  $("projCount").textContent = `${list.length}`;
  const box = $("projectFilters");
  box.innerHTML = "";
  for (const p of shown) {
    const row = document.createElement("label");
    row.className = "chk";
    const checked = state.selectedProjects.has(p.path);
    row.innerHTML = `<input type="checkbox" ${checked ? "checked" : ""}/>` +
      `<span class="lbl" title="${esc(p.path || p.name)}">${esc(p.name)}</span><span class="n">${p.n}</span>`;
    row.querySelector("input").onchange = (e) => {
      if (e.target.checked) state.selectedProjects.add(p.path);
      else state.selectedProjects.delete(p.path);
      render();
    };
    box.appendChild(row);
  }
}

/* ── filtering + sorting ────────────────────────────────────────────────── */
function applyFilters() {
  const q = state.query.toLowerCase();
  const from = state.dateFrom ? state.dateFrom : null;
  const to = state.dateTo ? state.dateTo : null;
  let out = state.all.filter((s) => {
    if (!state.enabledSources.has(s.source)) return false;
    if (state.selectedProjects.size && !state.selectedProjects.has(s.project_path || "")) return false;
    if (q) {
      const hay = `${s.title || ""} ${s.project || ""} ${s.model || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    const day = (s.updated_at || s.created_at || "").slice(0, 10);
    if (from && day && day < from) return false;
    if (to && day && day > to) return false;
    return true;
  });
  const cmp = {
    updated: (a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""),
    created: (a, b) => (b.created_at || "").localeCompare(a.created_at || ""),
    cost: (a, b) => (b.cost_usd || 0) - (a.cost_usd || 0),
    tokens: (a, b) => (b.tokens?.total || 0) - (a.tokens?.total || 0),
    messages: (a, b) => (b.message_count || 0) - (a.message_count || 0),
    title: (a, b) => (a.title || "").localeCompare(b.title || ""),
  }[state.sort];
  out.sort(cmp);
  state.filtered = out;
  return out;
}

/* ── render ─────────────────────────────────────────────────────────────── */
function render() {
  buildProjectList();
  const rows = applyFilters();
  const tbody = $("rows");
  tbody.innerHTML = "";
  const frag = document.createDocumentFragment();
  let sumTokens = 0, sumCost = 0;
  for (const s of rows) {
    sumTokens += s.tokens?.total || 0;
    if (s.cost_known && s.cost_usd != null) sumCost += s.cost_usd;
    const k = key(s);
    const selected = state.selected.has(k);
    const tr = document.createElement("tr");
    if (selected) tr.classList.add("sel");
    const t = s.tokens || {};
    const hit = fmtPct(t.cache_hit_rate);
    const basisMark = t.basis && t.basis !== "recorded" ? `<span class="basis" title="${esc(t.basis)}"> ~</span>` : "";
    const costCell = (s.cost_known && s.cost_usd != null)
      ? `<span class="cost">${fmtUSD(s.cost_usd)}${s.cost_estimated ? `<span class="est" title="estimated rate"> ~</span>` : ""}</span>`
      : `<span class="dash-cell" title="not priced">—</span>`;
    tr.innerHTML =
      `<td class="c-check"><div class="cell-check"><input type="checkbox" ${selected ? "checked" : ""}/></div></td>` +
      `<td class="c-title"><div class="cell-title">${esc(s.title || "(untitled)")}</div></td>` +
      `<td class="c-source"><span class="badge ${s.source}"><span class="dot ${s.source}"></span>${SOURCE_LABEL[s.source] || s.source}</span></td>` +
      `<td class="c-project"><span class="proj" title="${esc(s.project_path || "")}">${esc(s.project || "—")}</span></td>` +
      `<td class="c-date"><span class="date" title="${esc(s.updated_at || "")}">${fmtDate(s.updated_at || s.created_at)}</span></td>` +
      `<td class="c-num">${(s.message_count || 0).toLocaleString()}</td>` +
      `<td class="c-num"><span class="tok">${humanTokens(t.total)}${basisMark}</span></td>` +
      `<td class="c-num">${costCell}</td>` +
      `<td class="c-num">${hit ? `<span class="cache"><b>${hit}</b></span>` : `<span class="dash-cell">—</span>`}</td>`;

    const cb = tr.querySelector("input");
    cb.onclick = (e) => { e.stopPropagation(); toggleSelect(k, tr); };
    tr.onclick = () => openDetail(s);
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);

  $("empty").hidden = rows.length !== 0;
  $("count").textContent = `${rows.length.toLocaleString()} of ${state.all.length.toLocaleString()} sessions`
    + (rows.length !== state.all.length ? `  ·  ${humanTokens(sumTokens)} tok · ${fmtUSD(sumCost)}` : "");
  const allTokens = state.all.reduce((a, s) => a + (s.tokens?.total || 0), 0);
  const allCost = state.all.reduce((a, s) => a + (s.cost_known && s.cost_usd != null ? s.cost_usd : 0), 0);
  $("topstat").innerHTML = `<b>${state.all.length.toLocaleString()}</b> sessions · <b>${humanTokens(allTokens)}</b> tokens · <b>${fmtUSD(allCost)}</b>`;
  updateSelectAll();
  updateSelBar();
}

function toggleSelect(k, tr) {
  if (state.selected.has(k)) { state.selected.delete(k); tr?.classList.remove("sel"); tr && (tr.querySelector("input").checked = false); }
  else { state.selected.add(k); tr?.classList.add("sel"); tr && (tr.querySelector("input").checked = true); }
  updateSelectAll(); updateSelBar();
}

function updateSelectAll() {
  const cb = $("selectAll");
  const total = state.filtered.length;
  const selectedInView = state.filtered.reduce((a, s) => a + (state.selected.has(key(s)) ? 1 : 0), 0);
  cb.checked = total > 0 && selectedInView === total;
  cb.indeterminate = selectedInView > 0 && selectedInView < total;
  $("selectAllLabel").textContent = selectedInView > 0 ? `${selectedInView} selected` : "Select all";
}

function updateSelBar() {
  const bar = $("selbar");
  const items = [...state.selected].map((k) => state.index.get(k)).filter(Boolean);
  if (!items.length) { bar.hidden = true; return; }
  bar.hidden = false;
  let total = 0, read = 0, cacheable = 0, anyCache = false, cost = 0;
  for (const s of items) {
    const t = s.tokens || {};
    total += t.total || 0;
    if (s.cost_known && s.cost_usd != null) cost += s.cost_usd;
    if (t.cache_hit_rate != null) { anyCache = true; read += t.cache_read || 0; cacheable += (t.input || 0) + (t.cache_creation || 0) + (t.cache_read || 0); }
  }
  const hit = anyCache && cacheable ? fmtPct(read / cacheable) : null;
  $("selinfo").innerHTML =
    `<b>${items.length}</b> selected <span class="muted">·</span> <b>${humanTokens(total)}</b> tokens` +
    ` <span class="muted">·</span> <b>${fmtUSD(cost)}</b>` +
    (hit ? ` <span class="muted">·</span> <b>${hit}</b> <span class="muted">cache hit</span>` : "");
}

/* ── detail drawer ──────────────────────────────────────────────────────── */
const MAX_RENDER = 500;
async function openDetail(s) {
  const drawer = $("drawer");
  const scrim = $("scrim");
  scrim.hidden = false;
  drawer.hidden = false;
  const t = s.tokens || {};
  const cells = [
    ["Total", humanTokens(t.total)],
    ["Input", humanTokens(t.input)],
    ["Output", humanTokens(t.output)],
  ];
  if (t.cache_read) cells.push(["Cache read", humanTokens(t.cache_read)]);
  if (t.cache_creation) cells.push(["Cache write", humanTokens(t.cache_creation)]);
  if (t.reasoning) cells.push(["Reasoning", humanTokens(t.reasoning)]);
  const hit = fmtPct(t.cache_hit_rate);
  let tokGrid = cells.map(([k, v]) => `<div class="cell"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("") +
    (hit ? `<div class="cell"><div class="k">Cache hit</div><div class="v hit">${hit}</div></div>` : "");
  if (s.cost_known && s.cost_usd != null)
    tokGrid += `<div class="cell"><div class="k">Est. cost${s.cost_estimated ? " ~" : ""}</div><div class="v" style="color:var(--claude)">${fmtUSD(s.cost_usd)}</div></div>`;

  drawer.innerHTML =
    `<div class="drawer-head">
       <div class="row1">
         <h2 class="drawer-title">${esc(s.title || "(untitled)")}</h2>
         <button class="drawer-close" title="Close">
           <svg viewBox="0 0 24 24" class="ic"><path d="M18 6 6 18M6 6l12 12"/></svg>
         </button>
       </div>
       <div class="meta-line">
         <span class="badge ${s.source}"><span class="dot ${s.source}"></span>${SOURCE_LABEL[s.source] || s.source}</span>
         ${s.project ? `<span>${esc(s.project)}</span>` : ""}
         ${s.model ? `<span>· ${esc(s.model)}</span>` : ""}
         <span>· ${s.message_count || 0} msgs</span>
         <span>· ${fmtDate(s.created_at)} → ${fmtDate(s.updated_at)}</span>
       </div>
       ${s.project_path ? `<div class="meta-line" style="margin-top:6px"><code>${esc(s.project_path)}</code></div>` : ""}
     </div>
     <div class="tokgrid">${tokGrid}</div>
     <div class="tok-basis">Token basis: <b>${esc(t.basis || "recorded")}</b>${t.basis === "context-snapshot" ? " — Cursor records the final context size, not cumulative spend or cache hits, so cost is not computed." : ""}${(t.basis === "recorded" && !(s.cost_known)) ? ` — no price configured for model <code>${esc(s.model || "?")}</code> (add it in pricing.json).` : ""}${s.cost_estimated ? " — cost uses an estimated rate." : ""}</div>
     <div class="transcript" id="transcript"><div class="more-note">Loading transcript…</div></div>`;

  drawer.querySelector(".drawer-close").onclick = closeDetail;

  try {
    const res = await fetch(`/api/session?source=${encodeURIComponent(s.source)}&id=${encodeURIComponent(s.id)}`);
    const data = await res.json();
    renderTranscript(data.messages || []);
  } catch (e) {
    $("transcript").innerHTML = `<div class="more-note">Could not load transcript.</div>`;
  }
}

function renderTranscript(messages) {
  const box = $("transcript");
  const shown = messages.slice(0, MAX_RENDER);
  const html = shown.map((m) => {
    const role = m.role || "message";
    const when = m.ts ? `<span class="when">${esc(m.ts.replace("T", " ").replace("Z", ""))}</span>` : "";
    return `<div class="msg ${esc(role)}">
      <div class="who"><span class="rl">${esc(role)}</span>${when}</div>
      <div class="text">${esc(m.text || "")}</div></div>`;
  }).join("");
  const more = messages.length > MAX_RENDER
    ? `<div class="more-note">Showing first ${MAX_RENDER} of ${messages.length} messages. Export to see the full transcript.</div>` : "";
  box.innerHTML = html + more;
  box.scrollTop = 0;
}

function closeOverlays() {
  $("drawer").hidden = true;
  $("statsDrawer").hidden = true;
  $("scrim").hidden = true;
}
const closeDetail = closeOverlays;

/* ── stats panel (cost & usage by model / date, for the current filter) ──── */
function aggBy(sessions, keyFn) {
  const m = new Map();
  for (const s of sessions) {
    const k = keyFn(s);
    let e = m.get(k);
    if (!e) { e = { key: k, n: 0, tokens: 0, cost: 0, priced: 0, source: s.source }; m.set(k, e); }
    e.n++;
    e.tokens += s.tokens?.total || 0;
    if (s.cost_known && s.cost_usd != null) { e.cost += s.cost_usd; e.priced++; }
  }
  return [...m.values()];
}

function openStats() {
  const rows = state.filtered;
  $("scrim").hidden = false;
  const d = $("statsDrawer");
  d.hidden = false;

  let tokens = 0, cost = 0, priced = 0, unpriced = 0, read = 0, cacheable = 0, anyCache = false;
  for (const s of rows) {
    tokens += s.tokens?.total || 0;
    if (s.cost_known && s.cost_usd != null) { cost += s.cost_usd; priced++; } else unpriced++;
    const t = s.tokens || {};
    if (t.cache_hit_rate != null) { anyCache = true; read += t.cache_read || 0; cacheable += (t.input || 0) + (t.cache_creation || 0) + (t.cache_read || 0); }
  }
  const hit = anyCache && cacheable ? fmtPct(read / cacheable) : "—";

  const byModel = aggBy(rows, (s) => `${s.source}::${s.model || "—"}`).sort((a, b) => b.cost - a.cost || b.tokens - a.tokens);
  const byDate = aggBy(rows, (s) => (s.updated_at || s.created_at || "").slice(0, 10) || "—").sort((a, b) => b.key.localeCompare(a.key));
  const maxM = Math.max(1, ...byModel.map((e) => e.cost));
  const maxD = Math.max(1, ...byDate.map((e) => e.cost));

  const costCell = (e, max) => {
    if (e.priced === 0) return `<td class="r"><span class="dash-cell">—</span></td>`;
    const approx = e.priced < e.n ? `<span class="mono" title="${e.n - e.priced} not priced">~</span> ` : "";
    return `<td class="r">${approx}${fmtUSD(e.cost)}</td>`;
  };
  const barCell = (label, e, max) =>
    `<td class="lbl"><div class="bar" style="width:${(e.cost / max * 100).toFixed(1)}%"></div><span>${label}</span></td>`;

  const modelRows = byModel.map((e) => {
    const model = e.key.split("::")[1];
    const label = `<span class="badge ${e.source}"><span class="dot ${e.source}"></span>${SOURCE_LABEL[e.source] || e.source}</span> ${esc(model)}`;
    return `<tr>${barCell(label, e, maxM)}<td class="r">${e.n}</td><td class="r">${humanTokens(e.tokens)}</td>${costCell(e, maxM)}</tr>`;
  }).join("");

  const dateRows = byDate.map((e) =>
    `<tr>${barCell(esc(e.key), e, maxD)}<td class="r">${e.n}</td><td class="r">${humanTokens(e.tokens)}</td>${costCell(e, maxD)}</tr>`).join("");

  const scope = rows.length === state.all.length ? "all sessions" : "the current filter";
  d.innerHTML =
    `<div class="drawer-head">
       <div class="row1">
         <h2 class="drawer-title">Cost &amp; usage</h2>
         <button class="drawer-close" title="Close"><svg viewBox="0 0 24 24" class="ic"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
       </div>
       <div class="meta-line">Across <b>${scope}</b> — ${rows.length.toLocaleString()} session${rows.length === 1 ? "" : "s"}.</div>
     </div>
     <div class="stats-body">
     <div class="stats-tiles">
       <div class="cell"><div class="k">Sessions</div><div class="v">${rows.length.toLocaleString()}</div></div>
       <div class="cell"><div class="k">Tokens</div><div class="v">${humanTokens(tokens)}</div></div>
       <div class="cell"><div class="k">Est. cost</div><div class="v money">${fmtUSD(cost)}</div></div>
       <div class="cell"><div class="k">Cache hit</div><div class="v">${hit}</div></div>
     </div>
     <div class="stats-section">
       <h3>By model</h3>
       <table class="stats-table"><thead><tr><th>Model</th><th class="r">Sessions</th><th class="r">Tokens</th><th class="r">Cost</th></tr></thead>
       <tbody>${modelRows || '<tr><td colspan="4">—</td></tr>'}</tbody></table>
     </div>
     <div class="stats-section">
       <h3>By date</h3>
       <table class="stats-table"><thead><tr><th>Day</th><th class="r">Sessions</th><th class="r">Tokens</th><th class="r">Cost</th></tr></thead>
       <tbody>${dateRows || '<tr><td colspan="4">—</td></tr>'}</tbody></table>
     </div>
     <div class="stats-note">
       Cost is estimated from provider-recorded token usage × <code>pricing.json</code> (cache reads/writes included).
       ${unpriced ? `${unpriced} session${unpriced === 1 ? "" : "s"} not priced (Cursor context-snapshots, or models missing from pricing.json).` : ""}
       A <b>~</b> marks rows using an estimated rate.
     </div>
     <div class="stats-actions"><button class="btn ghost" id="reloadPrices">↻ Reload prices from pricing.json</button></div>
     </div>`;

  d.querySelector(".drawer-close").onclick = closeOverlays;
  d.querySelector("#reloadPrices").onclick = reloadPrices;
}

async function reloadPrices() {
  toast("Reloading prices…", true);
  try {
    const res = await fetch("/api/sessions?reprice=1");
    const p = await res.json();
    const m = new Map((p.sessions || []).map((s) => [key(s), s]));
    for (const s of state.all) {
      const n = m.get(key(s));
      if (n) { s.cost_usd = n.cost_usd; s.cost_known = n.cost_known; s.cost_estimated = n.cost_estimated; }
    }
    render();
    openStats();
    toast("Prices reloaded");
  } catch (e) { toast("Reload failed"); }
}

/* ── export ─────────────────────────────────────────────────────────────── */
function currentFilter() {
  return {
    sources: [...state.enabledSources],
    projects: state.selectedProjects.size ? [...state.selectedProjects] : "all",
    query: state.query || null,
    date_from: state.dateFrom || null,
    date_to: state.dateTo || null,
    sort: state.sort,
  };
}

async function doExport(format) {
  const items = [...state.selected].map((k) => state.index.get(k)).filter(Boolean).map((s) => ({ source: s.source, id: s.id }));
  if (!items.length) return;
  const btnRaw = $("exportRaw"), btnNotion = $("exportNotion");
  btnRaw.disabled = btnNotion.disabled = true;
  toast(`Preparing ${items.length} session${items.length > 1 ? "s" : ""}…`, true);
  try {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format, items, filter: currentFilter() }),
    });
    if (!res.ok) throw new Error((await res.json()).error || "export failed");
    const blob = await res.blob();
    let fname = format === "notion" ? "sessions-notion.zip" : "sessions-export.zip";
    const cd = res.headers.get("Content-Disposition");
    const m = cd && cd.match(/filename="([^"]+)"/);
    if (m) fname = m[1];
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = fname; document.body.appendChild(a); a.click();
    a.remove(); URL.revokeObjectURL(url);
    toast(`Exported ${items.length} session${items.length > 1 ? "s" : ""} → ${fname}`);
  } catch (e) {
    toast("Export failed: " + e.message);
  } finally {
    btnRaw.disabled = btnNotion.disabled = false;
  }
}

let toastTimer;
function toast(msg, sticky) {
  const el = $("toast");
  el.textContent = msg; el.hidden = false;
  clearTimeout(toastTimer);
  if (!sticky) toastTimer = setTimeout(() => (el.hidden = true), 3200);
}

/* ── static wiring ──────────────────────────────────────────────────────── */
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

function wireStaticEvents() {
  $("query").oninput = debounce((e) => { state.query = e.target.value.trim(); render(); }, 140);
  $("projQuery").oninput = debounce((e) => { state.projQuery = e.target.value.trim(); buildProjectList(); }, 120);
  $("dateFrom").onchange = (e) => { state.dateFrom = e.target.value; render(); };
  $("dateTo").onchange = (e) => { state.dateTo = e.target.value; render(); };
  $("sort").onchange = (e) => { state.sort = e.target.value; render(); };

  $("selectAll").onclick = (e) => {
    const check = e.target.checked;
    for (const s of state.filtered) { const k = key(s); check ? state.selected.add(k) : state.selected.delete(k); }
    render();
  };
  $("clearSel").onclick = () => { state.selected.clear(); render(); };
  $("exportRaw").onclick = () => doExport("raw");
  $("exportNotion").onclick = () => doExport("notion");

  $("reset").onclick = () => {
    state.query = state.projQuery = state.dateFrom = state.dateTo = "";
    state.selectedProjects.clear();
    state.enabledSources = new Set(state.sources);
    $("query").value = $("projQuery").value = ""; $("dateFrom").value = $("dateTo").value = "";
    buildSourceChips(); render();
  };

  $("refresh").onclick = async () => {
    toast("Re-scanning session files…", true);
    try {
      const res = await fetch("/api/sessions?refresh=1");
      const payload = await res.json();
      setData(payload);
      toast(`Indexed ${state.all.length} sessions`);
    } catch (e) { toast("Refresh failed"); }
  };

  $("statsBtn").onclick = openStats;
  $("scrim").onclick = closeOverlays;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeOverlays(); });
}

boot();
