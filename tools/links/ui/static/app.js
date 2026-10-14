"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let seenResults = 0, state = null, library = null, logSince = 0, lastJobId = null, polling = null, logHidden = false;

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-UI": "1" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

// ───── tabs
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  document.querySelectorAll("main > section").forEach((s) => (s.hidden = s.id !== "tab-" + name));
  if (name === "library") loadLibrary();
  if (name === "download") { initDownload(); refreshDlProgress(); }
  if (name === "lists") initLists();
  document.body.classList.toggle("tab-discover", name === "discover");
  if (typeof discoverToggle === "function") discoverToggle(name === "discover");
}

// ───── state
async function refresh() {
  state = await api("/api/state");
  renderHeader();
  if (!$("#importFolder").value) $("#importFolder").value = state.links_dir || "";
  renderProfileSelect();
  renderCreators();
  renderSites();
  renderSettings();
  if (state.job) attachJob(state.job);
}

function checkStale() {
  // an old server doesn't send these at all; a newer one reports when its code on disk has changed since it started
  const stale = !state.running_version || state.running_version !== state.disk_version;
  $("#staleBanner").hidden = !stale;
}

function renderHeader() {
  checkStale();
  const s = state.script, site = $("#site"), banner = $("#banner");
  const custom = state.profiles.filter((p) => !p.virtual);
  const domains = state.profiles.filter((p) => !p.virtual || (s.exists && s.domain)).map((p) => (p.base_url || "").replace(/^https?:\/\//, ""));
  if (!s.exists && !custom.length) {
    site.textContent = "Scraper not found"; site.className = "chip bad";
    banner.hidden = false; banner.textContent = "Can't find the scraper at " + s.path + ". Set the path in Settings, or add a site in the Sites tab.";
  } else if (s.exists && !s.domain && !custom.length) {
    site.textContent = "Site unknown"; site.className = "chip bad";
    banner.hidden = false; banner.textContent = s.error;
  } else {
    site.textContent = "Sites: " + domains.filter(Boolean).join(", "); site.className = "chip good";
    banner.hidden = true;
  }
}

function profileName(id) {
  const p = state.profiles.find((x) => x.id === (id || "script"));
  return p ? p.name : id;
}

function updateNameHint() {
  const p = state.profiles.find((x) => x.id === $("#newProfile").value);
  const n = p && !p.virtual ? (p.creator_patterns || []).length : 0;
  $("#nameHint").textContent = n
    ? "Names are looked up by trying " + n + " address" + (n === 1 ? "" : "es") + " for this site."
    : "To add by name instead of a link, give the site addresses to try in the Sites tab.";
}
$("#newProfile").addEventListener("change", () => { updateNameHint(); renderAlsoSites(); });

// the site you chose as the main one (Sites tab), else the first
const defaultSite = () => {
  const d = state.settings && state.settings.default_site;
  return state.profiles.some((p) => p.id === d) ? d : state.profiles[0].id;
};

function renderImportSites() {
  const sel = $("#importSite"), keep = sel.value;
  sel.innerHTML = state.profiles.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  sel.value = keep && state.profiles.some((p) => p.id === keep) ? keep : defaultSite();
}

const ALSO_KEY = "alsoSites";
function renderAlsoSites() {
  // other sites that can look a name up (they have "creator addresses to try"); the first site is the one in the select
  const first = $("#newProfile").value;
  let saved = [];
  try { saved = JSON.parse(localStorage.getItem(ALSO_KEY) || "[]"); } catch (e) { /* ignore */ }
  const others = state.profiles.filter((p) => !p.virtual && p.id !== first && (p.creator_patterns || []).some((x) => x.trim()));
  $("#alsoBox").hidden = !others.length;
  $("#alsoSites").innerHTML = others.map((p) =>
    `<label class="check"><input type="checkbox" value="${esc(p.id)}" ${saved.includes(p.id) ? "checked" : ""}> ${esc(p.name)}</label>`).join("");
  $("#alsoSites").querySelectorAll("input").forEach((i) => (i.onchange = () => {
    const ids = [...$("#alsoSites").querySelectorAll("input:checked")].map((x) => x.value);
    const keep = saved.filter((id) => !others.some((o) => o.id === id));       // remember choices for sites not shown now
    try { localStorage.setItem(ALSO_KEY, JSON.stringify([...keep, ...ids])); } catch (e) { /* ignore */ }
  }));
}

function renderProfileSelect() {
  renderImportSites();
  const sel = $("#newProfile"), keep = sel.value;
  sel.innerHTML = state.profiles.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  sel.value = keep && state.profiles.some((p) => p.id === keep) ? keep : defaultSite();
  updateNameHint();
  renderAlsoSites();
}

// ───── creators
const openRows = new Set(), linkCache = {}, panelState = {};
const HUES = [24, 152, 205, 275, 340, 48, 100, 180];
const GROUP_CAP = 120;

function catStyle(cat, cats) {
  if (cat === "Other") return "--h:220;--s:7%";
  return "--h:" + HUES[Math.max(0, cats.indexOf(cat)) % HUES.length];
}
const pstate = (slug) => (panelState[slug] = panelState[slug] ||
  { cats: new Set(), buckets: new Set(), sort: "order", q: "", minViews: "", expanded: new Set() });

// "100k" -> 100000, "1.5m" -> 1500000, "" or junk -> 0
function parseMinViews(raw) {
  const m = String(raw || "").trim().toLowerCase().replace(/[,\s]/g, "").match(/^(\d+(?:\.\d+)?)([kmb]?)$/);
  return m ? Math.round(parseFloat(m[1]) * { "": 1, k: 1e3, m: 1e6, b: 1e9 }[m[2]]) : 0;
}

async function loadPanel(c) {
  const cached = linkCache[c.slug];
  if (!cached || cached.stamp !== c.last_scraped) {
    try {
      const r = await api("/api/creator_links?slug=" + encodeURIComponent(c.slug));
      linkCache[c.slug] = { stamp: c.last_scraped, ...r };
    } catch (e) {
      const el = document.querySelector(`[data-panel="${CSS.escape(c.slug)}"]`);
      if (el) el.textContent = e.message;
      return;
    }
  }
  fillPanel(c.slug);
}

function prettyTitle(url) {
  try {
    const seg = decodeURIComponent(new URL(url).pathname.split("/").filter(Boolean).pop() || url);
    return seg.replace(/[-_]+/g, " ");
  } catch (e) { return url; }
}
const shortPath = (url) => { try { return new URL(url).pathname; } catch (e) { return url; } };

function visibleLinks(slug) {
  const d = linkCache[slug], s = pstate(slug), q = s.q.toLowerCase().trim();
  let items = d.links.filter((l) =>
    (!s.cats.size || s.cats.has(l.category)) &&
    (!s.buckets.size || s.buckets.has(l.bucket)) &&
    (!q || (l.url + " " + (l.title || prettyTitle(l.url)) + " " + l.category + " " + l.dur).toLowerCase().includes(q)));
  const minV = parseMinViews(s.minViews);
  if (minV) items = items.filter((l) => (l.views || 0) >= minV);          // a link with no view count can't pass a minimum
  const name = (l) => (l.title || prettyTitle(l.url));
  const az = (a, b) => name(a).localeCompare(name(b), undefined, { numeric: true, sensitivity: "base" });
  if (s.sort === "short" || s.sort === "long") {
    const key = (l) => (l.secs == null ? (s.sort === "short" ? Infinity : -Infinity) : l.secs);
    items = [...items].sort((a, b) => (s.sort === "short" ? key(a) - key(b) : key(b) - key(a)));
  } else if (s.sort === "views") {
    items = [...items].sort((a, b) => ((b.views ?? -1) - (a.views ?? -1)) || az(a, b));          // most viewed first, unknown last
  } else if (s.sort === "viewsAsc") {
    items = [...items].sort((a, b) => ((a.views ?? Infinity) - (b.views ?? Infinity)) || az(a, b));
  } else if (s.sort === "az") {
    items = [...items].sort(az);
  } else if (s.sort === "za") {
    items = [...items].sort((a, b) => az(b, a));
  }
  return items;
}

function fillPanel(slug) {
  const el = document.querySelector(`[data-panel="${CSS.escape(slug)}"]`);
  if (!el) return;
  const s = pstate(slug);
  el.innerHTML = `
    <div class="lp">
      <div class="catTiles"></div>
      <div class="lpTools">
        <input class="panelFilter" placeholder="Search these links…" value="${esc(s.q)}">
        <select class="panelSort">
          <option value="order">Scrape order</option>
          <option value="az">Title A to Z</option>
          <option value="za">Title Z to A</option>
          <option value="views">Most viewed first</option>
          <option value="viewsAsc">Least viewed first</option>
          <option value="short">Shortest first</option>
          <option value="long">Longest first</option>
        </select>
        <input class="panelMinViews" placeholder="Min views, e.g. 1m" value="${esc(s.minViews)}" title="Only links with at least this many views (100k, 1.5m …). Links with no view count are hidden while this is set." style="width:150px">
        <span class="muted panelCount"></span>
        <button class="panelCopy" data-copy="all">Copy shown</button>
      </div>
      <div class="bChips"></div>
      <div class="lpBody"></div>
    </div>`;
  el.querySelector(".panelSort").value = s.sort;
  el.querySelector(".panelFilter").oninput = (e) => { s.q = e.target.value; renderBody(slug); };
  el.querySelector(".panelSort").onchange = (e) => { s.sort = e.target.value; renderBody(slug); };
  el.querySelector(".panelMinViews").oninput = (e) => { s.minViews = e.target.value; renderBody(slug); };
  el.onclick = (e) => {
    const t = e.target.closest("[data-cat],[data-bucket],[data-more],[data-copy],[data-clear]");
    if (!t) return;
    if (t.dataset.cat !== undefined) {
      if (t.dataset.cat === "") s.cats.clear();
      else s.cats.has(t.dataset.cat) ? s.cats.delete(t.dataset.cat) : s.cats.add(t.dataset.cat);
      renderTiles(slug); renderBody(slug);
    } else if (t.dataset.bucket !== undefined) {
      s.buckets.has(t.dataset.bucket) ? s.buckets.delete(t.dataset.bucket) : s.buckets.add(t.dataset.bucket);
      renderBuckets(slug); renderBody(slug);
    } else if (t.dataset.more !== undefined) {
      s.expanded.add(t.dataset.more); renderBody(slug);
    } else if (t.dataset.clear !== undefined) {
      s.cats.clear(); s.buckets.clear(); s.q = ""; el.querySelector(".panelFilter").value = "";
      renderTiles(slug); renderBuckets(slug); renderBody(slug);
    } else if (t.dataset.copy !== undefined) {
      const items = visibleLinks(slug).filter((l) => t.dataset.copy === "all" || l.category === t.dataset.copy);
      navigator.clipboard.writeText(items.map((l) => l.url).join("\n"));
      const old = t.textContent; t.textContent = "Copied " + items.length;
      setTimeout(() => (t.textContent = old), 1300);
    }
  };
  renderTiles(slug); renderBuckets(slug); renderBody(slug);
}

function renderTiles(slug) {
  const d = linkCache[slug], s = pstate(slug), total = d.links.length;
  const counts = {};
  d.links.forEach((l) => (counts[l.category] = (counts[l.category] || 0) + 1));
  const order = d.categories.filter((c) => counts[c]);
  document.querySelector(`[data-panel="${CSS.escape(slug)}"] .catTiles`).innerHTML =
    `<button class="catTile all ${s.cats.size ? "" : "on"}" data-cat=""><span class="tName">All</span><span class="tCount">${total}</span><span class="tBar"><i style="width:100%"></i></span></button>` +
    order.map((c) => `
      <button class="catTile ${s.cats.has(c) ? "on" : ""}" style="${catStyle(c, d.categories)}" data-cat="${esc(c)}" aria-pressed="${s.cats.has(c)}">
        <span class="tName">${esc(c)}</span><span class="tCount">${counts[c]}</span>
        <span class="tBar"><i style="width:${(counts[c] / total) * 100}%"></i></span>
      </button>`).join("");
}

function renderBuckets(slug) {
  const d = linkCache[slug], s = pstate(slug), counts = {};
  d.links.forEach((l) => (counts[l.bucket] = (counts[l.bucket] || 0) + 1));
  const chips = d.bucket_labels.filter((b) => counts[b]);
  document.querySelector(`[data-panel="${CSS.escape(slug)}"] .bChips`).innerHTML = chips.length > 1
    ? '<span class="muted">Length</span>' + chips.map((b) =>
      `<button class="bChip ${s.buckets.has(b) ? "on" : ""}" data-bucket="${esc(b)}">${esc(b.replace(/_/g, " "))} <b>${counts[b]}</b></button>`).join("")
    : "";
}

function renderBody(slug) {
  const d = linkCache[slug], s = pstate(slug);
  const el = document.querySelector(`[data-panel="${CSS.escape(slug)}"]`);
  if (!el) return;
  const items = visibleLinks(slug);
  el.querySelector(".panelCount").textContent = items.length === d.links.length
    ? d.links.length + " links" : items.length + " of " + d.links.length;
  const groups = {};
  items.forEach((l) => (groups[l.category] = groups[l.category] || []).push(l));
  const cats = d.categories.filter((c) => groups[c]);
  el.querySelector(".lpBody").innerHTML = cats.length ? cats.map((c) => {
    const g = groups[c], capped = g.length > GROUP_CAP && !s.expanded.has(c);
    return `<section class="grp" style="${catStyle(c, d.categories)}">
      <header class="grpHead"><span class="dot"></span><strong>${esc(c)}</strong><span class="muted">${g.length} link${g.length === 1 ? "" : "s"}</span>
        <button class="link" data-copy="${esc(c)}">Copy</button></header>
      <div class="cards">${(capped ? g.slice(0, GROUP_CAP) : g).map((l) => `
        <a class="lcard" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer" title="${esc(l.title ? l.title + "\n" + l.url : l.url)}">
          <span class="cTitle ${l.title ? "real" : ""}">${esc(l.title || prettyTitle(l.url))}</span>
          <span class="cDur">${esc(l.dur)}</span>
          <span class="cPath">${esc(shortPath(l.url))}${l.views != null ? ` · <b class="cViews" title="${l.views.toLocaleString()} views">${fmtViews(l.views)} views</b>` : ""}</span>
        </a>`).join("")}</div>
      ${capped ? `<button class="more" data-more="${esc(c)}">Show all ${g.length}</button>` : ""}
    </section>`;
  }).join("") : `<div class="lpEmpty">No links match these filters. <button class="link" data-clear="1">Clear filters</button></div>`;
}

// 17600000 -> "17.6M", 340000 -> "340K"
function fmtViews(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e10 ? 0 : 1).replace(/\.0$/, "") + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (n >= 1e4) return Math.round(n / 1e3) + "K";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  return String(n);
}

function ago(ts) {
  if (!ts) return "never";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const renaming = new Set();

function creatorCard(c, rows) {
  const initial = (c.slug.replace(/[^a-z0-9]/gi, "")[0] || "?").toUpperCase();
  const open = openRows.has(c.slug) && c.count;
  return `
  <article class="ccard ${open ? "open" : ""}" data-card="${esc(c.slug)}">
    ${c.avatar_pending ? `
    <div class="cpic two">
      <figure><img src="${esc(c.avatar || "")}" alt=""><figcaption>Current${c.avatar_site_name ? " · " + esc(c.avatar_site_name) : ""}</figcaption></figure>
      <figure><img src="${esc(c.avatar_pending)}" alt=""><figcaption>New · ${esc(c.avatar_pending_site)}</figcaption></figure>
    </div>
    <div class="avchoice"><span>Two different pictures. Which one?</span>
      <button class="link" data-av="current|${esc(c.slug)}">Keep current</button>
      <button class="primary" data-av="new|${esc(c.slug)}">Use new</button></div>`
    : `<div class="cpic">${c.avatar ? `<img src="${esc(c.avatar)}" alt="" loading="lazy">` : `<span class="cinit">${esc(initial)}</span>`}</div>`}
    <div class="cbody">
      ${renaming.has(c.slug) ? `
      <div class="renameForm">
        <label>Name on this box <input data-rn-display value="${esc(c.display_name || "")}" placeholder="${esc(c.slug)}" spellcheck="false"></label>
        <label>Download folder <input data-rn-folder value="${esc(c.folder_custom ? c.folder : "")}" placeholder="${esc(c.folder || c.slug)}" spellcheck="false"></label>
        <label class="check"><input data-rn-move type="checkbox" checked> Also rename the existing folder</label>
        <div class="muted" style="font-size:12px">Leave a box empty for the automatic name. Folder names can use letters, numbers, - _ and . only (anything else becomes _).</div>
        <div class="row" style="margin-top:6px"><button class="primary" data-rn-save="${esc(c.slug)}">Save</button><button class="link" data-rn-cancel="${esc(c.slug)}">Cancel</button><span class="muted" data-rn-msg></span></div>
      </div>` : `
      <div class="cname" title="${esc(c.display || c.slug)}">${esc(c.display || c.slug)}</div>
      ${c.display && c.display !== c.slug ? `<div class="muted cmeta">${esc(c.slug)}</div>` : ""}
      <div class="muted cmeta">folder <code>${esc(c.folder || c.slug)}</code>${c.folder_custom ? " · custom" : ""}</div>`}
      <div class="cstats">
        ${c.count == null ? '<span class="muted">not scraped</span>'
          : `<button class="link cnt" data-toggle="${esc(c.slug)}" title="Show links">${c.count} links ${open ? "▴" : "▾"}</button>`}
        <span class="muted">${c.last_scraped ? ago(c.last_scraped) : ""}</span>
      </div>
      ${(c.sources || []).map((s) => `
      <div class="src">
        <div><span class="srcName">${esc(s.site)}</span> <span class="muted">· ${s.count ? s.count + " links" : "not scraped"}${s.all_pages ? " · all pages" : ""}</span>
          ${s.url ? `<button class="link" data-src-scrape="${esc(c.slug)}|${esc(s.profile)}" title="Re-scrape just this site">Re-scrape</button>` : ""}
          ${c.sources.length > 1 && s.url ? `<button class="link" data-src-unlink="${esc(c.slug)}|${esc(s.profile)}" title="Make this site its own creator again">Unlink</button>` : ""}
          ${c.sources.length > 1 ? `<button class="link danger" data-src-remove="${esc(c.slug)}|${esc(s.profile)}" title="Remove just this site's links">Remove</button>` : ""}</div>
        <div class="muted srcUrl">${s.url ? esc(s.url) : "imported from a file, no address yet. Add this creator's link for this site to be able to re-scrape."}</div>
      </div>`).join("")}
      <div class="cactions">
        <button class="link" data-scrape="${esc(c.slug)}">${c.count == null ? "Scrape" : "Re-scrape"}</button>
        <button class="link" data-rename="${esc(c.slug)}">Rename</button>
        <button class="link danger" data-remove="${esc(c.slug)}">Remove</button>
        ${rows.length > 1 ? `<select data-merge="${esc(c.slug)}" title="Same person as another creator? Merge them"><option value="">Merge into…</option>${rows.filter((o) => o.slug !== c.slug).map((o) => `<option value="${esc(o.slug)}">${esc(o.slug)}</option>`).join("")}</select>` : ""}
      </div>
    </div>
  </article>`;
}

// A creator's links open as a full-width panel under the last card of that card's row.
function placePanels() {
  const grid = $("#creatorGrid");
  grid.querySelectorAll(".gridPanel").forEach((p) => p.remove());
  const cards = [...grid.querySelectorAll(".ccard")];
  const cols = Math.max(1, getComputedStyle(grid).gridTemplateColumns.split(" ").length);
  cards.forEach((card, i) => {
    const slug = card.dataset.card;
    if (!(openRows.has(slug) && state.creators.find((c) => c.slug === slug && c.count))) return;
    const last = cards[Math.min((Math.floor(i / cols) + 1) * cols, cards.length) - 1];
    last.insertAdjacentHTML("afterend", `<div class="gridPanel"><div class="linkPanel" data-panel="${esc(slug)}"><span class="muted">Loading…</span></div></div>`);
  });
}

let lastCols = 0;
window.addEventListener("resize", () => {
  const grid = $("#creatorGrid");
  if (!grid || grid.hidden) return;
  const cols = getComputedStyle(grid).gridTemplateColumns.split(" ").length;
  if (cols !== lastCols) { lastCols = cols; placePanels(); state.creators.filter((c) => openRows.has(c.slug) && c.count).forEach(loadPanel); }
});

try { $("#creatorSort").value = localStorage.getItem("creatorSort") || "az"; } catch (e) { /* storage may be blocked */ }
$("#creatorSort").onchange = () => {
  try { localStorage.setItem("creatorSort", $("#creatorSort").value); } catch (e) { /* optional */ }
  renderCreators();
};

function renderCreators() {
  if (document.activeElement && document.activeElement.closest && document.activeElement.closest(".renameForm")) return;   // don't wipe what you're typing
  // sorted by the choice in the Sort box; names use the name shown on each box (so a renamed creator sorts under its new name)
  const byName = (a, b) => (a.display || a.slug).localeCompare(b.display || b.slug, undefined, { numeric: true, sensitivity: "base" });
  const mode = $("#creatorSort").value;
  const rows = [...state.creators].sort(
    mode === "za" ? (a, b) => byName(b, a)
    : mode === "most" ? (a, b) => ((b.count ?? -1) - (a.count ?? -1)) || byName(a, b)
    : mode === "least" ? (a, b) => ((a.count ?? 1e12) - (b.count ?? 1e12)) || byName(a, b)
    : byName);
  $("#creatorCount").textContent = rows.length ? "(" + rows.length + ")" : "";
  $("#empty").hidden = rows.length > 0;
  $("#creatorGrid").hidden = rows.length === 0;
  $("#creatorGrid").innerHTML = rows.map((c) => creatorCard(c, rows)).join("");
  lastCols = getComputedStyle($("#creatorGrid")).gridTemplateColumns.split(" ").length;
  placePanels();
  document.querySelectorAll("[data-toggle]").forEach((b) => (b.onclick = () => {
    const s = b.dataset.toggle;
    openRows.has(s) ? openRows.delete(s) : openRows.add(s);
    renderCreators();
  }));
  rows.filter((c) => openRows.has(c.slug) && c.count).forEach((c) => loadPanel(c));
  document.querySelectorAll("[data-scrape]").forEach((b) => (b.onclick = () => startScrape([b.dataset.scrape])));
  document.querySelectorAll("[data-src-scrape]").forEach((b) => (b.onclick = () => {
    const [slug, pid] = b.dataset.srcScrape.split("|");
    startScrape(null, false, { slug, pid });
  }));
  document.querySelectorAll("[data-av]").forEach((b) => (b.onclick = async () => {
    const [choice, slug] = b.dataset.av.split("|");
    try { await api("/api/creators/avatar_choice", { slug, choice }); refresh(); } catch (e) { alert(e.message); }
  }));
  document.querySelectorAll("[data-rename]").forEach((b) => (b.onclick = () => { renaming.add(b.dataset.rename); renderCreators(); }));
  document.querySelectorAll("[data-rn-cancel]").forEach((b) => (b.onclick = () => { renaming.delete(b.dataset.rnCancel); renderCreators(); }));
  document.querySelectorAll("[data-rn-save]").forEach((b) => (b.onclick = async () => {
    const card = b.closest(".ccard"), slug = b.dataset.rnSave, msg = card.querySelector("[data-rn-msg]");
    try {
      const r = await api("/api/creators/rename", {
        slug, display: card.querySelector("[data-rn-display]").value,
        folder: card.querySelector("[data-rn-folder]").value, move_existing: card.querySelector("[data-rn-move]").checked,
      });
      renaming.delete(slug);
      await refresh();
      if (r.note) alert(r.note);
    } catch (e) { msg.textContent = e.message; }
  }));
  document.querySelectorAll("[data-src-unlink]").forEach((b) => (b.onclick = async () => {
    const [slug, pid] = b.dataset.srcUnlink.split("|");
    if (!confirm("Split this site out of " + slug + " into its own creator?")) return;
    try { await api("/api/creators/unlink", { slug, pid }); refresh(); } catch (e) { alert(e.message); }
  }));
  document.querySelectorAll("[data-merge]").forEach((sel) => (sel.onchange = async () => {
    const into = sel.value, slug = sel.dataset.merge;
    if (!into) return;
    if (!confirm("Merge " + slug + " into " + into + "? Their links combine in one file, and " + slug + " is removed as a separate creator.")) { sel.value = ""; return; }
    try { await api("/api/creators/link", { slug, into }); refresh(); } catch (e) { alert(e.message); sel.value = ""; }
  }));
  document.querySelectorAll("[data-src-remove]").forEach((b) => (b.onclick = async () => {
    const [slug, pid] = b.dataset.srcRemove.split("|");
    if (!confirm("Remove this site's links for " + slug + "? Links from the creator's other sites stay.")) return;
    try { await api("/api/creators/remove_source", { slug, pid }); refresh(); } catch (e) { alert(e.message); }
  }));
  document.querySelectorAll("[data-remove]").forEach((b) => (b.onclick = async () => {
    if (!confirm("Remove " + b.dataset.remove + " and delete its saved links?")) return;
    await api("/api/creators/remove", { slug: b.dataset.remove });
    refresh();
  }));
}

async function addCreators(urls, linkMap) {
  const msg = $("#addMsg"), btn = $("#addBtn");
  btn.disabled = true;
  try {
    const r = await api("/api/creators/add", {
      urls, pages: $("#newPages").value, profile: $("#newProfile").value,
      scrape: $("#autoScrape").checked, link_map: linkMap || {},
    });
    const parts = [];
    if (r.added.length) parts.push(r.added.length + " added");
    if (r.linked && r.linked.length) parts.push(r.linked.map((l) => l.slug + " linked to " + l.to + (l.how === "auto" ? " (names match)" : "")).join(", "));
    if (r.attached && r.attached.length) parts.push(r.attached.join(", ") + ": address added to the file you imported");
    if (r.joined && r.joined.length) parts.push(r.joined.join(", ") + " already existed, so this site was added to the same creator");
    if (r.finding.length) parts.push("looking up " + r.finding.length + " name" + (r.finding.length === 1 ? "" : "s"));
    if (r.skipped.length) parts.push(r.skipped.length + " skipped (" + r.skipped.map((s) => s.reason).join("; ") + ")");
    if (r.suggestions && r.suggestions.length) parts.push(r.suggestions.length + " need your answer below");
    let t = parts.join(", ") || "Nothing to add";
    if (r.warnings.length) t += ". " + r.warnings[0];
    if (r.job) t += ". " + (r.added.length + r.finding.length + (r.joined || []).length + (r.linked || []).length > 1 ? "Working through them one by one…" : "Working on it…");
    msg.textContent = t;
    showSuggestions(r.suggestions || []);
    if (r.added.length || r.finding.length || (r.joined && r.joined.length) || (r.linked && r.linked.length) || (r.attached && r.attached.length)) {
      // keep only the lines still waiting for an answer
      $("#newUrls").value = (r.suggestions || []).map((x) => x.url).join("\n");
    }
    await refresh();
    if (r.job) { logHidden = false; attachJob(r.job); }
  } catch (e) { msg.textContent = e.message; }
  btn.disabled = false;
}

// Names that look like someone already in the list but not sure enough to merge on their own.
function showSuggestions(list) {
  const box = $("#linkSuggest");
  box.hidden = !list.length;
  box.innerHTML = list.map((x, i) => `
    <div class="suggest">
      <span><strong>${esc(x.slug)}</strong> looks like <strong>${esc(x.candidate)}</strong> (${x.pct}% of the shorter name matches). Same person?</span>
      <button class="link" data-sg="${i}" data-yes="1">Yes, link them</button>
      <button class="link" data-sg="${i}" data-yes="0">No, new creator</button>
    </div>`).join("");
  box.querySelectorAll("[data-sg]").forEach((b) => (b.onclick = () => {
    const x = list[+b.dataset.sg];
    addCreators(x.url, { [x.url]: b.dataset.yes === "1" ? x.candidate : "" });
  }));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitForJob() {
  for (;;) {
    await sleep(1500);
    const r = await api("/api/job?since=999999999");
    if (!r.job || r.job.status !== "running") return r.job;
  }
}

// One name, several sites, one after the other: the chosen site first (it also takes pasted links), then each ticked
// site gets just the names, and the next site only starts when the previous scrape has finished.
async function addAcrossSites(text) {
  const first = $("#newProfile").value;
  const extra = [...$("#alsoSites").querySelectorAll("input:checked")].map((i) => i.value).filter((id) => id !== first);
  if (!extra.length) return addCreators(text);
  const msg = $("#addMsg"), btn = $("#addBtn");
  const names = text.split("\n").filter((l) => l.trim() && !/https?:\/\//i.test(l)).join("\n");
  const plan = [{ id: first, urls: text }, ...extra.map((id) => ({ id, urls: names }))].filter((p) => p.urls.trim());
  btn.disabled = true;
  const summary = [], suggestions = [];
  try {
    for (let i = 0; i < plan.length; i++) {
      const p = plan[i], label = profileName(p.id);
      const step = "Site " + (i + 1) + " of " + plan.length + ": " + label;
      msg.textContent = step + "…";
      const r = await api("/api/creators/add", {
        urls: p.urls, pages: $("#newPages").value, profile: p.id,
        scrape: $("#autoScrape").checked, link_map: {},
      });
      suggestions.push(...(r.suggestions || []));
      const n = r.added.length + (r.joined || []).length + (r.linked || []).length + r.finding.length;
      summary.push(label + (r.skipped.length ? " (" + r.skipped.map((s) => s.reason).join("; ") + ")" : n ? " ✓" : " (nothing new)"));
      await refresh();
      if (r.job) {
        logHidden = false; attachJob(r.job);
        msg.textContent = step + ": scraping… (the next site starts when this one finishes)";
        await waitForJob();
        await refresh();
      }
    }
    msg.textContent = "Finished all " + plan.length + " sites: " + summary.join(" · ");
    $("#newUrls").value = suggestions.map((x) => x.url).join("\n");
    showSuggestions(suggestions);
  } catch (e) { msg.textContent = e.message + (summary.length ? "  (done so far: " + summary.join(" · ") + ")" : ""); }
  btn.disabled = false;
}

$("#addBtn").onclick = () => addAcrossSites($("#newUrls").value);

$("#importBtn").onclick = async () => {
  const msg = $("#importMsg"), btn = $("#importBtn");
  btn.disabled = true; msg.textContent = "Importing…";
  try {
    const r = await api("/api/creators/import", {
      folder: $("#importFolder").value, keep_underscores: $("#importUnderscore").checked,
      site: $("#importSite").value, overwrite: $("#importOverwrite").checked,
    });
    const total = r.imported.reduce((n, x) => n + x.count, 0), rtotal = (r.replaced || []).reduce((n, x) => n + x.count, 0);
    const bits = [];
    if (r.imported.length) bits.push(r.imported.length + " new creator" + (r.imported.length === 1 ? "" : "s") + " (" + total + " links)");
    if (r.replaced && r.replaced.length) bits.push(r.replaced.length + " replaced (" + rtotal + " links)");
    let t = (bits.join(", ") || "Nothing imported") + ", under " + r.site;
    if (r.skipped.length) t += ". Skipped " + r.skipped.length + ": " + r.skipped.slice(0, 6).map((s) => s.name + " (" + s.reason + ")").join("; ") + (r.skipped.length > 6 ? "…" : "");
    msg.textContent = t;
    await refresh();
  } catch (e) { msg.textContent = e.message; }
  btn.disabled = false;
};

// Scrapes run one creator at a time. Asking for more while a scrape is running queues them behind it.
async function startScrape(which, quiet, source) {
  try {
    const j = await api("/api/scrape", source ? { source } : { slugs: which });
    logHidden = false;
    attachJob(j);
    return null;
  } catch (e) {
    if (!quiet) alert(e.message);
    return e.message;
  }
}
// The links panels keep what they loaded, so after a keyword change they must be thrown away and re-read.
function dropCachedLinks() {
  for (const k of Object.keys(linkCache)) delete linkCache[k];
  library = null;
}

$("#recat").onclick = async () => {
  try {
    const r = await api("/api/recategorise", {});
    dropCachedLinks();
    await refresh();
    const top = Object.entries(r.counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => k + " " + v).join(", ");
    const moved = r.moved === null ? "First time pressed, so there's nothing to compare with yet."
      : r.moved === 0 ? "No link changed category since last time."
      : r.moved + " link" + (r.moved === 1 ? "" : "s") + " changed category since last time (" +
        Object.entries(r.flows).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, v]) => v + " " + k).join(", ") + ").";
    alert("Re-sorted " + r.total + " links with your current keywords.\n" + moved + "\nNow: " + top);
  } catch (e) { alert(e.message); }
};

$("#makeFolders").onclick = async () => {
  try {
    const r = await api("/api/creators/make_folders", {});
    alert(r.count ? "Created " + r.count + " folder" + (r.count === 1 ? "" : "s") + " in your library." : "Every creator already has a folder.");
  } catch (e) { alert(e.message); }
};
$("#findAddr").onclick = async () => {
  try {
    const j = await api("/api/creators/find_addresses", { pages: $("#newPages").value, scrape: $("#autoScrape").checked });
    logHidden = false; attachJob(j);
  } catch (e) { alert(e.message); }
};
$("#scrapeMissing").onclick = () => startScrape("missing");
$("#scrapeAll").onclick = () => startScrape("all");

// ───── job activity
function attachJob(job) {
  if (job.id !== lastJobId) { lastJobId = job.id; logSince = 0; seenResults = 0; $("#logOut").textContent = ""; }
  renderJob(job);
  if (job.status === "running" && !polling) polling = setInterval(pollJob, 1000);
}

function renderJob(job) {
  $("#jobTitle").textContent = job.title;
  const st = $("#jobStatus");
  st.textContent = job.status;
  st.className = "chip " + (job.status === "done" ? "good" : job.status === "failed" ? "bad" : "");
  $("#stopBtn").hidden = job.status !== "running";
  $("#activity").hidden = logHidden;
  $("#showLog").hidden = !logHidden;
}

// ───── download progress panel
function dpElapsed(it) {
  const t = Math.max(0, Math.round(((it.t1 || Date.now() / 1000) - it.t0)));
  return t >= 60 ? Math.floor(t / 60) + " min " + (t % 60 ? (t % 60) + " s" : "") : t + " s";
}
function dpName(it) {
  if (it.file) return it.file.replace(/\s*\[[^\]]*\]\.(mp4|mkv|webm)$/i, "").replace(/\.(mp4|mkv|webm)$/i, "");
  const m = it.url.match(/viewkey=([\w-]+)|\/videos\/([^/]+)\/?$/);
  return m ? (m[1] || m[2]).replace(/-/g, " ") : it.url;
}
function renderDlProgress(items, job, target) {
  const box = $("#dlProgress");
  if (!job || job.kind !== "download" || !items || !items.length) { box.hidden = !(job && job.kind === "download" && job.status === "running"); if (box.hidden) return; }
  box.hidden = false;
  items = items || [];
  const n = (st) => items.filter((i) => i.status === st).length;
  const done = n("done"), failed = n("failed"), going = n("downloading");
  const total = target || items.length;      // what you asked for, not counting replacements for failed links
  $("#dpSummary").textContent = "· " + done + " done" + (going ? ", " + going + " downloading" : "") + (failed ? ", " + failed + " failed" : "") + (total ? " · target " + total : "");
  const running = job.status === "running";
  const st = $("#dpState");
  st.textContent = running ? "running" : failed && !done ? "failed" : "finished";
  st.className = "chip " + (running ? "" : failed && !done ? "bad" : "good");
  const frac = total ? (done + items.filter((i) => i.status === "downloading").reduce((a, i) => a + (i.pct || 0) / 100, 0)) / total : 0;
  $("#dpTotalBar").style.width = Math.min(100, Math.round(frac * 100)) + "%";
  const order = { downloading: 0, failed: 1, done: 2 };
  $("#dpList").innerHTML = [...items].sort((a, b) => order[a.status] - order[b.status] || b.t0 - a.t0).map((it) => {
    const tag = it.status === "downloading" ? "Downloading" : it.status === "done" ? "Done" : "Failed";
    const indet = it.status === "downloading" && it.pct === null;
    const pct = it.status === "failed" ? Math.max(it.pct || 0, 0) : it.pct || 0;
    const num = it.status === "downloading" ? (it.pct === null ? it.mb.toFixed(0) + " MB" : Math.round(it.pct) + "%  ·  " + it.mb.toFixed(0) + " MB") + "  ·  " + dpElapsed(it)
      : it.status === "done" ? dpElapsed(it) : "";
    return `<div class="dpRow ${it.status}">
      <span class="dpTag ${it.status}">${tag}</span>
      <div class="dpMain">
        <div class="dpTitle" title="${esc(it.url)}">${esc(dpName(it))}</div>
        <div class="dpSub ${it.status === "failed" ? "bad" : ""}">${it.status === "failed" ? esc(it.reason || "failed") : esc(it.folder ? it.folder + "/" : "") + (it.status === "done" ? "" : "")}</div>
        <div class="dpBar"><i class="${indet ? "indet" : ""}" style="${indet ? "" : "width:" + pct.toFixed(1) + "%"}"></i></div>
      </div>
      <span class="dpNum">${esc(num)}</span>
    </div>`;
  }).join("");
}
async function refreshDlProgress() {
  try {
    const r = await api("/api/job?since=999999999");
    if (r.job) renderDlProgress(r.items, r.job, r.target);
  } catch (e) { /* the panel is optional */ }
}

