import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, del, fmtDuration, post, usePref } from "../api";
import type { ImportFolder, WatchFolder, WatchVideo } from "../types";
import { useDesk } from "../store";
import { cn } from "../utils/cn";
import { ContactSheet } from "./Frames";
import { Icon } from "./ui";

const FRAME_OPTIONS: [number, string][] = [[2, "2 s"], [5, "5 s"], [10, "10 s"], [30, "30 s"], [60, "1 min"]];

function usePoll(fn: () => Promise<void>, ms: number, deps: unknown[]) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    let stop = false;
    let timer = 0;
    const tick = async () => {
      try {
        await ref.current();
      } catch {
        /* a missed poll is fine */
      }
      if (!stop) timer = window.setTimeout(tick, ms);
    };
    tick();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export function CollectionsView() {
  const d = useDesk();
  return (
    <div>
      <p className="kicker">Collections</p>
      <div className="spread">
        <h1 style={{ fontSize: "clamp(32px, 4vw, 48px)" }}>Imports and favourites.</h1>
        <div className="seg" role="tablist" aria-label="Collection">
          <button type="button" className={d.collectionsTab === "images" ? "on" : ""} onClick={() => d.setCollectionsTab("images")}>Image folders</button>
          <button type="button" className={d.collectionsTab === "videos" ? "on" : ""} onClick={() => d.setCollectionsTab("videos")}>Video folders</button>
          <button type="button" className={d.collectionsTab === "favourites" ? "on" : ""} onClick={() => d.setCollectionsTab("favourites")}>Favourites · {d.favs.length}</button>
        </div>
      </div>
      {d.collectionsTab === "images" && <ImageFolders />}
      {d.collectionsTab === "videos" && <VideoFolders />}
      {d.collectionsTab === "favourites" && <Favourites />}
    </div>
  );
}

function ImageFolders() {
  const d = useDesk();
  const [rows, setRows] = useState<ImportFolder[] | null>(null);
  const load = useCallback(async () => {
    const r = await api<{ collections: ImportFolder[] }>("/api/imports");
    setRows(r.collections);
  }, []);
  usePoll(load, 15000, [d.dataVersion]);
  const pending = (rows || []).reduce((s, r) => s + r.pending, 0);
  const busy = d.jobs.some((j: { running: boolean; kind: string }) => j.running && ["import", "import-new", "import-many", "prepare", "index", "pilot"].includes(j.kind));
  return (
    <div className="stack" style={{ marginTop: 18 }}>
      <div className="panel panelbox">
        <button type="button" className={cn("toggle", d.autoImport && "on")} onClick={() => d.setAutoImport(!d.autoImport)} role="switch" aria-checked={d.autoImport}>
          <span className="track"><span className="knob" /></span>
          <span>
            <strong>Check for new files when Postroom opens and import them automatically</strong>
            <small>Files are imported only once they've finished copying (about 30 seconds after they last changed). Your files are only read.</small>
          </span>
        </button>
      </div>
      <div className="row">
        <button type="button" className="btn primary" onClick={() => d.setImportKind("images")}>Import image folder</button>
        <button type="button" className="btn" disabled={busy || !pending} onClick={async () => { if (await d.startJob({ kind: "import-new", names: [] })) load(); }}>
          Import all new{pending ? ` (${pending})` : ""}
        </button>
      </div>
      {rows == null && <p className="hint">Looking at your folders...</p>}
      {rows && !rows.length && (
        <div className="empty">
          <h2>No folders imported yet.</h2>
          <p className="hint">Import a folder of images and it becomes a collection you can search like an account.</p>
        </div>
      )}
      {(rows || []).map((s) => (
        <article key={s.name} className="source">
          <div>
            <p className="kicker">Images</p>
            <h3>{s.name}</h3>
            <p className="mono" style={{ color: "var(--dust)", margin: "4px 0", wordBreak: "break-all" }}>{s.folders.join("  ·  ")}</p>
            <p className="hint">{s.indexed != null ? `${s.indexed.toLocaleString()} indexed · ` : ""}{s.folders.length} folder{s.folders.length === 1 ? "" : "s"}</p>
          </div>
          <div className="stack" style={{ justifyItems: "end" }}>
            <span className="pending">{s.pending ? `${s.pending} new file${s.pending === 1 ? "" : "s"} waiting` : "Up to date"}</span>
            <div className="row">
              <button type="button" className="btn tiny" disabled={busy || !s.pending} onClick={async () => { if (await d.startJob({ kind: "import-new", names: [s.name] })) load(); }}>Import new</button>
              {s.folders[0] && <button type="button" className="btn tiny" onClick={() => d.revealPath(s.folders[0])}>Finder</button>}
            </div>
          </div>
        </article>
      ))}
      <p className="hint">Local files have no Instagram date, so a date filter on Search hides them. Videos: use Video folders. They are added instantly, with no search model.</p>
    </div>
  );
}

