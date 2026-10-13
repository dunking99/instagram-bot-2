/* Design A · Departures: renders every page from window.DATA (real snapshot of the running app). */
(() => {
const D = window.DATA;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf = (n) => Number(n).toLocaleString("en-GB");
const gb = (b) => (b / 1e9).toFixed(1) + " GB";
const mmss = (s) => { s = Math.round(s); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
const hhmm = (ms) => new Date(ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
const ICON = {
  star: '<path d="M12 3.5l2.6 5.5 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6L3.4 9.8l6-.8z"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5"/>',
  chev: '<path d="M6 9l6 6 6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  play: '<path d="M8 5l11 7-11 7z"/>',
  folder: '<path d="M3 7h6l2 2h10v10H3z"/>',
  find: '<path d="M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16zM21 21l-4.2-4.2"/>',
  dl: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
  text: '<path d="M5 6h14M12 6v13M9 19h6"/>',
  sliders: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6"/>',
};
const ic = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[n]}</svg>`;
const topName = (n) => n.split(" - ")[0];
const colourOf = (n) => D.colours[topName(n).replace(/ /g, "_")] || "#9aa5b1";
const H = D.host || "this Mac";

/* ---------- state ---------- */
const S = {
  page: "search", model: D.model || "clip",
  accounts: [D.accounts.find((a) => a.handle === "lily-larimar") || D.accounts[2]].filter(Boolean),
  query: "", signal: "text", tags: new Set(), videoOnly: true,
  rank: "Best", posts: 50, every: false, mix: "Pool", mode: "Instant thumbs", optsOpen: false,
  saved: new Set(), savedExtra: 0,
  sourcesTab: "accounts", sel: "kristenhancher", tag: null, tagIdx: false, conf: 0.5, autoImport: D.autoImport,
  vtab: "clips", pos: "Doggystyle", verifiedOnly: false, clipLen: "30 s", conf2: 0.5, only: "",
  rvFilter: "all", rvSort: "attention", rvQuery: "", rvSel: new Set(),
  keepAt: 0.7, junkAt: 0.2, whole: false, boardOpen: true, openJob: null,
  piles: JSON.parse(JSON.stringify(D.pilot.piles)), pileCounts: { ...D.pilot.counts },
};

/* ---------- pages meta ---------- */
const PAGES = [
  { id: "search", label: "Search", title: "Search", sub: "Describe a scene, drop a reference, match a pose, or leave it empty for a random draw." },
  { id: "saved", label: "Saved", title: "Saved", sub: () => `${nf(D.favTotal + S.savedExtra)} starred frames and clips.` },
  { id: "sources", label: "Sources", title: "Sources", sub: () => `${D.accounts.filter((a) => a.posts).length} accounts with images · ${D.watch.length} video folders` },
  { id: "videos", label: "Videos", title: "Videos", sub: () => `${(D.vidCounts.completed || 0) + (D.vidCounts.saved || 0) + (D.vidCounts.outdated || 0)} videos · ${(D.vidCounts.completed || 0) + (D.vidCounts.saved || 0)} verified by you` },
  { id: "sort", label: "Sort", title: "Sort the screenshot pile", sub: "Keep, review or junk. The Photos library is read-only." },
  { id: "fetch", label: "Fetch", title: "Fetch", sub: "Scrape, sort and download links. This is the Links tool, embedded." },
];

/* ---------- shell ---------- */
function drawShell() {
  $("#nav").innerHTML = PAGES.map((p) => `<button class="st" data-go="${p.id}" ${p.id === S.page ? 'aria-current="page"' : ""}><i class="dot"></i><span>${p.label}</span>${p.id === "saved" ? `<b>${D.favTotal + S.savedExtra}</b>` : ""}</button>`).join("");
  const p = PAGES.find((x) => x.id === S.page);
  $("#title").textContent = p.title;
  $("#subtitle").textContent = typeof p.sub === "function" ? p.sub() : p.sub;
  $$("#model button").forEach((b) => b.setAttribute("aria-selected", b.dataset.m === S.model));
  const low = D.storage.free < 5e9;
  $("#open-storage").innerHTML = `<span class="pip"></span>${gb(D.storage.free)} free`;
  $("#open-storage").classList.toggle("warn", low);
  $("#open-session").innerHTML = `<span class="pip"></span>${D.session.loggedIn ? "Logged in" : "Not logged in"}`;
  document.title = `${p.title} · Postroom`;
}

function go(id) {
  S.page = id; drawShell();
  $("#page").innerHTML = PAGE[id]();
  $("#page").scrollTop = 0;
  bind(id);
  try { history.replaceState(null, "", "#" + id); } catch (e) {}
}

/* ---------- route strip ---------- */
function route(timeline, dur, o = {}) {
  const total = dur || (timeline.length ? timeline[timeline.length - 1][2] : 1);
  let html = '<div class="route">', last = 0;
  html += '<i class="stn"></i>';
  timeline.forEach((t, i) => {
    const len = Math.max(0.5, t[2] - t[1]);
    const dim = o.focus && topName(t[0]) !== topName(o.focus) ? " dim" : "";
    html += `<span class="leg${dim}" style="flex:${len};background:${colourOf(t[0])}" title="${esc(t[0])} ${mmss(t[1])}–${mmss(t[2])}"></span>`;
    html += i === timeline.length - 1 ? '<i class="stn end"></i>' : '<i class="stn"></i>';
    last = t[2];
  });
  html += "</div>";
  if (o.times) html += `<div class="route-times"><span>0:00</span><span>${mmss(total)}</span></div>`;
  return html;
}
const key = (names) => `<div class="route-key">${names.map((n) => `<span><i style="background:${colourOf(n)}"></i>${esc(n.replace(/_/g, " "))}</span>`).join("")}</div>`;
const KEY_NAMES = ["Blowjob", "Doggystyle", "Missionary", "Cowgirl", "Reverse_Cowgirl", "Spooning", "Prone", "Handjob", "Titjob", "Foreplay"];

/* ---------- departures board (jobs) ---------- */
function groupJobs() {
  const out = [];
  D.jobs.forEach((j, i) => { const head = j.title.split(/ (?=\()/)[0], last = out[out.length - 1]; if (last && last.head === head && !j.running && !last.j.running) last.n++; else out.push({ j, i, n: 1, head }); });
  return out;
}
function drawBoard() {
  const running = D.jobs.filter((j) => j.running).length;
  const a = D.analysis.status || {};
  $("#board-count").textContent = D.jobs.length;
  $("#board").innerHTML = `
    <div class="board-h"><div class="spread"><h2>Departures</h2><span class="board-clock" id="clock">${new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span></div>
      <p class="board-sub">${running ? `${running} boarding` : "Nothing running"} · ${D.jobs.length - running} departed · video analysis ${D.analysis.enabled ? "automatic" : "off"}</p></div>
    <div class="board-cols lbl"><span>Time</span><span>Job</span><span>Status</span></div>
    <div class="board-list">${groupJobs().map(({ j, i, n }) => {
      const st = j.running ? '<span class="state live">Boarding</span>' : j.status === "done" ? '<span class="state done">Departed</span>' : '<span class="state stop">Failed</span>';
      const open = S.openJob === i; const [head, tail] = j.title.split(/ (?=\()/); const dd = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(j.started).setHours(0, 0, 0, 0)) / 864e5); const day = dd <= 0 ? "today" : dd === 1 ? "yesterday" : new Date(j.started).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
      return `<div class="dep ${j.running ? "live" : ""}"><button class="dep-main" data-job="${i}" aria-expanded="${open}">
        <span class="dep-time">${hhmm(j.started)}</span>
        <span><span class="dep-title">${esc(head)}${n > 1 ? `<span class="dep-n">×${n}</span>` : ""}</span><span class="dep-meta" style="display:block">${day} · ${esc(j.kind)}</span>${j.running ? `<span class="dep-bar" style="display:block"><i style="width:${j.progress}%;display:block"></i></span>` : ""}</span>${st}</button>
        ${open ? `<div class="dep-detail"><pre class="dep-log">${esc(j.log.join("\n"))}</pre><div class="row">${j.running ? '<button class="btn small danger" data-act="stop">Stop</button>' : '<button class="btn small" data-act="dismiss" data-i="' + i + '">Dismiss</button>'}<button class="btn small" data-act="log">Open full log</button></div></div>` : ""}</div>`;
    }).join("")}</div>
    <div class="board-foot"><span class="hint">${D.jobs.length} jobs this session</span><button class="btn small" id="clear-jobs">Dismiss finished</button></div>`;
  $$("[data-job]", $("#board")).forEach((b) => b.onclick = () => { const i = +b.dataset.job; S.openJob = S.openJob === i ? null : i; drawBoard(); });
  $$("[data-act=dismiss]", $("#board")).forEach((b) => b.onclick = () => { D.jobs.splice(+b.dataset.i, 1); S.openJob = null; drawBoard(); });
  $("#clear-jobs").onclick = () => { for (let i = D.jobs.length - 1; i >= 0; i--) if (!D.jobs[i].running) D.jobs.splice(i, 1); S.openJob = null; drawBoard(); toast("Finished jobs dismissed"); };
}

/* ---------- search ---------- */
function summary() { return `${S.rank} · ${S.posts} posts · ${{ Pool: "pooled", Each: "each account", Even: "evenly" }[S.mix]} · ${S.mode.toLowerCase()}`; }
function tagGroupsHtml() {
  return Object.entries(D.tagGroups).map(([g, names]) => `<div class="tag-group"><span class="lbl">${esc(g)}</span><div class="chips">${names.map((n) => `<button class="chip ${S.tags.has(g + ":" + n) ? "on" : ""}" data-tag="${esc(g + ":" + n)}">${esc(n)}</button>`).join("")}</div></div>`).join("");
}
function mustRow() {
  return `<button class="chip ${S.videoOnly ? "on" : ""}" id="vid100">100% videos ${S.videoOnly ? ic("x") : ""}</button>${[...S.tags].map((t) => `<button class="chip on" data-untag="${esc(t)}">${esc(t.split(":")[1])}${ic("x")}</button>`).join("")}<button class="chip ghost" id="tags-t" aria-expanded="${!!S.tagsOpen}">${S.tagsOpen ? "Hide tags" : "+ Add tags"}</button>`;
}
function bindMust() {
  $("#vid100").onclick = () => { S.videoOnly = !S.videoOnly; $("#must-row").innerHTML = mustRow(); bindMust(); };
  $("#tags-t").onclick = () => { S.tagsOpen = !S.tagsOpen; $("#taggroups").hidden = !S.tagsOpen; $("#must-row").innerHTML = mustRow(); bindMust(); };
  $$("[data-untag]").forEach((b) => b.onclick = () => { S.tags.delete(b.dataset.untag); $("#taggroups").innerHTML = tagGroupsHtml(); $("#must-row").innerHTML = mustRow(); bindMust(); });
}
function resultsHtml() {
  const items = D.favs.slice(0, 24);
  return `<div class="results-h"><div><h2>${items.length} frames</h2><p class="preview-note">Layout preview: sample frames from Saved stand in for a real draw.</p></div>
    <div class="row"><button class="btn small" data-act="slides">${ic("play")}Slideshow</button><button class="btn small" data-act="select">Select all</button><button class="btn small" data-act="saveall">${ic("dl")}Save selected full size</button></div></div>
    <div class="wall">${items.map((f, i) => tile(f, i)).join("")}</div>`;
}
function sigPanel() {
  if (S.signal === "ref") return `<div class="ref-panel"><label class="drop" id="drop"><input type="file" accept="image/*,video/*" hidden id="reffile"><b>Drop a reference image here</b><span>or click to choose a file</span></label><div style="display:grid;gap:12px"><p class="hint">Frames are ranked by how close they look to this reference. Combine it with the words above.</p><label class="field"><span>How much the reference counts · 60%</span><input type="range" min="0" max="100" value="60"></label><div class="row"><button class="btn small" id="describe">${ic("text")}Describe this image</button><span class="hint" id="descout"></span></div></div></div>`;
  if (S.signal === "pose") return `<div class="ref-panel"><label class="drop"><input type="file" accept="image/*" hidden><b>Drop a photo with the pose</b><span>or pick one from your library below</span></label><div style="display:grid;gap:8px"><span class="lbl">Pose from your library</span><div class="chips">${(D.tagGroups.pose || []).map((n) => `<button class="chip ${S.pose === n ? "on" : ""}" data-pose="${esc(n)}">${esc(n)}</button>`).join("")}</div></div></div>`;
  return "";
}
function tile(f, i) {
  const on = S.saved.has("r" + i);
  return `<figure class="tile" style="margin:0"><img loading="lazy" alt="" src="${f.thumb}">${f.video ? '<span class="vbadge">Video</span>' : ""}
    <div class="acts"><button class="icon-b star ${on ? "on" : ""}" data-star="r${i}" aria-label="Save to Saved" aria-pressed="${on}">${ic("star")}</button><button class="icon-b" aria-label="Open post">${ic("open")}</button><button class="icon-b" aria-label="Download full size">${ic("dl")}</button><button class="icon-b" aria-label="Show in Finder">${ic("folder")}</button></div>
    <figcaption class="cap"><span>@${esc(f.account)}</span><span>${esc(f.date || "local")}</span></figcaption></figure>`;
}
PAGE_search = () => `
  <section class="panel composer" aria-label="Search">
    <div class="block">
      <div class="spread"><span class="lbl">Accounts</span>
        <div class="row"><button class="btn small" id="pick-acc">${ic("plus")}Choose accounts · ${S.accounts.length}</button><button class="btn small" id="prepare">Prepare indexes</button></div></div>
      <div class="acct-row" id="acct-row">${S.accounts.map((a) => `<button class="chip on" data-rm="${esc(a.handle)}" title="Remove">${a.cover ? `<img alt="" src="${a.cover}">` : ""}@${esc(a.handle)}${ic("x")}</button>`).join("") || '<span class="hint">None chosen: every indexed account.</span>'}</div>
    </div>
    <div class="block">
      <textarea class="query" id="query" rows="2" placeholder="Describe the frame you want… (empty = fully random)">${esc(S.query)}</textarea>
      <div class="signals">
        <div class="seg" role="tablist" aria-label="Search by" id="signal">${[["text", "Scene text"], ["ref", "Reference"], ["pose", "Pose"]].map(([k, l]) => `<button role="tab" data-k="${k}" aria-selected="${S.signal === k}">${l}</button>`).join("")}</div>
        ${["smiling on a beach", "mirror selfie", "red dress, golden hour", "full body walking on a street", "cafe table, seated"].map((s) => `<button class="chip ghost" data-sugg="${esc(s)}">${esc(s)}</button>`).join("")}
      </div><div id="sigpanel">${sigPanel()}</div>
    </div>
    <div class="block">
      <div class="spread"><span class="lbl">Must match</span><span class="hint">Tags are optional · edit them in labels.json</span></div>
      <div class="row" style="margin-top:8px" id="must-row">${mustRow()}</div>
      <div class="tag-groups" id="taggroups" ${S.tagsOpen ? "" : "hidden"}>${tagGroupsHtml()}</div>
    </div>
    <div class="block act-row">
      <button class="opts-sum" id="opts-t" aria-expanded="${S.optsOpen}"><span class="lbl">Options</span><span id="sum">${summary()}</span>${ic("chev")}</button>
      <span class="grow"></span>
      <button class="btn" id="refine">${ic("sliders")}Refine</button>
      <button class="btn primary" id="draw">Draw random</button>
    </div>
    <div class="opts" id="opts" ${S.optsOpen ? "" : "hidden"}>
      <div class="opt"><span class="lbl">Results as</span><div class="seg" role="tablist" data-seg="mode">${["Instant thumbs", "Save full size", "Links"].map((m) => `<button role="tab" aria-selected="${S.mode === m}">${m}</button>`).join("")}</div></div>
      <div class="opt"><span class="lbl">Rank</span><div class="seg" role="tablist" data-seg="rank">${["Best", "Worst"].map((m) => `<button role="tab" aria-selected="${S.rank === m}">${m}</button>`).join("")}</div></div>
      <div class="opt"><span class="lbl">Posts</span><div class="row"><input class="num-sm" type="number" id="posts" min="1" max="1000" value="${S.posts}"><button class="chip ${S.every ? "on" : ""}" id="every" title="Take every post carrying the chosen tags, instead of a random handful">Everything matching</button></div></div>
      <div class="opt"><span class="lbl">Several accounts</span><div class="seg" role="tablist" data-seg="mix">${["Each", "Pool", "Even"].map((m) => `<button role="tab" aria-selected="${S.mix === m}">${m}</button>`).join("")}</div></div>
      <p class="hint" style="flex-basis:100%">An empty query draws at random from the indexed posts. Scores are similarities, not proof.</p>
    </div>
  </section>
  <div id="results">${resultsHtml()}</div>`;

/* ---------- saved ---------- */
function savedItems() {
  const t = S.savedType || "all", a = S.savedAcc || "";
  return D.favs.filter((f) => (t === "all" || (t === "video") === f.video) && (!a || f.account === a));
}
function savedHtml() {
  const items = savedItems();
  return `<div class="wall">${items.map((f, i) => `<figure class="tile" style="margin:0"><img loading="lazy" alt="" src="${f.thumb}">${f.video ? '<span class="vbadge">Video</span>' : ""}
    <div class="acts"><button class="icon-b on" data-unstar="${i}" aria-label="Remove from Saved" aria-pressed="true">${ic("star")}</button><button class="icon-b" aria-label="Open post">${ic("open")}</button><button class="icon-b" aria-label="Show in Finder">${ic("folder")}</button></div>
    <figcaption class="cap"><span>@${esc(f.account)}</span><span>${esc(f.date || "local")}</span></figcaption></figure>`).join("") || '<div class="empty"><h3>Nothing here</h3><p>No saved frames match this filter.</p></div>'}</div>`;
}
PAGE_saved = () => {
  const accs = [...new Set(D.favs.map((f) => f.account))].slice(0, 10);
  return `<div class="spread" style="margin-bottom:16px">
    <div class="row"><div class="seg" role="tablist" aria-label="Type" id="stype">${[["all", "All"], ["photo", "Photos"], ["video", "Videos"]].map(([k, l]) => `<button role="tab" data-k="${k}" aria-selected="${(S.savedType || "all") === k}">${l}</button>`).join("")}</div>
      <button class="chip ${!S.savedAcc ? "on" : ""}" data-sacc="">All accounts</button>${accs.map((a) => `<button class="chip ${S.savedAcc === a ? "on" : ""}" data-sacc="${esc(a)}">@${esc(a)}</button>`).join("")}</div>
    <div class="row"><button class="btn small" data-act="slides">${ic("play")}Slideshow</button><button class="btn small">${ic("dl")}Download all</button><button class="btn small">${ic("folder")}Show in Finder</button></div></div>
    <p class="preview-note" style="margin-bottom:12px">Showing ${savedItems().length} of ${D.favTotal} (snapshot holds the latest ${D.favs.length}).</p>
    <div id="saved-wall">${savedHtml()}</div>`;
};

/* ---------- sources ---------- */
const acctState = (a) => !a.built ? ["stop", "Not indexed"] : a.toOpen > 0 ? ["late", `${a.toOpen} carousels to open`] : ["go", "Up to date"];
const kindLabel = { instagram: "Instagram", local: "Local", videos: "Videos" };
function sourcesHtml() {
  const list = D.accounts.filter((a) => a.posts || a.videos || a.kind !== "videos");
  const a = D.accounts.find((x) => x.handle === S.sel) || list[0];
  const imp = D.imports.find((i) => i.name === a.handle);
  const [cls, label] = acctState(a);
  const tagImgs = D.tagImages;
  const tabs = `<div class="tabs" role="tablist" id="stabs">${[["accounts", "Accounts and tags"], ["video", "Video folders"]].map(([k, l]) => `<button role="tab" data-k="${k}" aria-selected="${S.sourcesTab === k}">${l}</button>`).join("")}
    <span class="tabs-end row"><button class="btn small" id="imp-folder">${ic("plus")}Import image folder</button><button class="btn small">Import all new</button><button class="btn small" id="prepare2">Prepare indexes</button><button class="btn small">Open library</button></span></div>`;
  if (S.sourcesTab === "video") return tabs + videoFolders();
  return tabs + `
  <div class="split">
    <section class="panel"><div class="panel-h"><h2>Accounts</h2><input type="search" id="acc-q" placeholder="Filter accounts" style="max-width:200px"></div>
      <div class="scroll"><table class="table"><thead><tr><th>Account</th><th class="num">Posts</th><th class="num">Videos</th><th>Index</th></tr></thead><tbody id="acc-body">${accRows(list)}</tbody></table></div>
      <div class="panel-b"><button class="toggle" id="auto-imp" aria-pressed="${S.autoImport}"><span class="track"></span><span><strong>Check for new files when Postroom opens and import them automatically</strong><small>Files are imported only once they've finished copying (about 30 seconds after they last changed). Your files are only read.</small></span></button></div></section>
    <section class="panel" id="detail">${detailHtml(a, imp, cls, label)}</section>
  </div>`;
}
function accRows(list) {
  return list.map((a) => { const [c, l] = acctState(a); return `<tr data-acc="${esc(a.handle)}" class="${a.handle === S.sel ? "sel" : ""}"><td><div class="handle">${a.cover ? `<img alt="" loading="lazy" src="${a.cover}">` : '<span class="ph"></span>'}<span>@${esc(a.handle)}<span class="sub-s">${kindLabel[a.kind] || a.kind}</span></span></div></td><td class="num">${nf(a.posts)}</td><td class="num">${nf(a.videos)}</td><td><span class="dotl ${c}"></span>${l}</td></tr>`; }).join("");
}
function detailHtml(a, imp, cls, label) {
  const groups = Object.entries(D.tagCounts).filter(([g, v]) => v.length);
  const max = Math.max(...groups.flatMap(([, v]) => v.map((x) => x[1])));
  return `<div class="panel-h"><h2>@${esc(a.handle)}</h2><div class="row"><button class="btn small">Import new</button><button class="btn small">${ic("folder")}Finder</button><button class="btn small">Prepare</button></div></div>
    <div class="panel-b" style="display:grid;gap:16px">
      <div class="summary" style="margin:0"><div><b>${nf(a.posts)}</b><span>posts</span></div><div><b>${nf(a.videos)}</b><span>videos</span></div><div><b>${nf(a.extra)}</b><span>extra slide photos</span></div></div>
      <p class="hint"><span class="dotl ${cls}"></span>${label} · ${a.prepared ? "prepared " + esc(a.prepared) : "never prepared"} · ${a.models.clip ? "CLIP ready" : "no CLIP index"}${a.models.siglip ? " · SigLIP ready" : ""}${imp ? ` · ${imp.folders} folder` : ""}</p>
      ${imp ? `<p class="mono" style="word-break:break-all;color:var(--dim)">${esc(imp.path)}</p>` : ""}
      <div class="sect"><div class="spread"><span class="lbl">Index every image</span><span class="mono">${a.opened} of ${a.opened + a.toOpen} carousel posts opened</span></div>
        <div class="idx-progress"><i style="width:${a.opened + a.toOpen ? (a.opened / (a.opened + a.toOpen)) * 100 : 100}%"></i></div>
        <p class="hint">Opens every carousel so each slide can be found by search. Progress is saved after every post, so you can stop any time.</p>
        <div class="row"><label class="row hint">Open at most <input class="num-sm" type="number" min="5" max="2000" value="10"> posts</label><label class="row hint">Windows <select style="width:64px"><option>1</option><option>2</option><option>3</option><option>4</option></select></label><button class="chip">Keep going until done</button><button class="btn small primary" ${a.toOpen ? "" : "disabled"}>${a.toOpen ? "Open carousels" : "All opened"}</button></div></div>
      <div class="sect"><div class="spread"><span class="lbl">Tags · ${nf(tagImgsFor(a))} images · CLIP</span><label class="row hint" style="gap:10px">How sure a tag must be · <b id="confv">${S.conf.toFixed(2)}</b><input type="range" id="conf" min="0.3" max="0.95" step="0.05" value="${S.conf}" style="width:120px"></label></div>
        ${groups.map(([g, v]) => `<div><p class="lbl" style="padding:6px 10px">${esc(g)}</p>${v.slice(0, 7).map(([n, c]) => `<button class="facet" data-t="${esc(g + ":" + n)}" aria-pressed="${S.tag === g + ":" + n}"><span>${esc(n)}</span><em>${nf(c)}</em><i class="bar" style="width:${(c / max) * 100}%"></i></button>`).join("")}</div>`).join("")}
        <p class="hint">A second tag from another group asks whether to show it alone or require both. A tag from the same group replaces the first.</p></div>
    </div>`;
}
const tagImgsFor = () => D.tagImages;
function videoFolders() {
  return `<section class="panel"><div class="panel-h"><h2>Video folders</h2><div class="row"><button class="btn small">${ic("plus")}Add folder</button><button class="btn small">Discover folders</button><button class="btn small">Rescan all</button><button class="btn small">${ic("play")}Random video</button></div></div>
    ${D.watch.filter((w) => w.count || w.attached).map((w) => `<div class="watch-row"><div class="posters">${w.videos.slice(0, 3).map((v) => `<img alt="" loading="lazy" src="${v.poster}">`).join("") || '<span class="ph"></span>'}</div>
      <div><div class="handle" style="margin-bottom:2px">@${esc(w.name)}</div><span class="hint">${w.count} video${w.count === 1 ? "" : "s"} · ${nf(w.frames)} frames · ${w.indexed} indexed${w.todo ? ` · ${mmss(w.todo)} still to index` : ""}</span></div>
      <div class="row"><span class="state ${w.todo ? "late" : "go"}">${w.todo ? "Indexing needed" : "Up to date"}</span><button class="btn small">Index</button><button class="btn small">${ic("folder")}Finder</button></div></div>`).join("")}
    </section><p class="hint" style="margin-top:12px">Videos are added instantly, with no search model. Local files have no Instagram date, so a date filter on Search hides them.</p>`;
}
PAGE_sources = () => sourcesHtml();

/* ---------- videos ---------- */
function posGroups() {
  const out = [];
  D.positions.forEach((p) => out.push({ ...p, child: p.name.includes(" - "), top: topName(p.name) }));
  return out;
}
function clipsHtml() {
  const pg = posGroups(), cur = pg.find((p) => p.name === S.pos) || pg[0];
  const matches = D.videos.filter((v) => v.timeline.some((t) => topName(t[0]) === topName(cur.name)) && (!S.verifiedOnly || v.verified) && (!S.only || (v.title + v.creator).toLowerCase().includes(S.only.toLowerCase()))).slice(0, 14);
  const poster = (c) => { const w = D.watch.find((x) => x.name.toLowerCase() === (c || "").toLowerCase()); return w && w.videos[0] ? w.videos[0].poster : ""; };
  return `<div class="split" style="grid-template-columns:minmax(260px,330px) minmax(0,1fr)">
    <section class="panel"><div class="panel-h"><h2>Position</h2><span class="hint">${pg.length} lines</span></div><div class="pos-list scroll" style="max-height:calc(100vh - 250px)">${pg.map((p) => `<button class="pos ${p.child ? "child" : ""}" data-pos="${esc(p.name)}" aria-pressed="${p.name === cur.name}"><span class="sw" style="background:${colourOf(p.name)}"></span><span><strong>${esc((p.child ? p.name.split(" - ")[1] : p.name).replace(/_/g, " "))}</strong><small>${p.verified} of ${p.videos} verified · ${nf(p.minutes)} min</small></span><span class="vc">${p.videos}</span></button>`).join("")}</div></section>
    <div style="display:grid;gap:16px">
      <section class="panel"><div class="panel-b" style="display:grid;gap:14px">
        <div class="row" style="gap:18px;align-items:flex-end"><label class="field" style="min-width:120px"><span>Clip length</span><select id="cl">${Object.keys(D.clipLengths).map((k) => `<option ${k === S.clipLen ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
          <label class="field" style="width:200px"><span>Model confidence · ${S.conf2.toFixed(2)}</span><input type="range" id="c2" min="0" max="1" step="0.05" value="${S.conf2}"></label>
          <label class="field grow"><span>Only this video or creator (optional)</span><input type="text" id="only" value="${esc(S.only)}" placeholder="Creator or title"></label></div>
        <div class="row"><button class="chip ${S.verifiedOnly ? "on" : ""}" id="vonly">Verified videos only</button><span class="grow"></span><button class="btn primary" id="show-clips">Show clips</button><button class="btn" data-act="slides">${ic("play")}Slideshow</button></div>
      </div></section>
      <section class="panel"><div class="panel-h"><div><h2>${esc(cur.name.replace(/_/g, " "))}</h2><p class="hint">${cur.videos} videos, about ${nf(cur.minutes)} minutes in total · ${D.posMeta.missingFiles} video files not found are skipped.</p></div><button class="btn small">Which videos have it</button></div>
        ${matches.map((v) => { const img = poster(v.creator); const seg = v.timeline.find((t) => topName(t[0]) === topName(cur.name)); return `<div class="clip"><div class="clip-time" style="--c:${colourOf(cur.name)}"><b>${seg ? mmss(seg[1]) : "–"}</b><span>${seg ? "to " + mmss(seg[2]) : ""}</span></div><div><h3>${esc(v.title)}</h3><p class="sub">${esc(v.creator)} · ${v.verified ? "verified" : "model " + Math.round(v.conf * 100) + "%"}</p><div style="margin-top:8px">${route(v.timeline, v.dur, { focus: cur.name, times: true })}</div></div><button class="btn small">${ic("play")}Play</button></div>`; }).join("") || '<div class="empty"><h3>No matching videos</h3><p>Try another position or clear the filter.</p></div>'}
      </section></div></div>`;
}
const statusMeta = (v) => v.verified ? ["go", "Verified"] : v.status === "outdated" ? ["late", "Older model"] : v.status === "failed" ? ["stop", "Failed"] : v.status === "queued" ? ["live", "Running"] : v.status === "waiting" ? ["wait", "Waiting"] : ["go", "Up to date"];
function reviewList() {
  let list = D.videos.filter((v) => {
    const [, l] = statusMeta(v);
    const f = S.rvFilter;
    return (f === "all" || (f === "attention" && !v.verified && v.status !== "completed") || (f === "verified" && v.verified) || (f === "older" && v.status === "outdated") || (f === "failed" && v.status === "failed")) && (!S.rvQuery || (v.title + v.creator).toLowerCase().includes(S.rvQuery.toLowerCase()));
  });
  if (S.rvSort === "conf") list = [...list].sort((a, b) => b.conf - a.conf);
  if (S.rvSort === "dur") list = [...list].sort((a, b) => b.dur - a.dur);
  return list.slice(0, 40);
}
function reviewHtml() {
  const c = D.vidCounts, ver = (c.completed || 0) + (c.saved || 0), old = c.outdated || 0, tot = ver + old;
  const list = reviewList();
  return `<div class="summary"><div><b>${ver}</b><span>verified by you</span></div><div><b>${old}</b><span>on an older model</span></div><div><b>0</b><span>failed</span></div><div><b>${tot}</b><span>videos in total</span></div></div>
    <div class="split-meter"><i style="width:${(ver / tot) * 100}%;background:var(--go)"></i><i style="width:${(old / tot) * 100}%;background:var(--late)"></i></div>
    <div class="row" style="margin-bottom:12px"><button class="btn primary" id="analyse-all">Analyse everything that needs it (${old})</button><button class="btn" id="sel-all">Select all (${tot})</button>
      <span class="grow"></span><input type="search" id="rv-q" placeholder="Search title or creator" style="max-width:240px" value="${esc(S.rvQuery)}"><select id="rv-sort" style="width:210px"><option value="attention" ${S.rvSort === "attention" ? "selected" : ""}>Sort: needs attention first</option><option value="conf" ${S.rvSort === "conf" ? "selected" : ""}>Sort: model confidence</option><option value="dur" ${S.rvSort === "dur" ? "selected" : ""}>Sort: length</option></select></div>
    <div class="row" style="margin-bottom:12px">${[["all", "All"], ["attention", "Needs analysis"], ["verified", "Verified"], ["older", "Older model"], ["failed", "Failed"]].map(([k, l]) => `<button class="chip ${S.rvFilter === k ? "on" : ""}" data-rf="${k}">${l}</button>`).join("")}<span class="grow"></span>${key(KEY_NAMES.slice(0, 7))}</div>
    <section class="panel"><div class="rv-row rv-head"><span></span><span>Status</span><span>Video</span><span>Route, start to end</span><span class="hide-md">Conf.</span><span class="hide-md">Length</span><span></span></div>
      ${list.map((v, i) => { const [cl, l] = statusMeta(v); return `<div class="rv-row"><input type="checkbox" data-sel="${i}" aria-label="Select"><span class="state ${cl}">${l}</span><div><h3>${esc(v.title)}</h3><p class="sub">${esc(v.creator)} · ${v.sections} sections</p></div><div>${route(v.timeline, v.dur)}</div><span class="mono hide-md">${Math.round(v.conf * 100)}%</span><span class="mono hide-md">${mmss(v.dur)}</span><div class="row" style="flex-wrap:nowrap"><button class="btn small" data-rvopen="${i}">Review</button><button class="btn small">Re-run</button></div></div>`; }).join("")}</section>
    <p class="hint" style="margin-top:10px">Showing ${list.length} of ${tot}. The model was last trained ${esc(D.vidModel && D.vidModel.trained || "recently")}. Videos you verified are never overwritten by anything on this page.</p>`;
}
PAGE_videos = () => `<div class="tabs" role="tablist" id="vtabs">${[["clips", "Find clips"], ["review", "Review analysis"]].map(([k, l]) => `<button role="tab" data-k="${k}" aria-selected="${S.vtab === k}">${l}</button>`).join("")}</div><div id="vbody">${S.vtab === "clips" ? clipsHtml() : reviewHtml()}</div>`;

/* ---------- sort ---------- */
const PILE_META = { keep: ["Keep", "Looks like a photo of a person", "var(--go)"], review: ["Review", "Unsure, have a look", "var(--late)"], junk: ["Junk", "Screenshot noise, not a portrait", "var(--stop)"] };
function pilesHtml() {
  return ["keep", "review", "junk"].map((k) => { const [t, s, c] = PILE_META[k]; return `<section style="--c:${c}"><div class="pile-h"><h2>${t}</h2><b>${S.pileCounts[k]}</b></div><p class="pile-sub">${s}</p>
    ${S.piles[k].map((it, i) => `<article class="shot"><img loading="lazy" alt="" src="${it.crop}"><div class="meta"><span class="score" style="color:${c}">${it.score.toFixed(2)}</span><span>${it.body ? "Body found" : "No body"}</span><span class="hint">${esc(it.file)} · ${esc(it.date)}</span><span class="hint">${esc(it.prompt)}</span>
      <div class="moves">${["keep", "review", "junk"].map((m) => `<button data-move="${k}|${i}|${m}" aria-pressed="${m === k}">${m}</button>`).join("")}</div></div></article>`).join("")}</section>`; }).join("");
}
PAGE_sort = () => `<div class="row" style="margin-bottom:14px"><label class="row hint">Run the pilot on <input class="num-sm" type="number" value="400" min="10" max="2000"> random screenshots</label><button class="btn primary">Run the pilot</button>
  <button class="toggle" style="width:auto;padding:0" id="whole" aria-pressed="${S.whole}"><span class="track"></span><span><strong>Show the whole screenshot instead of the cropped photo</strong></span></button><span class="grow"></span><button class="btn" id="undo" disabled>Undo correction</button></div>
  <section class="panel"><div class="panel-b"><div class="spread"><span class="lbl">Photo score, 0 to 1</span><span class="hint">${D.pilot.total} screenshots: ${S.pileCounts.keep} keep, ${S.pileCounts.review} to review, ${S.pileCounts.junk} junk. A body found in the crop also counts towards keep. A manual move stays put when the sliders change.</span></div>
    <div class="ramp"><div class="ramp-bar"><i style="background:#ff6b5e"></i><i style="background:#ff8a50"></i><i style="background:#ffb224"></i><i style="background:#d6c64a"></i><i style="background:#9ccc5c"></i><i style="background:#5fd38d"></i></div>
    <input type="range" id="junk" min="0" max="1" step="0.05" value="${S.junkAt}" aria-label="Junk below"><input type="range" id="keep" min="0" max="1" step="0.05" value="${S.keepAt}" aria-label="Keep at least" style="margin-top:0">
    <span class="ramp-l" id="jl" style="left:${S.junkAt * 100}%">Junk below ${S.junkAt.toFixed(2)}</span><span class="ramp-l" id="kl" style="left:${S.keepAt * 100}%;top:60px">Keep at least ${S.keepAt.toFixed(2)}</span></div></div></section>
  <div class="piles" id="piles">${pilesHtml()}</div>`;

/* ---------- fetch ---------- */
PAGE_fetch = () => `<div class="frame-wrap"><iframe title="Links tool" src="http://127.0.0.1:8791"></iframe></div>`;

const PAGE = { search: PAGE_search, saved: PAGE_saved, sources: PAGE_sources, videos: PAGE_videos, sort: PAGE_sort, fetch: PAGE_fetch };

/* ---------- wiring ---------- */
function toast(t) { const e = document.createElement("div"); e.className = "toast"; e.textContent = t; document.body.appendChild(e); setTimeout(() => e.remove(), 2200); }
function segs(root) {
  $$(".seg[data-seg]", root).forEach((g) => g.onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S[g.dataset.seg] = b.textContent; $$("button", g).forEach((x) => x.setAttribute("aria-selected", x === b)); const s = $("#sum"); if (s) s.textContent = summary(); });
}
function bind(id) {
  const p = $("#page");
  if (id === "search") {
    segs(p);
    $("#opts-t").onclick = () => { S.optsOpen = !S.optsOpen; $("#opts").hidden = !S.optsOpen; $("#opts-t").setAttribute("aria-expanded", S.optsOpen); };
    $("#posts").oninput = (e) => { S.posts = +e.target.value || 1; $("#sum").textContent = summary(); };
    $("#every").onclick = (e) => { S.every = !S.every; e.currentTarget.classList.toggle("on", S.every); };
    $("#query").oninput = (e) => S.query = e.target.value;
    bindMust();
    $("#signal").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.signal = b.dataset.k; $$("#signal button").forEach((x) => x.setAttribute("aria-selected", x === b)); sigBind(); };
    sigBind();
    $$("[data-sugg]", p).forEach((b) => b.onclick = () => { $("#query").value = S.query = b.dataset.sugg; $("#query").focus(); });
    $("#taggroups").onclick = (e) => { const b = e.target.closest("[data-tag]"); if (!b) return; const k = b.dataset.tag; S.tags.has(k) ? S.tags.delete(k) : S.tags.add(k); b.classList.toggle("on"); $("#must-row").innerHTML = mustRow(); bindMust(); };
    $("#acct-row").onclick = (e) => { const b = e.target.closest("[data-rm]"); if (!b) return; S.accounts = S.accounts.filter((a) => a.handle !== b.dataset.rm); go("search"); };
    $("#pick-acc").onclick = openAccountPicker; $("#prepare").onclick = openPrepare; $("#refine").onclick = openRefine;
    $("#draw").onclick = () => { $("#results").innerHTML = resultsHtml(); bindResults(); toast("Layout preview: no search is run in this prototype"); };
    bindResults();
  }
  if (id === "saved") {
    $("#stype").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.savedType = b.dataset.k; go("saved"); };
    $$("[data-sacc]", p).forEach((b) => b.onclick = () => { S.savedAcc = b.dataset.sacc; go("saved"); });
    $("#saved-wall").onclick = (e) => { const b = e.target.closest("[data-unstar]"); if (!b) return; const t = b.closest(".tile"); t.remove(); S.savedExtra--; drawShell(); };
    $$("[data-act=slides]", p).forEach((b) => b.onclick = openSlides);
  }
  if (id === "sources") {
    $("#stabs").onclick = (e) => { const b = e.target.closest("[data-k]"); if (!b) return; S.sourcesTab = b.dataset.k; go("sources"); };
    $("#imp-folder").onclick = openImport; $("#prepare2").onclick = openPrepare;
    const body = $("#acc-body");
    if (body) {
      body.onclick = (e) => { const r = e.target.closest("[data-acc]"); if (!r) return; S.sel = r.dataset.acc; go("sources"); };
      $("#acc-q").oninput = (e) => { const q = e.target.value.toLowerCase(); $$("tr", body).forEach((r) => r.hidden = !r.dataset.acc.toLowerCase().includes(q)); };
      $("#auto-imp").onclick = (e) => { S.autoImport = !S.autoImport; e.currentTarget.setAttribute("aria-pressed", S.autoImport); };
      $("#detail").onclick = (e) => { const b = e.target.closest("[data-t]"); if (!b) return; S.tag = S.tag === b.dataset.t ? null : b.dataset.t; $$("[data-t]", $("#detail")).forEach((x) => x.setAttribute("aria-pressed", x.dataset.t === S.tag)); };
      $("#conf").oninput = (e) => { S.conf = +e.target.value; $("#confv").textContent = S.conf.toFixed(2); };
    }
  }
  if (id === "videos") {
    $("#vtabs").onclick = (e) => { const b = e.target.closest("[data-k]"); if (!b) return; S.vtab = b.dataset.k; go("videos"); };
    if (S.vtab === "clips") {
      $$("[data-pos]", p).forEach((b) => b.onclick = () => { S.pos = b.dataset.pos; go("videos"); });
      $("#vonly").onclick = () => { S.verifiedOnly = !S.verifiedOnly; go("videos"); };
      $("#show-clips").onclick = () => { S.only = $("#only").value; go("videos"); };
      $("#c2").oninput = (e) => { S.conf2 = +e.target.value; };
      $("#cl").onchange = (e) => S.clipLen = e.target.value;
      $$("[data-act=slides]", p).forEach((b) => b.onclick = openSlides);
    } else {
      $$("[data-rf]", p).forEach((b) => b.onclick = () => { S.rvFilter = b.dataset.rf; go("videos"); });
      $("#rv-q").onchange = (e) => { S.rvQuery = e.target.value; go("videos"); };
      $("#rv-sort").onchange = (e) => { S.rvSort = e.target.value; go("videos"); };
      $("#analyse-all").onclick = () => toast("Layout preview: analysis jobs are not started here");
      $("#sel-all").onclick = () => $$("[data-sel]", p).forEach((c) => c.checked = true);
      $$("[data-rvopen]", p).forEach((b) => b.onclick = () => openReview(+b.dataset.rvopen));
    }
  }
  if (id === "sort") {
    const upd = () => { $("#jl").style.left = S.junkAt * 100 + "%"; $("#kl").style.left = S.keepAt * 100 + "%"; $("#jl").textContent = "Junk below " + S.junkAt.toFixed(2); $("#kl").textContent = "Keep at least " + S.keepAt.toFixed(2); };
    $("#junk").oninput = (e) => { S.junkAt = Math.min(+e.target.value, S.keepAt - 0.05); e.target.value = S.junkAt; upd(); };
    $("#keep").oninput = (e) => { S.keepAt = Math.max(+e.target.value, S.junkAt + 0.05); e.target.value = S.keepAt; upd(); };
    $("#whole").onclick = (e) => { S.whole = !S.whole; e.currentTarget.setAttribute("aria-pressed", S.whole); };
    $("#piles").onclick = (e) => { const b = e.target.closest("[data-move]"); if (!b) return; const [from, i, to] = b.dataset.move.split("|"); if (from === to) return; const [it] = S.piles[from].splice(+i, 1); S.piles[to].unshift(it); S.pileCounts[from]--; S.pileCounts[to]++; $("#undo").disabled = false; $("#piles").innerHTML = pilesHtml(); };
  }
}
function sigBind() {
  const sp = $("#sigpanel"); sp.innerHTML = sigPanel();
  $$("[data-pose]", sp).forEach((b) => b.onclick = () => { S.pose = S.pose === b.dataset.pose ? "" : b.dataset.pose; sigBind(); });
  const d = $("#describe"); if (d) d.onclick = () => { $("#descout").textContent = "Layout preview: the real app describes the chosen image and fills the box above."; };
  const f = $("#reffile"); if (f) f.onchange = () => { $("#drop b").textContent = f.files[0] ? f.files[0].name : "Drop a reference image here"; };
}
function bindResults() {
  $$("[data-star]", $("#page")).forEach((b) => b.onclick = () => { const k = b.dataset.star; const on = !S.saved.has(k); on ? S.saved.add(k) : S.saved.delete(k); b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); S.savedExtra += on ? 1 : -1; drawShell(); });
  $$("[data-act=slides]", $("#page")).forEach((b) => b.onclick = openSlides);
  const sa = $("[data-act=select]"); if (sa) sa.onclick = () => $$("[data-star]").forEach((b) => { if (!b.classList.contains("on")) b.click(); });
}