async function pollJob() {
  const r = await api("/api/job?since=" + logSince);
  if (!r.job) return;
  renderDlProgress(r.items, r.job, r.target);
  const pre = $("#logOut");
  if (r.lines.length) {
    const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 30;
    pre.textContent += (pre.textContent ? "\n" : "") + r.lines.join("\n");
    logSince += r.lines.length;
    if (atBottom) pre.scrollTop = pre.scrollHeight;
    for (const l of r.lines) {
      const m = l.match(/^@@POS (\d+) (\d+)/);
      if (m && r.job.kind.startsWith("capture:")) saveCapture(r.job.kind.slice(8), [+m[1], +m[2]]);
    }
  }
  renderJob(r.job);
  if (r.job.results.length !== seenResults && r.job.status === "running") { seenResults = r.job.results.length; refresh(); } // table updates as each creator finishes
  if (r.job.status !== "running") {
    clearInterval(polling); polling = null;
    refresh(); if (!$("#tab-library").hidden || !$("#tab-download").hidden) loadLibrary();
  }
}

async function saveCapture(key, xy) {
  await api("/api/settings", { [key]: xy });
  refresh();
}

$("#stopBtn").onclick = () => api("/api/stop", {});
$("#hideLog").onclick = () => { logHidden = true; $("#activity").hidden = true; $("#showLog").hidden = false; };
$("#showLog").onclick = () => { logHidden = false; $("#activity").hidden = false; $("#showLog").hidden = true; };