function VideoFolders() {
  const d = useDesk();
  const [folders, setFolders] = useState<WatchFolder[] | null>(null);
  const load = useCallback(async () => {
    const r = await api<{ folders: WatchFolder[] }>("/api/watch");
    setFolders(r.folders);
  }, []);
  usePoll(load, 3000, [d.dataVersion]);
  const [every, setEvery] = usePref("videoEvery", 5);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const needs = (f: WatchFolder) => f.count > 0 && f.count - f.indexedVideos > 0;
  const chosen = (folders || []).filter((f) => picked[f.name] && needs(f));
  const todoSecs = chosen.reduce((s, f) => s + f.todoSeconds, 0);
  const todoVideos = chosen.reduce((s, f) => s + (f.count - f.indexedVideos), 0);
  const busyAny = d.jobs.some((j: { running: boolean; kind: string }) => j.running && ["prepare", "index", "import", "import-new", "import-many", "pilot", "index-videos"].includes(j.kind));
  return (
    <div className="stack" style={{ marginTop: 18 }}>
      <p className="hint">
        Point a collection at a folder. Videos added to it, or to any sub-folder, show up here within a few seconds, ready to play. No search model runs on them, so adding is quick. A new name makes a collection of videos; the name of an account you already have attaches the videos to it. Your files are only read. Keep this page open while you copy files in.
      </p>
      <div className="row">
        <button type="button" className="btn primary" onClick={() => d.setImportKind("videos")}>Watch a video folder</button>
        <button type="button" className="btn" onClick={() => d.setImportKind("bulk")}>Create several at once</button>
        <button type="button" className="btn" onClick={async () => {
          try {
            const r = await post<{ total: number; folders: number }>("/api/watch/rescan");
            d.toast(r.total ? `Found ${r.total} new video${r.total === 1 ? "" : "s"}` : `No new videos in ${r.folders} watched folders`);
            load();
          } catch (e) {
            d.fail(e);
          }
        }}>Check for new videos now</button>
      </div>
      <p className="hint">Videos you add to a folder that is already watched are picked up automatically every 30 seconds while the server is running, even with this page closed.</p>
      <FindNew onAdded={load} />
      {folders && folders.length > 0 && (
        <div className="panel panelbox">
          <strong>Make videos searchable</strong>
          <p className="hint">Reads a frame every few seconds so you can search the videos by pose, scene or a reference photo and jump to the matching moment. Tick the folders (or all of them) and start one job that works through them in turn. Videos already done are skipped.</p>
          <div className="row" style={{ marginTop: 10 }}>
            <button type="button" className="btn tiny" onClick={() => setPicked(Object.fromEntries((folders || []).filter(needs).map((f) => [f.name, true])))}>
              Select all that need it ({(folders || []).filter(needs).length})
            </button>
            <button type="button" className="btn tiny" disabled={!Object.values(picked).some(Boolean)} onClick={() => setPicked({})}>Select none</button>
            <label className="inline-num">Frame every
              <select value={every} onChange={(e) => setEvery(Number(e.target.value))} aria-label="Seconds between searchable frames">
                {FRAME_OPTIONS.map(([n, label]) => <option key={n} value={n}>{label}</option>)}
              </select>
            </label>
            <button type="button" className="btn primary" disabled={!chosen.length || busyAny} onClick={async () => {
              if (await d.startJob({ kind: "index-videos", names: chosen.map((f) => f.name), every })) setPicked({});
            }}>
              {busyAny ? "Another job is running" : chosen.length ? `Make ${chosen.length} folder${chosen.length === 1 ? "" : "s"} searchable` : "Make selected searchable"}
            </button>
          </div>
          {chosen.length > 0 && (
            <p className="hint" style={{ marginTop: 8 }}>
              {todoVideos} video{todoVideos === 1 ? "" : "s"}, {(todoSecs / 3600).toFixed(1)} hours of footage: about {Math.round(todoSecs / every).toLocaleString()} frames before near-duplicates are dropped
              {todoSecs / every > 1000 ? `, roughly ${Math.round(todoSecs / every / 11.6 / 60)} minutes of embedding plus reading the video and the pose pass.` : "."}
              {every <= 2 ? " Two-second spacing uses the most time and disk." : every >= 30 ? " Wide spacing is quick but can miss short moments." : ""}
            </p>
          )}
        </div>
      )}
      {folders == null && <p className="hint">Looking at your folders...</p>}
      {folders && !folders.length && (
        <div className="empty">
          <h2>No folders are being watched yet.</h2>
          <p className="hint">Add one above and its videos appear here within seconds.</p>
        </div>
      )}
      {(folders || []).map((f) => <WatchPanel key={f.name} folder={f} reload={load} every={every} checked={!!picked[f.name]} onCheck={() => setPicked({ ...picked, [f.name]: !picked[f.name] })} />)}
    </div>
  );
}

