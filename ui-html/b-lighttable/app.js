/* Design B · Light table: renders every page from window.DATA (real snapshot of the running app). */
(() => {
const D = window.DATA;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf = (n) => Number(n).toLocaleString("en-GB");
const gb = (b) => (b / 1e9).toFixed(1) + " GB";
const mmss = (s) => { s = Math.round(s); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
const hhmm = (ms) => new Date(ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
const ICO = {
  chev: '<path d="M6 9l6 6 6-6"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>', open: '<path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5"/>',
  play: '<path d="M8 5l11 7-11 7z"/>', plus: '<path d="M12 5v14M5 12h14"/>', dl: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
  folder: '<path d="M3 7h6l2 2h10v10H3z"/>', check: '<path d="M5 12.5l4.5 4.5L19 7"/>', redo: '<path d="M20 12a8 8 0 1 1-3-6.2M20 4v5h-5"/>', left: '<path d="M19 12H5M11 6l-6 6 6 6"/>', right: '<path d="M5 12h14M13 6l6 6-6 6"/>', text: '<path d="M5 6h14M12 6v13M9 19h6"/>', sliders: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6"/>',
};
const ic = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICO[n]}</svg>`;
const topName = (n) => n.split(" - ")[0];
const colourOf = (n) => D.colours[topName(n).replace(/ /g, "_")] || "#9aa5b1";
const MARK = '<svg class="mark-svg" viewBox="0 0 80 100" preserveAspectRatio="none" aria-hidden="true"><path pathLength="1" d="M7 52 C4 22 30 5 54 8 C78 11 80 58 64 82 C48 101 12 95 9 62 C7 48 12 36 21 28"/></svg>';
const ring = (cls) => `<span class="badge ${cls}"><svg viewBox="0 0 34 34" aria-hidden="true"><path d="${cls === "f" ? "M6 6L28 28M28 6L6 28" : "M5 18C4 9 14 3 22 4C31 6 32 20 25 27C18 33 7 30 5 21C4 17 6 13 10 10"}"/></svg>${cls === "v" ? ic("check") : cls === "o" ? ic("redo") : ""}</span>`;

/* ---------- state ---------- */
const S = {
  page: "find", model: D.model || "clip", lbOpen: null,
  accounts: [D.accounts.find((a) => a.handle === "lily-larimar") || D.accounts[2]].filter(Boolean),
  query: "", signal: "text", tags: new Set(), videoOnly: true,
  rank: "Best", posts: 50, every: false, mix: "Pool", mode: "Instant thumbs",
  lb: D.favs.map((f) => ({ ...f })), lbExtra: D.favTotal - D.favs.length, lbType: "all",
  picked: new Set(), tagSel: "pose:standing", conf: 0.5, scope: "",
  pos: "", vFilter: "all", vSort: "attention", vQuery: "", verifiedOnly: false, clipLen: "15 seconds", conf2: 0.5,
  piles: JSON.parse(JSON.stringify(D.pilot.piles)), counts: { ...D.pilot.counts }, tri: "keep", ti: 0, keepAt: 0.7, junkAt: 0.2, whole: false, lastMove: null,
  jobOpen: null, srcTab: "accounts", autoImport: D.autoImport,
};
const PAGES = [["find", "Find"], ["library", "Library"], ["videos", "Videos"], ["triage", "Triage"], ["fetch", "Fetch"]];

/* ---------- chrome ---------- */
function lbCount() { return S.lb.length + S.lbExtra; }
function drawTop() {
  $("#tabs").innerHTML = PAGES.map(([id, l], i) => `<button class="tab" data-go="${id}" ${id === S.page ? 'aria-current="page"' : ""}>${l}</button>`).join("");
  $$("#model button").forEach((b) => b.setAttribute("aria-selected", b.dataset.m === S.model));
  $("#open-status").innerHTML = `<i></i>${gb(D.storage.free)} free · ${D.session.loggedIn ? "Logged in" : "Logged out"}`;
  $("#open-status").classList.toggle("warn", D.storage.free < 5e9);
  const running = D.jobs.filter((j) => j.running).length;
  $("#open-act").className = "act-btn" + (running ? " busy" : "");
  $("#open-act").innerHTML = `<span class="spin"></span>Activity ${running ? running + " running" : D.jobs.length}`;
  $("#open-lb").innerHTML = `Lightbox <b>${lbCount()}</b>`;
  $("#open-lb").setAttribute("aria-pressed", lbVisible());
}
const lbVisible = () => S.lbOpen === null ? S.page === "find" : S.lbOpen;
function applyLb() { const v = lbVisible(); $("#layout").classList.toggle("no-lb", !v); $("#open-lb").setAttribute("aria-pressed", v); }

function go(id) {
  S.page = id; drawTop(); applyLb();
  $("#page").classList.toggle("flush", id === "fetch"); $("#page").innerHTML = `<div class="page-w">${PAGE[id]()}</div>`;
  drawLb(); bind(id); window.scrollTo(0, 0);
  document.title = PAGES.find((p) => p[0] === id)[1] + " · Postroom";
  try { history.replaceState(null, "", "#" + id); } catch (e) {}
}

/* ---------- lightbox ---------- */
function removeLb(i) {
  const [it] = S.lb.splice(i, 1); S.picked.delete(it.key); const f = $(`[data-pick="${it.key}"]`); if (f) f.closest(".fr").classList.remove("picked", "static");
  drawTop(); drawLb();
  const e = document.createElement("div"); e.className = "toast"; e.innerHTML = 'Removed from Lightbox <button class="btn sm" style="margin-left:12px;min-height:26px">Undo</button>'; document.body.appendChild(e);
  e.querySelector("button").onclick = () => { S.lb.splice(i, 0, it); if (it.key) { S.picked.add(it.key); const f2 = $(`[data-pick="${it.key}"]`); if (f2) f2.closest(".fr").classList.add("picked", "static"); } drawTop(); drawLb(); e.remove(); };
  setTimeout(() => e.remove(), 5000);
}
function drawLb() {
  const items = S.lb.filter((f) => S.lbType === "all" || (S.lbType === "video") === !!f.video);
  $("#lightbox").innerHTML = `<div class="lb-h"><h2>Lightbox <b>${lbCount()}</b></h2>
    <div class="seg" id="lbt" role="tablist" aria-label="Type">${[["all", "All"], ["photo", "Photos"], ["video", "Videos"]].map(([k, l]) => `<button role="tab" data-k="${k}" aria-selected="${S.lbType === k}">${l}</button>`).join("")}</div></div>
    <div class="lb-grid">${items.map((f, i) => `<div class="lb-it" title="@${esc(f.account)}"><button class="lb-open" data-lbo="${S.lb.indexOf(f)}" aria-label="Preview @${esc(f.account)}"><img loading="lazy" alt="" src="${f.thumb}"></button><button class="lb-x" data-lb="${S.lb.indexOf(f)}" aria-label="Remove from Lightbox">${ic("x")}</button></div>`).join("")}</div>
    <div class="lb-foot"><button class="btn sm" id="lb-slides">${ic("play")}Slides</button><button class="btn sm">${ic("dl")}Download</button><button class="btn sm ghost" aria-label="Show in Finder">${ic("folder")}</button></div>`;
  $("#lbt").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.lbType = b.dataset.k; drawLb(); };
  $("#lb-slides").onclick = openSlides;
  $("#lightbox").onclick = (e) => {
    const o = e.target.closest("[data-lbo]"); if (o) { const f = S.lb[+o.dataset.lbo]; sheet(`<div class="dlg" style="width:min(560px,96vw)" role="dialog" aria-label="Preview"><div class="dlg-h"><h2>@${esc(f.account)}</h2>${X}</div><div class="dlg-b"><div style="background:#0b0c0d;padding:10px"><img alt="" style="width:100%;max-height:60vh;object-fit:contain;display:block" src="${f.thumb}"></div><div class="spread"><span class="hint">${esc(f.date || "local file")}</span><button class="btn danger" id="rmlb">Remove from Lightbox</button></div></div></div>`, true); $("#rmlb").onclick = () => { closeSheet(); removeLb(+o.dataset.lbo); }; return; }
    const b = e.target.closest("[data-lb]"); if (b) removeLb(+b.dataset.lb); };
  $("#lb-slides").onclick = openSlides;
}

/* ---------- find ---------- */
const sumText = () => `${S.rank} · ${S.posts} posts · ${{ Pool: "pooled", Each: "each", Even: "even" }[S.mix]}`;
function frame(f, i, o = {}) {
  const key = "f" + i, picked = S.picked.has(key);
  return `<figure class="fr ${picked ? "picked static" : ""}"><button class="fr-in" data-pick="${key}" aria-pressed="${picked}" aria-label="Circle to keep"><img loading="lazy" alt="" src="${f.thumb}">${f.video ? '<span class="vb">VIDEO</span>' : ""}<span class="fr-edge"><span><i class="tr3"></i>${String(i + 1).padStart(2, "0")}</span><span>${f.video ? "VIDEO" : esc(S.model.toUpperCase())}</span></span>${MARK}</button>
    <div class="tools"><span class="ibtn" role="img" aria-label="Open post">${ic("open")}</span></div>
    <figcaption class="fr-meta"><b>@${esc(f.account)}</b><span>${esc(f.date || "local")}</span></figcaption></figure>`;
}
function contact() {
  const items = D.favs.slice(8, 32);
  return `<div class="sheet-head"><div><h2 class="sec-h">Contact sheet · ${items.length} frames</h2><p class="hint">Layout preview: sample frames stand in for a real draw. Click a frame to circle it into the Lightbox.</p></div>
    <div class="row"><button class="btn sm" data-act="slides">${ic("play")}Slideshow</button><button class="btn sm" id="circle-all">Circle all</button><button class="btn sm">${ic("dl")}Save circled full size</button></div></div>
    <div class="contact" id="contact">${items.map((f, i) => frame(f, i)).join("")}</div>`;
}
PAGE_find = () => `
  <div class="page-head compact"><h1 class="h-page sm">Find a frame.</h1><p class="sub-page">Describe it, drop a reference, match a pose or require tags. Empty means random.</p></div>
  <div class="qbar"><div class="tokens" id="tokens">${S.accounts.map((a) => `<button class="tok" data-rm="${esc(a.handle)}" title="Remove">${a.cover ? `<img alt="" src="${a.cover}">` : ""}@${esc(a.handle)}${ic("x")}</button>`).join("")}</div>
    <input id="query" type="text" placeholder="Describe the frame you want… or leave empty for random" value="${esc(S.query)}" autocomplete="off"><button class="btn pri" id="draw">Draw random</button></div>
  <div class="filters">
    <button class="pill" id="p-acc" aria-expanded="false">Accounts <b>${S.accounts.length}</b>${ic("chev")}</button>
    <button class="pill" id="p-sig" aria-expanded="false">Search by <b>${{ text: "scene text", ref: "reference", pose: "pose" }[S.signal]}</b>${ic("chev")}</button>
    <button class="pill" id="p-tag" aria-expanded="false">Must match <b id="tagn">${S.tags.size + (S.videoOnly ? 1 : 0)}</b>${ic("chev")}</button>
    <button class="pill" id="p-opt" aria-expanded="false"><span id="optsum">${sumText()}</span>${ic("chev")}</button>
    <span class="grow"></span>
    <button class="btn sm ghost" id="refine">${ic("sliders")}Refine</button></div>
  <div class="sugg"><span class="lbl">Try</span>${["smiling on a beach", "mirror selfie", "red dress, golden hour", "full body walking on a street", "cafe table, seated"].map((s) => `<button class="tag" data-sugg="${esc(s)}">${esc(s)}</button>`).join("")}</div>
  <div id="results">${contact()}</div>`;

/* ---------- library ---------- */
function libraryWall() {
  const imgs = D.favs.filter((f) => !f.video).slice(0, 28);
  const [g, n] = S.tagSel.split(":"); const row = (D.tagCounts[g] || []).find((x) => x[0] === n) || [n, 0];
  return `<div class="sheet-head" style="margin-top:0"><div><h2 class="sec-h">${esc(n)} <span class="mono mute">${esc(g)}</span></h2><p class="hint">${nf(row[1])} images carry it · best matches first. Layout preview: sample frames.</p></div>
    <div class="row"><button class="btn sm ghost" id="second">Add a second tag</button><button class="btn sm">${ic("play")}Slideshow</button></div></div>
    <div class="contact" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr))">${imgs.map((f, i) => `<figure class="fr"><div class="fr-in" style="cursor:default"><img loading="lazy" alt="" src="${f.thumb}"><span class="fr-edge"><span><i class="tr3"></i>${String(i + 1).padStart(2, "0")}</span><span>${esc(n.toUpperCase().slice(0, 12))}</span></span></div></figure>`).join("")}</div>`;
}
PAGE_library = () => {
  const groups = Object.entries(D.tagCounts).filter(([, v]) => v.length);
  const max = Math.max(...groups.flatMap(([, v]) => v.map((x) => x[1])));
  const built = D.accounts.filter((a) => a.built && a.posts);
  return `<div class="page-head"><div><h1 class="h-page">What's in the index.</h1><p class="sub-page">${built.length} indexed accounts. Pick a tag to see the images carrying it (counts below are from a sample of 13 accounts).</p></div>
    <div class="row"><button class="btn" id="open-src">Manage sources · ${D.accounts.filter((a) => a.posts || a.videos).length}</button><button class="btn ghost">Open library folder</button><button class="btn ghost" id="lib-prep">Prepare indexes</button></div></div>
  <div class="lib-top"><label class="field" style="min-width:250px"><span>Account</span><select id="scope"><option value="">All indexed accounts</option>${built.map((a) => `<option value="${esc(a.handle)}" ${S.scope === a.handle ? "selected" : ""}>@${esc(a.handle)} · ${a.posts}</option>`).join("")}</select></label>
    <label class="field" style="min-width:260px"><span>How sure a tag must be · <b id="confv">${S.conf.toFixed(2)}</b></span><input type="range" id="conf" min="0.3" max="0.95" step="0.05" value="${S.conf}"></label>
    <div class="figs" style="margin:0"><div><b>${nf(D.tagImages)}</b><span>images tagged in sample</span></div><div><b>${built.reduce((s, a) => s + a.videos, 0)}</b><span>videos</span></div><div><b>${nf(built.reduce((s, a) => s + a.extra, 0))}</b><span>extra slide photos</span></div></div></div>
  <div class="lib"><div class="facets" id="facets">${groups.map(([g, v]) => `<div class="fg"><span class="lbl">${esc(g)}</span>${v.slice(0, 9).map(([n, c]) => `<button class="fct" data-t="${esc(g + ":" + n)}" aria-pressed="${S.tagSel === g + ":" + n}"><span>${esc(n)}</span><em>${nf(c)}</em><i class="b" style="width:${(c / max) * 100}%"></i></button>`).join("")}</div>`).join("")}
    <p class="hint">A second tag from another group asks whether to show it alone or require both. A tag from the same group replaces the first.</p></div>
    <div id="wall">${libraryWall()}</div></div>`;
};

