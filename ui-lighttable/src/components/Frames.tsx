import { useEffect, useRef, useState } from "react";
import { api, fmtDuration } from "../api";
import { itemLabel, type Item } from "../types";
import { useDesk } from "../store";
import { cn } from "../utils/cn";
import { Check, Icon, Star } from "./ui";

export function downloadName(item: Item) {
  if (item.filename) return item.filename;
  return `${item.account}_${item.name.replace("@", "_s")}${item.score != null ? `_${item.score}` : ""}.jpg`;
}

export function downloadHref(item: Item) {
  return `/api/download?p=${encodeURIComponent(item.src)}&name=${encodeURIComponent(downloadName(item))}`;
}

/** "Open on Instagram" for Instagram images, "Show in Finder" for images that came from a folder. */
export function SourceButton({ item, className = "fav" }: { item: Item; className?: string }) {
  const desk = useDesk();
  if (item.type === "instagram" && item.url) {
    return (
      <a className={className} href={item.url} target="_blank" rel="noreferrer" aria-label="Open on Instagram" title="Open on Instagram">
        <Icon name="external" size={14} />
      </a>
    );
  }
  if (!item.original) return null;
  return (
    <button type="button" className={className} aria-label="Show in Finder" title="Show in Finder" onClick={() => desk.revealPath(item.original)}>
      <Icon name="folder" size={14} />
    </button>
  );
}

export function FrameCard({ item, index, selected, showSelect, pool }: {
  item: Item;
  index: number;
  selected?: boolean;
  showSelect?: boolean;
  pool?: Item[];
}) {
  const desk = useDesk();
  const faved = desk.isFav(item.id);
  const [broken, setBroken] = useState(false);
  const open = () => {
    const items = pool && pool.length ? pool : [item];
    const at = items.findIndex((r) => (r.rid || r.id) === (item.rid || item.id));
    desk.openSlides(items, at >= 0 ? at : 0, false);
  };
  return (
    <article className={cn("frame", selected && "sel", faved && "faved")}>
      {faved && (
        <svg className="mark-svg" viewBox="0 0 80 100" preserveAspectRatio="none" aria-hidden="true">
          <path pathLength="1" d="M7 52 C4 22 30 5 54 8 C78 11 80 58 64 82 C48 101 12 95 9 62 C7 48 12 36 21 28" />
        </svg>
      )}
      {showSelect && (
        <button type="button" className="tick" aria-label={selected ? "Deselect frame" : "Select frame"} onClick={() => desk.toggleSelected(item.rid)}>
          <Check />
        </button>
      )}
      {item.score != null && <span className={cn("score-pill", item.score < 0.45 && "low")}>{item.score.toFixed(3)}</span>}
      <button type="button" className="open" onClick={open} aria-label="Open">
        {item.thumb && !broken ? <img src={item.thumb} alt={`${item.account} ${item.name}`} loading="lazy" onError={() => setBroken(true)} /> : <span className="noimg">No saved image for this post yet</span>}
        <span className="scrim" />
        {item.video && <span className="vid-badge"><Icon name="play" size={14} /></span>}
      </button>
      <span className="foot" title={item.date ? `${item.account} · posted ${item.date}` : item.account}>
        <b>{String(index + 1).padStart(2, "0")} · {itemLabel(item)}</b>
        <span>{item.at != null ? `at ${fmtDuration(item.at)} · ` : ""}{item.account}{item.date ? ` · ${item.date}` : ""}</span>
      </span>
      <span className="cluster">
        <SourceButton item={item} />
        {item.thumb && (
          <a className="fav" href={downloadHref(item)} download aria-label="Download" title="Download">
            <Icon name="download" size={14} />
          </a>
        )}
        {!item.noFav && item.thumb && (
          <button type="button" className={cn("fav", faved && "on")} aria-label={faved ? "Remove favourite" : "Add favourite"} title={faved ? "Remove from favourites" : "Add to favourites"} onClick={() => desk.toggleFav(item)}>
            <Star filled={faved} />
          </button>
        )}
      </span>
    </article>
  );
}

export function ContactSheet({ items, showSelect, marks = true }: { items: Item[]; showSelect?: boolean; marks?: boolean }) {
  const desk = useDesk();
  return (
    <div className={cn("sheet-wrap", !marks && "no-marks")}>
      <div className="sheet">
        {items.map((item, i) => (
          <FrameCard key={item.rid || item.id + i} item={item} index={i} showSelect={showSelect} selected={desk.selectedIds.includes(item.rid)} pool={items} />
        ))}
      </div>
    </div>
  );
}

