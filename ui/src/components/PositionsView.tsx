import { useCallback, useEffect, useRef, useState } from "react";
import { api, post, usePref } from "../api";
import { useDesk } from "../store";
import { cn } from "../utils/cn";
import type { Item } from "../types";

type PositionRow = { name: string; videos: number; verified: number; minutes: number };
type PositionList = { positions: PositionRow[]; built: string; videos: number; verifiedVideos: number; missingFiles: number };
type Clip = {
  id: string; video: string; title: string; creator: string; position: string; startS: number; endS: number;
  sectionStart: number; sectionEnd: number; source: "verified" | "model"; confidence: number | null;
  url: string; offset: number; file: string;
};
type VideoRow = { name: string; title: string; creator: string; verified: boolean; seconds: number; hasFile: boolean };

const LENGTHS: [string, number][] = [["15 seconds", 15], ["30 seconds", 30], ["1 minute", 60], ["2 minutes", 120], ["5 minutes", 300], ["Whole section", 0]];
const CONF: [string, number][] = [["Any confidence", 0], ["At least 0.4", 0.4], ["At least 0.5", 0.5], ["At least 0.6", 0.6]];

const toItem = (c: Clip): Item => ({
  id: c.id, rid: c.id, account: c.creator, url: null, slide: null, name: c.title, score: null, date: null, type: "local",
  original: c.file, video: true, hasThumb: false, thumb: null, full: null, src: "", noFav: true,
  videoName: c.title,
  clip: { url: c.url, start: c.offset, position: c.position, title: c.title, creator: c.creator,
          range: `${Math.floor(c.startS / 60)}:${String(Math.round(c.startS % 60)).padStart(2, "0")}–${Math.floor(c.endS / 60)}:${String(Math.round(c.endS % 60)).padStart(2, "0")}`,
          source: c.source, confidence: c.confidence },
});