// ───── library
async function loadLibrary() {
  library = await api("/api/library");
  const L = library;
  $("#libTotal").textContent = L.total ? "(" + L.total + " links, " + L.downloaded + " downloaded)" : "";
  $("#libEmpty").hidden = L.total > 0;
  $("#libGrid").innerHTML = Object.entries(L.categories).map(([cat, c]) => {
    const max = Math.max(1, ...Object.values(c.buckets));
    return `<div class="catBlock"><h3><span>${esc(cat)}</span><span class="muted">${c.count}</span></h3>
      <div class="bars">${L.bucket_labels.map((b) => `
        <span>${esc(b.replace(/_/g, " "))}</span>
        <div class="bar"><i style="width:${(c.buckets[b] / max) * 100}%"></i></div>
        <span class="num">${c.buckets[b]}</span>`).join("")}</div></div>`;
  }).join("");
}

// ───── download tab: what to download
const DL = { mode: "pick", inc: new Set(), exc: new Set(), cats: new Set(), buckets: new Set(), mix: false, weights: {}, seed: null, timer: null };

async function initDownload() {
  library = await api("/api/library");
  const slugs = library.creators.map((c) => c.slug);
  DL.inc = new Set([...DL.inc].filter((s) => slugs.includes(s)));
  DL.exc = new Set([...DL.exc].filter((s) => slugs.includes(s)));
  DL.cats = new Set([...DL.cats].filter((c) => c in library.categories));
  renderDlChips(); renderDlMix(); dlRefreshSoon();
}