/* ---------- overlays ---------- */
function overlay(html, side) {
  const o = $("#overlay"); o.className = side ? "side" : ""; o.innerHTML = html; o.hidden = false;
  o.onmousedown = (e) => { if (e.target === o) closeOverlay(); };
  $$("[data-close]", o).forEach((b) => b.onclick = closeOverlay);
  return o;
}
function closeOverlay() { const o = $("#overlay"); o.hidden = true; o.innerHTML = ""; }
function openAccountPicker() {
  const list = D.accounts.filter((a) => a.built && a.posts);
  const o = overlay(`<div class="dialog" role="dialog" aria-label="Choose accounts"><div class="dialog-h"><h2>Choose accounts</h2><button class="icon-b" data-close aria-label="Close">${ic("x")}</button></div><div class="dialog-b"><input type="search" id="aq" placeholder="Filter" autofocus><div class="chips" id="alist">${list.map((a) => `<button class="chip ${S.accounts.some((x) => x.handle === a.handle) ? "on" : ""}" data-a="${esc(a.handle)}">${a.cover ? `<img alt="" src="${a.cover}">` : ""}@${esc(a.handle)} · ${a.posts}</button>`).join("")}</div><button class="btn primary" data-close id="adone">Done</button></div></div>`);
  $("#aq").oninput = (e) => $$("#alist .chip").forEach((c) => c.hidden = !c.dataset.a.includes(e.target.value.toLowerCase()));
  $("#alist").onclick = (e) => { const b = e.target.closest("[data-a]"); if (!b) return; const h = b.dataset.a; const i = S.accounts.findIndex((x) => x.handle === h); i >= 0 ? S.accounts.splice(i, 1) : S.accounts.push(D.accounts.find((x) => x.handle === h)); b.classList.toggle("on"); };
  $("#adone").addEventListener("click", () => go("search"));
}
function openPrepare() {
  overlay(`<div class="dialog" role="dialog" aria-label="Prepare"><div class="dialog-h"><h2>Build the index first</h2><button class="icon-b" data-close aria-label="Close">${ic("x")}</button></div><div class="dialog-b">
    <p class="hint">Reads each account once so searches are instant. Safe to stop and resume.</p><label class="field"><span>Accounts</span><input type="text" placeholder="username, another_username"></label>
    <div class="chips">${D.accounts.filter((a) => !a.built).slice(0, 10).map((a) => `<button class="chip">@${esc(a.handle)}</button>`).join("")}</div>
    <label class="field"><span>Model</span><select><option>CLIP</option><option>SigLIP</option></select></label><button class="btn primary" data-close>Build the index</button></div></div>`);
}
function openImport() {
  overlay(`<div class="dialog" role="dialog" aria-label="Import"><div class="dialog-h"><h2>Import a folder of images</h2><button class="icon-b" data-close aria-label="Close">${ic("x")}</button></div><div class="dialog-b"><label class="field"><span>Name</span><input type="text" placeholder="Reference pulls"></label><label class="field"><span>Folder</span><input type="text" placeholder="/Users/you/Pictures/pulls"></label><button class="btn primary" data-close>Import</button></div></div>`);
}
function openRefine() {
  const yr = new Date().getFullYear();
  overlay(`<aside class="drawer" role="dialog" aria-label="Refine search"><div class="dialog-h"><h2>Refine</h2><button class="icon-b" data-close aria-label="Close">${ic("x")}</button></div><div class="dialog-b">
    <p class="hint">The main desk stays a query. Dates, videos, carousels and the cache live here.</p>
    <div class="sect"><span class="lbl">When</span><div class="chips">${["Any", "Last 90 days", yr, yr - 1, yr - 2].map((x) => `<button class="chip">${x}</button>`).join("")}</div><div class="row"><label class="field grow"><span>From</span><input type="date"></label><label class="field grow"><span>Until (not included)</span><input type="date"></label></div><p class="hint">Images imported from a folder or video have no date and are left out while a date is set.</p></div>
    <div class="sect"><span class="lbl">Videos</span>
      <button class="toggle" aria-pressed="false" onclick="this.setAttribute('aria-pressed',this.getAttribute('aria-pressed')!=='true')"><span class="track"></span><span><strong>Allow reels and videos</strong><small>Off by default, so a photo search stays a photo search.</small></span></button>
      <button class="toggle" aria-pressed="false" onclick="this.setAttribute('aria-pressed',this.getAttribute('aria-pressed')!=='true')"><span class="track"></span><span><strong>With a search, still mix in videos from watched folders</strong><small>Random videos from the folders you picked are added alongside the matching photos.</small></span></button>
      <button class="toggle" aria-pressed="false" onclick="this.setAttribute('aria-pressed',this.getAttribute('aria-pressed')!=='true')"><span class="track"></span><span><strong>Choose the mix of videos and photos</strong><small>The number of posts becomes the total across everything you picked.</small></span></button>
      <label class="field"><span>Video clip length</span><select>${Object.keys(D.clipLengths).map((k) => `<option>${esc(k)}</option>`).join("")}</select></label></div>
    <div class="sect"><span class="lbl">Carousels</span><div class="seg" role="tablist"><button role="tab" aria-selected="true">First photo only</button><button role="tab" aria-selected="false">Save every slide</button></div><label class="field"><span>Look inside the N most promising carousels · off</span><input type="number" min="0" max="200" value="0"></label></div>
    <div class="sect"><span class="lbl">Matches and cache</span><label class="field"><span>Choose randomly among the top 20 matches (with a search)</span><input type="number" min="1" max="500" value="20"></label><div class="seg" role="tablist"><button role="tab" aria-selected="true">Saved</button><button role="tab" aria-selected="false">Check for new posts</button><button role="tab" aria-selected="false">Rebuild (slow)</button></div><label class="field"><span>Save folder (for "Save full size")</span><input type="text" value="~/instagram-bot-2/picks"></label></div>
    <button class="btn primary" data-close>Find with these</button></div></aside>`, true);
  $$("#overlay .seg").forEach((g) => g.onclick = (e) => { const b = e.target.closest("button"); if (b) $$("button", g).forEach((x) => x.setAttribute("aria-selected", x === b)); });
}
function openSlides() {
  const f = D.favs.filter((x) => !x.video).slice(0, 8); let i = 0;
  const o = overlay(`<div class="dialog" style="width:min(760px,96vw)" role="dialog" aria-label="Slideshow"><div class="dialog-h"><h2>Slideshow</h2><button class="icon-b" data-close aria-label="Close">${ic("x")}</button></div><div class="dialog-b"><img id="sl" alt="" style="width:100%;max-height:58vh;object-fit:contain;background:#000" src="${f[0].thumb}"><div class="spread"><button class="btn" id="sp">Previous</button><span class="mono" id="sc">1 / ${f.length}</span><button class="btn primary" id="sn">Next</button></div></div></div>`);
  const show = () => { $("#sl").src = f[i].thumb; $("#sc").textContent = `${i + 1} / ${f.length}`; };
  $("#sn").onclick = () => { i = (i + 1) % f.length; show(); }; $("#sp").onclick = () => { i = (i - 1 + f.length) % f.length; show(); };
}
function openReview(i) {
  const list = reviewList(), v = list[i]; if (!v) return;
  const [cl, l] = statusMeta(v);
  overlay(`<div class="dialog" role="dialog" aria-label="Review video" style="width:min(720px,96vw)"><div class="dialog-h"><div><h2 style="font-size:22px">${esc(v.title)}</h2><p class="hint">${esc(v.creator)} · ${mmss(v.dur)}</p></div><button class="icon-b" data-close aria-label="Close">${ic("x")}</button></div><div class="det">
    <div class="row"><span class="state ${cl}">${l}</span><span class="hint">${v.verified ? "Checked by you" : "Model confidence " + Math.round(v.conf * 100) + "%"}</span></div>
    ${route(v.timeline, v.dur, { times: true })}
    <div class="sections">${v.timeline.map((t) => `<div><i style="background:${colourOf(t[0])}"></i><span>${esc(t[0].replace(/_/g, " "))}</span><span class="mono">${mmss(t[1])} to ${mmss(t[2])}</span></div>`).join("")}</div>
    <div class="row"><button class="btn primary" data-close>Mark as verified</button><button class="btn">Edit sections</button><button class="btn">${ic("play")}Play</button><button class="btn">Re-run</button></div></div></div>`);
}
function openStorage() {
  const s = D.storage, pct = (b) => (b / s.total) * 100;
  overlay(`<div class="dialog" role="dialog" aria-label="Storage"><div class="dialog-h"><h2>Storage on this Mac</h2><button class="icon-b" data-close aria-label="Close">${ic("x")}</button></div><div class="dialog-b">
    <div class="bar-stack"><i style="width:${pct(s.mine)}%;background:var(--yellow)"></i><i style="width:${pct(s.used - s.mine)}%;background:var(--seam-2)"></i></div>
    <p class="hint">${gb(s.free)} free of ${gb(s.total)} · Postroom uses ${gb(s.mine)}</p>
    <div class="sect"><span class="lbl">Largest folders</span>${s.biggest.slice(0, 7).map((b) => `<button class="facet"><span>${esc(b.name.length > 44 ? b.name.slice(0, 44) + "…" : b.name)}</span><em>${gb(b.bytes)}</em></button>`).join("")}</div>
    <button class="btn">Recalculate</button></div></div>`);
}
function openSession() {
  overlay(`<div class="dialog" role="dialog" aria-label="Session"><div class="dialog-h"><h2>Instagram session</h2><button class="icon-b" data-close aria-label="Close">${ic("x")}</button></div><div class="dialog-b">
    <p><span class="state ${D.session.loggedIn ? "go" : "stop"}">${D.session.loggedIn ? "Session saved" : "Not logged in"}</span></p><p class="hint">Saved in auth.json. Checking and rebuilding indexes need a valid login.</p>
    <div class="row"><button class="btn">Check the session</button><button class="btn primary">Log in again</button></div></div></div>`);
}
const COMMANDS = [
  ...PAGES.map((p) => ({ l: "Go to " + p.label.toLowerCase(), h: p.title, run: () => go(p.id) })),
  { l: "Open image folders", h: "Sources", run: () => { S.sourcesTab = "accounts"; go("sources"); } },
  { l: "Open video folders", h: "Sources", run: () => { S.sourcesTab = "video"; go("sources"); } },
  { l: "Find clips by position", h: "Videos", run: () => { S.vtab = "clips"; go("videos"); } },
  { l: "Review video analysis", h: "Videos", run: () => { S.vtab = "review"; go("videos"); } },
  { l: "Prepare an account", h: "Index up front", run: openPrepare },
  { l: "Open refine", h: "Dates, cache, video", run: () => { go("search"); openRefine(); } },
  { l: "Switch search model", h: "Separate indexes", run: () => { S.model = S.model === "clip" ? "siglip" : "clip"; drawShell(); } },
  { l: "Session, login and storage", h: "auth.json", run: openStorage },
  { l: "Show or hide departures", h: "Jobs", run: toggleBoard },
  { l: "Draw random posts", h: "Ignore the query once", run: () => { go("search"); $("#draw").click(); } },
];
function openPalette() {
  overlay(`<div class="dialog" style="padding:0" role="dialog" aria-label="Go to"><input class="pal-in" id="pq" placeholder="Go to, or do…" autocomplete="off"><div id="pl"></div></div>`);
  let sel = 0, shown = COMMANDS;
  const draw = () => { $("#pl").innerHTML = shown.map((c, i) => `<button class="pal-item" role="option" data-i="${i}" aria-selected="${i === sel}"><span>${esc(c.l)}</span><small>${esc(c.h)}</small></button>`).join(""); };
  draw(); $("#pq").focus();
  $("#pq").oninput = (e) => { const q = e.target.value.toLowerCase(); shown = COMMANDS.filter((c) => (c.l + c.h).toLowerCase().includes(q)); sel = 0; draw(); };
  $("#pl").onclick = (e) => { const b = e.target.closest("[data-i]"); if (b) { closeOverlay(); shown[+b.dataset.i].run(); } };
  $("#pq").onkeydown = (e) => { if (e.key === "ArrowDown") { sel = Math.min(shown.length - 1, sel + 1); draw(); e.preventDefault(); } if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); } if (e.key === "Enter" && shown[sel]) { closeOverlay(); shown[sel].run(); } };
}
function toggleBoard() { S.boardOpen = !S.boardOpen; $("#shell").classList.toggle("no-board", !S.boardOpen); $("#open-board").setAttribute("aria-pressed", S.boardOpen); }

/* ---------- boot ---------- */
document.addEventListener("click", (e) => { const g = e.target.closest("[data-go]"); if (g) go(g.dataset.go); });
$("#model").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.model = b.dataset.m; drawShell(); };
$("#open-board").onclick = toggleBoard; $("#open-palette").onclick = openPalette;
$("#open-storage").onclick = openStorage; $("#open-session").onclick = openSession;
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); }
  else if (e.key === "Escape") closeOverlay();
  else if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); go("search"); setTimeout(() => $("#query") && $("#query").focus(), 30); }
});
setInterval(() => { const c = $("#clock"); if (c) c.textContent = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }); }, 15000);
drawBoard();
if (window.innerWidth < 980) { S.boardOpen = false; $("#shell").classList.add("no-board"); }
go(PAGES.some((p) => p.id === location.hash.slice(1)) ? location.hash.slice(1) : "search");
})();