const hms = (s: number) => {
  const t = Math.round(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

export function PositionsView() {
  const d = useDesk();
  const [list, setList] = useState<PositionList | null>(null);
  const [position, setPosition] = usePref("positions.position", "Doggystyle");
  const [count, setCount] = usePref("positions.count", 10);
  const [seconds, setSeconds] = usePref("positions.seconds", 30);
  const [verifiedOnly, setVerifiedOnly] = usePref("positions.verifiedOnly", false);
  const [minConf, setMinConf] = usePref("positions.minConf", 0);
  const [video, setVideo] = useState("");
  const [tab, setTab] = useState<"clips" | "videos">("clips");
  const [clips, setClips] = useState<Clip[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [vids, setVids] = useState<{ with: VideoRow[]; without: VideoRow[] } | null>(null);

  useEffect(() => {
    api<PositionList>("/api/positions").then(setList).catch((e) => d.fail(e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.dataVersion]);

  const body = (extra: object = {}) => ({ position, count, seconds, verifiedOnly, minConf, video: video.trim() || null, ...extra });

  const show = useCallback(async () => {
    setBusy(true);
    setNote("");
    try {
      const r = await post<{ clips: Clip[]; requested: number; found: number }>("/api/positions/clips", body());
      setClips(r.clips);
      if (!r.found) setNote("Nothing matches. Try a shorter clip, a lower confidence, or untick verified only.");
      else if (r.found < r.requested && !video.trim()) setNote(`Only ${r.found} videos have a long enough ${position} section.`);
    } catch (e) {
      d.fail(e);
    }
    setBusy(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [position, count, seconds, verifiedOnly, minConf, video]);

  // Slideshow: the clips play one after another full screen, and new ones are fetched as the end gets close
  const shown = useRef<Set<string>>(new Set());
  const slideshow = async () => {
    let list = clips;
    if (!list.length) {
      setBusy(true);
      try {
        const r = await post<{ clips: Clip[] }>("/api/positions/clips", body());
        list = r.clips;
        setClips(list);
      } catch (e) {
        d.fail(e);
      }
      setBusy(false);
    }
    if (!list.length) { setNote("Nothing matches. Try a shorter clip, a lower confidence, or untick verified only."); return; }
    shown.current = new Set(list.map((c) => c.video));
    const more = async (): Promise<Item[]> => {
      let r = await post<{ clips: Clip[] }>("/api/positions/clips", body({ excludeVideos: [...shown.current] }));
      if (!r.clips.length) {                                  // every matching video has been shown: start the round again
        shown.current = new Set();
        r = await post<{ clips: Clip[] }>("/api/positions/clips", body());
      }
      r.clips.forEach((c) => shown.current.add(c.video));
      return r.clips.map(toItem);
    };
    d.openSlides(list.map(toItem), 0, true, more);
  };

  const another = async (i: number) => {
    try {
      const r = await post<{ clips: Clip[] }>("/api/positions/clips", body({ count: 1, excludeVideos: clips.map((c) => c.video) }));
      if (!r.clips.length) { d.toast("No other video has a matching section"); return; }
      setClips(clips.map((c, k) => (k === i ? r.clips[0] : c)));
    } catch (e) {
      d.fail(e);
    }
  };

  const loadVideos = useCallback(async () => {
    try {
      setVids(await api(`/api/positions/videos?position=${encodeURIComponent(position)}`));
    } catch (e) {
      d.fail(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [position]);
  useEffect(() => { if (tab === "videos") loadVideos(); }, [tab, loadVideos, d.dataVersion]);

  const cur = list?.positions.find((p) => p.name === position);

  return (
    <div>
      <p className="kicker">Positions</p>
      <h1 style={{ fontSize: "clamp(32px, 4vw, 48px)" }}>Find clips by position.</h1>
      <p className="lede">
        Pick a position and get clips taken from the parts of your videos where the model (or you) marked it. Every video is analysed automatically when it lands in the library.
      </p>

      <div className="panel panelbox" style={{ marginTop: 14 }}>
        <div className="row" style={{ alignItems: "flex-end", gap: 14 }}>
          <label className="field">
            <span>Position</span>
            <select value={position} onChange={(e) => setPosition(e.target.value)} className="textin">
              {(list?.positions || []).map((p) => (
                <option key={p.name} value={p.name}>{p.name.replace(/_/g, " ")} ({p.videos} videos)</option>
              ))}
            </select>
          </label>
          <label className="field" style={{ width: 90 }}>
            <span>Videos</span>
            <input type="number" min={1} max={60} value={count} onChange={(e) => setCount(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} />
          </label>
          <label className="field">
            <span>Clip length</span>
            <select value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} className="textin">
              {LENGTHS.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Model confidence</span>
            <select value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} className="textin">
              {CONF.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field" style={{ minWidth: 190 }}>
            <span>Only this video / creator (optional)</span>
            <input type="text" value={video} placeholder="part of a name" onChange={(e) => setVideo(e.target.value)} />
          </label>
          <button type="button" className={cn("signal", verifiedOnly && "on")} onClick={() => setVerifiedOnly(!verifiedOnly)}>
            Verified videos only
          </button>
          <button type="button" className="btn primary" disabled={busy || !position} onClick={show}>
            {busy ? "Cutting clips..." : clips.length ? "Shuffle again" : "Show clips"}
          </button>
          <button type="button" className="btn gold" disabled={busy || !position} onClick={slideshow} title="Play the clips one after another, full screen, and keep going with new ones">
            ▶ Slideshow
          </button>
        </div>
        {list && (
          <p className="hint" style={{ marginTop: 10 }}>
            {list.videos} analysed videos, {list.verifiedVideos} verified by you; the rest are the model's guess (with its confidence shown). {cur ? `${cur.name.replace(/_/g, " ")}: ${cur.videos} videos, about ${cur.minutes} minutes in total.` : ""}
            {list.missingFiles ? ` ${list.missingFiles} video file(s) not found in the library are skipped.` : ""}
          </p>
        )}
      </div>

      <div className="row" style={{ marginTop: 14 }}>
        <button type="button" className={cn("chip", tab === "clips" && "on")} onClick={() => setTab("clips")}>Clips</button>
        <button type="button" className={cn("chip", tab === "videos" && "on")} onClick={() => setTab("videos")}>Which videos have it</button>
      </div>

      {tab === "clips" && (
        <>
          {note && <p className="hint warn" style={{ marginTop: 12 }}>{note}</p>}
          {!clips.length && !busy && !note && <p className="hint" style={{ marginTop: 16 }}>Choose a position and press Show clips.</p>}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 14, marginTop: 14 }}>
            {clips.map((c, i) => (
              <article key={c.id} className="panel panelbox" style={{ padding: 10 }}>
                <video
                  src={c.offset ? `${c.url}#t=${c.offset}` : c.url}
                  controls
                  preload="metadata"
                  playsInline
                  loop
                  style={{ width: "100%", maxHeight: 360, background: "#000", borderRadius: 6 }}
                />
                <div className="spread" style={{ marginTop: 8 }}>
                  <strong>{c.position.replace(/_/g, " ")}</strong>
                  <span className={cn("hint", c.source === "verified" ? "sage" : "warn")}>
                    {c.source === "verified" ? "verified" : `model guess${c.confidence != null ? `, ${c.confidence.toFixed(2)}` : ""}`}
                  </span>
                </div>
                <p style={{ margin: "4px 0 0", fontSize: 13.5 }}>{c.title}</p>
                <p className="hint">{c.creator} · clip {hms(c.startS)}–{hms(c.endS)} · section {hms(c.sectionStart)}–{hms(c.sectionEnd)}</p>
                <div className="row" style={{ marginTop: 8 }}>
                  <button type="button" className="btn tiny" onClick={() => another(i)}>Another video</button>
                  <button type="button" className="btn tiny" onClick={() => post("/api/reveal", { path: c.file }).catch((e) => d.fail(e))}>Show file</button>
                </div>
              </article>
            ))}
          </div>
        </>
      )}

      {tab === "videos" && (
        <div style={{ marginTop: 14 }}>
          {!vids && <p className="hint">Loading...</p>}
          {vids && (
            <>
              <p className="hint">{vids.with.length} videos have {position.replace(/_/g, " ")}, {vids.without.length} do not.</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 18, marginTop: 10 }}>
                {([["Has it", vids.with, true], ["Doesn't have it", vids.without, false]] as [string, VideoRow[], boolean][]).map(([label, rows, has]) => (
                  <section key={label}>
                    <h3>{label} <span className="hint">{rows.length}</span></h3>
                    <div style={{ maxHeight: 520, overflow: "auto", marginTop: 6 }}>
                      {rows.map((v) => (
                        <div key={v.name} className="spread" style={{ padding: "5px 0", borderBottom: "1px solid var(--line)" }}>
                          <span style={{ fontSize: 13.5 }}>{v.title}<span className="hint"> · {v.creator}</span></span>
                          <span className="hint">{has ? `${hms(v.seconds)} · ` : ""}{v.verified ? "verified" : "model"}</span>
                        </div>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