function renderDlChips() {
  const L = library, cats = Object.keys(L.categories), q = $("#dlFind").value.toLowerCase().trim();
  const chip = (cls, attr, val, label, n, on) => `<button class="tChip ${cls} ${on ? "on" : ""} ${q && !on && !label.toLowerCase().includes(q) ? "hide" : ""}" ${attr}="${esc(val)}">${esc(label)}${n === undefined ? "" : `<b>${n}</b>`}</button>`;
  $("#dlInc").innerHTML = L.creators.length
    ? chip("", "data-dlinc", "", "All", undefined, !DL.inc.size) + L.creators.map((c) => chip("", "data-dlinc", c.slug, c.slug, c.count, DL.inc.has(c.slug))).join("")
    : '<span class="muted">No creators with links yet.</span>';
  $("#dlExc").innerHTML = L.creators.map((c) => chip("exc", "data-dlexc", c.slug, c.slug, c.count, DL.exc.has(c.slug))).join("") || '<span class="muted">-</span>';
  $("#dlIncHint").textContent = DL.inc.size ? "(" + DL.inc.size + " selected)" : "(all)";
  $("#dlExcHint").textContent = DL.exc.size ? "(" + DL.exc.size + " left out)" : "(none)";
  $("#dlCats").innerHTML = cats.map((c) => `<button class="tChip cat ${DL.cats.has(c) ? "on" : ""}" style="${catStyle(c, cats)}" data-dlcat="${esc(c)}">${esc(c)}<b>${L.categories[c].count}</b></button>`).join("");
  const bt = {};
  cats.forEach((c) => Object.entries(L.categories[c].buckets).forEach(([b, n]) => (bt[b] = (bt[b] || 0) + n)));
  $("#dlBuckets").innerHTML = L.bucket_labels.filter((b) => bt[b]).map((b) =>
    `<button class="tChip ${DL.buckets.has(b) ? "on" : ""}" data-dlb="${esc(b)}">${esc(b.replace(/_/g, " "))}<b>${bt[b]}</b></button>`).join("");
}

