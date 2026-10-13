import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, fmtBytes, post } from "../api";
import type { Account, Job, View } from "../types";
import { EXPECTED_API, useDesk } from "../store";
import { cn } from "../utils/cn";
import { Slideshow } from "./Frames";
import { Lightbox } from "./Lightbox";
import { Icon, Modal, Seg } from "./ui";

const NAV: { id: View; label: string; icon: string }[] = [
  { id: "search", label: "Search", icon: "search" },
  { id: "library", label: "Library", icon: "grid" },
  { id: "collections", label: "Collections", icon: "folder" },
  { id: "pilot", label: "Pilot", icon: "aperture" },
  { id: "positions", label: "Positions", icon: "play" },
  { id: "analysis", label: "Analysis", icon: "layers" },
  { id: "data18", label: "Data18 Scraper", icon: "download" },
  { id: "links", label: "Links", icon: "link" },
];

type Storage = { free: number; used: number; total: number; mine: number; biggest: { name: string; bytes: number }[]; thumbs: { name: string; bytes: number }[] };

/** True while the window is at most `px` wide (the Lightbox tray starts hidden there, so it does not cover the page). */
function useNarrow(px: number) {
  const query = `(max-width: ${px}px)`;
  const [narrow, setNarrow] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setNarrow(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return narrow;
}

export function Chrome({ children }: { children: ReactNode }) {
  const d = useDesk();
  const running = d.jobs.filter((j: Job) => j.running).length;
  const [storage, setStorage] = useState<Storage | null>(null);
  const [lbPref, setLbPref] = useState<boolean | null>(null);       // null = automatic: shown on Search, hidden elsewhere
  const narrow = useNarrow(900);
  const lbVisible = lbPref ?? (d.view === "search" && !narrow);

  useEffect(() => {
    api<Storage>("/api/storage").then(setStorage).catch(() => undefined);
  }, [d.dataVersion]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        d.setPaletteOpen(true);
        return;
      }
      if (e.key === "/" && !typing && !d.slides.open) {
        e.preventDefault();
        d.setView("search");
        d.setComposerOpen(true);
        window.setTimeout(() => document.getElementById("query")?.focus(), 30);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [d]);

  const low = storage && storage.free < 5e9;
  const who = d.session.loggedIn ? (d.session.user ? `@${d.session.user}` : "Logged in") : "No session";
  return (
    <div className="app">
      <header className="top" id="top">
        <button type="button" className="brand" onClick={() => d.setView("search")} aria-label="Postroom, home">
          <span className="mark" aria-hidden />
          <span>Postroom</span>
        </button>
        <nav className="tabs" aria-label="Pages">
          {NAV.map((item) => (
            <button key={item.id} type="button" className="tab" aria-current={d.view === item.id ? "page" : undefined} onClick={() => d.setView(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>
        <button type="button" className="cmd" onClick={() => d.setPaletteOpen(true)} aria-label="Go to or do anything">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16zM21 21l-4.2-4.2" /></svg>
          <span>Go to a page, find an account, run a command</span>
          <kbd>⌘K</kbd>
        </button>
        <div className="top-end">
          <Seg
            label="Search model"
            value={d.model}
            onChange={d.setModel}
            options={[{ id: "siglip", label: "SigLIP" }, { id: "clip", label: "CLIP" }]}
          />
          <button type="button" className={cn("status", low && "warn")} onClick={() => d.setSessionOpen(true)} title={`${storage ? `${fmtBytes(storage.free)} free · ` : ""}${who}. Session, storage and indexes`}>
            <i className={d.session.loggedIn ? "ok" : "bad"} />
            <span>{storage ? `${low ? "Low space · " : ""}${fmtBytes(storage.free)} free · ` : ""}{who}</span>
          </button>
          <button type="button" className={cn("act-btn", running > 0 && "busy")} aria-expanded={d.jobsOpen} onClick={() => d.setJobsOpen(!d.jobsOpen)}>
            <span className="spin" />Activity {running ? `${running} running` : d.jobs.length}
          </button>
          <button type="button" className="lb-btn" aria-pressed={lbVisible} onClick={() => setLbPref(!lbVisible)} title="Your favourites, always at hand">
            Lightbox <b>{d.favs.length}</b>
          </button>
        </div>
      </header>
      {d.config.host && d.config.apiVersion !== EXPECTED_API && (
        <div className="banner" style={{ margin: "12px 28px 0" }}>
          <p>This page is newer than the server running behind it, so some buttons will fail. Stop the server (Ctrl+C in its terminal) and run <span className="mono">python3 server.py</span> again, then refresh.</p>
        </div>
      )}
      <div className={cn("layout", !lbVisible && "no-lb")} id="layout">
        <main className="main" id="page" tabIndex={-1}>
          <div className={cn("stage", (d.view === "links" || d.view === "data18") && "flush")}>{children}</div>
        </main>
        <Lightbox />
      </div>
      <div className="toast-wrap" aria-live="polite">
        {d.toasts.map((t: { id: string; text: string }) => <div key={t.id} className="toast">{t.text}</div>)}
      </div>
      <Slideshow />
      <ActivityPanel />
      {d.refineOpen && <RefineDrawer />}
      {d.sessionOpen && <SessionSheet storage={storage} onRefresh={() => api<Storage>("/api/storage?refresh=true").then(setStorage).catch(() => undefined)} />}
      {d.prepareFor !== null && <PrepareSheet />}
      {d.importKind === "images" && <ImportImagesSheet />}
      {d.importKind === "videos" && <WatchSheet />}
      {d.importKind === "bulk" && <BulkSheet />}
      {d.paletteOpen && <Palette />}
    </div>
  );
}

/** The jobs list: a panel under the top bar instead of a strip that sits on every page. Same jobs, same stop and dismiss. */
function ActivityPanel() {
  const d = useDesk();
  const jobs: Job[] = d.jobs;
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { if (d.activeJob) setOpen(d.activeJob); }, [d.activeJob]);
  if (!d.jobsOpen) return null;
  const finished = jobs.filter((j) => !j.running);
  const minutes = (j: Job) => Math.max(1, Math.round((Date.now() - j.started) / 60000));
  return (
    <div className="pop-layer" onMouseDown={() => d.setJobsOpen(false)}>
      <div className="act-panel" role="dialog" aria-label="Activity" onMouseDown={(e) => e.stopPropagation()}>
        <div className="act-h">
          <h2>Activity</h2>
          <div className="row">
            {finished.length > 1 && <button type="button" className="btn tiny" onClick={() => finished.forEach((j) => d.dismissJob(j.id))}>Clear finished ({finished.length})</button>}
            <button type="button" className="icon-btn" aria-label="Close" onClick={() => d.setJobsOpen(false)}><Icon name="x" size={14} /></button>
          </div>
        </div>
        {!jobs.length && <p className="hint" style={{ padding: 16 }}>Nothing is running. Prepare, index and import jobs show up here and keep their log after a refresh.</p>}
        {jobs.map((j) => {
          const mk = j.running ? "busy" : j.status === "failed" ? "bad" : j.status === "stopped" ? "stop" : "";
          return (
            <div key={j.id} className="job">
              <button type="button" className="job-main" aria-expanded={open === j.id} onClick={() => { setOpen(open === j.id ? null : j.id); d.setActiveJob(j.id); }}>
                <span className={cn("mk", mk)} aria-hidden />
                <span>
                  <span className="job-t">{j.title}</span>
                  <span className="job-s" style={{ display: "block" }}>
                    {j.running ? `running ${minutes(j)} min` : j.status}{j.progress != null ? ` · ${Math.round(j.progress)}%` : ""}{j.progressText ? ` · ${j.progressText}` : ""} · pid {j.pid}
                  </span>
                </span>
                <span className="job-s">{open === j.id ? "hide" : "log"}</span>
              </button>
              {open === j.id && (
                <>
                  {j.running && <div className={cn("progress", j.progress == null && "indeterminate")}><i style={{ width: `${j.progress ?? 40}%` }} /></div>}
                  <pre className="job-log">{j.log.join("\n") || "Starting..."}</pre>
                  <div className="job-x">
                    {j.running && <button type="button" className="btn tiny danger" onClick={() => d.stopJob(j.id)}>Stop</button>}
                    {!j.running && <button type="button" className="btn tiny" onClick={() => d.dismissJob(j.id)}>Dismiss</button>}
                    <span className="hint mono">{j.logPath}</span>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RefineDrawer() {
  const d = useDesk();
  const lengths = Object.entries(d.config.clipLengths as Record<string, number>);
  const year = new Date().getFullYear();
  const setYear = (y: number) => { d.setDateFrom(`${y}-01-01`); d.setDateTo(`${y + 1}-01-01`); };
  return (
    <div className="drawer-back" onMouseDown={() => d.setRefineOpen(false)}>
      <aside className="drawer" onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-label="Refine search">
        <header>
          <div>
            <p className="kicker">Refine</p>
            <h2>The quieter controls.</h2>
          </div>
          <button type="button" className="icon-btn" aria-label="Close" onClick={() => d.setRefineOpen(false)}><Icon name="x" /></button>
        </header>
        <p className="hint">The main desk stays a query. Dates, videos, carousels and the cache live here so they don't crowd the search.</p>

        <div className="section">
          <p className="lbl">When</p>
          <div className="chips">
            <button type="button" className="chip" onClick={() => { d.setDateFrom(""); d.setDateTo(""); }}>Any</button>
            <button type="button" className="chip" onClick={() => {
              const from = new Date();
              from.setDate(from.getDate() - 90);
              d.setDateFrom(from.toISOString().slice(0, 10));
              d.setDateTo("");
            }}>Last 90 days</button>
            <button type="button" className="chip" onClick={() => setYear(year)}>{year}</button>
            <button type="button" className="chip" onClick={() => setYear(year - 1)}>{year - 1}</button>
            <button type="button" className="chip" onClick={() => setYear(year - 2)}>{year - 2}</button>
          </div>
          <div className="two">
            <label className="field"><span>From</span><input type="date" min="2010-01-01" value={d.dateFrom} onChange={(e) => d.setDateFrom(e.target.value)} /></label>
            <label className="field"><span>Until (not included)</span><input type="date" min="2010-01-01" value={d.dateTo} onChange={(e) => d.setDateTo(e.target.value)} /></label>
          </div>
          <p className="hint">Every Instagram post can be dated from its post code. Images imported from a folder or video have no date and are left out while a date is set.</p>
        </div>

        <div className="section">
          <p className="lbl">Videos</p>
          <button type="button" className={cn("toggle", d.includeVideo && "on")} onClick={() => d.setIncludeVideo(!d.includeVideo)}>
            <span className="track"><span className="knob" /></span>
            <span><strong>Allow reels and videos</strong><small>Off by default, so a photo search stays a photo search.</small></span>
          </button>
          <button type="button" className={cn("toggle", d.mixVideos && "on")} onClick={() => d.setMixVideos(!d.mixVideos)}>
            <span className="track"><span className="knob" /></span>
            <span><strong>With a search, still mix in videos from watched folders</strong><small>Watched videos aren't searched by content. When you search or filter by tags, random videos from the folders you picked are added alongside the matching photos.</small></span>
          </button>
          <button type="button" className={cn("toggle", d.videoMix != null && "on")} onClick={() => d.setVideoMix(d.videoMix == null ? 50 : null)}>
            <span className="track"><span className="knob" /></span>
            <span><strong>Choose the mix of videos and photos</strong><small>The number of posts becomes the total across everything you picked. If you ask for more videos than exist, videos repeat with different segments.</small></span>
          </button>
          {d.videoMix != null && (
            <label className="field">
              <span>Videos in the results · {d.videoMix}% · {Math.round((d.count * d.videoMix) / 100)} video segment(s) and {d.count - Math.round((d.count * d.videoMix) / 100)} photo(s) of {d.count}</span>
              <input type="range" min={0} max={100} step={10} value={d.videoMix} onChange={(e) => d.setVideoMix(Number(e.target.value))} />
            </label>
          )}
          <label className="field">
            <span>Video clip length</span>
            <select className="quiet" value={d.clipSeconds} onChange={(e) => d.setClipSeconds(Number(e.target.value))}>
              {lengths.map(([label, secs]) => <option key={label} value={secs}>{label}</option>)}
            </select>
          </label>
          <p className="hint">For imported videos: how long the clip is when you play it or save results. "Full video" plays the whole file, starting at the matched moment.</p>
        </div>

        <div className="section">
          <p className="lbl">Carousels</p>
          <Seg
            label="Carousels"
            value={d.allSlides ? "all" : "cover"}
            onChange={(v: string) => d.setAllSlides(v === "all")}
            options={[{ id: "cover", label: "First photo only" }, { id: "all", label: "Save every slide" }]}
          />
          <p className="hint">"Save every slide" clicks through carousels when saving full-size. With a search, only slides that still match are kept.</p>
          {d.allSlides && (
            <label className="field">
              <span>Carousel strictness · {d.margin == null ? "automatic" : d.margin.toFixed(2)} (smaller = only slides very close to the first one's score)</span>
              <div className="row">
                <input type="range" min={0} max={0.1} step={0.01} value={d.margin ?? 0.03} onChange={(e) => d.setMargin(Number(e.target.value))} style={{ flex: 1 }} />
                <button type="button" className={cn("chip", d.margin == null && "on")} onClick={() => d.setMargin(d.margin == null ? 0.03 : null)}>Auto</button>
              </div>
            </label>
          )}
          <label className="field">
            <span>Look inside the N most promising carousels · {d.expand === 0 ? "off" : d.expand}</span>
            <input type="number" min={0} max={200} value={d.expand} onChange={(e) => d.setExpand(Math.max(0, Math.min(200, Number(e.target.value) || 0)))} />
          </label>
          <p className="hint">Carousels are normally judged by their first photo. This opens the best-ranked ones for your search or tags, searches all their photos too, and remembers them (about 10 seconds each). Needs the account's carousels detected first (Library).</p>
        </div>

        <div className="section">
          <p className="lbl">Matches and cache</p>
          <label className="field">
            <span>Choose randomly among the top {d.top} matches (with a search)</span>
            <input type="number" min={1} max={500} value={d.top} onChange={(e) => d.setTop(Math.max(1, Math.min(500, Number(e.target.value) || 1)))} />
          </label>
          <Seg
            label="Cache"
            value={d.cacheMode}
            onChange={d.setCacheMode}
            options={[{ id: "cache", label: "Saved" }, { id: "refresh", label: "Check for new posts" }, { id: "rebuild", label: "Rebuild (slow)" }]}
          />
          <p className="hint">Rebuild ignores the cache and reads the profile again. A first run on a new model can take several minutes. Checking and rebuilding need an Instagram login.</p>
          <label className="field">
            <span>Save folder (for "Save full size")</span>
            <input className="textin" value={d.baseDir} onChange={(e) => d.setBaseDir(e.target.value)} />
          </label>
        </div>
        <button type="button" className="btn primary" onClick={() => { d.setRefineOpen(false); d.find(); }}>Find with these</button>
      </aside>
    </div>
  );
}

function SessionSheet({ storage, onRefresh }: { storage: Storage | null; onRefresh: () => void }) {
  const d = useDesk();
  const [checking, setChecking] = useState(false);
  const loggingIn = d.jobs.some((j: Job) => j.kind === "login" && j.running);
  const folders: [string, string][] = [
    ["picks", "Saved search results"],
    ["favourites", "Starred copies and favourites.json"],
    ["library", "Categorised folders"],
    ["pilot", "Screenshot crops and scores"],
    ["cache", "Posts, thumbnails, indexes and job logs"],
  ];
  return (
    <Modal kicker="This desk" title="Session, indexes, storage" onClose={() => d.setSessionOpen(false)}>
      <div className="section" style={{ borderTop: 0, paddingTop: 0 }}>
        <div className="spread">
          <div>
            <p className="kicker">auth.json</p>
            <h3>{!d.session.authFile ? "Not logged in yet" : d.session.loggedIn ? "Session saved" : "Saved session has no login"}</h3>
            <p className="hint">
              {d.session.user ? `@${d.session.user}` : d.session.userId ? `Account ID ${d.session.userId}` : "Unknown account"}
              {d.session.checkedAt ? ` · checked ${d.session.checkedAt}` : " · not checked this visit"}
            </p>
          </div>
          <i className={cn("dot", d.session.loggedIn ? "ok" : "bad")} />
        </div>
        <div className="row">
          <button type="button" className="btn tiny" disabled={checking || !d.session.authFile} onClick={async () => { setChecking(true); await d.checkSession(); setChecking(false); }}>
            {checking ? "Checking..." : "Check which account I'm using"}
          </button>
          <button type="button" className="btn primary" disabled={loggingIn} onClick={() => d.startJob({ kind: "login" })}>
            {loggingIn ? "Waiting for you to log in..." : d.session.authFile ? "Log in / switch account" : "Log in"}
          </button>
        </div>
        <p className="hint">Logging in opens a browser window on this Mac. Sign in there, including 2FA; you have up to 3 minutes. Postroom never asks for the password. Treat auth.json as a logged-in browser.</p>
      </div>
      <div className="section">
        <p className="lbl">Index</p>
        <p className="hint">SigLIP is the current embedding index. CLIP is the older one. Each account keeps them apart, and switching does not delete either. The first time an account is opened with a model, its index is built from the saved images (a few minutes per 1,000).</p>
      </div>
      <div className="section">
        <div className="spread">
          <p className="lbl">Storage</p>
          <button type="button" className="btn tiny" onClick={onRefresh}>Recalculate</button>
        </div>
        {storage ? (
          <>
            <p className="hint">
              This project folder: {fmtBytes(storage.mine)} · Mac storage: {fmtBytes(storage.used)} used of {fmtBytes(storage.total)} · Free: {fmtBytes(storage.free)} ({Math.round((storage.free / storage.total) * 100)}%)
            </p>
            <div className="meter" aria-hidden><i style={{ width: `${(storage.used / storage.total) * 100}%`, background: "var(--cream)" }} /></div>
            {storage.free < 5e9 && <p className="hint warn">Storage is almost full. Importing and indexing need free space to work.</p>}
            {storage.biggest.map((b) => <div key={b.name} className="count-line static"><span>{b.name}</span><em>{fmtBytes(b.bytes)}</em></div>)}
            {!!storage.thumbs.length && <p className="tag-label" style={{ marginTop: 8 }}>Largest saved-image folders</p>}
            {storage.thumbs.map((b) => <div key={b.name} className="count-line static"><span>{b.name}</span><em>{fmtBytes(b.bytes)}</em></div>)}
          </>
        ) : <p className="hint">Measuring...</p>}
      </div>
      <div className="section">
        <p className="lbl">On disk</p>
        {folders.map(([path, note]) => (
          <button key={path} type="button" className="count-line" onClick={() => d.openFolder(path)}>
            <span>{path}/</span>
            <em>{note} · open</em>
          </button>
        ))}
      </div>
    </Modal>
  );
}

function PrepareSheet() {
  const d = useDesk();
  const [raw, setRaw] = useState(d.prepareFor || "");
  const [n, setN] = useState(0);
  const names = raw.split(/[\s,]+/).filter(Boolean).map((x: string) => x.replace(/^@/, "").toLowerCase());
  return (
    <Modal kicker="Prepare" title="Build the index first." onClose={() => d.setPrepareFor(null)}>
      <p className="hint">Does all the one-off work up front so every later search is instant: reads the whole profile, keeps the thumbnails, builds the photo and pose indexes and records which posts are carousels. Roughly 8 minutes for about 1,000 posts. Safe to run again; it only fills in what's missing.</p>
      <label className="field" style={{ marginTop: 12 }}>
        <span>Account(s), one after another</span>
        <input className="textin" value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="username, another_username" autoFocus />
      </label>
      <div className="chips" style={{ marginTop: 8, maxHeight: 96, overflow: "auto" }}>
        {(d.accounts as Account[]).filter((a) => a.kind === "instagram").map((a) => (
          <button type="button" key={a.handle} className={cn("chip", names.includes(a.handle) && "on")} onClick={() => setRaw(names.includes(a.handle) ? names.filter((x: string) => x !== a.handle).join(", ") : [...names, a.handle].join(", "))}>@{a.handle}</button>
        ))}
      </div>
      <label className="field" style={{ marginTop: 12 }}>
        <span>Also look inside up to N carousels now · {n === 0 ? "skip" : n}</span>
        <input type="number" min={0} max={500} value={n} onChange={(e) => setN(Math.max(0, Math.min(500, Number(e.target.value) || 0)))} />
      </label>
      <p className="hint">Opens each carousel and indexes all its photos (about 10 seconds each). You can also do this later from Library, in batches.</p>
      <button
        type="button"
        className="btn primary"
        style={{ marginTop: 14 }}
        disabled={!names.length}
        onClick={async () => {
          if (await d.startJob({ kind: "prepare", users: raw, expand: n })) {
            d.setSelectedAccounts((prev: string[]) => [...new Set([...prev, ...names])]);
            d.setPrepareFor(null);
          }
        }}
      >
        Start prepare
      </button>
    </Modal>
  );
}

function ImportImagesSheet() {
  const d = useDesk();
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  return (
    <Modal kicker="Import" title="Folder of images" onClose={() => d.setImportKind(null)}>
      <p className="hint">Adds every image in a folder (including sub-folders) as a collection that works like an account: search, tags, pose matching, breakdown and favourites. Your files are only read; the tool keeps its own resized copies. Run it again later to add new files.</p>
      <label className="field" style={{ marginTop: 12 }}>
        <span>Collection name (letters and numbers, e.g. "holiday")</span>
        <input className="textin" value={name} onChange={(e) => setName(e.target.value)} placeholder="Reference pulls" autoFocus />
      </label>
      <label className="field" style={{ marginTop: 8 }}>
        <span>Folder path</span>
        <input className="textin" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/Users/you/Pictures/pulls" />
      </label>
      <p className="hint" style={{ marginTop: 6 }}>In Finder: right-click the folder, hold Option, choose "Copy ... as Pathname", then paste it here.</p>
      <p className="hint">Videos: use "Watch a video folder" in Collections. They are added instantly, with no search model.</p>
      <button
        type="button"
        className="btn primary"
        style={{ marginTop: 14 }}
        disabled={!name.trim() || !path.trim()}
        onClick={async () => {
          if (await d.startJob({ kind: "import", name: name.trim(), path: path.trim().replace(/^['"]|['"]$/g, "") })) d.setImportKind(null);
        }}
      >
        Start import
      </button>
    </Modal>
  );
}

function WatchSheet() {
  const d = useDesk();
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Modal kicker="Watch" title="Video folder" onClose={() => d.setImportKind(null)}>
      <p className="hint">Point a collection at a folder. Videos added to it, or to any sub-folder, show up within a few seconds, ready to play. No search model runs on them, so adding is quick. A new name makes a collection of videos; the name of an account you already have attaches the videos to it. Your files are only read.</p>
      <label className="field" style={{ marginTop: 12 }}>
        <span>Collection name</span>
        <input className="textin" value={name} onChange={(e) => setName(e.target.value)} placeholder="Trip clips" autoFocus />
      </label>
      <label className="field" style={{ marginTop: 8 }}>
        <span>Folder path</span>
        <input className="textin" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/Users/you/Movies/trip" />
      </label>
      <button
        type="button"
        className="btn primary"
        style={{ marginTop: 14 }}
        disabled={!name.trim() || !path.trim() || busy}
        onClick={async () => {
          setBusy(true);
          try {
            await post("/api/watch", { name: name.trim(), folder: path.trim() });
            d.toast(`Watching ${name.trim()}`);
            d.bump();
            d.refreshAccounts();
            d.setCollectionsTab("videos");
            d.setView("collections");
            d.setImportKind(null);
          } catch (e) {
            d.fail(e);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Adding..." : "Watch"}
      </button>
    </Modal>
  );
}

function BulkSheet() {
  const d = useDesk();
  const [n, setN] = useState(6);
  const [rows, setRows] = useState<{ name: string; folder: string }[]>(Array.from({ length: 6 }, () => ({ name: "", folder: "" })));
  const [report, setReport] = useState<{ name: string; status: string; videos: number; photos: number }[] | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const resize = (k: number) => {
    const size = Math.max(1, Math.min(100, k || 1));
    setN(size);
    setRows((prev) => Array.from({ length: size }, (_, i) => prev[i] || { name: "", folder: "" }));
  };
  return (
    <Modal kicker="Watch" title="Create several at once" onClose={() => d.setImportKind(null)} wide>
      <p className="hint">Say how many, then give each one a name and the folder to take its videos and photos from. Videos are added instantly (no search model). Photos are imported in the background.</p>
      <label className="field" style={{ margin: "10px 0", maxWidth: 160 }}>
        <span>How many</span>
        <input type="number" min={1} max={100} value={n} onChange={(e) => resize(Number(e.target.value))} />
      </label>
      <div className="bulk-table">
        {rows.map((r, i) => (
          <div key={i} className="bulk-row">
            <input className="textin" placeholder="Name" value={r.name} onChange={(e) => setRows((p) => p.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
            <input className="textin" placeholder="Folder path" value={r.folder} onChange={(e) => setRows((p) => p.map((x, j) => (j === i ? { ...x, folder: e.target.value } : x)))} />
          </div>
        ))}
      </div>
      <button
        type="button"
        className="btn primary"
        style={{ marginTop: 14 }}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await post<{ report: typeof report; started: boolean; note: string }>("/api/watch/bulk", { rows, model: d.model });
            setReport(r.report);
            setNote(r.started ? "Photos are being imported in the background; they appear in searches when that job finishes." : r.note);
            d.bump();
            d.refreshAccounts();
          } catch (e) {
            d.fail(e);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Creating..." : "Create all"}
      </button>
      {report && (
        <div style={{ marginTop: 14 }}>
          {report.map((r, i) => (
            <div key={i} className="count-line static"><span>{r.name || "(empty)"} · {r.status}</span><em>{r.videos} videos · {r.photos} photos</em></div>
          ))}
          {note && <p className="hint" style={{ marginTop: 8 }}>{note}</p>}
        </div>
      )}
    </Modal>
  );
}

function Palette() {
  const d = useDesk();
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const commands = useMemo(() => [
    { id: "search", label: "Go to search", hint: "Desk", run: () => d.setView("search") },
    { id: "library", label: "Go to library", hint: "Tags and counts", run: () => d.setView("library") },
    { id: "images", label: "Open image folders", hint: "Imports", run: () => { d.setView("collections"); d.setCollectionsTab("images"); } },
    { id: "videos", label: "Open video folders", hint: "Watched folders", run: () => { d.setView("collections"); d.setCollectionsTab("videos"); } },
    { id: "favs", label: "Open favourites", hint: "Starred frames", run: () => { d.setView("collections"); d.setCollectionsTab("favourites"); } },
    { id: "pilot", label: "Open photos pilot", hint: "Keep, review, junk", run: () => d.setView("pilot") },
    { id: "positions", label: "Find clips by position", hint: "Doggystyle, cowgirl...", run: () => d.setView("positions") },
    { id: "analysis", label: "Open analysis", hint: "Every video and what the model made of it", run: () => d.setView("analysis") },
    { id: "data18", label: "Open Data18 Scraper", hint: "Performers, videos, photos, model results", run: () => d.setView("data18") },
    { id: "links", label: "Open links", hint: "Scrape, sort, download", run: () => d.setView("links") },
    { id: "prepare", label: "Prepare an account", hint: "Indexes up front", run: () => d.setPrepareFor("") },
    { id: "refine", label: "Open refine", hint: "Dates, cache, video", run: () => { d.setView("search"); d.setRefineOpen(true); } },
    { id: "model", label: d.model === "siglip" ? "Switch to CLIP" : "Switch to SigLIP", hint: "Separate indexes", run: () => d.setModel(d.model === "siglip" ? "clip" : "siglip") },
    { id: "session", label: "Session, login and storage", hint: "auth.json", run: () => d.setSessionOpen(true) },
    { id: "jobs", label: "Show jobs", hint: "Logs and stop", run: () => d.setJobsOpen(true) },
    { id: "random", label: "Draw random posts", hint: "Ignore the query once", run: () => d.find({ forceRandom: true }) },
  ], [d]);
  const filtered = commands.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()));
  const current = filtered[Math.min(cursor, Math.max(0, filtered.length - 1))];

  return (
    <div className="modal-back" onMouseDown={() => d.setPaletteOpen(false)}>
      <div className="palette" role="dialog" aria-label="Commands" onMouseDown={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={q}
          placeholder="Jump, prepare, switch index..."
          onChange={(e) => { setQ(e.target.value); setCursor(0); }}
          onKeyDown={(e) => {
            if (e.key === "Escape") d.setPaletteOpen(false);
            if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(filtered.length - 1, c + 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(0, c - 1)); }
            if (e.key === "Enter" && current) { current.run(); d.setPaletteOpen(false); }
          }}
        />
        {filtered.map((c, i) => (
          <button key={c.id} type="button" className={cn("cmd", i === cursor && "on")} onMouseEnter={() => setCursor(i)} onClick={() => { c.run(); d.setPaletteOpen(false); }}>
            {c.label}
            <small>{c.hint}</small>
          </button>
        ))}
        {!filtered.length && <p className="hint" style={{ padding: 16 }}>No command.</p>}
      </div>
    </div>
  );
}
