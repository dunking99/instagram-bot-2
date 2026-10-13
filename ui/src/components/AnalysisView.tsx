import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, post, usePref } from "../api";
import { useDesk } from "../store";
import { cn } from "../utils/cn";

type Status = "completed" | "saved" | "current" | "outdated" | "waiting" | "failed" | "running" | "queued";
type Row = {
  name: string; title: string; creator: string; status: Status; hasFile: boolean; path: string | null;
  verified: boolean; completed: boolean; confidence: number | null; sections: number; draftedAt: number | null;
  outdated: boolean; duration: number | null; timeline: [string, number, number][]; error: string | null; queuePos: number | null;
};
type Data = {
  videos: Row[]; counts: Partial<Record<Status, number>>; running: boolean; current: string | null; queued: number;
  done: number; failedNow: number; paused: boolean; model: { trainedAt: number; videos: number; frames: number | null };
  colours: Record<string, string>;
};

const META: Record<Status, { label: string; short: string; tone: string; hint: string }> = {
  completed: { label: "Verified", short: "Verified", tone: "good", hint: "You checked and completed this one. The model never overwrites it." },
  saved: { label: "Saved by you", short: "Saved", tone: "good2", hint: "You saved corrections but have not marked it completed." },
  current: { label: "Model · up to date", short: "Up to date", tone: "ok", hint: "The model's draft, made by the current model." },
  outdated: { label: "Model · older version", short: "Older model", tone: "warn", hint: "The model's draft, made before the latest retrain. Worth re-running." },
  waiting: { label: "Not analysed yet", short: "Waiting", tone: "idle", hint: "In the library, but the model has not looked at it." },
  failed: { label: "Failed", short: "Failed", tone: "bad", hint: "The last attempt failed. Retry, or see the message." },
  running: { label: "Analysing now", short: "Running", tone: "run", hint: "The model is working on this right now." },
  queued: { label: "Queued", short: "Queued", tone: "queue", hint: "Waiting its turn." },
};
const ORDER: Status[] = ["failed", "running", "queued", "waiting", "outdated", "current", "saved", "completed"];
const FILTERS: [string, string][] = [
  ["all", "All"], ["todo", "Needs analysis"], ["verified", "Verified"], ["current", "Up to date"],
  ["outdated", "Older model"], ["waiting", "Waiting"], ["failed", "Failed"], ["active", "Running / queued"],
];
const inFilter = (r: Row, f: string) => {
  if (f === "all") return true;
  if (f === "todo") return r.status === "waiting" || r.status === "failed" || r.status === "outdated";
  if (f === "verified") return r.verified;
  if (f === "active") return r.status === "running" || r.status === "queued";
  return r.status === f;
};