function renderDlMix() {
  $("#dlMixBox").hidden = !DL.mix;
  $("#dlWeights").innerHTML = state.profiles.map((p) =>
    `<label class="mixItem">${esc(p.name)}<input type="number" min="0" step="any" data-dlw="${esc(p.id)}" value="${esc(DL.weights[p.id] ?? "1")}"></label>`).join("");
}

function dlBody() {
  if (!DL.seed) DL.seed = newSeed();
  const b = { mode: DL.mode, n: $("#dlN").value || 10, exclude_downloaded: $("#dlExcl").checked, seed: DL.seed, min_views: $("#dlMinViews").value, max_per_creator: $("#dlMaxPer").value, spread: $("#dlSpread").value, min_per_creator: $("#dlMinPer").value };
  if (DL.mode === "list") b.list = $("#dlList").value;
  if (DL.mode === "manual") {
    b.manual = $("#dlManual").value; b.manual_folder = $("#dlManualFolder").value;
    b.n = Math.max(1, (b.manual.match(/https?:\/\/\S+|(?:^|\s)www\.\S+/gim) || []).length);       // as many as were pasted
  }
  b.creators = [...DL.inc]; b.exclude_creators = [...DL.exc]; b.categories = [...DL.cats]; b.buckets = [...DL.buckets];
  if (DL.mix) b.site_weights = Object.fromEntries(state.profiles.map((p) => [p.id, parseFloat(DL.weights[p.id] ?? "1") || 0]));
  return b;
}