export function LinkList({ items }: { items: Item[] }) {
  const desk = useDesk();
  return (
    <div className="list">
      {items.map((item) => (
        <article key={item.rid || item.id} className="list-row">
          {item.thumb ? <img src={item.thumb} alt="" loading="lazy" /> : <span className="list-noimg" />}
          <div>
            <h3>@{item.account}</h3>
            <p>
              {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.url}</a> : item.original || item.name}
            </p>
            <p>
              {item.date ? `Posted ${item.date}` : "No post date"} · {itemLabel(item)}
              {item.score != null ? ` · score ${item.score.toFixed(3)}` : ""}
            </p>
          </div>
          <div className="row">
            {item.url && item.type === "instagram" ? (
              <>
                <a className="btn tiny" href={item.url} target="_blank" rel="noreferrer">Open</a>
                <button type="button" className="btn tiny" onClick={() => desk.copyText(item.url)}>Copy link</button>
              </>
            ) : item.original ? (
              <button type="button" className="btn tiny" onClick={() => desk.revealPath(item.original)}>Finder</button>
            ) : null}
            {item.thumb && !item.noFav && (
              <button type="button" className="btn tiny" onClick={() => desk.toggleFav(item)}>
                {desk.isFav(item.id) ? "Unfavourite" : "Favourite"}
              </button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

type Clip = { url: string; start: number; name: string };

/** Full-screen viewer and slideshow: arrows, pause, shuffle, full screen, a timer, and video clips that play to the end. */
export function Slideshow() {
  const desk = useDesk();
  const { open, items: list, index, play, more } = desk.slides as { open: boolean; items: Item[]; index: number; play: boolean; more?: () => Promise<Item[]> };
  const root = useRef<HTMLDivElement>(null);
  const [order, setOrder] = useState<number[]>([]);
  const [pos, setPos] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [secs, setSecs] = useState(5);
  const [clip, setClip] = useState<Clip | null>(null);
  const [clipState, setClipState] = useState<"idle" | "loading" | "error">("idle");
  // Full screen: the layout switches at once (side panel gone, the picture or video fills the screen), and the browser's
  // own full screen is requested on top. If the browser refuses, the layout still works and a note says so.
  const [immersive, setImmersive] = useState(false);
  const [chrome, setChrome] = useState(true);          // the top bar and arrows show while the mouse moves, then fade
  const [fsNote, setFsNote] = useState("");

  const started = useRef({ open: false, first: "" });
  const fetchingMore = useRef(false);
  useEffect(() => {
    if (!open) { started.current = { open: false, first: "" }; return; }
    const first = list[0]?.rid || list[0]?.id || "";
    if (started.current.open && started.current.first === first && order.length && list.length > order.length) {
      setOrder((o) => [...o, ...list.slice(o.length).map((_, i) => o.length + i)]);      // more clips were added: keep the place
      return;
    }
    started.current = { open: true, first };
    setOrder(list.map((_, i) => i));
    setPos(index);
    setPlaying(play);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, list, index, play]);

  const item: Item | undefined = list[order[pos]];
  const n = order.length;
  const go = (dir: number) => setPos((p) => (n ? (p + dir + n) % n : 0));

  // video results: ask the server for the clip (cut on demand)
  useEffect(() => {
    setClip(null);
    setClipState("idle");
    if (open && item?.clip) {                                   // a ready-made clip (position search): nothing to cut
      setClip({ url: item.clip.url, start: item.clip.start, name: item.clip.title });
      return;
    }
    if (!open || !item?.video || !item.url) return;
    let live = true;
    setClipState("loading");
    const len = desk.clipSeconds || 120;
    api<Clip>(`/api/clip?account=${encodeURIComponent(item.account)}&url=${encodeURIComponent(item.url)}&secs=${len}`)
      .then((c) => live && (setClip(c), setClipState("idle")))
      .catch(() => live && setClipState("error"));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, item?.rid, item?.id]);

  // images advance on a timer; a video plays to its end first
  const isVideoNow = !!item?.video && clipState !== "error";
  useEffect(() => {
    if (!open || !playing || !n || isVideoNow) return;
    const t = window.setTimeout(() => go(1), secs * 1000);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, playing, pos, secs, n, isVideoNow]);

  useEffect(() => {
    if (!open || !n) return;
    const next = list[order[(pos + 1) % n]];
    if (next?.full) new Image().src = next.full;
    if (next?.clip) { const v = document.createElement("video"); v.preload = "auto"; v.src = next.clip.url; }   // the next clip is ready when this one ends
  }, [open, pos, order, list, n]);

  // endless mode: two clips before the end, ask for more
  useEffect(() => {
    if (!open || !more || !n || pos < n - 2 || fetchingMore.current) return;
    fetchingMore.current = true;
    more().then((items) => { if (items.length) desk.appendSlides(items); }).catch(() => undefined).finally(() => { fetchingMore.current = false; });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pos, n, more]);

  const shuffle = () => {
    setOrder((o) => {
      const a = [...o];
      for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
      }
      return a;
    });
    setPos(0);
  };

  const fullscreen = () => {
    if (immersive || document.fullscreenElement) {
      setImmersive(false);
      setFsNote("");
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      return;
    }
    setImmersive(true);
    setChrome(true);
    const ask = root.current?.requestFullscreen?.();
    if (ask) ask.catch(() => setFsNote("Your browser wouldn't switch to its own full screen, so this fills the window instead. Esc leaves it."));
    else setFsNote("This browser has no full screen mode, so this fills the window instead. Esc leaves it.");
  };

  // leaving the browser's full screen (Esc, or its own controls) also leaves our layout
  useEffect(() => {
    const onChange = () => { if (!document.fullscreenElement) { setImmersive(false); setFsNote(""); } };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  // while full screen: the controls fade after a moment without the mouse moving
  useEffect(() => {
    if (!immersive) { setChrome(true); return; }
    let t: number | undefined;
    const wake = () => {
      setChrome(true);
      window.clearTimeout(t);
      t = window.setTimeout(() => setChrome(false), 2600);
    };
    wake();
    window.addEventListener("mousemove", wake);
    window.addEventListener("keydown", wake);
    return () => { window.clearTimeout(t); window.removeEventListener("mousemove", wake); window.removeEventListener("keydown", wake); };
  }, [immersive]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "SELECT" || tag === "INPUT") return;
      if (e.key === "Escape" && !document.fullscreenElement) { if (immersive) { setImmersive(false); setFsNote(""); } else desk.closeSlides(); }
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === "s") shuffle();
      else if (e.key === "f") fullscreen();
      else if (e.key === "h" && item && !item.noFav) desk.toggleFav(item);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, item, n, immersive]);

  useEffect(() => {
    if (!open) { setImmersive(false); setFsNote(""); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); }
  }, [open]);

  if (!open || !item) return null;
  const faved = desk.isFav(item.id);
  const src = item.full || item.thumb;

  return (
    <div className={cn("slideshow", immersive && "immersive", immersive && !chrome && "idle")} role="dialog" aria-label="Slideshow" ref={root}>
      <div className="slide-col">
        <div className="slide-stage">
          <button type="button" className="slide-nav prev" aria-label="Previous" onClick={() => go(-1)}>←</button>
          {item.video && clip ? (
            <video
              key={clip.url}
              src={clip.url}
              poster={src || undefined}
              controls
              controlsList="nofullscreen"
              disablePictureInPicture
              autoPlay
              playsInline
              onLoadedMetadata={(e) => {
                if (clip.start) e.currentTarget.currentTime = clip.start;
              }}
              onEnded={() => playing && go(1)}
            />
          ) : src ? (
            <img src={src} alt={`${item.account} ${item.name}`} />
          ) : (
            <p className="hint">No saved image for this post yet.</p>
          )}
          {fsNote && <p className="hint slide-note fs-note">{fsNote}</p>}
          {clipState === "loading" && <p className="hint slide-note">Cutting the clip...</p>}
          {clipState === "error" && <p className="hint warn slide-note">The clip could not be made, so the still is shown.</p>}
          <button type="button" className="slide-nav next" aria-label="Next" onClick={() => go(1)}>→</button>
        </div>
        {playing && !isVideoNow && <div className="slide-prog"><i key={`${pos}-${secs}`} style={{ animationDuration: `${secs}s` }} /></div>}
        <div className="slide-bar">
          <button type="button" className="btn tiny" aria-label="Previous" onClick={() => go(-1)}>← Prev</button>
          <button type="button" className="icon-btn" aria-label={playing ? "Pause" : "Play"} onClick={() => setPlaying((p) => !p)}>
            <Icon name={playing ? "pause" : "play"} size={15} />
          </button>
          <button type="button" className="btn tiny" aria-label="Next" onClick={() => go(1)}>Next →</button>
          <select className="quiet" value={secs} onChange={(e) => setSecs(Number(e.target.value))} aria-label="Seconds per image">
            {[2, 3, 5, 8, 15].map((s) => <option key={s} value={s}>{s} s</option>)}
          </select>
          <button type="button" className="btn tiny" onClick={shuffle}><Icon name="shuffle" size={14} /> Shuffle</button>
          <span className="slide-cap">{item.clip ? `${item.clip.position.replace(/_/g, " ")} · ${item.clip.title}` : null}{!item.clip && item.account}{item.slide ? ` · slide ${item.slide}` : ""}{item.score != null ? ` · score ${item.score.toFixed(3)}` : ""}{item.date ? ` · posted ${item.date}` : ""}</span>
          <button type="button" className="btn tiny" onClick={fullscreen}><Icon name="expand" size={14} /> {immersive ? "Exit full screen" : "Full screen"}</button>
        </div>
      </div>
      <aside className="slide-meta">
        <div className="spread">
          <p className="kicker">{String(pos + 1).padStart(2, "0")} / {String(n).padStart(2, "0")}</p>
          <button type="button" className="icon-btn" onClick={desk.closeSlides} aria-label="Close slideshow"><Icon name="x" /></button>
        </div>
        {item.clip && (
          <>
            <h2 style={{ fontSize: 30, marginTop: 8 }}>{item.clip.position.replace(/_/g, " ")}</h2>
            <p style={{ margin: "6px 0 0", fontSize: 14 }}>{item.clip.title}</p>
            <p className="hint" style={{ marginTop: 6 }}>{item.clip.creator} · clip {item.clip.range}</p>
            <p className={cn("hint", item.clip.source === "verified" ? "sage" : "warn")} style={{ marginTop: 6 }}>
              {item.clip.source === "verified" ? "Verified by you" : `Model's guess${item.clip.confidence != null ? `, confidence ${item.clip.confidence.toFixed(2)}` : ""}`}
            </p>
            {more && <p className="hint" style={{ marginTop: 6 }}>Keeps going with new clips when these run out.</p>}
          </>
        )}
        {!item.clip && item.score != null && (
          <>
            <h2 style={{ fontSize: 32, marginTop: 8 }}>{item.score.toFixed(3)}</h2>
            <div className="score-bar"><i style={{ width: `${Math.round(Math.max(0, Math.min(1, item.score)) * 100)}%` }} /></div>
          </>
        )}
        {!item.clip && (
          <p className="hint" style={{ marginTop: 8 }}>
            @{item.account} · {item.date ? `posted ${item.date}` : "no post date"} · {itemLabel(item)}
          </p>
        )}
        {item.caption && <p className="hint" style={{ marginTop: 8 }}>{item.caption}</p>}
        {item.at != null && <p className="hint" style={{ marginTop: 8 }}>Matched moment: {fmtDuration(item.at)} in {item.videoName}</p>}
        {item.video && clip && item.at == null && <p className="hint" style={{ marginTop: 8 }}>{clip.name}</p>}
        <div className="row" style={{ marginTop: 16 }}>
          {!item.noFav && item.thumb && (
            <button type="button" className={cn("btn tiny", faved && "gold")} onClick={() => desk.toggleFav(item)}>
              <Star filled={faved} /> {faved ? "Favourited" : "Favourite"}
            </button>
          )}
          {item.thumb && <a className="btn tiny" href={downloadHref(item)} download><Icon name="download" size={14} /> Download</a>}
          {item.type === "instagram" && item.url ? (
            <>
              <a className="btn tiny" href={item.url} target="_blank" rel="noreferrer"><Icon name="external" size={14} /> Instagram</a>
              <button type="button" className="btn tiny" onClick={() => desk.copyText(item.url)}>Copy link</button>
            </>
          ) : item.original ? (
            <button type="button" className="btn tiny" onClick={() => desk.revealPath(item.original)}><Icon name="folder" size={14} /> Finder</button>
          ) : null}
        </div>
        <p className="hint" style={{ marginTop: 18 }}>← → frames · space pause · S shuffle · F full screen · H favourite · Esc close</p>
      </aside>
    </div>
  );
}