/* ---------- videos ---------- */
const vStat = (v) => v.verified ? ["v", "Verified"] : v.status === "outdated" ? ["o", "Older model"] : v.status === "failed" ? ["f", "Failed"] : ["o", "Up to date"];
function vRows() {
  let list = D.videos.filter((v) => {
    const f = S.vFilter;
    return (f === "all" || (f === "attention" && !v.verified && v.status !== "completed") || (f === "verified" && v.verified) || (f === "older" && v.status === "outdated") || (f === "failed" && v.status === "failed") || (f === "waiting" && v.status === "waiting") || (f === "running" && v.status === "queued"))
      && (!S.pos || v.timeline.some((t) => topName(t[0]) === topName(S.pos))) && (!S.verifiedOnly || v.verified)
      && (!S.vQuery || (v.title + v.creator).toLowerCase().includes(S.vQuery.toLowerCase()));
  });
  if (S.vSort === "conf") list = [...list].sort((a, b) => b.conf - a.conf);
  if (S.vSort === "dur") list = [...list].sort((a, b) => b.dur - a.dur);
  list = list.slice(0, 30); S.vlist = list;
  if (!list.length) return '<div class="empty"><h3>No videos match</h3><p>Clear a filter or choose another position.</p></div>';
  return list.map((v) => {
    const [cls, lab] = vStat(v), seg = S.pos && v.timeline.find((t) => topName(t[0]) === topName(S.pos));
    return `<article class="vrow"><div class="vrow-top"><label class="vsel"><input type="checkbox" data-vs="${i}" aria-label="Select video">${ring(cls)}</label><div><h3>${esc(v.title)}</h3><p class="sub">${esc(v.creator)} · ${lab} · ${v.sections} sections · ${v.verified ? "checked by you" : "model " + Math.round(v.conf * 100) + "%"}</p></div>
      <div class="row"><button class="btn sm ghost" data-rv="${i}">Review</button>${seg ? `<button class="btn sm">${ic("play")}Play clip</button>` : '<button class="btn sm ghost">Re-run</button>'}</div></div>
      <div><div class="tl">${v.timeline.map((t) => `<i class="${S.pos && topName(t[0]) !== topName(S.pos) ? "dim" : ""}" style="flex:${Math.max(0.5, t[2] - t[1])};background:${colourOf(t[0])}" title="${esc(t[0])} ${mmss(t[1])}–${mmss(t[2])}"></i>`).join("")}</div><div class="tl-t"><span>0:00</span><span>${mmss(v.dur)}</span></div></div>
      ${seg ? `<div class="clipline"><span class="t">${mmss(seg[1])} → ${mmss(Math.min(seg[2], seg[1] + (D.clipLengths[S.clipLen] || 15)))}</span><span class="hint">${esc(S.pos.replace(/_/g, " "))} · section ${mmss(seg[1])}–${mmss(seg[2])}</span></div>` : ""}</article>`; }).join("");
}
PAGE_videos = () => {
  const c = D.vidCounts, ver = (c.completed || 0) + (c.saved || 0), old = c.outdated || 0, tot = ver + old;
  const cur = S.pos ? D.positions.find((p) => p.name === S.pos) : null;
  return `<div class="page-head"><div><h1 class="h-page">Every video, and what the model made of it.</h1><p class="sub-page">${tot} videos. Pick a position to see where it happens and cut clips; videos you verified are never overwritten.</p></div>
    <div class="row"><button class="btn pri" id="analyse-all" style="min-height:40px">Analyse everything that needs it (${old})</button><button class="btn ghost" id="sel-all">Select all (${tot})</button><button class="btn ghost" id="rerun-sel">Re-run selected</button></div></div>
  <div class="figs"><div><b>${ver}</b><span>verified by you</span></div><div><b>${old}</b><span>on an older model</span></div><div><b>${D.videos.filter((v) => v.status === "failed").length}</b><span>failed</span></div></div>
  <div class="meter"><i style="width:${(ver / tot) * 100}%;background:var(--pick)"></i><i style="width:${(old / tot) * 100}%;background:var(--maybe)"></i></div>
  <div class="row" style="margin:14px 0 20px">${[["all", "All"], ["attention", "Needs analysis"], ["verified", "Verified"], ["older", "Older model"], ["waiting", "Waiting"], ["running", "Running"], ["failed", "Failed"]].map(([k, l]) => `<button class="tag ${S.vFilter === k ? "on" : ""}" data-vf="${k}">${l}</button>`).join("")}
    <span class="grow"></span><input type="search" id="vq" placeholder="Search title or creator" style="width:230px" value="${esc(S.vQuery)}"><select id="vs" style="width:200px"><option value="attention" ${S.vSort === "attention" ? "selected" : ""}>Needs attention first</option><option value="conf" ${S.vSort === "conf" ? "selected" : ""}>Model confidence</option><option value="dur" ${S.vSort === "dur" ? "selected" : ""}>Length</option></select></div>
  <div class="vsplit"><div class="pos-col" id="poscol"><span class="lbl" style="display:block;padding-bottom:6px;border-bottom:2px solid var(--ink)">Position</span>
    <button class="pos-i" data-pos="" aria-pressed="${!S.pos}"><i style="background:linear-gradient(90deg,#d9534f,#4f8fd9,#7b5ea7)"></i><span>All positions</span><em>${tot}</em></button>
    ${D.positions.map((p) => `<button class="pos-i ${p.name.includes(" - ") ? "child" : ""}" data-pos="${esc(p.name)}" aria-pressed="${S.pos === p.name}"><i style="background:${colourOf(p.name)}"></i><span>${esc((p.name.includes(" - ") ? p.name.split(" - ")[1] : p.name).replace(/_/g, " "))}</span><em>${p.videos}</em></button>`).join("")}</div>
    <div><div id="vctl" ${cur ? "" : "hidden"} style="background:var(--sheet);border:1px solid var(--rule);padding:12px 14px;margin-bottom:12px"><div class="spread"><div><b>${cur ? esc(cur.name.replace(/_/g, " ")) : ""}</b> <span class="hint">${cur ? `${cur.videos} videos, about ${nf(cur.minutes)} minutes · ${D.posMeta.missingFiles} files not found are skipped` : ""}</span></div>
        <div class="row"><label class="row hint">Clip <select id="cl" style="width:140px">${Object.keys(D.clipLengths).map((k) => `<option ${k === S.clipLen ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label><label class="row hint">Confidence ${S.conf2.toFixed(2)} <input type="range" id="c2" min="0" max="1" step="0.05" value="${S.conf2}" style="width:110px"></label>
        <button class="tag ${S.verifiedOnly ? "on" : ""}" id="vonly">Verified only</button><button class="btn sm" data-act="slides">${ic("play")}Slideshow</button></div></div></div>
      <div id="vrows">${vRows()}</div><p class="hint" style="margin-top:8px">Showing the first 30. Colours match the position lines in the list.</p></div></div>`;
};

/* ---------- triage ---------- */
const PM = { keep: ["Keep", "k", "K"], review: ["Review", "r", "R"], junk: ["Junk", "j", "J"] };
function triView() {
  const pile = S.piles[S.tri], it = pile[Math.min(S.ti, pile.length - 1)];
  if (!it) return '<div class="empty"><h3>Nothing in this pile</h3><p>Move something here or run the pilot again.</p></div>';
  const mk = (cls) => `<span class="m ${cls}"></span>`;
  return `<div class="tri"><div><div class="viewer"><img alt="" src="${it.crop}"><span class="vm ${S.tri}" key="${S.ti}${S.tri}">${S.tri === "junk" ? '<svg class="xm" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path pathLength="1" d="M8 8L92 92M92 8L8 92"/></svg>' : MARK}</span><span class="fr-edge"><span><i class="tr3"></i>${String(S.ti + 1).padStart(2, "0")} / ${pile.length}</span><span>${esc(it.file)}</span></span></div>
      <div class="film" id="film">${pile.map((p, i) => `<button data-fi="${i}" aria-current="${i === S.ti}" aria-label="Item ${i + 1}"><img loading="lazy" alt="" src="${p.crop}">${mk(S.tri)}</button>`).join("")}</div></div>
    <div style="display:grid;gap:18px"><div><p class="lbl">Photo score</p><p style="font:800 56px/1 var(--sans);letter-spacing:-0.05em;margin-top:6px">${it.score.toFixed(2)}</p><p class="hint" style="margin-top:6px">${it.body ? "Body found in the crop." : "No body found."} ${esc(it.prompt)} · ${esc(it.file)} · ${esc(it.date)}</p></div>
      <div class="decide" id="decide">${Object.entries(PM).map(([k, [l, c, key]]) => `<button class="${c}" data-d="${k}" aria-pressed="${S.tri === k}">${l}<small>${key}</small></button>`).join("")}</div>
      <div class="row"><button class="btn" id="tprev">${ic("left")}Previous</button><button class="btn" id="tnext">Next${ic("right")}</button><span class="grow"></span><button class="btn ghost" id="undo" ${S.lastMove ? "" : "disabled"}>Undo correction</button></div>
      <p class="hint">Keys: K keep · R review · J junk · ← → move. A manual move stays put when the sliders change.</p></div></div>`;
}
PAGE_triage = () => `<div class="page-head"><div><h1 class="h-page">Sort the screenshot pile.</h1><p class="sub-page">Crops the likely photo out of each screenshot, scores whether it looks like a person, and files it. The Photos library is read-only.</p></div>
    <div class="row"><button class="pill" id="p-run" aria-expanded="false">Run the pilot on <b>400</b> random screenshots${ic("chev")}</button><button class="sw" id="whole" aria-pressed="${S.whole}" style="width:auto"><span class="trk"></span><span><strong style="font-size:13.5px">Whole screenshot</strong></span></button></div></div>
  <div style="background:var(--sheet);border:1px solid var(--rule);padding:14px 18px 14px;margin-bottom:20px"><div class="ramp"><div class="zones"><i style="background:var(--reject);flex:${S.junkAt}"></i><i style="background:var(--maybe);flex:${S.keepAt - S.junkAt}" id="zr"></i><i style="background:var(--pick);flex:${1 - S.keepAt}"></i></div>
    <input type="range" id="junk" min="0" max="1" step="0.05" value="${S.junkAt}" aria-label="Junk below"><input type="range" id="keep" min="0" max="1" step="0.05" value="${S.keepAt}" aria-label="Keep at least">
    <span class="rl" id="jl" style="left:${S.junkAt * 100}%">Junk below ${S.junkAt.toFixed(2)}</span><span class="rl b" id="kl" style="left:${S.keepAt * 100}%">Keep at least ${S.keepAt.toFixed(2)}</span></div>
    <p class="hint" style="margin-top:36px">${D.pilot.total} screenshots: ${S.counts.keep} keep, ${S.counts.review} to review, ${S.counts.junk} junk. A body found in the crop also counts towards keep.</p></div>
  <div class="tabbar" id="tabbar" role="tablist">${Object.entries(PM).map(([k, [l, c]]) => `<button role="tab" class="${c}" data-tri="${k}" aria-selected="${S.tri === k}">${l}<b>${S.counts[k]}</b></button>`).join("")}</div><div id="triv">${triView()}</div>`;

/* ---------- fetch ---------- */
PAGE_fetch = () => `<div class="frame-wrap"><iframe title="Links tool" src="http://127.0.0.1:8791"></iframe></div>`;
const PAGE = { find: PAGE_find, library: PAGE_library, videos: PAGE_videos, triage: PAGE_triage, fetch: PAGE_fetch };

/* ---------- popovers ---------- */
function pop(anchor, html, cls = "") {
  const L = $("#pop"); L.hidden = false; L.innerHTML = `<div class="pop ${cls}" role="dialog">${html}</div>`;
  const p = $(".pop", L), r = anchor.getBoundingClientRect();
  p.style.top = Math.min(r.bottom + 6, innerHeight - 120) + "px"; p.style.left = Math.max(12, Math.min(r.left, innerWidth - p.offsetWidth - 12)) + "px";
  L.onmousedown = (e) => { if (e.target === L) closePop(); };
  anchor.setAttribute("aria-expanded", "true"); L._a = anchor; return p;
}
function closePop() { const L = $("#pop"); if (L._a) L._a.setAttribute("aria-expanded", "false"); L.hidden = true; L.innerHTML = ""; L._a = null; }
function refreshFind() { const t = $("#tokens"); if (!t) return; t.innerHTML = S.accounts.map((a) => `<button class="tok" data-rm="${esc(a.handle)}" title="Remove">${a.cover ? `<img alt="" src="${a.cover}">` : ""}@${esc(a.handle)}${ic("x")}</button>`).join(""); $("#p-acc").innerHTML = `Accounts <b>${S.accounts.length}</b>${ic("chev")}`; $("#p-sig").innerHTML = `Search by <b>${{ text: "scene text", ref: "reference", pose: "pose" }[S.signal]}</b>${ic("chev")}`; $("#p-tag").innerHTML = `Must match <b>${S.tags.size + (S.videoOnly ? 1 : 0)}</b>${ic("chev")}`; $("#p-opt").innerHTML = `<span>${sumText()}</span>${ic("chev")}`; }
function accPop(a) {
  const list = D.accounts.filter((x) => x.built && x.posts);
  const p = pop(a, `<input type="search" id="aq" placeholder="Filter accounts" autofocus><div class="pop-grid" id="al">${list.map((x) => `<button class="pick-row" data-a="${esc(x.handle)}" aria-pressed="${S.accounts.some((y) => y.handle === x.handle)}">${x.cover ? `<img alt="" loading="lazy" src="${x.cover}">` : '<span class="ph"></span>'}<span><b>@${esc(x.handle)}</b> <span class="mute mono">${x.posts}</span></span><span class="chk">${ic("check")}</span></button>`).join("")}</div><div class="row spread"><button class="btn sm ghost" id="prep">Prepare indexes…</button><span class="hint">None chosen = every indexed account</span></div>`);
  $("#aq", p).oninput = (e) => $$(".pick-row", p).forEach((r) => r.hidden = !r.dataset.a.includes(e.target.value.toLowerCase()));
  $("#al", p).onclick = (e) => { const b = e.target.closest("[data-a]"); if (!b) return; const h = b.dataset.a, i = S.accounts.findIndex((x) => x.handle === h); i >= 0 ? S.accounts.splice(i, 1) : S.accounts.push(D.accounts.find((x) => x.handle === h)); b.setAttribute("aria-pressed", i < 0); refreshFind(); };
  $("#prep", p).onclick = () => { closePop(); openPrepare(); };
}
function sigPop(a) {
  const p = pop(a, `<div class="seg" id="sg" role="tablist" aria-label="Search by">${[["text", "Scene text"], ["ref", "Reference"], ["pose", "Pose"]].map(([k, l]) => `<button role="tab" data-k="${k}" aria-selected="${S.signal === k}">${l}</button>`).join("")}</div>
    <div id="sgb">${sigBody()}</div>`);
  const body = () => { $("#sgb", p).innerHTML = sigBody(); };
  $("#sg", p).onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.signal = b.dataset.k; $$("#sg button", p).forEach((x) => x.setAttribute("aria-selected", x === b)); body(); refreshFind(); };
}
function sigBody() {
  if (S.signal === "ref") return `<div style="border:2px dashed var(--rule-2);padding:26px;text-align:center;color:var(--mute)">Drop a reference image here, or <b style="color:var(--ink)">choose a file</b><br><span class="hint">The search ranks frames by how close they are to it.</span></div><label class="field"><span>How much the reference counts</span><input type="range" min="0" max="100" value="60"></label><button class="btn sm" style="width:fit-content">${ic("text")}Describe this image</button>`;
  if (S.signal === "pose") return `<p class="hint">Pick a pose from your own library.</p><div class="row" style="gap:6px">${(D.tagGroups.pose || []).map((n) => `<button class="tag">${esc(n)}</button>`).join("")}</div>`;
  return '<p class="hint">Describe the scene in the bar above. Everything is ranked against your words.</p>';
}
function tagPop(a) {
  const p = pop(a, `<button class="tag ${S.videoOnly ? "on" : ""}" id="v100" style="width:fit-content">100% videos</button><div class="tg">${Object.entries(D.tagGroups).map(([g, v]) => `<div><span class="lbl">${esc(g)}</span><div class="row" style="gap:5px;margin-top:6px">${v.map((n) => `<button class="tag ${S.tags.has(g + ":" + n) ? "on" : ""}" data-tag="${esc(g + ":" + n)}">${esc(n)}</button>`).join("")}</div></div>`).join("")}</div><p class="hint">Tags are optional. Edit them in labels.json.</p>`, "wide");
  $("#v100", p).onclick = (e) => { S.videoOnly = !S.videoOnly; e.currentTarget.classList.toggle("on", S.videoOnly); refreshFind(); };
  p.onclick = (e) => { const b = e.target.closest("[data-tag]"); if (!b) return; const k = b.dataset.tag; S.tags.has(k) ? S.tags.delete(k) : S.tags.add(k); b.classList.toggle("on"); refreshFind(); };
}
function optPop(a) {
  const seg = (k, vals) => `<div class="seg" data-s="${k}" role="tablist">${vals.map((v) => `<button role="tab" aria-selected="${S[k] === v}">${v}</button>`).join("")}</div>`;
  const p = pop(a, `<label class="field"><span>Results as</span>${seg("mode", ["Instant thumbs", "Save full size", "Links"])}</label><label class="field"><span>Rank</span>${seg("rank", ["Best", "Worst"])}</label>
    <div class="row"><label class="field"><span>Posts</span><input class="n" type="number" id="posts" min="1" max="1000" value="${S.posts}"></label><button class="tag ${S.every ? "on" : ""}" id="every" style="margin-top:20px" title="Take every post carrying the chosen tags, instead of a random handful">Everything matching</button></div>
    <label class="field"><span>Several accounts</span>${seg("mix", ["Each", "Pool", "Even"])}</label><p class="hint">An empty query draws at random from the indexed posts. Scores are similarities, not proof.</p>`);
  $$(".seg", p).forEach((g) => g.onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S[g.dataset.s] = b.textContent; $$("button", g).forEach((x) => x.setAttribute("aria-selected", x === b)); refreshFind(); });
  $("#posts", p).oninput = (e) => { S.posts = +e.target.value || 1; refreshFind(); };
  $("#every", p).onclick = (e) => { S.every = !S.every; e.currentTarget.classList.toggle("on", S.every); };
}
function runPop(a) {
  const p = pop(a, `<label class="field"><span>How many random screenshots</span><input class="n" type="number" value="400" min="10" max="2000"></label><p class="hint">Crops the likely photo out of each screenshot and scores it. Nothing in the Photos library is changed or copied.</p><button class="btn pri" data-x="1" style="min-height:40px">Run the pilot</button>`);
  $("[data-x]", p).onclick = () => { closePop(); toast("Layout preview: the pilot is not started here"); };
}

/* ---------- dialogs and sheets ---------- */
function sheet(html, center) { const L = $("#sheet"); L.className = "sheet-layer" + (center ? " center" : ""); L.hidden = false; L.innerHTML = html; L.onmousedown = (e) => { if (e.target === L) closeSheet(); }; $$("[data-close]", L).forEach((b) => b.onclick = closeSheet); return L; }
function closeSheet() { const L = $("#sheet"); L.hidden = true; L.innerHTML = ""; }
const X = `<button class="ibtn" data-close aria-label="Close">${ic("x")}</button>`;
function openSources() {
  const L = sheet(`<div class="sheet" role="dialog" aria-label="Sources"><div class="sheet-h"><h2>Sources</h2>${X}</div><div class="sheet-b">
    <div class="row"><button class="btn sm" id="imp">${ic("plus")}Import image folder</button><button class="btn sm ghost">Import all new</button><button class="btn sm ghost" id="sp">Prepare indexes</button><span class="grow"></span><div class="seg" id="st" role="tablist">${[["accounts", "Accounts"], ["video", "Video folders"]].map(([k, l]) => `<button role="tab" data-k="${k}" aria-selected="${S.srcTab === k}">${l}</button>`).join("")}</div></div>
    <div id="sb">${srcBody()}</div></div></div>`);
  $("#st", L).onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.srcTab = b.dataset.k; $$("#st button", L).forEach((x) => x.setAttribute("aria-selected", x === b)); $("#sb", L).innerHTML = srcBody(); bindSrc(L); };
  $("#imp", L).onclick = openImport; $("#sp", L).onclick = openPrepare; bindSrc(L);
}
function bindSrc(L) { const a = $("#auto", L); if (a) a.onclick = () => { S.autoImport = !S.autoImport; a.setAttribute("aria-pressed", S.autoImport); }; }
function srcBody() {
  if (S.srcTab === "video") return `<table class="tbl"><thead><tr><th>Folder</th><th class="num">Videos</th><th class="num">Frames</th><th>Index</th><th></th></tr></thead><tbody>${D.watch.filter((w) => w.count || w.attached).map((w) => `<tr><td><div class="who">${w.videos[0] ? `<img alt="" loading="lazy" src="${w.videos[0].poster}">` : '<span class="ph"></span>'}@${esc(w.name)}</div></td><td class="num">${w.count}</td><td class="num">${nf(w.frames)}</td><td><span class="dotc ${w.todo ? "warn" : "ok"}"></span>${w.todo ? mmss(w.todo) + " to index" : "Up to date"}</td><td><button class="btn sm ghost">Index</button></td></tr>`).join("")}</tbody></table>
    <div class="row"><button class="btn sm">${ic("plus")}Add folder</button><button class="btn sm ghost">Discover folders</button><button class="btn sm ghost">Rescan all</button><button class="btn sm ghost">${ic("play")}Random video</button></div>`;
  const todo = D.accounts.filter((a) => a.toOpen > 0)[0];
  return `${todo ? `<div class="sect"><div class="spread"><b>Index every image · @${esc(todo.handle)}</b><span class="mono">${todo.opened} of ${todo.opened + todo.toOpen} carousel posts opened</span></div><div class="mini-bar"><i style="width:${(todo.opened / (todo.opened + todo.toOpen)) * 100}%"></i></div><p class="hint">Opens every carousel so each slide can be found by search. Progress is saved after every post, so you can stop any time.</p>
      <div class="row"><label class="row hint">Open at most <input class="n" type="number" value="10" min="5" max="2000"> posts</label><label class="row hint">Windows <select style="width:64px"><option>1</option><option>2</option><option>3</option><option>4</option></select></label><button class="tag">Keep going until done</button><button class="btn sm pri" style="min-height:32px;padding:0 14px;font-size:13.5px">Open carousels</button></div></div>` : ""}
    <table class="tbl"><thead><tr><th>Account</th><th class="num">Posts</th><th class="num">Videos</th><th>Index</th><th></th></tr></thead><tbody>${D.accounts.filter((a) => a.posts || a.videos).map((a) => { const st = !a.built ? ["bad", "Not indexed"] : a.toOpen ? ["warn", a.toOpen + " carousels to open"] : ["ok", "Up to date"]; return `<tr><td><div class="who">${a.cover ? `<img alt="" loading="lazy" src="${a.cover}">` : '<span class="ph"></span>'}<span>@${esc(a.handle)}<br><span class="mute" style="font-weight:500;font-size:12.5px">${{ instagram: "Instagram", local: "Local folder", videos: "Videos" }[a.kind]}</span></span></div></td><td class="num">${nf(a.posts)}</td><td class="num">${nf(a.videos)}</td><td><span class="dotc ${st[0]}"></span>${st[1]}</td><td><div class="row" style="flex-wrap:nowrap"><button class="btn sm ghost">Import new</button><button class="btn sm ghost">Finder</button></div></td></tr>`; }).join("")}</tbody></table>
    <button class="sw" id="auto" aria-pressed="${S.autoImport}"><span class="trk"></span><span><strong>Check for new files when Postroom opens and import them automatically</strong><small>Files are imported only once they've finished copying (about 30 seconds after they last changed). Your files are only read. Local files have no Instagram date, so a date filter on Find hides them.</small></span></button>`;
}
function openPrepare() { sheet(`<div class="dlg" role="dialog" aria-label="Prepare"><div class="dlg-h"><h2>Build the index first</h2>${X}</div><div class="dlg-b"><p class="hint">Reads each account once so searches are instant. Safe to stop and resume.</p><label class="field"><span>Accounts</span><input type="text" placeholder="username, another_username"></label><div class="row" style="gap:6px">${D.accounts.filter((a) => !a.built).slice(0, 10).map((a) => `<button class="tag">@${esc(a.handle)}</button>`).join("")}</div><label class="field"><span>Model</span><select><option>CLIP</option><option>SigLIP</option></select></label><button class="btn pri" data-close>Build the index</button></div></div>`, true); }
function openImport() { sheet(`<div class="dlg" role="dialog" aria-label="Import"><div class="dlg-h"><h2>Import a folder of images</h2>${X}</div><div class="dlg-b"><label class="field"><span>Name</span><input type="text" placeholder="Reference pulls"></label><label class="field"><span>Folder</span><input type="text" placeholder="/Users/you/Pictures/pulls"></label><button class="btn pri" data-close>Import</button></div></div>`, true); }
function openRefine() {
  const yr = new Date().getFullYear(), tg = "onclick=\"this.setAttribute('aria-pressed',this.getAttribute('aria-pressed')!=='true')\"";
  const L = sheet(`<div class="sheet" style="width:min(520px,100vw)" role="dialog" aria-label="Refine"><div class="sheet-h"><h2>Refine</h2>${X}</div><div class="sheet-b">
    <p class="hint">The main bar stays a query. Dates, videos, carousels and the cache live here.</p>
    <div class="sect"><span class="lbl">When</span><div class="row" style="gap:6px">${["Any", "Last 90 days", yr, yr - 1, yr - 2].map((x) => `<button class="tag">${x}</button>`).join("")}</div><div class="row"><label class="field grow"><span>From</span><input type="date"></label><label class="field grow"><span>Until (not included)</span><input type="date"></label></div><p class="hint">Images imported from a folder or video have no date and are left out while a date is set.</p></div>
    <div class="sect"><span class="lbl">Videos</span><button class="sw" aria-pressed="false" ${tg}><span class="trk"></span><span><strong>Allow reels and videos</strong><small>Off by default, so a photo search stays a photo search.</small></span></button>
      <button class="sw" aria-pressed="false" ${tg}><span class="trk"></span><span><strong>With a search, still mix in videos from watched folders</strong><small>Random videos from the folders you picked are added alongside the matching photos.</small></span></button>
      <button class="sw" aria-pressed="false" ${tg}><span class="trk"></span><span><strong>Choose the mix of videos and photos</strong><small>The number of posts becomes the total across everything you picked.</small></span></button>
      <label class="field"><span>Videos in the results · 50%</span><input type="range" min="0" max="100" step="10" value="50"></label>
      <label class="field"><span>Video clip length</span><select>${Object.keys(D.clipLengths).map((k) => `<option>${esc(k)}</option>`).join("")}</select></label></div>
    <div class="sect"><span class="lbl">Carousels</span><div class="seg" role="tablist"><button role="tab" aria-selected="true">First photo only</button><button role="tab" aria-selected="false">Save every slide</button></div><label class="field"><span>Look inside the N most promising carousels · off</span><input type="number" min="0" max="200" value="0"></label></div>
    <div class="sect"><span class="lbl">Matches and cache</span><label class="field"><span>Choose randomly among the top 20 matches (with a search)</span><input type="number" min="1" max="500" value="20"></label><div class="seg" role="tablist"><button role="tab" aria-selected="true">Saved</button><button role="tab" aria-selected="false">Check for new posts</button><button role="tab" aria-selected="false">Rebuild (slow)</button></div><label class="field"><span>Save folder (for "Save full size")</span><input type="text" value="~/instagram-bot-2/picks"></label></div>
    <button class="btn pri" data-close>Find with these</button></div></div>`);
  $$(".seg", L).forEach((g) => g.onclick = (e) => { const b = e.target.closest("button"); if (b) $$("button", g).forEach((x) => x.setAttribute("aria-selected", x === b)); });
}
function openSlides() {
  const f = S.lb.filter((x) => !x.video).slice(0, 10); let i = 0;
  const L = sheet(`<div class="dlg" style="width:min(760px,96vw)" role="dialog" aria-label="Slideshow"><div class="dlg-h"><h2>Slideshow</h2>${X}</div><div class="dlg-b"><div style="background:#0b0c0d;padding:12px"><img id="sl" alt="" style="width:100%;max-height:56vh;object-fit:contain;display:block" src="${f[0].thumb}"></div><div class="spread"><button class="btn" id="sp">${ic("left")}Previous</button><span class="mono" id="sc">1 / ${f.length}</span><button class="btn pri" id="sn" style="min-height:38px">Next${ic("right")}</button></div></div></div>`, true);
  const show = () => { $("#sl", L).src = f[i].thumb; $("#sc", L).textContent = `${i + 1} / ${f.length}`; };
  $("#sn", L).onclick = () => { i = (i + 1) % f.length; show(); }; $("#sp", L).onclick = () => { i = (i - 1 + f.length) % f.length; show(); };
}
function openVideo(v) {
  if (!v) return; const [cls, lab] = vStat(v);
  sheet(`<div class="dlg" style="width:min(720px,96vw)" role="dialog" aria-label="Review video"><div class="dlg-h"><div><h2>${esc(v.title)}</h2><p class="hint">${esc(v.creator)} · ${mmss(v.dur)} · ${lab}</p></div>${X}</div><div class="dlg-b">
    <div><div class="tl">${v.timeline.map((t) => `<i style="flex:${Math.max(0.5, t[2] - t[1])};background:${colourOf(t[0])}"></i>`).join("")}</div><div class="tl-t"><span>0:00</span><span>${mmss(v.dur)}</span></div></div>
    <table class="tbl"><tbody>${v.timeline.map((t) => `<tr><td><span class="dotc" style="background:${colourOf(t[0])}"></span>${esc(t[0].replace(/_/g, " "))}</td><td class="num">${mmss(t[1])} to ${mmss(t[2])}</td></tr>`).join("")}</tbody></table>
    <div class="row"><button class="btn pri" data-close>Mark as verified</button><button class="btn">Edit sections</button><button class="btn">${ic("play")}Play</button><button class="btn">Re-run</button></div></div></div>`, true);
}
function openStatus() {
  const s = D.storage, pct = (b) => (b / s.total) * 100;
  sheet(`<div class="dlg" role="dialog" aria-label="Storage and session"><div class="dlg-h"><h2>This desk</h2>${X}</div><div class="dlg-b">
    <div class="sect"><div class="spread"><b>Instagram session</b><span class="row"><span class="dotc ${D.session.loggedIn ? "ok" : "bad"}"></span>${D.session.loggedIn ? "Session saved" : "Not logged in"}</span></div><p class="hint">Saved in auth.json. Checking and rebuilding indexes need a valid login.</p><div class="row"><button class="btn sm">Check the session</button><button class="btn sm pri" style="min-height:32px;font-size:13.5px;padding:0 14px">Log in again</button></div></div>
    <div class="sect"><div class="spread"><b>Storage on this Mac</b><span class="mono">${gb(s.free)} free of ${gb(s.total)}</span></div><div class="meter" style="height:12px;border:1px solid var(--ink)"><i style="width:${pct(s.mine)}%;background:var(--pick)"></i><i style="width:${pct(s.used - s.mine)}%;background:var(--rule-2)"></i></div><p class="hint">Postroom uses ${gb(s.mine)}.</p>
      ${s.biggest.slice(0, 6).map((b) => `<button class="fct"><span>${esc(b.name.length > 52 ? b.name.slice(0, 52) + "…" : b.name)}</span><em>${gb(b.bytes)}</em></button>`).join("")}<button class="btn sm ghost" style="width:fit-content">Recalculate</button></div></div></div>`, true);
}
function openActivity(a) {
  const run = D.jobs.filter((j) => j.running).length;
  const p = pop(a, `<div class="act-h"><div><b>Activity</b><p class="hint">${run ? run + " running" : "Nothing running"} · ${D.jobs.length - run} finished · video analysis ${D.analysis.enabled ? "automatic" : "off"}</p></div><button class="btn sm ghost" id="cj">Dismiss finished</button></div>
    <div style="max-height:min(60vh,520px);overflow:auto">${D.jobs.map((j, i) => { const dd = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(j.started).setHours(0, 0, 0, 0)) / 864e5); const when = dd <= 0 ? "today" : dd === 1 ? "yesterday" : new Date(j.started).toLocaleDateString("en-GB", { day: "numeric", month: "short" }); const open = S.jobOpen === i; return `<div class="job"><button class="job-main" data-j="${i}" aria-expanded="${open}"><span class="mk ${j.running ? "busy" : j.status === "done" ? "" : "bad"}"></span><span><span class="job-t">${esc(j.title.split(/ (?=\()/)[0])}</span><span class="job-s" style="display:block">${when} ${hhmm(j.started)} · ${esc(j.kind)} · pid ${j.pid}</span></span><span class="mono mute">${j.running ? Math.round(j.progress) + "%" : "done"}</span></button>${open ? `<pre class="job-log">${esc(j.log.join("\n"))}</pre><div class="job-x">${j.running ? '<button class="btn sm danger">Stop</button>' : `<button class="btn sm ghost" data-dis="${i}">Dismiss</button>`}<button class="btn sm ghost">Open full log</button></div>` : ""}</div>`; }).join("")}</div>`, "act-panel");
  p.style.top = ""; p.style.left = "";
  p.onclick = (e) => { const b = e.target.closest("[data-j]"); if (b) { S.jobOpen = S.jobOpen === +b.dataset.j ? null : +b.dataset.j; closePop(); openActivity(a); return; } const d = e.target.closest("[data-dis]"); if (d) { D.jobs.splice(+d.dataset.dis, 1); S.jobOpen = null; closePop(); drawTop(); openActivity(a); } };
  $("#cj", p).onclick = () => { for (let i = D.jobs.length - 1; i >= 0; i--) if (!D.jobs[i].running) D.jobs.splice(i, 1); S.jobOpen = null; closePop(); drawTop(); toast("Finished jobs dismissed"); };
}
const COMMANDS = [
  ...PAGES.map(([id, l]) => ({ l: "Go to " + l.toLowerCase(), h: "Page", run: () => go(id) })),
  { l: "Open sources", h: "Accounts, folders, imports", run: () => { go("library"); openSources(); } },
  { l: "Open video folders", h: "Sources", run: () => { S.srcTab = "video"; go("library"); openSources(); } },
  { l: "Find clips by position", h: "Videos", run: () => go("videos") },
  { l: "Open the Lightbox", h: "Saved frames", run: () => { S.lbOpen = true; applyLb(); } },
  { l: "Prepare an account", h: "Index up front", run: openPrepare },
  { l: "Open refine", h: "Dates, cache, video", run: () => { go("find"); openRefine(); } },
  { l: "Switch search model", h: "Separate indexes", run: () => { S.model = S.model === "clip" ? "siglip" : "clip"; drawTop(); } },
  { l: "Session, login and storage", h: "auth.json", run: openStatus },
  { l: "Show activity", h: "Jobs", run: () => openActivity($("#open-act")) },
  { l: "Draw random posts", h: "Ignore the query once", run: () => { go("find"); $("#draw").click(); } },
];
function openPalette() {
  const L = sheet(`<div class="pal" role="dialog" aria-label="Go to"><input id="pq" type="text" placeholder="Go to a page, or run a command…" autocomplete="off"><div id="pl"></div></div>`, true);
  let sel = 0, shown = COMMANDS;
  const draw = () => { $("#pl", L).innerHTML = shown.map((c, i) => `<button class="pal-i" data-i="${i}" aria-selected="${i === sel}"><span>${esc(c.l)}</span><small>${esc(c.h)}</small></button>`).join(""); };
  draw(); $("#pq", L).focus();
  $("#pq", L).oninput = (e) => { const q = e.target.value.toLowerCase(); shown = COMMANDS.filter((c) => (c.l + c.h).toLowerCase().includes(q)); sel = 0; draw(); };
  $("#pl", L).onclick = (e) => { const b = e.target.closest("[data-i]"); if (b) { closeSheet(); shown[+b.dataset.i].run(); } };
  $("#pq", L).onkeydown = (e) => { if (e.key === "ArrowDown") { sel = Math.min(shown.length - 1, sel + 1); draw(); e.preventDefault(); } if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); } if (e.key === "Enter" && shown[sel]) { closeSheet(); shown[sel].run(); } };
}
function toast(t) { const e = document.createElement("div"); e.className = "toast"; e.textContent = t; document.body.appendChild(e); setTimeout(() => e.remove(), 2200); }

