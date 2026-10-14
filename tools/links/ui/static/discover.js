"use strict";
// Discover: swipe through performers. Keep = add as a creator and scrape their links; skip = never show again.
const DC = { on: false, init: false, sum: null, queue: null, deck: [], left: 0, hist: [], pending: new Set(), flying: new Set(),
  chain: Promise.resolve(), filling: false, poll: null, kept: [], drag: null, bgOn: 0, lastKey: 0 };
const dcQ = (s) => document.querySelector(s);
const fmtN = (n) => (n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "K" : String(n || 0));
const hue = (s) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7);

function dcToast(msg, ms = 2400) {
  const t = dcQ("#dcToast"); t.textContent = msg; t.classList.add("on");
  clearTimeout(dcToast.t); dcToast.t = setTimeout(() => t.classList.remove("on"), ms);
}

function discoverToggle(on) {
  DC.on = on;
  if (!on) { clearInterval(DC.poll); DC.poll = null; return; }
  if (!DC.init) dcInit();
  dcRefresh(true);
  clearInterval(DC.poll); DC.poll = setInterval(() => dcRefresh(false), 2500);
}

function dcInit() {
  DC.init = true;
  dcQ("#dcNope").onclick = () => dcDecide(false);
  dcQ("#dcKeep").onclick = () => dcDecide(true);
  dcQ("#dcUndo").onclick = dcUndo;
  dcQ("#dcOpen").onclick = dcOpen;
  dcQ("#dcShuffle").onclick = dcShuffle;
  dcQ("#dcGear").onclick = () => { const p = dcQ("#dcSettings"); p.hidden = !p.hidden; dcQ("#dcFilters").hidden = true; if (!p.hidden) dcRenderSettings(); };
  dcQ("#dcFilterBtn").onclick = dcToggleFilters;
  document.addEventListener("keydown", (e) => {
    if (!DC.on || e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    const k = e.key;
    if (k === "ArrowRight") { e.preventDefault(); dcDecide(true); }
    else if (k === "ArrowLeft") { e.preventDefault(); dcDecide(false); }
    else if (k === "z" || k === "Z" || k === "Backspace") { e.preventDefault(); dcUndo(); }
    else if (k === "o" || k === "O" || k === "ArrowUp") { e.preventDefault(); dcOpen(); }
    else if (k === "r" || k === "R") dcShuffle();
    else if (k === "f" || k === "F") dcToggleFilters();
    else if (k === "Escape") { dcQ("#dcSettings").hidden = true; dcQ("#dcFilters").hidden = true; }
  });
  const st = dcQ("#dcStage");
  st.addEventListener("pointerdown", dcDragStart);
  window.addEventListener("pointermove", dcDragMove);
  window.addEventListener("pointerup", dcDragEnd);
  window.addEventListener("pointercancel", dcDragEnd);
}

// ───────── state
async function dcRefresh(first) {
  try {
    const s = await api("/api/discover/state");
    DC.sum = s; DC.queue = s.queue;
    if (!DC.pending.size) DC.left = s.left;
    const busy = s.progress.running;
    const picturesArriving = busy && s.total > s.pictures + 3;       // do not deal cards before their pictures exist
    if (!s.has_data || (picturesArriving && !DC.deck.length)) { DC.wasBusy = busy; dcShowWelcome(); return; }
    if (DC.wasBusy && !busy) { DC.wasBusy = false; await dcFill(true); }    // a collection just finished: reload so cards get their pictures
    DC.wasBusy = busy;
    dcQ("#dcWelcome").hidden = true; dcQ("#dcApp").hidden = false;
    if (first || (DC.deck.length < 8 && DC.left > DC.deck.length)) await dcFill(first);
    dcRenderStats(); dcRenderScrape();
    if (s.kept || DC.kept.length) dcLoadKept();
    if (busy && !dcQ("#dcSettings").hidden) dcRenderSettings(true);
  } catch (e) { /* the next poll tries again */ }
}

async function dcFill(reset) {
  if (DC.filling) return;
  DC.filling = true;
  try {
    if (reset) DC.deck = [];
    const skip = [...DC.deck.map((c) => c.slug), ...DC.pending, ...DC.flying].join(",");
    const r = await api("/api/discover/deck?n=24&skip=" + encodeURIComponent(skip));
    const have = new Set(DC.deck.map((c) => c.slug));
    DC.deck.push(...r.cards.filter((c) => !have.has(c.slug)));
    if (!DC.pending.size) DC.left = r.left;
    dcRenderStage(); dcRenderStats();
  } catch (e) { /* ignore */ }
  DC.filling = false;
}

// ───────── welcome / collecting
function dcShowWelcome() {
  const w = dcQ("#dcWelcome"), p = DC.sum.progress;
  dcQ("#dcApp").hidden = true; w.hidden = false; dcSetBg(null);
  if (p.running) {
    const frac = p.phase === "images" && p.images_total ? 0.5 + 0.5 * (p.images / p.images_total) : p.pages ? 0.5 * (p.page / p.pages) : 0;
    w.innerHTML = `<div class="dcHero"><div class="eyebrow">Collecting</div><h1>Reading the<br>directory…</h1>
      <p>${esc(p.message || "")}</p>
      <div class="dcProg"><div class="bar"><i style="width:${Math.round(frac * 100)}%"></i></div>
        <div class="row"><span>${p.phase === "images" ? "Saving pictures" : "Reading pages"}: ${p.phase === "images" ? p.images + " / " + p.images_total : p.page + " / " + p.pages}</span><span>${p.found} performers found</span></div>
        ${p.error ? `<div class="err">${esc(p.error)}</div>` : ""}</div>
      <p class="dcMini">It pauses a few seconds between pages on purpose, so this takes a few minutes. You can leave this page.</p>
      <button class="dcGo ghost" id="dcStopCollect" style="margin-top:14px">Stop</button></div>`;
    dcQ("#dcStopCollect").onclick = async () => { await api("/api/stop", {}); dcToast("Stopping…"); };
    return;
  }
  w.innerHTML = `<div class="dcHero"><div class="eyebrow">Discover</div><h1>Find people<br>worth keeping.</h1>
    <p>Pulls the performer directory, saves everyone's picture, shuffles the lot, and deals them to you one at a time. Swipe right to keep (their links get scraped for you), left to skip.</p>
    <div class="dcForm"><label>Pages to read <input type="number" id="dcPages" min="1" max="100" value="40"></label>
      <button class="dcGo" id="dcCollect">Collect performers</button></div>
    ${p.error ? `<div class="dcProg"><div class="err">${esc(p.error)}</div></div>` : ""}
    <p class="dcMini">About 45 performers per page, so 40 pages is roughly 1,800 people. Takes a few minutes. Slow on purpose, and it stops if the site pushes back.</p></div>`;
  dcQ("#dcCollect").onclick = () => dcCollect(+dcQ("#dcPages").value || 40);
}

async function dcCollect(pages) {
  try { await api("/api/discover/collect", { pages }); dcToast("Collecting " + pages + " pages…"); dcRefresh(false); }
  catch (e) { dcToast(e.message, 4000); }
}

// ───────── rendering
function dcRenderStats() {
  const s = DC.sum; if (!s) return;
  const decided = s.kept + s.skipped, tot = decided + DC.left;
  dcQ("#dcStats").innerHTML =
    `<div class="dcStat"><b>${DC.left}</b><span>in the deck</span></div>
     <div class="dcStat keep"><b>${s.kept}</b><span>kept</span></div>
     <div class="dcStat nope"><b>${s.skipped}</b><span>skipped</span></div>
     <div class="dcStat"><b>${tot ? Math.round((decided / tot) * 100) : 0}%</b><span>done</span></div>`;
  dcRenderChips();
  dcQ("#dcUndo").disabled = !s.can_undo && !DC.hist.length;
  const empty = !DC.deck.length;
  dcQ("#dcKeep").disabled = dcQ("#dcNope").disabled = dcQ("#dcOpen").disabled = empty;
}

function dcRenderScrape() {
  const q = DC.queue || {}, p = DC.sum.progress, box = dcQ("#dcScrape");
  let h = `<div class="t">Scraper</div>`;
  if (q.scraping) h += `<div class="now">${esc(q.scraping.replace(/_/g, " "))}</div><div class="bar"><i></i></div><div class="idle">${q.waiting.length} waiting after this one</div>`;
  else if (q.busy_with) h += `<div class="now">Busy: ${esc(q.busy_with)}</div><div class="idle">${q.waiting.length} kept performers will start when it finishes</div>`;
  else h += `<div class="idle">Idle. ${q.waiting.length ? q.waiting.length + " waiting to start." : "Kept performers are scraped here, one at a time."}</div>`;
  if (p.running) h += `<div class="t" style="margin-top:6px">Collecting</div><div class="now">${esc(p.message || "")}</div><div class="bar"><i></i></div>`;
  box.innerHTML = h;
}

function dcCardEl(c) {
  const d = document.createElement("div");
  d.className = "dcCard"; d.dataset.slug = c.slug;
  const img = c.image
    ? `<div class="dcImg" style="background-image:url('${c.image}')"></div>`
    : `<div class="dcImg none" style="background:linear-gradient(145deg,hsl(${hue(c.slug)} 55% 38%),hsl(${(hue(c.slug) + 60) % 360} 60% 20%))">${esc((c.name || "?").trim()[0] || "?")}</div>`;
  d.innerHTML = `${img}<div class="dcShade"></div>
    ${c.rank ? `<div class="dcRank">#${c.rank}</div>` : ""}${c.verified ? `<div class="dcVer">✓ Verified</div>` : ""}
    <div class="dcStamp keep">KEEP</div><div class="dcStamp nope">NOPE</div>
    <div class="dcInfo"><h2>${esc(c.name)}</h2><div class="dcChips">
      <span>${fmtN(c.videos)} videos</span>${c.views ? `<span>${fmtN(c.views)} views</span>` : ""}${c.page ? `<span>directory p.${c.page}</span>` : ""}</div></div>`;
  d.addEventListener("dblclick", dcOpen);
  return d;
}

function dcRenderStage() {
  const st = dcQ("#dcStage"), top = DC.deck.slice(0, 3);
  const want = new Set(top.map((c) => c.slug));
  [...st.children].forEach((el) => { if (!want.has(el.dataset.slug) && !el.classList.contains("fly")) el.remove(); });
  top.forEach((c, i) => {
    let el = [...st.children].find((x) => x.dataset.slug === c.slug && !x.classList.contains("fly"));
    if (!el) { el = dcCardEl(c); st.appendChild(el); }
    el.classList.remove("pos0", "pos1", "pos2"); el.classList.add("pos" + i);
    el.style.transform = i === 0 ? "" : ""; el.style.zIndex = 3 - i;
  });
  const old = st.querySelector(".dcEmptyCard"); if (old) old.remove();
  if (!top.length && DC.sum && DC.sum.has_data) {
    const e = document.createElement("div"); e.className = "dcCard pos0 dcEmptyCard"; e.style.cursor = "default";
    const s = DC.sum;
    e.innerHTML = `<div class="dcImg none" style="background:linear-gradient(145deg,#1f1b3a,#10272a);font-size:20px;text-align:center;padding:30px;display:grid;gap:14px;place-content:center">
      <div style="font-size:34px;font-weight:800;line-height:1.05">That's everyone<br>for now.</div>
      <div style="color:#b7b5c7;font-weight:500;font-size:14px">${s.skipped} skipped, ${s.kept} kept${s.hidden_existing ? `, ${s.hidden_existing} already in Creators` : ""}.</div>
      <div style="display:grid;gap:8px"><button class="dcGo" id="dcMoreBtn">Collect more pages</button>
      ${s.skipped ? `<button class="dcGo ghost" id="dcAgainBtn">Show the ${s.skipped} skipped again</button>` : ""}</div></div>`;
    st.appendChild(e);
    dcQ("#dcMoreBtn").onclick = () => { dcQ("#dcSettings").hidden = false; dcRenderSettings(); };
    const ag = dcQ("#dcAgainBtn"); if (ag) ag.onclick = dcResetSkipped;
  }
  dcSetBg(top[0] && top[0].image);
  top.slice(0, 7).forEach((c) => { if (c.image) new Image().src = c.image; });
  DC.deck.slice(3, 9).forEach((c) => { if (c.image) new Image().src = c.image; });
}

function dcSetBg(url) {
  const a = dcQ("#dcBg"), b = dcQ("#dcBg2"), cur = DC.bgOn ? b : a, nxt = DC.bgOn ? a : b;
  if (DC.bgUrl === url) return;
  DC.bgUrl = url;
  if (url) { nxt.style.backgroundImage = `url('${url}')`; nxt.classList.add("on"); }
  cur.classList.remove("on"); DC.bgOn = 1 - DC.bgOn;
  if (!url) { a.classList.remove("on"); b.classList.remove("on"); }
}

// ───────── choosing
function dcTop() { return [...dcQ("#dcStage").children].find((x) => x.classList.contains("pos0") && !x.classList.contains("fly") && !x.classList.contains("dcEmptyCard")); }

function dcFly(el, keep, dx) {
  const dir = keep ? 1 : -1, x = (dx !== undefined && Math.abs(dx) > 40 ? dx : dir * 40) + dir * window.innerWidth * 0.9;
  el.classList.remove("drag"); el.classList.add("fly");
  el.style.transform = `translateX(${x}px) rotate(${dir * 24}deg)`;
  setTimeout(() => el.remove(), 280);
}

function dcDecide(keep, el, dx) {
  const card = DC.deck[0]; if (!card) return;
  el = el || dcTop(); if (!el) return;
  DC.deck.shift(); DC.left = Math.max(0, DC.left - 1);
  DC.hist.push({ card, keep });
  DC.pending.add(card.slug); DC.flying.add(card.slug);
  if (keep) DC.sum.kept++; else DC.sum.skipped++;
  DC.sum.can_undo = true;
  dcFly(el, keep, dx);
  setTimeout(() => DC.flying.delete(card.slug), 400);
  dcRenderStage(); dcRenderStats();
  if (DC.deck.length < 8) dcFill(false);
  DC.chain = DC.chain.then(() => api("/api/discover/decide", { slug: card.slug, keep })).then((r) => {
    DC.pending.delete(card.slug);
    if (r.error) dcToast("Kept, but: " + r.error, 5000);
    else if (keep) { dcToast("Kept " + card.name + (r.queued ? " · scraping queued" : " · waits for the current job")); dcLoadKept(); }
  }).catch((e) => { DC.pending.delete(card.slug); dcToast("Could not save that choice: " + e.message, 5000); });
}

async function dcUndo() {
  if (!DC.sum || !DC.sum.can_undo) return;
  await DC.chain.catch(() => {});
  try {
    const r = await api("/api/discover/undo", {});
    if (!r.card) { dcToast("Nothing to undo"); return; }
    DC.deck = [r.card, ...DC.deck.filter((c) => c.slug !== r.card.slug)];
    DC.left++; if (r.was_keep) DC.sum.kept = Math.max(0, DC.sum.kept - 1); else DC.sum.skipped = Math.max(0, DC.sum.skipped - 1);
    DC.hist.pop();
    dcRenderStage(); const top = dcTop(); if (top) { top.classList.add("enter"); setTimeout(() => top.classList.remove("enter"), 400); }
    dcRenderStats(); if (r.note) dcToast(r.note, 4500); else dcToast("Back to " + r.card.name);
    dcRefresh(false);
  } catch (e) { dcToast(e.message, 4000); }
}

function dcOpen() { const c = DC.deck[0]; if (c) window.open(c.url, "_blank", "noopener"); }

async function dcShuffle() {
  try { const r = await api("/api/discover/shuffle", {}); await dcFill(true); dcToast("Re-shuffled " + r.left + " performers"); }
  catch (e) { dcToast(e.message, 3000); }
}

async function dcResetSkipped() {
  try { const r = await api("/api/discover/reset", {}); DC.hist = []; await dcRefresh(true); dcToast(r.restored + " skipped performers are back in the deck"); }
  catch (e) { dcToast(e.message, 3000); }
}

// ───────── dragging
function dcDragStart(e) {
  const el = dcTop(); if (!el || !el.contains(e.target) || e.button > 0) return;
  DC.drag = { el, x0: e.clientX, y0: e.clientY, t0: performance.now(), dx: 0, id: e.pointerId };
  el.classList.add("drag");
}
function dcDragMove(e) {
  const d = DC.drag; if (!d) return;
  d.dx = e.clientX - d.x0; const dy = (e.clientY - d.y0) * 0.35;
  d.el.style.transform = `translate(${d.dx}px, ${dy}px) rotate(${d.dx / 16}deg)`;
  const f = Math.min(1, Math.abs(d.dx) / 140);
  d.el.querySelector(".dcStamp.keep").style.opacity = d.dx > 0 ? f : 0;
  d.el.querySelector(".dcStamp.nope").style.opacity = d.dx < 0 ? f : 0;
  d.el.classList.toggle("dcGlowKeep", d.dx > 60); d.el.classList.toggle("dcGlowNope", d.dx < -60);
}
function dcDragEnd() {
  const d = DC.drag; if (!d) return; DC.drag = null;
  const v = d.dx / Math.max(1, performance.now() - d.t0);              // px per ms
  d.el.classList.remove("dcGlowKeep", "dcGlowNope");
  if (Math.abs(d.dx) > 110 || (Math.abs(d.dx) > 40 && Math.abs(v) > 0.6)) { dcDecide(d.dx > 0, d.el, d.dx); return; }
  d.el.classList.remove("drag"); d.el.style.transform = "";
  d.el.querySelectorAll(".dcStamp").forEach((s) => (s.style.opacity = 0));
}

// ───────── kept strip
async function dcLoadKept() {
  if (dcLoadKept.busy) return; dcLoadKept.busy = true;
  try {
    const r = await api("/api/discover/kept"); DC.queue = r.queue; DC.kept = r.kept;
    dcQ("#dcKeptCount").textContent = DC.sum ? DC.sum.kept + " total" : "";
    dcQ("#dcKept").innerHTML = r.kept.map((k) => `<a class="dcAv ${k.status}" href="${esc(k.url)}" target="_blank" rel="noopener"
        title="${esc(k.name)}: ${k.status === "done" ? k.links + " links scraped" : k.status === "scraping" ? "scraping now" : k.status === "queued" ? "waiting its turn" : "added, no links yet"}">
        <span class="pic" style="${k.image ? `background-image:url('${k.image}')` : ""}">${k.image ? "" : esc(k.name[0])}</span>
        ${k.links ? `<span class="links">${k.links}</span>` : ""}<span class="n">${esc(k.name.split(" ")[0])}</span></a>`).join("");
    dcRenderScrape();
  } catch (e) { /* ignore */ }
  dcLoadKept.busy = false;
}

// ───────── settings
function dcRenderSettings(keepOpen) {
  const s = DC.sum, st = s.settings, p = s.progress, box = dcQ("#dcSettings");
  const pg = ["5", "10", "25", "50", "all"];
  box.innerHTML = `
    <div><h4>When I keep someone, scrape</h4><div class="dcSeg">${pg.map((x) => `<button data-sp="${x}" class="${st.scrape_pages === x ? "on" : ""}">${x === "all" ? "All pages" : x + " pages"}</button>`).join("")}</div>
      <p class="small">Pages of their videos, most viewed first. Each page is about 30 videos.</p></div>
    <div><h4>Collect more</h4><div class="row"><input type="number" id="dcMorePages" min="1" max="100" value="${Math.max(40, (s.collected_pages || 0) + 10)}">
      <button class="dcGo" id="dcMoreGo" ${p.running ? "disabled" : ""} style="padding:8px 14px;font-size:13px">${p.running ? "Collecting…" : "Collect"}</button></div>
      <p class="small">${s.total} performers and ${s.pictures} pictures so far (${s.collected_pages || 0} pages read). Reading more pages adds new people to the deck.</p></div>
    <div><h4>Skipped</h4><button class="dcGo ghost" id="dcResetBtn" style="padding:8px 14px;font-size:13px" ${s.skipped ? "" : "disabled"}>Show the ${s.skipped} skipped again</button></div>`;
  box.querySelectorAll("[data-sp]").forEach((b) => (b.onclick = () => dcSaveSettings({ scrape_pages: b.dataset.sp })));
  dcQ("#dcMoreGo").onclick = () => dcCollect(+dcQ("#dcMorePages").value || 40);
  dcQ("#dcResetBtn").onclick = dcResetSkipped;
}

async function dcSaveSettings(patch, quiet) {
  try {
    let r = await api("/api/discover/settings", patch);
    r = r.settings ? r : { settings: r, left: DC.left };           // an older server answers with just the settings
    DC.sum.settings = r.settings; DC.left = r.left;
    const filterChange = Object.keys(patch).some((k) => k !== "scrape_pages");
    if (filterChange) { DC.sum.filters_active = FKEYS.filter((k) => r.settings[k]).length; await dcFill(true); dcRenderFilters(); dcRenderStats(); }
    else dcRenderSettings();
    if (!quiet) dcToast("Saved");
  } catch (e) { dcToast(e.message, 3500); }
}

// ───────── filters
const FKEYS = ["min_videos", "max_videos", "min_views", "max_views", "verified_only", "max_rank"];
const MV = 1e6;
const vwTxt = (n) => fmtN(n);

function dcToggleFilters() {
  const p = dcQ("#dcFilters"); p.hidden = !p.hidden; dcQ("#dcSettings").hidden = true;
  if (!p.hidden) dcRenderFilters();
}

function dcActiveFilters() {
  const f = (DC.sum && DC.sum.settings) || {}, out = [];
  if (f.min_views) out.push({ k: "min_views", t: "Views ≥ " + vwTxt(f.min_views) });
  if (f.max_views) out.push({ k: "max_views", t: "Views ≤ " + vwTxt(f.max_views) });
  if (f.min_videos) out.push({ k: "min_videos", t: "Videos ≥ " + f.min_videos });
  if (f.max_videos) out.push({ k: "max_videos", t: "Videos ≤ " + f.max_videos });
  if (f.max_rank) out.push({ k: "max_rank", t: "Top " + f.max_rank });
  if (f.verified_only) out.push({ k: "verified_only", t: "Verified only" });
  return out;
}

function dcRenderChips() {
  const act = dcActiveFilters(), row = dcQ("#dcChipsRow"), badge = dcQ("#dcFilterBadge");
  badge.hidden = !act.length; badge.textContent = act.length;
  row.hidden = !act.length;
  if (!act.length) { row.innerHTML = ""; return; }
  row.innerHTML = `<span class="lbl">Filters</span>` + act.map((a) => `<button class="dcFchip" data-fk="${a.k}" title="Remove this filter">${esc(a.t)} <b>✕</b></button>`).join("")
    + `<button class="dcFclear" id="dcFclear">Clear all</button><span class="lbl" style="margin-left:auto">${DC.left} match</span>`;
  row.querySelectorAll("[data-fk]").forEach((b) => (b.onclick = () => dcSaveSettings({ [b.dataset.fk]: b.dataset.fk === "verified_only" ? false : 0 }, true)));
  dcQ("#dcFclear").onclick = () => dcSaveSettings({ reset_filters: true }, true);
}

function dcRenderFilters() {
  const s = DC.sum, f = s.settings, r = s.ranges || {}, box = dcQ("#dcFilters");
  const viewsPre = [0, 10, 50, 100, 500, 1000], vidsPre = [0, 10, 50, 100, 500], rankPre = [0, 100, 250, 500, 1000];
  const m = (n) => (n ? +(n / MV).toFixed(2) : "");
  const seg = (arr, cur, attr, lab) => arr.map((x) => `<button data-${attr}="${x}" class="${cur === x ? "on" : ""}">${lab(x)}</button>`).join("");
  const act = dcActiveFilters().length;
  box.innerHTML = `
    <div><h4>Views at least</h4><div class="dcSeg">${seg(viewsPre, Math.round((f.min_views || 0) / MV), "vp", (x) => (x ? (x >= 1000 ? "1B" : x + "M") : "Any"))}</div>
      <div class="two" style="margin-top:10px"><label class="f">Min views (millions)<input type="number" id="fMinViews" min="0" step="any" value="${m(f.min_views)}" placeholder="any"></label>
        <label class="f">Max views (millions)<input type="number" id="fMaxViews" min="0" step="any" value="${m(f.max_views)}" placeholder="any"></label></div>
      <p class="small">Biggest in your list: ${vwTxt(r.max_views || 0)} views.</p></div>
    <div><h4>Number of videos</h4><div class="dcSeg">${seg(vidsPre, f.min_videos || 0, "vd", (x) => (x ? x + "+" : "Any"))}</div>
      <div class="two" style="margin-top:10px"><label class="f">At least<input type="number" id="fMinVids" min="0" value="${f.min_videos || ""}" placeholder="any"></label>
        <label class="f">At most<input type="number" id="fMaxVids" min="0" value="${f.max_videos || ""}" placeholder="any"></label></div></div>
    <div><h4>Directory rank</h4><div class="dcSeg">${seg(rankPre, f.max_rank || 0, "rk", (x) => (x ? "Top " + x : "Any"))}</div>
      <div class="row" style="margin-top:10px"><label class="f" style="width:120px">Top N only<input type="number" id="fRank" min="0" value="${f.max_rank || ""}" placeholder="any"></label>
        <span class="small" style="margin:18px 0 0">1 is the most popular. Ranks go up to ${r.max_rank || "?"}.</span></div></div>
    <div><button type="button" class="dcSwitch ${f.verified_only ? "on" : ""}" id="fVer" aria-pressed="${!!f.verified_only}"><i></i><span>Verified performers only</span></button></div>
    <div class="foot"><div class="count">${DC.left} <span>of ${s.total} match</span></div>
      <button class="dcGo ghost" id="fClear" style="padding:8px 14px;font-size:13px" ${act ? "" : "disabled"}>Clear filters</button></div>`;
  const save = (patch) => dcSaveSettings(patch, true);
  const debounced = (id, key, scale) => { const el = dcQ(id); let t; el.oninput = () => { clearTimeout(t); t = setTimeout(() => save({ [key]: Math.round((parseFloat(el.value) || 0) * scale) }), 450); }; };
  debounced("#fMinViews", "min_views", MV); debounced("#fMaxViews", "max_views", MV);
  debounced("#fMinVids", "min_videos", 1); debounced("#fMaxVids", "max_videos", 1); debounced("#fRank", "max_rank", 1);
  box.querySelectorAll("[data-vp]").forEach((b) => (b.onclick = () => save({ min_views: +b.dataset.vp * MV })));
  box.querySelectorAll("[data-vd]").forEach((b) => (b.onclick = () => save({ min_videos: +b.dataset.vd })));
  box.querySelectorAll("[data-rk]").forEach((b) => (b.onclick = () => save({ max_rank: +b.dataset.rk })));
  dcQ("#fVer").onclick = () => save({ verified_only: !f.verified_only });
  dcQ("#fClear").onclick = () => save({ reset_filters: true });
}