function dlRefreshSoon() { clearTimeout(DL.timer); DL.timer = setTimeout(dlRefresh, 250); }

function breakdown(o) { const e = Object.entries(o); return e.length > 1 ? e.map(([k, v]) => k + " " + v).join(", ") : ""; }

async function dlRefresh() {
  if (!library) return;
  try {
    const r = await api("/api/download_preview", dlBody());
    const n = +($("#dlN").value || 10);
    if (DL.mode === "manual") {
      $("#dlInfo").textContent = r.pool
        ? r.pool + " link" + (r.pool === 1 ? "" : "s") + " will download into library/" + r.folder + (r.folder_exists ? " (existing folder)" : " (a new folder)")
        : "Paste at least one link.";
      return;
    }
    let t = r.pool + " link" + (r.pool === 1 ? "" : "s") + (DL.mode === "list" ? " recognised" : " match");
    if (r.pool && r.pool < n) t += ". Fewer than the " + n + " you asked for";
    const bd = breakdown(r.by_site);
    if (bd) t += ". The first " + r.shown + " would be: " + bd;
    if (r.unknown) t += ". " + r.unknown + " line" + (r.unknown === 1 ? " isn't" : "s aren't") + " in your library and will be skipped (e.g. " + r.unknown_sample[0].slice(0, 70) + ")";
    $("#dlInfo").textContent = t;
  } catch (e) { $("#dlInfo").textContent = e.message; }
}

function setDlMode(mode) {
  DL.mode = mode;
  document.querySelectorAll("[data-dlmode]").forEach((b) => b.classList.toggle("on", b.dataset.dlmode === mode));
  $("#dlListBox").hidden = mode !== "list"; $("#dlFilterNote").hidden = mode !== "list";   // the filters show in both modes
  $("#dlManualBox").hidden = mode !== "manual";
  $("#dlPickBox").hidden = mode === "manual";                                                  // none of the filters apply to links you typed
  document.querySelectorAll("#tab-download .filters").forEach((f) => (f.hidden = mode === "manual"));
  if (mode === "manual") api("/api/library_folders").then((r) => { $("#dlFolders").innerHTML = r.folders.map((f) => `<option value="${esc(f)}">`).join(""); }).catch(() => {});
  dlRefreshSoon();
}

$("#tab-download").addEventListener("click", (e) => {
  const t = e.target.closest("[data-dlmode],[data-dlinc],[data-dlexc],[data-dlcat],[data-dlb]");
  if (!t) return;
  if (t.dataset.dlmode) return setDlMode(t.dataset.dlmode);
  if (t.dataset.dlinc !== undefined) {
    if (t.dataset.dlinc === "") DL.inc.clear(); else { toggleIn(DL.inc, t.dataset.dlinc); DL.exc.delete(t.dataset.dlinc); }
  } else if (t.dataset.dlexc !== undefined) { toggleIn(DL.exc, t.dataset.dlexc); DL.inc.delete(t.dataset.dlexc); }
  else if (t.dataset.dlcat !== undefined) toggleIn(DL.cats, t.dataset.dlcat);
  else toggleIn(DL.buckets, t.dataset.dlb);
  renderDlChips(); dlRefreshSoon();
});
$("#dlFind").addEventListener("input", renderDlChips);
$("#dlMix").addEventListener("change", (e) => { DL.mix = e.target.checked; renderDlMix(); dlRefreshSoon(); });
$("#dlWeights").addEventListener("input", (e) => { if (e.target.dataset.dlw) { DL.weights[e.target.dataset.dlw] = e.target.value; dlRefreshSoon(); } });
["#dlN", "#dlExcl", "#dlList", "#dlMinViews", "#dlMaxPer", "#dlMinPer"].forEach((id) => $(id).addEventListener("input", dlRefreshSoon));
$("#dlSpread").addEventListener("change", () => { $("#dlMinPerWrap").hidden = $("#dlSpread").value !== "min"; dlRefreshSoon(); });

function listFromListsTab() {
  if (!LB.last || !LB.last.total) return null;
  return LB.last.groups.filter((g) => g.count).flatMap((g) => g.lines).join("\n");
}
$("#dlLoadList").onclick = () => {
  const txt = listFromListsTab();
  if (!txt) { $("#dlInfo").textContent = "Nothing to load yet. Build a list on the Lists tab first."; return; }
  $("#dlList").value = txt; dlRefreshSoon();
};
// Pick "How many" links at random from whatever list the Lists tab is currently building (its creator / category /
// length filters and the skip-already-downloaded tick all apply), and put them in the box.
$("#dlRandom").onclick = async () => {
  const msg = $("#dlRandomMsg"), n = Math.max(1, parseInt($("#dlN").value, 10) || 1);
  msg.textContent = "";
  if (!LB.last || !LB.last.total) await buildList();
  const all = (listFromListsTab() || "").trim();
  if (!all) { msg.textContent = "The Lists tab has nothing to pick from yet. Open it, choose what to include, and come back."; return; }
  try {
    // the server narrows that list with the filters below, shuffles it, and keeps the first n
    const r = await api("/api/download_preview", { ...dlBody(), mode: "list", list: all, random: true, seed: newSeed(), n });
    if (!r.links.length) { msg.textContent = "Nothing in that list matches the filters below."; return; }
    $("#dlList").value = r.links.map((l) => l.url).join("\n");
    msg.textContent = "Picked " + r.links.length + " at random from " + r.pool + " that match" + (r.unknown ? " (" + r.unknown + " in the list weren't in your library)" : "") + ". Press again for a different set.";
    dlRefreshSoon();
  } catch (e) { msg.textContent = e.message; }
};

$("#lbToDownload").onclick = () => {
  const txt = listFromListsTab();
  if (!txt) { $("#lbMsg").textContent = "Nothing in the preview yet."; return; }
  showTab("download"); setDlMode("list"); $("#dlList").value = txt;
  dlRefreshSoon();
};

["#dlManual", "#dlManualFolder"].forEach((id) => $(id).addEventListener("input", () => dlRefreshSoon()));

$("#dlPreview").onclick = async () => {
  if (DL.mode === "pick") DL.seed = newSeed(); // "Download these" reuses this seed, so it downloads exactly what you see
  try {
    const r = await api("/api/download_preview", dlBody());
    const out = $("#dlPrev");
    out.hidden = false; $("#dlCopy").hidden = false;
    out.value = r.links.map((l) => l.url + "  |  " + l.dur + (l.title ? "  |  " + l.title : "")).join("\n") || "No links match.";
    dlRefresh();
  } catch (e) { $("#dlInfo").textContent = e.message; }
};
$("#dlCopy").onclick = () => navigator.clipboard.writeText($("#dlPrev").value);

$("#dlGo").onclick = async () => {
  try {
    const j = await api("/api/download", dlBody());
    logSince = 0; $("#logOut").textContent = ""; logHidden = false; attachJob(j);
  } catch (e) { alert(e.message); }
};

$("#exportBtn").onclick = async () => {
  const r = await api("/api/export", {});
  $("#exportMsg").textContent = "Saved to " + r.folder;
};

// ───── settings
const FIELDS = [
  ["scraper_path", "Scraper script", "text", true],
  ["library_dir", "Where finished downloads go", "text", true],
  ["download_dir", "Browser download folder (Video DownloadHelper method only)", "text", true],
  ["download_method", "How to download", "select", false, [["vdh", "Video DownloadHelper (clicks in Chrome)"], ["ytdlp", "yt-dlp (no browser, no clicking)"]]],
  ["ytdlp_max_height", "yt-dlp only: highest quality in pixels, e.g. 720 (empty = best)", "number"],
  ["bucket_edges_min", "Duration edges (minutes, comma separated)", "list"],
  ["scrape_pause", "Seconds between scrapes", "number"],
  ["min_video_minutes", "Skip videos shorter than (minutes, empty = no limit)", "number"],
  ["max_video_minutes", "Skip videos longer than (minutes, empty = no limit)", "number"],
  ["target_success", "Downloads per run", "number"],
  ["max_attempts", "Max attempts per run", "number"],
  ["startup_delay", "Seconds before first click", "number"],
  ["page_load_wait", "Wait for page to load (s)", "number"],
  ["menu_wait", "Wait after opening VDH (s)", "number"],
  ["download_wait", "Wait for a download to start (s)", "number"],
  ["max_parallel", "Downloads running at the same time", "number"],
  ["max_download_minutes", "Give up on one download after (minutes)", "number"],
  ["pause_between_links", "Seconds between links", "number"],
  ["stop_after_failures", "Stop a run after this many links in a row fail to start (0 = never)", "number"],
  ["pages_default_all", "Scrape every page by default (stops when a page says it wasn't found)", "check"],
  ["name_match", "Link the same person across sites automatically", "check"],
  ["name_match_min_len", "Auto-link only if the shorter name has at least this many letters", "number"],
  ["name_match_ask_pct", "Ask me when this % of the shorter name matches", "number"],
  ["use_image_clicks", "Find the VDH icon and Download button by their picture (recommended)", "check"],
  ["vdh_icon_image", "VDH icon picture", "image"],
  ["download_button_image", "Download button picture", "image"],
  ["image_match_threshold", "How closely the screen must match the picture (0 to 1)", "number"],
  ["vdh_icon", "VDH icon position (used if there's no picture)", "pos"],
  ["download_button", "VDH download button position (used if there's no picture)", "pos"],
];