const hms = (s: number) => {
  const t = Math.round(s);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60);
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}` : `${m}:${String(t % 60).padStart(2, "0")}`;
};
const ago = (ms: number | null) => {
  if (!ms) return "";
  const m = Math.round((Date.now() - ms) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
};

function Timeline({ row, colours }: { row: Row; colours: Record<string, string> }) {
  const total = row.duration || Math.max(1, ...row.timeline.map((t) => t[2]));
  if (!row.timeline.length) return <div className="an-tl empty">{row.status === "waiting" || row.status === "failed" ? "no sections yet" : "no position sections"}</div>;
  return (
    <div className="an-tl" aria-label="Positions across the video">
      {row.timeline.map(([pos, a, b], i) => (
        <i
          key={i}
          style={{ left: `${(a / total) * 100}%`, width: `${Math.max(((b - a) / total) * 100, 0.4)}%`, background: colours[pos] || "#8a8178" }}
          title={`${pos.replace(/_/g, " ")}  ${hms(a)}–${hms(b)}`}
        />
      ))}
    </div>
  );
}

function Meter({ value }: { value: number | null }) {
  if (value == null) return <span className="hint">–</span>;
  const tone = value >= 0.6 ? "hi" : value >= 0.45 ? "mid" : "lo";
  return (
    <div className="an-meter" title={`Mean model confidence ${value.toFixed(2)}. Under 0.45 usually means a messy draft.`}>
      <b><i className={tone} style={{ width: `${Math.min(value, 1) * 100}%` }} /></b>
      <span>{value.toFixed(2)}</span>
    </div>
  );
}

export function AnalysisView() {
  const d = useDesk();
  const [data, setData] = useState<Data | null>(null);
  const [filter, setFilter] = usePref("analysis.filter", "all");
  const [sort, setSort] = usePref("analysis.sort", "status");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      setData(await api<Data>("/api/analysis/videos"));
    } catch (e) {
      d.fail(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { load(); }, [load, d.dataVersion]);
  useEffect(() => {
    window.clearInterval(timer.current);
    timer.current = window.setInterval(load, data?.running || data?.queued ? 3000 : 15000);
    return () => window.clearInterval(timer.current);
  }, [load, data?.running, data?.queued]);

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    let list = data.videos.filter((r) => inFilter(r, filter) && (!needle || `${r.title} ${r.creator}`.toLowerCase().includes(needle)));
    const cmp: Record<string, (a: Row, b: Row) => number> = {
      status: (a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || a.creator.localeCompare(b.creator) || a.title.localeCompare(b.title),
      name: (a, b) => a.title.localeCompare(b.title),
      creator: (a, b) => a.creator.localeCompare(b.creator) || a.title.localeCompare(b.title),
      confidence: (a, b) => (a.confidence ?? 9) - (b.confidence ?? 9),
      length: (a, b) => (b.duration ?? 0) - (a.duration ?? 0),
    };
    list = [...list].sort(cmp[sort] || cmp.status);
    return list;
  }, [data, filter, sort, q]);

  const c = data?.counts || {};
  const n = (...k: Status[]) => k.reduce((s, x) => s + (c[x] || 0), 0);
  const total = data?.videos.length || 0;
  const needs = n("waiting", "failed", "outdated");
  const groups: { key: string; label: string; count: number; tone: string; f: string }[] = [
    { key: "v", label: "Verified by you", count: (data?.videos || []).filter((r) => r.verified).length, tone: "good", f: "verified" },
    { key: "c", label: "Model, up to date", count: n("current"), tone: "ok", f: "current" },
    { key: "o", label: "Model, older version", count: n("outdated"), tone: "warn", f: "outdated" },
    { key: "w", label: "Not analysed yet", count: n("waiting"), tone: "idle", f: "waiting" },
    { key: "f", label: "Failed", count: n("failed"), tone: "bad", f: "failed" },
  ];

  const queue = async (body: object, label: string) => {
    setBusy(true);
    try {
      const r = await post<{ added: number; started: boolean; skipped: number }>("/api/analysis/queue", body);
      d.toast(r.added ? `${label}: ${r.added} video${r.added === 1 ? "" : "s"} queued` : "Nothing to add: already queued or running");
      setSel(new Set());
      await load();
    } catch (e) {
      d.fail(e);
    }
    setBusy(false);
  };
  const runSelected = () => {
    const names = [...sel];
    const verified = data!.videos.filter((r) => sel.has(r.name) && r.verified).length;
    if (verified && !window.confirm(
      `${verified} of the ${names.length} selected videos are ones you verified.\n\nTheir saved versions, completed marks, excluded frames and the training data are NOT touched. Only the model's own draft for them is replaced (the old draft is kept under Compare versions).\n\nRun the model on all ${names.length}?`)) return;
    queue({ names }, "Selected");
  };
  const stop = async () => {
    try {
      const r = await post<{ cleared: number }>("/api/analysis/cancel", {});
      d.toast(`Queue cleared (${r.cleared}). Stopping after the current video.`);
      await load();
    } catch (e) {
      d.fail(e);
    }
  };
  const toggle = (name: string) => setSel((s) => { const x = new Set(s); if (x.has(name)) x.delete(name); else x.add(name); return x; });
  const allShown = rows.length > 0 && rows.every((r) => sel.has(r.name));

  const keyPositions = ["Blowjob", "Doggystyle", "Missionary", "Cowgirl", "Reverse_Cowgirl", "Spooning", "Standing_Doggystyle", "Eating_Out"];

  return (
    <div className="an">
      <p className="kicker">Analysis</p>
      <h1 style={{ fontSize: "clamp(32px, 4vw, 48px)" }}>Every video, and what the model made of it.</h1>
      <p className="lede">
        {data
          ? `${total} videos. The current model was trained ${new Date(data.model.trainedAt).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} on ${data.model.videos} of your videos. Videos you verified are never overwritten by anything on this page.`
          : "Loading..."}
      </p>

      {data && (
        <>
          <div className="an-bar" aria-hidden>
            {groups.map((g) => g.count > 0 && <i key={g.key} className={g.tone} style={{ flex: g.count }} title={`${g.label}: ${g.count}`} />)}
          </div>
          <div className="an-cards">
            {groups.map((g) => (
              <button key={g.key} type="button" className={cn("an-card", g.tone, filter === g.f && "on")} onClick={() => setFilter(filter === g.f ? "all" : g.f)}>
                <b>{g.count}</b><span>{g.label}</span>
              </button>
            ))}
          </div>

          {(data.running || data.queued > 0) && (
            <div className="an-run">
              <div className="an-run-bar"><i /></div>
              <div className="spread" style={{ gap: 10 }}>
                <span>
                  <strong>Analysing</strong> {data.current ? `"${data.videos.find((v) => v.name === data.current)?.title || data.current}"` : "..."}
                  <span className="hint"> · {data.queued} still queued · {data.done} done this run{data.failedNow ? ` · ${data.failedNow} failed` : ""}</span>
                </span>
                <button type="button" className="btn tiny danger" onClick={stop}>Stop after this one</button>
              </div>
            </div>
          )}

          <div className="an-tools">
            <button type="button" className="btn primary" disabled={busy || !needs} onClick={() => queue({ scope: "todo" }, "Everything that needs it")}
              title="Videos not analysed yet, ones that failed, and drafts from an older model. Verified videos are skipped.">
              Analyse everything that needs it ({needs})
            </button>
            <button type="button" className="btn" onClick={() => setSel(allShown ? new Set() : new Set(rows.map((r) => r.name)))}>
              {allShown ? "Clear selection" : `Select all${filter === "all" && !q ? "" : " shown"} (${rows.length})`}
            </button>
            {sel.size > 0 && (
              <button type="button" className="btn gold" disabled={busy} onClick={runSelected}>Re-run the model on {sel.size} selected</button>
            )}
            <span className="sp" />
            <input type="text" className="textin" placeholder="Search title or creator" value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 220 }} />
            <select className="textin" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="status">Sort: needs attention first</option>
              <option value="name">Sort: title</option>
              <option value="creator">Sort: creator</option>
              <option value="confidence">Sort: lowest confidence</option>
              <option value="length">Sort: longest</option>
            </select>
          </div>
          <div className="chips" style={{ margin: "10px 0 6px" }}>
            {FILTERS.map(([id, label]) => (
              <button key={id} type="button" className={cn("chip", filter === id && "on")} onClick={() => setFilter(id)}>{label}</button>
            ))}
          </div>
          <div className="an-legend">
            {keyPositions.filter((p) => data.colours[p]).map((p) => (
              <span key={p}><i style={{ background: data.colours[p] }} />{p.replace(/_/g, " ")}</span>
            ))}
            <span className="hint">the strip on each row is the video from start to end</span>
          </div>

          <div className="an-list">
            {rows.map((r) => {
              const m = META[r.status];
              return (
                <div key={r.name} className={cn("an-row", m.tone, sel.has(r.name) && "sel")}>
                  <label className="an-chk"><input type="checkbox" checked={sel.has(r.name)} onChange={() => toggle(r.name)} /></label>
                  <div className="an-status" title={m.hint}>
                    <span className={cn("an-pill", m.tone)}>{r.status === "queued" && r.queuePos ? `Queued #${r.queuePos}` : m.short}</span>
                    {r.verified && r.outdated && <em title="Your saved version is what the dashboard shows. The model's own draft for this video is from an older model.">draft older</em>}
                  </div>
                  <div className="an-title">
                    <strong title={r.name}>{r.title}</strong>
                    <span className="hint">{r.creator}{!r.hasFile ? " · file not in library" : ""}</span>
                    {r.error && <span className="an-err" title={r.error}>{r.error.split("\n").pop()}</span>}
                  </div>
                  <Timeline row={r} colours={data.colours} />
                  <div className="an-conf">
                    {r.verified ? <span className="an-ver">checked by you</span> : <Meter value={r.confidence} />}
                  </div>
                  <div className="an-meta hint">
                    {r.duration ? hms(r.duration) : "–"}{r.sections ? ` · ${r.sections} sections` : ""}
                    {r.draftedAt ? <><br />{ago(r.draftedAt)}</> : null}
                  </div>
                  <div className="an-act">
                    {r.status === "running" && <span className="hint">working...</span>}
                    {r.status === "queued" && <span className="hint">waiting</span>}
                    {(r.status === "waiting" || r.status === "failed") && (
                      <button type="button" className="btn tiny primary" disabled={busy || !r.hasFile} onClick={() => queue({ names: [r.name] }, r.title)}>
                        {r.status === "failed" ? "Retry" : "Analyse"}
                      </button>
                    )}
                    {(r.status === "current" || r.status === "outdated") && (
                      <button type="button" className={cn("btn tiny", r.status === "outdated" && "gold")} disabled={busy} onClick={() => queue({ names: [r.name] }, r.title)}>Re-run</button>
                    )}
                    {(r.status === "saved" || r.status === "completed") && (
                      <button type="button" className="btn tiny ghost" disabled={busy} title="Your saved version stays exactly as it is. Only the model's own draft is replaced."
                        onClick={() => { if (window.confirm(`Re-run the model on "${r.title}"?\n\nYour verified version is NOT changed. Only the model's own draft is replaced, and the old draft is kept under Compare versions.`)) queue({ names: [r.name] }, r.title); }}>
                        Re-run model
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
            {!rows.length && <p className="hint" style={{ padding: 24 }}>Nothing matches.</p>}
          </div>
        </>
      )}
    </div>
  );
}
