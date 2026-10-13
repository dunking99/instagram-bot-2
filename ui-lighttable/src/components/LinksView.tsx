import { useCallback, useEffect, useRef, useState } from "react";
import { api, post, usePref } from "../api";
import { useDesk } from "../store";
import { openReview } from "./AnalysisView";

type LinksState = { running: boolean; url: string; exists?: boolean };

type FramesJob = {
  id: string; running: boolean; phase: "queued" | "starting" | "finding" | "indexing" | "grabbing" | "model" | "done" | "error";
  message?: string; error?: string; name?: string; url?: string; done?: number; total?: number; mb?: number;
  range_start?: number; range_end?: number; video_length?: number; progress?: number; eta_seconds?: number | null; started?: number; t_frames?: number; t_model?: number;
  frames?: number; fetched_mb?: number; file_mb?: number; percent_fetched?: number | null; sections?: number | null; failed?: number; seconds?: number;
};

const ACTIVE = ["queued", "starting", "finding", "indexing", "grabbing", "model"];

/** "2:00", "1:05:30" or just minutes ("8", "2.5") -> seconds. Empty -> 0. Anything else -> NaN. */
function toSeconds(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  if (/^\d+(\.\d+)?$/.test(t)) return Math.round(parseFloat(t) * 60);
  const m = t.match(/^(?:(\d+):)?(\d{1,2}):(\d{2})$/);
  return m ? (Number(m[1] || 0) * 3600 + Number(m[2]) * 60 + Number(m[3])) : NaN;
}
const STAGES: { id: FramesJob["phase"][]; label: string }[] = [
  { id: ["starting", "finding"], label: "Find the video" },
  { id: ["indexing"], label: "Read its index" },
  { id: ["grabbing"], label: "Take frames" },
  { id: ["model"], label: "Run the model" },
];
const clock = (sec: number) => {
  const s = Math.round(sec);
  return s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

/** A labelled progress bar for the whole job: the four stages, the percentage, frames done and the time left. */
function Progress({ job }: { job: FramesJob }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(t); }, []);
  const pct = Math.max(1, Math.min(100, Math.round(job.progress ?? 1)));
  const at = STAGES.findIndex((st) => st.id.includes(job.phase));
  const elapsed = job.started ? Math.max(0, now / 1000 - job.started) : 0;
  const detail =
    job.phase === "grabbing"
      ? `${job.done ?? 0} of ${job.total ?? "?"} frames${job.mb != null ? ` · ${job.mb} MB read` : ""}${job.eta_seconds != null && (job.done ?? 0) > 2 ? ` · about ${clock(job.eta_seconds)} left` : ""}`
      : job.message ?? "";
  return (
    <div className="frames-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="fp-head"><span>{job.phase === "queued" ? "Waiting its turn" : STAGES[Math.max(at, 0)].label}</span><b>{pct}%</b><span className="hint">{clock(elapsed)} elapsed</span></div>
      <div className="fp-bar"><i style={{ width: `${pct}%` }} /></div>
      <div className="fp-stages">
        {STAGES.map((st, i) => <span key={st.label} className={i < at ? "done" : i === at ? "on" : ""}>{i < at ? "✓ " : ""}{st.label}</span>)}
      </div>
      <p className="hint">{detail}</p>
    </div>
  );
}

const rangeText = (j: FramesJob) =>
  j.range_start != null && (j.range_start > 0 || (j.range_end != null && j.video_length != null && j.range_end < j.video_length))
    ? ` (${clock(j.range_start)} to ${clock(j.range_end ?? 0)} of the video)` : "";

/** One video of the batch: its progress while it works, then what it produced. */
function JobCard({ job }: { job: FramesJob }) {
  const d = useDesk();
  const active = ACTIVE.includes(job.phase);
  const title = job.name || job.url || "video";
  return (
    <div className="frames-job">
      <div className="fj-title" title={job.url}>{title}</div>
      {job.phase === "error" && <p className="hint warn">{job.error}</p>}
      {active && <Progress job={job} />}
      {job.phase === "done" && (
        <>
          <p className="hint sage">
            {job.frames} frames{rangeText(job)} are in the model dashboard{job.sections ? `, drafted into ${job.sections} sections` : ""}. Read {job.fetched_mb} MB of a {job.file_mb} MB video
            {job.percent_fetched != null ? ` (${job.percent_fetched}%)` : ""}; the video itself was never saved.{job.seconds != null ? ` Took ${clock(job.seconds)}.` : ""}{job.failed ? ` ${job.failed} frame(s) could not be read.` : ""}
          </p>
          <div className="row">
            <button type="button" className="btn" onClick={() => openReview(d.fail, job.name)}>Open in the model dashboard</button>
            <button type="button" className="btn" onClick={() => d.setView("analysis")}>Show in Analysis</button>
          </div>
        </>
      )}
    </div>
  );
}

/** Frames from video page links without downloading the videos; they go straight into the model dashboard and the model runs on them.
 *  Paste several links (one per line): up to three are taken at the same time, the rest wait their turn. */