/* ---------- page wiring ---------- */
function bind(id) {
  const P = $("#page");
  if (id === "find") {
    $("#query").oninput = (e) => S.query = e.target.value;
    $("#query").onkeydown = (e) => { if (e.key === "Enter") $("#draw").click(); };
    $("#draw").onclick = () => { $("#results").innerHTML = contact(); bindFrames(); toast("Layout preview: no search is run in this prototype"); };
    $("#tokens").onclick = (e) => { const b = e.target.closest("[data-rm]"); if (!b) return; S.accounts = S.accounts.filter((a) => a.handle !== b.dataset.rm); refreshFind(); };
    $("#p-acc").onclick = (e) => accPop(e.currentTarget); $("#p-sig").onclick = (e) => sigPop(e.currentTarget); $("#p-tag").onclick = (e) => tagPop(e.currentTarget); $("#p-opt").onclick = (e) => optPop(e.currentTarget);
    $("#refine").onclick = openRefine;
    $$("[data-sugg]", P).forEach((b) => b.onclick = () => { $("#query").value = S.query = b.dataset.sugg; $("#query").focus(); });
    bindFrames();
  }
  if (id === "library") {
    $("#open-src").onclick = openSources; $("#second").onclick = () => { S.second = true; toast("Now click a tag from another group"); }; $("#lib-prep").onclick = openPrepare;
    $("#scope").onchange = (e) => S.scope = e.target.value;
    $("#conf").oninput = (e) => { S.conf = +e.target.value; $("#confv").textContent = S.conf.toFixed(2); };
    $("#facets").onclick = (e) => { const b = e.target.closest("[data-t]"); if (!b) return; const prev = S.tagSel; S.tagSel = b.dataset.t; if (prev && prev.split(":")[0] !== b.dataset.t.split(":")[0] && S.second) { S.second = false; sheet(`<div class="dlg" role="dialog" aria-label="Second tag"><div class="dlg-h"><h2>Two tags from different groups</h2>${X}</div><div class="dlg-b"><p class="hint">Show <b>${esc(b.dataset.t.split(":")[1])}</b> on its own, or only images that carry both <b>${esc(prev.split(":")[1])}</b> and <b>${esc(b.dataset.t.split(":")[1])}</b>?</p><div class="row"><button class="btn pri" data-close>Require both</button><button class="btn" data-close>Show it alone</button></div></div></div>`, true); } $$("[data-t]", P).forEach((x) => x.setAttribute("aria-pressed", x.dataset.t === S.tagSel)); $("#wall").innerHTML = libraryWall(); };
  }
  if (id === "videos") {
    $$("[data-vf]", P).forEach((b) => b.onclick = () => { S.vFilter = b.dataset.vf; go("videos"); });
    $("#vq").onchange = (e) => { S.vQuery = e.target.value; go("videos"); }; $("#vs").onchange = (e) => { S.vSort = e.target.value; go("videos"); };
    $("#poscol").onclick = (e) => { const b = e.target.closest("[data-pos]"); if (!b) return; S.pos = b.dataset.pos; go("videos"); };
    $("#analyse-all").onclick = () => toast("Layout preview: analysis jobs are not started here"); $("#sel-all").onclick = () => { $$("[data-vs]", P).forEach((c) => c.checked = true); toast("All shown videos selected"); }; $("#rerun-sel").onclick = () => toast(`Layout preview: ${$$("[data-vs]:checked", P).length} selected, nothing is run here`);
    $("#vrows").onclick = (e) => { const b = e.target.closest("[data-rv]"); if (b) openVideo(S.vlist[+b.dataset.rv]); };
    const v = $("#vonly"); if (v) { v.onclick = () => { S.verifiedOnly = !S.verifiedOnly; go("videos"); }; $("#cl").onchange = (e) => { S.clipLen = e.target.value; $("#vrows").innerHTML = vRows(); }; $("#c2").oninput = (e) => S.conf2 = +e.target.value; $$("[data-act=slides]", P).forEach((b) => b.onclick = openSlides); }
  }
  if (id === "triage") {
    $("#p-run").onclick = (e) => runPop(e.currentTarget);
    $("#whole").onclick = (e) => { S.whole = !S.whole; e.currentTarget.setAttribute("aria-pressed", S.whole); };
    const upd = () => { $("#jl").style.left = S.junkAt * 100 + "%"; $("#kl").style.left = S.keepAt * 100 + "%"; $("#jl").textContent = "Junk below " + S.junkAt.toFixed(2); $("#kl").textContent = "Keep at least " + S.keepAt.toFixed(2); const z = $$(".zones i"); z[0].style.flex = S.junkAt; z[1].style.flex = S.keepAt - S.junkAt; z[2].style.flex = 1 - S.keepAt; };
    $("#junk").oninput = (e) => { S.junkAt = Math.min(+e.target.value, S.keepAt - 0.05); e.target.value = S.junkAt; upd(); };
    $("#keep").oninput = (e) => { S.keepAt = Math.max(+e.target.value, S.junkAt + 0.05); e.target.value = S.keepAt; upd(); };
    $("#tabbar").onclick = (e) => { const b = e.target.closest("[data-tri]"); if (!b) return; S.tri = b.dataset.tri; S.ti = 0; go("triage"); };
    bindTri();
  }
}
function bindTri() {
  const v = $("#triv"); if (!v) return;
  const f = $("#film"); if (f) f.onclick = (e) => { const b = e.target.closest("[data-fi]"); if (!b) return; S.ti = +b.dataset.fi; refreshTri(); };
  const d = $("#decide"); if (d) d.onclick = (e) => { const b = e.target.closest("[data-d]"); if (b) decide(b.dataset.d); };
  const pr = $("#tprev"), nx = $("#tnext"); if (pr) pr.onclick = () => step(-1); if (nx) nx.onclick = () => step(1);
  const u = $("#undo"); if (u) u.onclick = undo;
}
function refreshTri() { $("#triv").innerHTML = triView(); bindTri(); $$("#tabbar b").forEach((b, i) => b.textContent = S.counts[Object.keys(PM)[i]]); }
function step(n) { const len = S.piles[S.tri].length; S.ti = (S.ti + n + len) % len; refreshTri(); }
function decide(to) {
  const from = S.tri; if (to === from) return; const [it] = S.piles[from].splice(S.ti, 1); S.piles[to].unshift(it); S.counts[from]--; S.counts[to]++; S.lastMove = { from, to, i: S.ti, it };
  S.ti = Math.min(S.ti, Math.max(0, S.piles[from].length - 1)); refreshTri();
}
function undo() { const m = S.lastMove; if (!m) return; const j = S.piles[m.to].indexOf(m.it); S.piles[m.to].splice(j, 1); S.piles[m.from].splice(m.i, 0, m.it); S.counts[m.to]--; S.counts[m.from]++; S.lastMove = null; S.ti = m.i; refreshTri(); }
function bindFrames() {
  $$("[data-pick]", $("#page")).forEach((b) => b.onclick = () => {
    const k = b.dataset.pick, fr = b.closest(".fr"), items = D.favs.slice(8, 32), f = items[+k.slice(1)];
    if (S.picked.has(k)) { S.picked.delete(k); fr.classList.remove("picked", "static"); S.lb = S.lb.filter((x) => x.key !== k); }
    else { S.picked.add(k); fr.classList.add("picked"); S.lb.unshift({ ...f, key: k }); }
    b.setAttribute("aria-pressed", S.picked.has(k)); drawTop(); drawLb();
  });
  $$("[data-act=slides]", $("#page")).forEach((b) => b.onclick = openSlides);
  const ca = $("#circle-all"); if (ca) ca.onclick = () => $$("[data-pick]").forEach((b) => { if (b.getAttribute("aria-pressed") !== "true") b.click(); });
}

/* ---------- boot ---------- */
document.addEventListener("click", (e) => { const g = e.target.closest("[data-go]"); if (g) { closePop(); go(g.dataset.go); } });
$("#model").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.model = b.dataset.m; drawTop(); };
$("#cmd").onclick = openPalette; $("#open-status").onclick = openStatus;
$("#open-act").onclick = (e) => { $("#pop").hidden ? openActivity(e.currentTarget) : closePop(); };
$("#open-lb").onclick = () => { S.lbOpen = !lbVisible(); applyLb(); };
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); }
  else if (e.key === "Escape") { closeSheet(); closePop(); }
  else if (e.key === "/" && !typing) { e.preventDefault(); go("find"); setTimeout(() => $("#query") && $("#query").focus(), 30); }
  else if (S.page === "triage" && !typing && $("#decide") && !e.metaKey && !e.ctrlKey && !e.altKey) {
    const k = e.key.toLowerCase();
    if (k === "k") decide("keep"); else if (k === "r") decide("review"); else if (k === "j") decide("junk");
    else if (e.key === "ArrowRight") step(1); else if (e.key === "ArrowLeft") step(-1);
  }
});
go(PAGES.some((p) => p[0] === location.hash.slice(1)) ? location.hash.slice(1) : "find");
})();