type Found = {
  name: string; dir: string; folder: string; videos: number; photos: number;
  addVideos: boolean; addPhotos: boolean; attaches: boolean; clash: string | null;
};

/** Scans a library folder for sub-folders that aren't added yet, and adds the ones you tick in one go. */
function FindNew({ onAdded }: { onAdded: () => Promise<void> }) {
  const d = useDesk();
  const [root, setRoot] = useState("library");
  const [auto, setAuto] = useState(false);
  const [rows, setRows] = useState<Found[] | null>(null);
  const [total, setTotal] = useState(0);
  const [names, setNames] = useState<Record<string, string>>({});
  const [off, setOff] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<{ name: string; status: string; videos: number }[] | null>(null);
  const [note, setNote] = useState("");

  const scan = useCallback(async (folder?: string) => {
    setBusy(true);
    try {
      const r = await api<{ root: string; rows: Found[]; total: number; autoAdd: boolean; savedRoot: string }>(
        `/api/watch/discover${folder ? `?root=${encodeURIComponent(folder)}` : ""}`);
      setRows(r.rows);
      setTotal(r.total);
      setAuto(r.autoAdd);
      if (!folder) setRoot(r.savedRoot);
      setNames({});
      setOff(Object.fromEntries(r.rows.filter((x) => x.clash).map((x) => [x.folder, true])));
    } catch (e) {
      d.fail(e);
    } finally {
      setBusy(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { scan(); }, [scan, d.dataVersion]);

  const chosen = (rows || []).filter((r) => !off[r.folder]);
  return (
    <div className="panel panelbox">
      <div className="spread">
        <div>
          <strong>Find new folders</strong>
          <p className="hint">Looks at the sub-folders of a library folder and lists the ones holding videos (or photos) that haven't been added yet. Folders are matched by where they are on disk, so a folder you already watch is never listed twice.</p>
        </div>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <label className="field" style={{ flex: 1, minWidth: 240 }}>
          <span>Library folder</span>
          <input className="textin" value={root} onChange={(e) => setRoot(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") scan(root); }} placeholder="library" />
        </label>
        <button type="button" className="btn" disabled={busy} onClick={async () => {
          await scan(root);
          try { await post("/api/settings/library", { root }); } catch { /* a bad folder was already reported */ }
        }}>{busy ? "Scanning..." : "Scan"}</button>
      </div>
      <button type="button" className={cn("toggle", auto && "on")} style={{ marginTop: 10 }} role="switch" aria-checked={auto} onClick={async () => {
        const next = !auto;
        setAuto(next);
        try { await post("/api/settings/library", { root, auto: next }); } catch (e) { setAuto(!next); d.fail(e); }
      }}>
        <span className="track"><span className="knob" /></span>
        <span>
          <strong>Add new folders automatically</strong>
          <small>While the server runs, every minute or so any new sub-folder with videos is watched, and its photos are imported. Off by default.</small>
        </span>
      </button>

      {rows && !rows.length && (
        <p className="hint" style={{ marginTop: 12 }}>Nothing new. All {total} sub-folders of {root} that hold videos are already watched.</p>
      )}
      {rows && rows.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="spread" style={{ marginBottom: 6 }}>
            <p className="hint">{rows.length} new of {total} sub-folders. Untick any you don't want; you can rename them first.</p>
            <div className="row">
              <button type="button" className="btn tiny" onClick={() => setOff({})}>Tick all</button>
              <button type="button" className="btn tiny" onClick={() => setOff(Object.fromEntries(rows.map((r) => [r.folder, true])))}>Untick all</button>
            </div>
          </div>
          <div className="found-list">
            {rows.map((r) => (
              <div key={r.folder} className={cn("found-row", off[r.folder] && "off")}>
                <button type="button" className={cn("pick-box big", !off[r.folder] && "on")} aria-pressed={!off[r.folder]} aria-label={`Add ${r.name}`} onClick={() => setOff({ ...off, [r.folder]: !off[r.folder] })}>
                  {!off[r.folder] && <Icon name="check" size={12} />}
                </button>
                <input className="textin" value={names[r.folder] ?? r.name} onChange={(e) => setNames({ ...names, [r.folder]: e.target.value })} aria-label="Collection name" />
                <span className="hint">
                  {r.dir}/ · {r.addVideos ? `${r.videos} video${r.videos === 1 ? "" : "s"}` : ""}{r.addVideos && r.addPhotos ? " · " : ""}{r.addPhotos ? `${r.photos.toLocaleString()} photos to import` : ""}
                  {r.attaches ? " · joins the existing account of that name" : ""}
                  {r.clash ? ` · name already used for ${r.clash}` : ""}
                </span>
              </div>
            ))}
          </div>
          <button type="button" className="btn primary" style={{ marginTop: 12 }} disabled={busy || !chosen.length} onClick={async () => {
            setBusy(true);
            try {
              const r = await post<{ report: { name: string; status: string; videos: number }[]; started: boolean; note: string }>("/api/watch/add-found", {
                model: d.model,
                rows: chosen.map((x) => ({ name: names[x.folder] ?? x.name, folder: x.folder, videos: x.addVideos, photos: x.addPhotos, photoCount: x.photos })),
              });
              setReport(r.report);
              setNote(r.started ? "Photos are being imported in the background; they appear in searches when that job finishes." : r.note);
              d.toast(`Added ${r.report.filter((x) => x.status.includes("watching") || x.status.includes("queued")).length} folder(s)`);
              d.refreshAccounts();
              d.bump();
              await onAdded();
              await scan(root);
            } catch (e) {
              d.fail(e);
            } finally {
              setBusy(false);
            }
          }}>Add {chosen.length} folder{chosen.length === 1 ? "" : "s"}</button>
        </div>
      )}
      {report && (
        <div style={{ marginTop: 12 }}>
          {report.map((r, i) => <div key={i} className="count-line static"><span>{r.name} · {r.status}</span><em>{r.videos} videos</em></div>)}
          {note && <p className="hint" style={{ marginTop: 8 }}>{note}</p>}
        </div>
      )}
    </div>
  );
}

function WatchPanel({ folder, reload, every, checked, onCheck }: { folder: WatchFolder; reload: () => Promise<void>; every: number; checked: boolean; onCheck: () => void }) {
  const d = useDesk();
  const lengths = Object.entries(d.config.clipLengths as Record<string, number>);
  const [secs, setSecs] = useState(15);
  const [pick, setPick] = useState<{ url: string; start: number; name: string; from: number } | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const indexing = d.jobs.some((j: { kind: string; running: boolean; account: string | null }) => j.kind === "index-videos" && j.running && j.account === folder.name);
  const anyHeavy = d.jobs.some((j: { running: boolean; kind: string }) => j.running && ["prepare", "index", "import", "import-new", "import-many", "pilot", "index-videos"].includes(j.kind));
  const todo = folder.count - folder.indexedVideos;
  return (
    <div className="panel panelbox">
      <div className="spread">
        <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
          <button type="button" className={cn("pick-box big", checked && "on")} style={{ marginTop: 3 }} aria-pressed={checked} aria-label={`Select ${folder.name}`} onClick={onCheck}>
            {checked && <Icon name="check" size={12} />}
          </button>
        <div>
          <strong>{folder.name}</strong> · {folder.count} video{folder.count === 1 ? "" : "s"}{folder.attached ? " · attached to the account" : ""}
          {folder.frames > 0 && <span className="hint"> · {folder.frames.toLocaleString()} searchable frames from {folder.indexedVideos} video{folder.indexedVideos === 1 ? "" : "s"}</span>}
          <p className="mono" style={{ color: "var(--dust)", wordBreak: "break-all" }}>{folder.folder}</p>
          {folder.error && <p className="hint warn">{folder.error}</p>}
        </div>
        </div>
        <div className="row">
          <button type="button" className="btn tiny" disabled={!folder.count || anyHeavy || (todo <= 0 && folder.frames > 0)} title="Reads a frame every few seconds so you can search the videos by pose, scene or a reference photo, and jump to the matching moment" onClick={() => d.startJob({ kind: "index-videos", name: folder.name, every })}>
            {indexing ? "Indexing..." : folder.frames > 0 ? (todo > 0 ? `Index ${todo} new` : "All searchable") : "Make searchable"}
          </button>
          <select className="quiet" value={secs} onChange={(e) => setSecs(Number(e.target.value))} aria-label="Random clip length">
            {lengths.map(([label, v]) => <option key={label} value={v}>{label}</option>)}
          </select>
          <button type="button" className="btn tiny" disabled={!folder.count || busy} onClick={async () => {
            setBusy(true);
            try {
              setPick(await post(`/api/watch/${encodeURIComponent(folder.name)}/random`, { secs }));
            } catch (e) {
              d.fail(e);
            } finally {
              setBusy(false);
            }
          }}>
            <Icon name="shuffle" size={14} /> {busy ? "Cutting..." : "Random clip"}
          </button>
          <button type="button" className="btn tiny danger" title="Stop watching this folder (your files are untouched)" onClick={async () => {
            await del(`/api/watch/${encodeURIComponent(folder.name)}`);
            d.refreshAccounts();
            reload();
          }}>Stop</button>
        </div>
      </div>
      {pick && (
        <div className="clip-box">
          <p className="hint">{pick.name} · from {fmtDuration(pick.from)}</p>
          <video key={pick.url} src={pick.url} controls autoPlay playsInline onLoadedMetadata={(e) => { if (pick.start) e.currentTarget.currentTime = pick.start; }} />
        </div>
      )}
      <div className="vid-grid">
        {folder.videos.map((v: WatchVideo) => (
          <div key={v.id} className="vid-card">
            {playing === v.id ? (
              <video src={v.url} controls autoPlay playsInline />
            ) : v.poster ? (
              <img src={v.poster} alt="" loading="lazy" />
            ) : (
              <span className="noimg">No preview yet</span>
            )}
            <p className="hint" title={v.file}>{v.name} · {fmtDuration(v.duration)}{v.indexed ? " · searchable" : ""}</p>
            <div className="row">
              <button type="button" className="btn tiny" onClick={() => setPlaying(playing === v.id ? null : v.id)}><Icon name="play" size={12} /> {playing === v.id ? "Hide" : "Play"}</button>
              <button type="button" className="btn tiny" onClick={() => d.revealPath(v.file)}>Finder</button>
            </div>
          </div>
        ))}
      </div>
      {folder.count > folder.videos.length && <p className="hint">Showing the newest {folder.videos.length} of {folder.count}.</p>}
    </div>
  );
}

function Favourites() {
  const d = useDesk();
  const accounts = useMemo(() => [...new Set(d.favs.map((f: { account: string }) => f.account))].sort() as string[], [d.favs]);
  const filter = d.favFilter !== "all" && !accounts.includes(d.favFilter) ? "all" : d.favFilter;
  const shown = d.favs
    .filter((f: { account: string }) => filter === "all" || f.account === filter)
    .map((f: { id: string }) => ({ ...f, rid: f.id }));
  return (
    <div style={{ marginTop: 18 }}>
      <div className="spread" style={{ marginBottom: 12 }}>
        <div className="chips">
          <button type="button" className={cn("chip", filter === "all" && "on")} onClick={() => d.setFavFilter("all")}>All</button>
          {accounts.map((a) => (
            <button type="button" key={a} className={cn("chip", filter === a && "on")} onClick={() => d.setFavFilter(a)}>@{a}</button>
          ))}
        </div>
        <button type="button" className="btn tiny" onClick={() => d.openFolder("favourites")}>Open favourites folder</button>
      </div>
      {shown.length ? (
        <ContactSheet items={shown} />
      ) : (
        <div className="empty">
          <h2>No favourites yet.</h2>
          <p className="hint">Press the star on any image to keep it here. Starring copies the picture into favourites/&lt;account&gt;/ and records the link.</p>
        </div>
      )}
      <p className="hint" style={{ marginTop: 10 }}>{d.favs.length} favourite{d.favs.length === 1 ? "" : "s"} in total.</p>
    </div>
  );
}