function FramesBar({ onHeight }: { onHeight: (h: number) => void }) {
  const d = useDesk();
  const [open, setOpen] = usePref("links.frames.open", false);
  const [links, setLinks] = usePref("links.frames.url", "");
  const [every, setEvery] = usePref("links.frames.every", "5");
  const [ids, setIds] = usePref<string[]>("links.frames.jobs", []);
  const [jobs, setJobs] = useState<Record<string, FramesJob>>({});
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(() => onHeight(ref.current?.offsetHeight ?? 0));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [onHeight]);

  const poll = useCallback(async () => {
    if (!ids.length) return;
    try {
      const r = await api<{ jobs: FramesJob[] }>("/lt/frames/list");
      const m: Record<string, FramesJob> = {};
      for (const j of r.jobs) m[j.id] = j;
      setJobs(m);
      const kept = ids.filter((id) => m[id]);                  // after a server restart the old jobs are gone
      if (kept.length !== ids.length) setIds(kept);
    } catch { /* keep what is shown */ }
  }, [ids, setIds]);
  useEffect(() => { poll(); }, [poll]);
  const mine = ids.map((id) => jobs[id]).filter(Boolean) as FramesJob[];
  const active = mine.filter((j) => ACTIVE.includes(j.phase));
  useEffect(() => {
    if (!active.length) return;
    const t = window.setInterval(poll, 1000);
    return () => window.clearInterval(t);
  }, [active.length, poll]);

  const urls = links.split("\n").map((x) => x.trim()).filter(Boolean);
  const start = async () => {
    try {
      const startSeconds = toSeconds(from), endSeconds = toSeconds(to);
      if (Number.isNaN(startSeconds) || Number.isNaN(endSeconds)) throw new Error("Times look like 2:00, 8:30 or just minutes (2, 8.5). Leave a box empty for the start or end of the video.");
      if (endSeconds && endSeconds <= startSeconds) throw new Error("The end of the section has to be after its start.");
      const started: string[] = [];
      for (const url of urls) {
        const r = await post<{ id: string }>("/lt/frames/start", { url, every: Number(every), startSeconds, endSeconds });
        started.push(r.id);
      }
      setIds([...started, ...ids].slice(0, 30));
      setLinks("");
    } catch (e) { d.fail(e); }
  };
  const done = mine.filter((j) => j.phase === "done").length, failed = mine.filter((j) => j.phase === "error").length;
  const waiting = mine.filter((j) => j.phase === "queued").length;

  return (
    <div className="frames-bar" ref={ref}>
      <button type="button" className="frames-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "▾" : "▸"} Frames from video links <span className="hint">no download: only the parts of each video that are needed are read</span>
        {active.length > 0 && <b className="frames-live"> · working on {active.length} video{active.length === 1 ? "" : "s"}</b>}
      </button>
      {open && (
        <div className="frames-body">
          <div className="row" style={{ alignItems: "flex-start" }}>
            <textarea className="textin" style={{ flex: 1, minWidth: 260, resize: "vertical" }} rows={Math.min(5, Math.max(1, links.split("\n").length))}
              placeholder={"Paste the link of the page that plays the video.\nOne link per line to take several videos."} value={links} onChange={(e) => setLinks(e.target.value)} />
            <label className="row" style={{ gap: 6 }}><span className="hint">a frame every</span>
              <select value={every} onChange={(e) => setEvery(e.target.value)}>{["2", "5", "10", "15", "30"].map((x) => <option key={x} value={x}>{x} s</option>)}</select>
            </label>
            <button type="button" className="btn" disabled={!urls.length} onClick={start}>{urls.length > 1 ? `Get frames (${urls.length} videos)` : "Get frames"}</button>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <span className="hint">Only this part of each video:</span>
            <input type="text" className="textin frames-time" placeholder="from 0:00" aria-label="From" value={from} onChange={(e) => setFrom(e.target.value)} />
            <span className="hint">to</span>
            <input type="text" className="textin frames-time" placeholder="the end" aria-label="To" value={to} onChange={(e) => setTo(e.target.value)} />
            <span className="hint">Times like 2:00 and 8:00, or just minutes (2 and 8). Leave both empty for whole videos. Up to 3 videos are taken at once; the rest wait.</span>
          </div>
          {mine.length > 0 && (
            <div className="frames-status">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <b className="hint">{done} of {mine.length} done{waiting ? ` · ${waiting} waiting` : ""}{failed ? ` · ${failed} failed` : ""}</b>
                {mine.length > active.length && <button type="button" className="btn" style={{ minHeight: 28, padding: "0 10px" }} onClick={() => setIds(ids.filter((id) => jobs[id] && ACTIVE.includes(jobs[id].phase)))}>Clear finished</button>}
              </div>
              {mine.map((j) => <JobCard key={j.id} job={j} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// The Links tool (scrape, sort, download) runs as its own small server; this page starts it and shows it in place.
export function LinksView() {
  const [state, setState] = useState<"starting" | "ready" | "failed">("starting");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [barH, setBarH] = useState(44);

  const start = async () => {
    setState("starting");
    setError("");
    try {
      const s = await api<LinksState>("/api/links/status");
      const r = s.running ? s : await post<LinksState>("/api/links/start", {});
      setUrl(r.url);
      setState("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState("failed");
    }
  };
  useEffect(() => { start(); }, []);

  return (
    <>
      <FramesBar onHeight={setBarH} />
      {state !== "ready" ? (
        <div className="section" style={{ padding: 32, marginTop: barH }}>
          <p className="kicker">Links</p>
          <h3>{state === "starting" ? "Starting Links..." : "Links could not start"}</h3>
          {error && <p className="hint">{error}</p>}
          {state === "failed" && <button type="button" className="btn" onClick={start}>Try again</button>}
        </div>
      ) : (
        <iframe title="Links" src={url} className="links-frame" style={{ top: `calc(var(--top-h) + ${barH}px)`, height: `calc(100vh - var(--top-h) - ${barH}px)` }} />
      )}
    </>
  );
}
