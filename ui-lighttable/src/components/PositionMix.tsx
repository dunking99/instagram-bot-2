import { useEffect, useRef, useState } from "react";
import { api, post, usePref } from "../api";
import { useDesk } from "../store";
import { cn } from "../utils/cn";
import { CONF, LENGTHS, hms, toItem, type Clip, type PositionList } from "./PositionsView";
import { Icon, Seg } from "./ui";

type Vid = { name: string; title: string; creator: string; verified: boolean; seconds: number; hasFile: boolean };
/** One line of the search: a position, optionally tied to certain creators, and (in exact mode) how many videos. */
type Rule = { id: string; position: string; count: number; creators: string[] };
type Got = { clip: Clip; rule: string };

const nice = (n: string) => n.replace(/_/g, " ");
const pick = <T,>(a: T[]) => a[Math.floor(Math.random() * a.length)];
const shuffle = <T,>(a: T[]) => { const b = [...a]; for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; };
const newRule = (position: string, count = 1): Rule => ({ id: `${position}#${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`, position, count, creators: [] });

/** A small dropdown with a search box and ticks, for choosing creators. */
function CreatorPick({ options, value, onChange, label }: { options: { name: string; count: number }[]; value: string[]; onChange: (v: string[]) => void; label: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const shown = options.filter((o) => o.name.toLowerCase().includes(q.trim().toLowerCase()));
  const toggle = (n: string) => onChange(value.includes(n) ? value.filter((x) => x !== n) : [...value, n]);
  return (
    <div className="picker" ref={box}>
      <button type="button" className={cn("btn tiny", value.length > 0 && "primary")} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {value.length === 0 ? label : value.length === 1 ? value[0] : `${value.length} creators`} <Icon name="plus" size={12} />
      </button>
      {open && (
        <div className="picker-pop" role="dialog" aria-label="Choose creators">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter creators" aria-label="Filter creators" />
          <div className="row" style={{ margin: "8px 0" }}>
            <button type="button" className="btn tiny" disabled={!value.length} onClick={() => onChange([])}>Clear</button>
          </div>
          <div className="picker-list">
            {shown.map((o) => {
              const on = value.includes(o.name);
              return (
                <button type="button" key={o.name} className={cn("pick-item", on && "on")} onClick={() => toggle(o.name)} aria-pressed={on}>
                  <span className="pick-box">{on ? <Icon name="check" size={12} /> : null}</span>
                  <span className="pick-name">{o.name}</span>
                  <em>{o.count} video{o.count === 1 ? "" : "s"}</em>
                </button>
              );
            })}
            {!shown.length && <p className="hint" style={{ padding: 8 }}>No creator matches.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

const byCreator = (vids: Vid[]) => {
  const m = new Map<string, number>();
  vids.forEach((v) => m.set(v.creator, (m.get(v.creator) || 0) + 1));
  return [...m].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
};

/** Search by position: choose positions (each can be tied to creators), then how many videos, as a random mix or exact numbers. */
export function PositionMix() {
  const d = useDesk();
  const [list, setList] = useState<PositionList | null>(null);
  const [mode, setMode] = usePref<"random" | "exact">("mix.mode", "random");
  const [total, setTotal] = usePref("mix.total", 12);
  const [rules, setRules] = usePref<Rule[]>("mix.rules", []);
  const [seconds, setSeconds] = usePref("mix.seconds", 30);
  const [verifiedOnly, setVerifiedOnly] = usePref("mix.verifiedOnly", false);
  const [minConf, setMinConf] = usePref("mix.minConf", 0);
  const [gCreators, setGCreators] = usePref<string[]>("mix.gCreators", []);
  const [gExclude, setGExclude] = usePref("mix.gExclude", false);
  const [perCreator, setPerCreator] = usePref("mix.perCreator", 0);                 // 0 = no limit
  const [got, setGot] = useState<Got[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [everyone, setEveryone] = useState<Vid[]>([]);
  const [, bump] = useState(0);
  const cache = useRef<Record<string, Vid[]>>({});                                  // position -> videos that have it
  const shown = useRef<Set<string>>(new Set());

  useEffect(() => {
    api<PositionList>("/api/positions").then(setList).catch((e) => d.fail(e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.dataVersion]);

  async function loadPos(position: string): Promise<Vid[]> {
    if (cache.current[position]) return cache.current[position];
    const r = await api<{ with: Vid[]; without: Vid[] }>(`/api/positions/videos?position=${encodeURIComponent(position)}`);
    cache.current[position] = r.with;
    setEveryone([...r.with, ...r.without]);
    bump((n) => n + 1);
    return r.with;
  }
  useEffect(() => {                                                               // creator lists for the rules on screen
    const want = new Set(rules.map((r) => r.position));
    if (!want.size && !everyone.length) want.add("Blowjob");
    want.forEach((p) => { loadPos(p).catch(() => undefined); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rules.map((r) => r.position).join("|"), d.dataVersion]);
  useEffect(() => { cache.current = {}; }, [d.dataVersion]);

  const prows = list?.positions || [];
  const live = rules.filter((r) => !list || prows.some((p) => p.name === r.position));
  const exactTotal = live.reduce((a, r) => a + r.count, 0);
  const want = mode === "exact" ? exactTotal : total;

  const toggle = (n: string) => setRules((rs) => (rs.some((r) => r.position === n) ? rs.filter((r) => r.position !== n) : [...rs, newRule(n)]));
  const patch = (id: string, p: Partial<Rule>) => setRules((rs) => rs.map((r) => (r.id === id ? { ...r, ...p } : r)));
  const step = (id: string, by: number) => setRules((rs) => rs.map((r) => (r.id === id ? { ...r, count: Math.max(1, Math.min(60, r.count + by)) } : r)));
  const allMain = () => setRules(prows.filter((r) => !r.name.includes(" - ") && r.videos >= 8).map((r) => newRule(r.name)));

  const allowed = (v: Vid, r: Rule) => {
    if (r.creators.length) { if (!r.creators.includes(v.creator)) return false; }
    else if (gCreators.length && !gExclude && !gCreators.includes(v.creator)) return false;
    if (gExclude && gCreators.includes(v.creator)) return false;
    return !verifiedOnly || v.verified;
  };
  const pool = (r: Rule) => (cache.current[r.position] || []).filter((v) => v.hasFile && allowed(v, r));

  /** Take up to n videos for one rule: choose from the right creators (never a video already used, never more than the
   *  per-creator limit), then cut those clips. A chosen video whose section is too short is dropped and replaced. */
  async function fill(r: Rule, n: number, used: Set<string>, perC: Map<string, number>, bad: Set<string>): Promise<Got[]> {
    const out: Got[] = [];
    for (let round = 0; round < 4 && out.length < n; round++) {
      const cands = shuffle((await loadPos(r.position)).filter((v) => v.hasFile && allowed(v, r) && !used.has(v.name) && !bad.has(`${r.position}|${v.name}`)));
      const need = n - out.length, chosen: Vid[] = [], cc = new Map(perC);
      for (const v of cands) {
        if (chosen.length >= need) break;
        if (perCreator > 0 && (cc.get(v.creator) || 0) >= perCreator) continue;
        chosen.push(v);
        cc.set(v.creator, (cc.get(v.creator) || 0) + 1);
      }
      if (!chosen.length) break;
      const keep = new Set(chosen.map((v) => v.name));
      const exclude = everyone.map((v) => v.name).filter((x) => !keep.has(x) || used.has(x));
      const res = await post<{ clips: Clip[] }>("/api/positions/clips", {
        position: r.position, count: chosen.length, seconds, verifiedOnly, minConf, excludeVideos: exclude,
      });
      const found = new Set<string>();
      for (const c of res.clips) {
        if (used.has(c.video)) continue;
        used.add(c.video);
        found.add(c.video);
        perC.set(c.creator, (perC.get(c.creator) || 0) + 1);
        out.push({ clip: c, rule: r.id });
      }
      chosen.forEach((v) => { if (!found.has(v.name)) bad.add(`${r.position}|${v.name}`); });
    }
    return out;
  }

  async function build(used: Set<string>): Promise<{ list: Got[]; notes: string[] }> {
    for (const r of live) await loadPos(r.position);
    const out: Got[] = [], notes: string[] = [], perC = new Map<string, number>(), bad = new Set<string>();
    const asked: Record<string, number> = {};
    live.forEach((r) => { asked[r.id] = 0; });
    if (mode === "exact") live.forEach((r) => { asked[r.id] = r.count; });
    else {
      const open = live.filter((r) => pool(r).length > 0);
      for (let i = 0; i < total && open.length; i++) asked[pick(open).id]++;
    }
    const order = [...live].sort((a, b) => pool(a).length - pool(b).length);       // scarce ones first
    const gotBy: Record<string, number> = {};
    const exhausted = new Set<string>();
    for (const r of order) {
      if (!asked[r.id]) continue;
      const g = await fill(r, asked[r.id], used, perC, bad);
      out.push(...g);
      gotBy[r.id] = g.length;
      if (g.length < asked[r.id]) exhausted.add(r.id);
    }
    if (mode === "random") {                                                       // a line ran dry: give its share to the others
      for (let round = 0; round < 4; round++) {
        const left = total - out.length;
        const open = live.filter((r) => !exhausted.has(r.id) && pool(r).length > 0);
        if (left <= 0 || !open.length) break;
        const extra: Record<string, number> = {};
        for (let i = 0; i < left; i++) { const r = pick(open); extra[r.id] = (extra[r.id] || 0) + 1; }
        for (const r of open) {
          if (!extra[r.id]) continue;
          const g = await fill(r, extra[r.id], used, perC, bad);
          out.push(...g);
          if (g.length < extra[r.id]) exhausted.add(r.id);
        }
      }
      out.sort(() => Math.random() - 0.5);
      if (out.length < total) notes.push(`Only ${out.length} of ${total} videos were available with these settings. Loosen the creators, clip length or confidence.`);
    } else {
      live.forEach((r) => {
        if ((gotBy[r.id] || 0) < r.count) notes.push(`${label(r)}: only ${gotBy[r.id] || 0} of ${r.count} videos fit.`);
      });
      const ids = live.map((r) => r.id);
      out.sort((a, b) => ids.indexOf(a.rule) - ids.indexOf(b.rule));
    }
    return { list: out, notes };
  }

  const label = (r: Rule) => `${nice(r.position)}${r.creators.length ? ` (${r.creators.join(", ")})` : ""}`;

  async function run() {
    setBusy(true);
    try {
      shown.current = new Set();
      const r = await build(shown.current);
      setGot(r.list);
      setNotes(r.list.length ? r.notes : ["Nothing matches. Try other creators, a shorter clip, a lower confidence, or untick verified only."]);
    } catch (e) {
      d.fail(e);
    }
    setBusy(false);
  }

  async function another(i: number) {
    try {
      const g = got[i];
      const r = rules.find((x) => x.id === g.rule) || newRule(g.clip.position);
      const used = new Set(got.map((x) => x.clip.video));
      const perC = new Map<string, number>();
      got.forEach((x, k) => { if (k !== i) perC.set(x.clip.creator, (perC.get(x.clip.creator) || 0) + 1); });
      const res = await fill(r, 1, used, perC, new Set());
      if (!res.length) { d.toast("No other video fits"); return; }
      setGot(got.map((x, k) => (k === i ? res[0] : x)));
    } catch (e) {
      d.fail(e);
    }
  }

  async function slideshow() {
    let cur = got;
    if (!cur.length) {
      setBusy(true);
      try { shown.current = new Set(); cur = (await build(shown.current)).list; setGot(cur); } catch (e) { d.fail(e); }
      setBusy(false);
    }
    if (!cur.length) return;
    shown.current = new Set(cur.map((g) => g.clip.video));
    const more = async () => {
      let r = await build(shown.current);
      if (!r.list.length) { shown.current = new Set(); r = await build(shown.current); }
      return r.list.map((g) => toItem(g.clip));
    };
    d.openSlides(cur.map((g) => toItem(g.clip)), 0, true, more);
  }

  const parents = prows.filter((r) => !r.name.includes(" - "));
  const chip = (r: { name: string; videos: number }, sub = false) => {
    const on = rules.some((x) => x.position === r.name);
    return (
      <button key={r.name} type="button" className={cn("chip", on && "on")} onClick={() => toggle(r.name)} aria-pressed={on}
        title={`${r.videos} analysed videos have this`}>
        {sub ? nice(r.name.split(" - ")[1]) : nice(r.name)} <span style={{ opacity: 0.6, marginLeft: 6, fontWeight: 400 }}>{r.videos}</span>
      </button>
    );
  };
  const counts: Record<string, number> = {};
  got.forEach((g) => { const k = g.clip.position; counts[k] = (counts[k] || 0) + 1; });
  const canRun = !busy && live.length > 0 && want > 0;
  const creatorsAll = byCreator(everyone.filter((v) => v.hasFile));
  const filterNote = [
    gCreators.length ? `${gExclude ? "not" : "only"} ${gCreators.length === 1 ? gCreators[0] : `${gCreators.length} creators`}` : "",
    perCreator > 0 ? `at most ${perCreator} per creator` : "",
    verifiedOnly ? "verified only" : "",
  ].filter(Boolean).join(" · ");

  return (
    <div>
      <header className="search-intro">
        <p className="kicker">Search desk</p>
        <h1>Find videos by position.</h1>
        <p className="lede">
          Choose positions, optionally tie each to certain creators, then say how many videos. Each video is a clip taken from the part of that video where the position was marked. The same video is never used twice.
        </p>
      </header>

      <section className="composer">
        <div className="spread">
          <p className="kicker" style={{ margin: 0 }}>1 · Positions <span className="hint" style={{ textTransform: "none", letterSpacing: 0 }}>click to add or remove</span></p>
          <div className="row">
            <button type="button" className="btn tiny" onClick={allMain}>All main positions</button>
            <button type="button" className="btn tiny" disabled={!rules.length} onClick={() => setRules([])}>Clear</button>
          </div>
        </div>
        <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
          {parents.map((p) => {
            const subs = prows.filter((r) => r.name.startsWith(p.name + " - "));
            return (
              <div key={p.name} className="row" style={{ alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                {chip(p)}
                {subs.length > 0 && <span className="hint">→</span>}
                {subs.map((s) => chip(s, true))}
              </div>
            );
          })}
          {!prows.length && <p className="hint">Loading positions...</p>}
        </div>
        <p className="hint" style={{ marginTop: 8 }}>
          The number beside each position is how many analysed videos have it. A main position (like Doggystyle) includes all its types. Pick a type (like Standing) to get only that.
        </p>

        <div style={{ marginTop: 16 }}>
          <p className="kicker" style={{ margin: 0 }}>2 · Creators <span className="hint" style={{ textTransform: "none", letterSpacing: 0 }}>for every position, unless a position below has its own</span></p>
          <div className="row" style={{ marginTop: 8, flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <Seg label="Creator filter" value={gExclude ? "not" : "only"} onChange={(v: string) => setGExclude(v === "not")}
              options={[{ id: "only", label: "Only these" }, { id: "not", label: "Everyone except" }]} />
            <CreatorPick label="Any creator" options={creatorsAll} value={gCreators} onChange={setGCreators} />
            {gCreators.map((c) => <button type="button" key={c} className="chip on" onClick={() => setGCreators(gCreators.filter((x) => x !== c))}>{c} ×</button>)}
            <label className="inline-num" title="Stops one creator filling the whole result">Max per creator
              <select value={perCreator} onChange={(e) => setPerCreator(Number(e.target.value))}>
                <option value={0}>No limit</option>
                {[1, 2, 3, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
        </div>

        <div className="footbar" style={{ marginTop: 16 }}>
          <Seg label="How to split" value={mode} onChange={setMode}
            options={[{ id: "random", label: "Random mix" }, { id: "exact", label: "Exact number each" }]} />
          <div className="row">
            {mode === "random" ? (
              <label className="inline-num">Videos in total
                <input type="number" min={1} max={60} value={total} onChange={(e) => setTotal(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} />
              </label>
            ) : (
              <span className="inline-num">Total <b>{exactTotal}</b> videos</span>
            )}
            <label className="inline-num">Clip length
              <select value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}>
                {LENGTHS.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="inline-num">Confidence
              <select value={minConf} onChange={(e) => setMinConf(Number(e.target.value))}>
                {CONF.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <button type="button" className={cn("signal", verifiedOnly && "on")} onClick={() => setVerifiedOnly(!verifiedOnly)}>Verified videos only</button>
          </div>
        </div>

        <div style={{ marginTop: 12, display: "grid", gap: 6, maxWidth: 720 }}>
          {!live.length && <p className="hint">Pick positions above. Each one appears here, where you can tie it to creators{mode === "exact" ? " and set how many videos" : ""}.</p>}
          {live.map((r) => {
            const opts = byCreator((cache.current[r.position] || []).filter((v) => v.hasFile));
            const n = pool(r).length;
            return (
              <div key={r.id} className="spread" style={{ borderBottom: "1px solid var(--rule)", padding: "6px 0", gap: 10, flexWrap: "wrap" }}>
                <span style={{ minWidth: 190 }}>
                  <b>{nice(r.position)}</b>
                  <span className="hint"> · {n} video{n === 1 ? "" : "s"} fit{n === 1 ? "s" : ""}{r.creators.length || gCreators.length ? " these creators" : ""}</span>
                </span>
                <span className="row" style={{ gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <CreatorPick label="Any creator" options={opts} value={r.creators} onChange={(v) => patch(r.id, { creators: v })} />
                  <button type="button" className="btn tiny" title="Add another line for this position, for example with a different creator"
                    onClick={() => setRules((rs) => { const at = rs.findIndex((x) => x.id === r.id); const c = [...rs]; c.splice(at + 1, 0, newRule(r.position)); return c; })}>+ Another</button>
                  {mode === "exact" && (
                    <>
                      <button type="button" className="btn tiny" onClick={() => step(r.id, -1)} aria-label={`Fewer ${label(r)}`}>−</button>
                      <b style={{ minWidth: 22, textAlign: "center" }}>{r.count}</b>
                      <button type="button" className="btn tiny" onClick={() => step(r.id, 1)} aria-label={`More ${label(r)}`}>+</button>
                    </>
                  )}
                  <button type="button" className="btn tiny" onClick={() => setRules((rs) => rs.filter((x) => x.id !== r.id))} aria-label={`Remove ${label(r)}`}><Icon name="x" size={12} /></button>
                </span>
              </div>
            );
          })}
        </div>
        {mode === "random" && live.length > 0 && (
          <p className="hint" style={{ marginTop: 10 }}>{total} videos drawn at random across {live.map(label).join(", ")}{filterNote ? ` · ${filterNote}` : ""}. Each press gives a different combination.</p>
        )}
        {mode === "exact" && live.length > 0 && filterNote && <p className="hint" style={{ marginTop: 10 }}>{filterNote}</p>}

        <div className="row" style={{ marginTop: 14 }}>
          <button type="button" className="btn primary" disabled={!canRun} onClick={run}>
            {busy ? "Cutting clips..." : got.length ? "Draw again" : `Find ${want} video${want === 1 ? "" : "s"}`}
          </button>
          <button type="button" className="btn" disabled={!canRun} onClick={slideshow} title="Play them one after another, full screen, and keep going with new ones">▶ Slideshow</button>
        </div>
      </section>

      {notes.map((n) => <p key={n} className="hint warn" style={{ marginTop: 10 }}>{n}</p>)}

      {got.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="results-head">
            <div>
              <h2>{got.length} {got.length === 1 ? "video" : "videos"}</h2>
              <p>{Object.entries(counts).map(([k, v]) => `${v} × ${nice(k)}`).join(" · ")}</p>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 14, marginTop: 14 }}>
            {got.map((g, i) => {
              const c = g.clip;
              return (
                <article key={c.id} className="panel panelbox" style={{ padding: 10 }}>
                  <video src={c.offset ? `${c.url}#t=${c.offset}` : c.url} controls preload="metadata" playsInline loop
                    style={{ width: "100%", maxHeight: 360, background: "#000" }} />
                  <div className="spread" style={{ marginTop: 8 }}>
                    <strong>{nice(c.position)}</strong>
                    <span className={cn("hint", c.source === "verified" ? "sage" : "warn")}>
                      {c.source === "verified" ? "verified" : `model guess${c.confidence != null ? `, ${c.confidence.toFixed(2)}` : ""}`}
                    </span>
                  </div>
                  <p style={{ margin: "4px 0 0", fontSize: 13.5 }}>{c.title}</p>
                  <p className="hint">{c.creator} · clip {hms(c.startS)}–{hms(c.endS)}</p>
                  <div className="row" style={{ marginTop: 8 }}>
                    <button type="button" className="btn tiny" onClick={() => another(i)}>Another video</button>
                    <button type="button" className="btn tiny" onClick={() => post("/api/reveal", { path: c.file }).catch((e) => d.fail(e))}>Show file</button>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