function renderSettings() {
  if ($("#settingsForm").dataset.ready && document.activeElement && document.activeElement.closest("#settingsForm")) return;
  const s = state.settings;
  $("#settingsForm").dataset.ready = "1";
  $("#settingsForm").innerHTML = FIELDS.map(([k, label, type, wide, opts]) => {
    let input;
    if (type === "pos") {
      input = `<div class="inline"><input data-k="${k}" data-pos="0" type="number" value="${s[k][0]}"><input data-k="${k}" data-pos="1" type="number" value="${s[k][1]}"><button data-capture="${k}" type="button">Capture</button></div>`;
    } else if (type === "select") {
      input = `<select data-k="${k}">${opts.map(([v, t]) => `<option value="${esc(v)}" ${s[k] === v ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
    } else if (type === "image") {
      const name = k.replace("_image", ""), t = (state.templates || {})[name];
      input = `<div class="inline">${t ? `<img class="tplPic" src="/templates/${name}.png?v=${t}" alt="">` : '<span class="muted">not captured yet</span>'}
        <button data-capture="${k}" type="button">${t ? "Capture again" : "Capture"}</button></div>
        <span class="muted">Click Capture, then within 5 seconds put the mouse right on ${name === "vdh_icon" ? "the VDH icon in Chrome's toolbar" : "the Download button in VDH's popup (open the popup first)"} and keep still.</span>`;
    } else if (type === "check") {
      input = `<input data-k="${k}" type="checkbox" ${s[k] ? "checked" : ""}>`;
    } else if (type === "list") {
      input = `<input data-k="${k}" value="${esc(s[k].join(", "))}">`;
    } else {
      input = `<input data-k="${k}" type="${type}" step="any" value="${esc(s[k])}">`;
    }
    return `<label class="${wide ? "wide" : ""}">${label}${input}</label>`;
  }).join("");
  document.querySelectorAll("[data-capture]").forEach((b) => (b.onclick = async () => {
    b.blur();
    try {
      const j = await api("/api/capture", { which: b.dataset.capture });
      logSince = 0; $("#logOut").textContent = ""; logHidden = false; attachJob(j);
    } catch (e) { alert(e.message); }
  }));
}

$("#saveSettings").onclick = async () => {
  const out = {};
  document.querySelectorAll("#settingsForm [data-k]").forEach((el) => {
    const k = el.dataset.k;
    if (el.dataset.pos !== undefined) { (out[k] = out[k] || [0, 0])[+el.dataset.pos] = +el.value; }
    else if (k === "bucket_edges_min") out[k] = el.value.split(",").map((x) => x.trim()).filter(Boolean).map(Number);
    else if (el.type === "checkbox") out[k] = el.checked;
    else out[k] = el.value;
  });
  try {
    await api("/api/settings", out);
    $("#saveMsg").textContent = "Saved";
    $("#settingsForm").dataset.ready = "";
    refresh();
  } catch (e) { $("#saveMsg").textContent = e.message; }
};

// ───── list builder
// A seed fixes the random order, so what you preview is exactly what Save and Download .txt give you.
const newSeed = () => String(Math.random()).slice(2) + Date.now();
const LB = { creators: new Set(), cats: new Set(), buckets: new Set(), timer: null, ready: false, last: null, seed: newSeed() };

async function initLists() {
  library = await api("/api/library");
  const L = library;
  // drop selections that no longer exist
  LB.creators = new Set([...LB.creators].filter((s) => L.creators.some((c) => c.slug === s)));
  const catNames = Object.keys(L.categories);
  LB.cats = new Set([...LB.cats].filter((c) => catNames.includes(c)));
  renderLbChips();
  buildList();
}

function renderLbChips() {
  const L = library, cats = Object.keys(L.categories);
  $("#lbCreators").innerHTML = L.creators.length
    ? `<button class="tChip ${LB.creators.size ? "" : "on"}" data-lbc="">All</button>` +
      L.creators.map((c) => `<button class="tChip ${LB.creators.has(c.slug) ? "on" : ""}" data-lbc="${esc(c.slug)}">${esc(c.slug)}<b>${c.count}</b></button>`).join("")
    : '<span class="muted">No creators scraped yet.</span>';
  $("#lbCreatorHint").textContent = LB.creators.size ? "(" + LB.creators.size + " selected)" : "(all)";
  $("#lbCats").innerHTML = cats.map((c) => `<button class="tChip cat ${LB.cats.has(c) ? "on" : ""}" style="${catStyle(c, cats)}" data-lbk="${esc(c)}">${esc(c)}<b>${L.categories[c].count}</b></button>`).join("");
  const bt = {};
  cats.forEach((c) => Object.entries(L.categories[c].buckets).forEach(([b, n]) => (bt[b] = (bt[b] || 0) + n)));
  $("#lbBuckets").innerHTML = L.bucket_labels.filter((b) => bt[b]).map((b) =>
    `<button class="tChip ${LB.buckets.has(b) ? "on" : ""}" data-lbb="${esc(b)}">${esc(b.replace(/_/g, " "))}<b>${bt[b]}</b></button>`).join("");
}

function toggleIn(set, v) { set.has(v) ? set.delete(v) : set.add(v); }

$("#tab-lists").addEventListener("click", (e) => {
  const t = e.target.closest("[data-lbc],[data-lbk],[data-lbb]");
  if (!t) return;
  if (t.dataset.lbc !== undefined) { t.dataset.lbc === "" ? LB.creators.clear() : toggleIn(LB.creators, t.dataset.lbc); }
  else if (t.dataset.lbk !== undefined) toggleIn(LB.cats, t.dataset.lbk);
  else toggleIn(LB.buckets, t.dataset.lbb);
  renderLbChips(); buildListSoon();
});
$("#lbMinViews").addEventListener("input", buildListSoon);
["#lbOrder", "#lbSplit", "#lbDur", "#lbTitles", "#lbExcl"].forEach((id) => $(id).addEventListener("change", () => {
  $("#lbShuffle").hidden = $("#lbOrder").value !== "random";
  buildListSoon();
}));
$("#lbShuffle").onclick = () => { LB.seed = newSeed(); buildList(); };

function lbBody(save) {
  return {
    creators: [...LB.creators], categories: [...LB.cats], buckets: [...LB.buckets],
    order: $("#lbOrder").value, split: $("#lbSplit").value,
    durations: $("#lbDur").checked, titles: $("#lbTitles").checked, exclude_downloaded: $("#lbExcl").checked,
    min_views: $("#lbMinViews").value,
    save: !!save, name: $("#lbName").value, seed: LB.seed,
  };
}

function buildListSoon() { clearTimeout(LB.timer); LB.timer = setTimeout(buildList, 200); }

async function buildList() {
  try {
    const r = await api("/api/build_list", lbBody(false));
    LB.last = r;
    $("#lbTotal").textContent = r.total ? "(" + r.total + " links" + (r.groups.length > 1 ? " in " + r.groups.length + " lists" : "") + ")" : "";
    $("#lbEmpty").hidden = r.total > 0;
    $("#lbGroups").innerHTML = r.groups.filter((g) => g.count).map((g, i) => `
      <div class="lbGroup">
        <div class="lbGroupHead">
          ${r.groups.length > 1 ? `<strong>${esc(g.name)}</strong>` : "<strong>Combined list</strong>"}
          <span class="muted">${g.count} links</span>
          <span class="push"><button data-lbcopy="${i}">Copy</button><button data-lbdl="${i}">Download .txt</button></span>
        </div>
        <textarea readonly spellcheck="false">${esc(g.lines.join("\n"))}</textarea>
      </div>`).join("");
  } catch (e) { $("#lbMsg").textContent = e.message; }
}

$("#lbGroups").addEventListener("click", (e) => {
  const t = e.target.closest("[data-lbcopy],[data-lbdl]");
  if (!t || !LB.last) return;
  const groups = LB.last.groups.filter((g) => g.count);
  if (t.dataset.lbcopy !== undefined) {
    navigator.clipboard.writeText(groups[+t.dataset.lbcopy].lines.join("\n"));
    const old = t.textContent; t.textContent = "Copied"; setTimeout(() => (t.textContent = old), 1200);
  } else {
    const g = groups[+t.dataset.lbdl];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([g.lines.join("\n") + "\n"], { type: "text/plain" }));
    a.download = ($("#lbName").value.trim() || "links") + (groups.length > 1 ? "_" + g.name : "") + ".txt";
    a.click(); URL.revokeObjectURL(a.href);
  }
});

$("#lbSave").onclick = async () => {
  try {
    const r = await api("/api/build_list", lbBody(true));
    $("#lbMsg").textContent = r.saved ? "Saved " + r.saved.files.length + " file" + (r.saved.files.length === 1 ? "" : "s") + " to " + r.saved.folder : "Nothing to save";
  } catch (e) { $("#lbMsg").textContent = e.message; }
};

// ───── sites (profiles)
let editing = null; // profile object being edited (id undefined => new)

function renderSites() {
  $("#siteList").innerHTML = state.profiles.map((p) => `
    <div class="siteRow">
      <div><strong>${esc(p.name)}</strong>${p.virtual ? ' <span class="chip">runs your script</span>' : ""}${p.id === defaultSite() ? ' <span class="chip good">main site</span>' : ""}
        <div class="muted">${esc(p.base_url || "domain not found")} · ${esc(Object.keys(p.keywords || {}).join(", ") || "no categories")}</div></div>
      <div class="row" style="margin:0">
        ${p.virtual ? "" : `<button class="link" data-edit="${esc(p.id)}">Edit</button>`}
        <button class="link" data-dup="${esc(p.id)}">Duplicate</button>
        ${p.id === defaultSite() ? "" : `<button class="link" data-main="${esc(p.id)}">Make main site</button>`}
      </div>
    </div>`).join("");
  document.querySelectorAll("[data-main]").forEach((b) => (b.onclick = async () => {
    try { await api("/api/settings", { default_site: b.dataset.main }); await refresh(); } catch (e) { alert(e.message); }
  }));
  document.querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => openEditor(state.profiles.find((p) => p.id === b.dataset.edit))));
  document.querySelectorAll("[data-dup]").forEach((b) => (b.onclick = () => {
    const src = state.profiles.find((p) => p.id === b.dataset.dup);
    openEditor({ ...state.defaults, ...src, id: undefined, virtual: false, name: src.name.replace(/ \(.*\)$/, "") + " copy",
      slug_strip: src.slug_strip || state.defaults.slug_strip });
  }));
}

$("#newSite").onclick = () => openEditor({ ...state.defaults, id: undefined });

function openEditor(p) {
  editing = p;
  $("#siteEditor").hidden = false;
  $("#editorTitle").textContent = p.id ? "Edit " + p.name : "New site";
  $("#sName").value = p.name || "";
  $("#sBase").value = p.base_url || "";
  $("#sTemplate").value = p.page_template || "{path}/{page}/";
  syncPreset();
  $("#sStrip").value = (p.slug_strip || []).join(", ");
  $("#sKeywords").value = Object.entries(p.keywords || {}).map(([k, v]) => k + ": " + v.join(", ")).join("\n");
  $("#sNegative").value = (p.negative || []).join(", ");
  fillDominant(p.dominant || "");
  $("#sMethod").value = p.download_method || "";
  $("#sPatterns").value = (p.creator_patterns || []).join("\n");
  $("#sNotFound").value = (p.not_found_text || ["page not found"]).join("\n");
  $("#sLinkRe").value = p.video_link_regex || "";
  $("#sDurRe").value = p.duration_regex || "";
  $("#sDelay").value = p.request_delay ?? 1;
  $("#sKeepQuery").checked = !!p.keep_query;
  $("#sKeyAttr").value = p.video_key_attr || "";
  $("#sUrlTpl").value = p.video_url_template || "/view_video.php?viewkey={key}";
  $("#sScope").value = p.scope_selector || "";
  $("#sExclude").value = p.exclude_selector || "";
  $("#sViews").value = p.views_selector || "";
  $("#sSections").value = (p.sections || []).map((x) => x.address + (x.scope ? " | " + x.scope : "")).join("\n");
  $("#sAvatarSel").value = p.avatar_selector || "";
  $("#sAvatarAttr").value = p.avatar_attr || "src";
  $("#deleteSite").hidden = !p.id;
  $("#siteMsg").textContent = ""; $("#testOut").hidden = true;
  $("#siteEditor").scrollIntoView({ behavior: "smooth", block: "start" });
}

// the dominant dropdown lists whatever categories are currently typed in the box above it
function fillDominant(keep) {
  const sel = $("#sDominant"), cur = keep !== undefined ? keep : sel.value;
  const names = $("#sKeywords").value.split("\n").map((l) => (l.indexOf(":") > 0 ? unquote(l.slice(0, l.indexOf(":"))) : "")).filter(Boolean);
  sel.innerHTML = '<option value="">None (the first category above that matches wins)</option>' + names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  sel.value = names.includes(cur) ? cur : "";
}
$("#sKeywords").addEventListener("input", () => fillDominant());

function syncPreset() {
  const t = $("#sTemplate").value;
  const sel = $("#sPreset");
  sel.value = [...sel.options].some((o) => o.value === t && t) ? t : "";
  $("#sExample").textContent = "Page 2 would be: " + (($("#sBase").value || "https://site.com").replace(/\/$/, "")) +
    t.replace("{path}", "/creator-name").replace("{page}", "2");
}
$("#sPreset").onchange = () => { if ($("#sPreset").value) $("#sTemplate").value = $("#sPreset").value; else $("#sTemplate").focus(); syncPreset(); };
$("#sTemplate").oninput = syncPreset;
$("#sBase").oninput = syncPreset;

// Quotes around words are optional: "pear1", 'pear1' and pear1 all mean the same thing.
const unquote = (x) => x.trim().replace(/^["'“”‘’]+|["'“”‘’]+$/g, "").trim();
const splitList = (s) => s.split(",").map(unquote).filter(Boolean);

function readEditor() {
  const keywords = {};
  $("#sKeywords").value.split("\n").forEach((line) => {
    const i = line.indexOf(":");
    if (i > 0) keywords[unquote(line.slice(0, i))] = splitList(line.slice(i + 1));
  });
  return {
    id: editing && editing.id, name: $("#sName").value, base_url: $("#sBase").value,
    page_template: $("#sTemplate").value.trim(),
    slug_strip: splitList($("#sStrip").value), keywords, negative: splitList($("#sNegative").value),
    creator_patterns: $("#sPatterns").value.split("\n").map(unquote).filter(Boolean),
    dominant: $("#sDominant").value, download_method: $("#sMethod").value,
    not_found_text: $("#sNotFound").value.split("\n").map((x) => x.trim()).filter(Boolean),
    video_link_regex: $("#sLinkRe").value, duration_regex: $("#sDurRe").value,
    request_delay: parseFloat($("#sDelay").value) || 0,
    keep_query: $("#sKeepQuery").checked,
    video_key_attr: $("#sKeyAttr").value.trim(), video_url_template: $("#sUrlTpl").value.trim(), scope_selector: $("#sScope").value.trim(), exclude_selector: $("#sExclude").value.trim(), views_selector: $("#sViews").value.trim(), sections: $("#sSections").value,
    avatar_selector: $("#sAvatarSel").value.trim(), avatar_attr: $("#sAvatarAttr").value.trim() || "src",
  };
}

$("#saveSite").onclick = async () => {
  try {
    const r = await api("/api/profiles/save", { profile: readEditor() });
    editing = { ...editing, id: r.id };
    $("#siteMsg").textContent = "Saved";
    dropCachedLinks();       // keywords may have changed: open panels must be re-read
    await refresh();
    $("#editorTitle").textContent = "Edit " + $("#sName").value; $("#deleteSite").hidden = false;
  } catch (e) { $("#siteMsg").textContent = e.message; }
};

$("#deleteSite").onclick = async () => {
  if (!editing || !editing.id || !confirm("Delete this site profile?")) return;
  try {
    await api("/api/profiles/delete", { id: editing.id });
    $("#siteEditor").hidden = true; editing = null; refresh();
  } catch (e) { $("#siteMsg").textContent = e.message; }
};

$("#findBtn").onclick = async () => {
  const out = $("#testOut");
  out.hidden = false; out.textContent = "Trying addresses…";
  try {
    const r = await api("/api/profiles/test", { profile: readEditor(), name: $("#testName").value });
    out.textContent = r.output;
  } catch (e) { out.textContent = e.message; }
};

$("#testBtn").onclick = async () => {
  const out = $("#testOut");
  out.hidden = false; out.textContent = "Testing...";
  try {
    const r = await api("/api/profiles/test", { profile: readEditor(), url: $("#testUrl").value });
    out.textContent = r.output;
  } catch (e) { out.textContent = e.message; }
};

refresh();
