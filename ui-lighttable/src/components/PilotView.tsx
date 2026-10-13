import { useCallback, useEffect, useMemo, useState } from "react";
import { api, post, usePref } from "../api";
import { assignPile, type Pile, type PilotShot } from "../types";
import { useDesk } from "../store";
import { cn } from "../utils/cn";

const PILES: { id: Pile; label: string; note: string }[] = [
  { id: "keep", label: "Keep", note: "Looks like a photo of a person" },
  { id: "review", label: "Review", note: "Unsure, have a look" },
  { id: "junk", label: "Junk", note: "Screenshot noise, not a portrait" },
];
const SHOW = 40;

type Undo = { id: string; prev: Pile | null };

export function PilotView() {
  const d = useDesk();
  const [items, setItems] = useState<PilotShot[] | null>(null);
  const [overrides, setOverrides] = useState<Record<string, Pile>>({});
  const [keepAt, setKeepAt] = usePref("pilot.keepAt", 0.7);
  const [junkAt, setJunkAt] = usePref("pilot.junkAt", 0.2);
  const [undo, setUndo] = usePref<Undo[]>("pilot.undo", []);
  const [full, setFull] = useState(false);
  const [more, setMore] = useState<Record<Pile, number>>({ keep: SHOW, review: SHOW, junk: SHOW });
  const [drag, setDrag] = useState<string | null>(null);
  const [over, setOver] = useState<Pile | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api<{ items: PilotShot[]; overrides: Record<string, Pile> }>("/api/pilot");
      setItems(r.items);
      setOverrides(r.overrides);
    } catch (e) {
      d.fail(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { load(); }, [load, d.dataVersion]);

  const pileOf = useCallback((s: PilotShot): Pile => overrides[s.id] || assignPile(s.score, s.body, keepAt, junkAt), [overrides, keepAt, junkAt]);
  const grouped = useMemo(() => {
    const g: Record<Pile, PilotShot[]> = { keep: [], review: [], junk: [] };
    for (const s of items || []) g[pileOf(s)].push(s);
    for (const k of Object.keys(g) as Pile[]) g[k].sort((a, b) => Number(!overrides[a.id]) - Number(!overrides[b.id]) || b.score - a.score);
    return g;
  }, [items, pileOf, overrides]);

  const setPile = async (id: string, pile: Pile | "auto", record = true) => {
    if (record) setUndo((u) => [...u.slice(-49), { id, prev: overrides[id] ?? null }]);
    try {
      const r = await post<{ overrides: Record<string, Pile> }>("/api/pilot/pile", { id, pile });
      setOverrides(r.overrides);
    } catch (e) {
      d.fail(e);
    }
  };
  const undoLast = async () => {
    const last = undo[undo.length - 1];
    if (!last) return;
    setUndo(undo.slice(0, -1));
    await setPile(last.id, last.prev ?? "auto", false);
    d.toast("Undid correction");
  };

  const running = d.jobs.some((j: { kind: string; running: boolean }) => j.kind === "pilot" && j.running);
  const corrected = Object.keys(overrides).filter((id) => (items || []).some((s) => s.id === id)).length;

  return (
    <div>
      <p className="kicker">Photos pilot</p>
      <h1 style={{ fontSize: "clamp(32px, 4vw, 48px)" }}>Sort the screenshot pile.</h1>
      <p className="lede">
        Sorts screenshots from your Photos library into keep, review and junk. It crops the likely photo out of each screenshot, scores whether it looks like a person, and files it. The library is read-only; nothing in it is changed or copied.
      </p>
      <div className="row" style={{ marginTop: 14 }}>
        <button type="button" className="btn primary" disabled={running} onClick={() => d.startJob({ kind: "pilot", n: 400 })}>
          {running ? "Sorting..." : "Run the pilot on 400 random screenshots"}
        </button>
        <button type="button" className={cn("signal", full && "on")} onClick={() => setFull(!full)}>Show the whole screenshot instead of the cropped photo</button>
      </div>

      {items == null && <p className="hint" style={{ marginTop: 16 }}>Loading...</p>}
      {items && !items.length && (
        <div className="empty"><h2>No pilot run yet.</h2><p className="hint">Run the pilot above. It takes a few minutes and the results appear here.</p></div>
      )}

      {items && items.length > 0 && (
        <>
          <div className="panel panelbox" style={{ marginTop: 18 }}>
            <div className="spread">
              <label className="field" style={{ flex: 1 }}>
                <span>Keep when the photo score is at least {keepAt.toFixed(2)}</span>
                <input type="range" min={0.3} max={0.99} step={0.01} value={keepAt} onChange={(e) => setKeepAt(Number(e.target.value))} />
              </label>
              <label className="field" style={{ flex: 1 }}>
                <span>Junk when the score is below {junkAt.toFixed(2)}</span>
                <input type="range" min={0.01} max={0.6} step={0.01} value={junkAt} onChange={(e) => setJunkAt(Number(e.target.value))} />
              </label>
              <button type="button" className="btn tiny" disabled={!undo.length} onClick={undoLast}>Undo correction</button>
            </div>
            <div className="hist" aria-hidden>
              {items.map((p) => <i key={p.id} className={pileOf(p)} style={{ left: `${p.score * 100}%` }} />)}
              <em style={{ left: `${junkAt * 100}%` }} />
              <em style={{ left: `${keepAt * 100}%` }} />
            </div>
            <p className="hint">
              {items.length} screenshots: {grouped.keep.length} keep, {grouped.review.length} to review, {grouped.junk.length} junk.{corrected ? ` You've corrected ${corrected}.` : ""} A body found in the crop also counts towards keep. A manual move stays put when the sliders change.
            </p>
          </div>

          <div className="piles" style={{ marginTop: 14 }}>
            {PILES.map((pile) => {
              const cards = grouped[pile.id];
              return (
                <section
                  key={pile.id}
                  className={cn("pile", pile.id, over === pile.id && "over")}
                  onDragOver={(e) => { e.preventDefault(); setOver(pile.id); }}
                  onDragLeave={() => setOver((v) => (v === pile.id ? null : v))}
                  onDrop={() => {
                    if (drag) setPile(drag, pile.id);
                    setDrag(null);
                    setOver(null);
                  }}
                >
                  <h3>{pile.label} <span>{cards.length}</span></h3>
                  <p className="hint">{pile.note}</p>
                  {cards.slice(0, more[pile.id]).map((s) => (
                    <article key={s.id} className="pilot-card" draggable onDragStart={() => setDrag(s.id)}>
                      <div className={cn("shot", "single")}>
                        {full ? (s.screenshot ? <img src={s.screenshot} alt="" loading="lazy" /> : <span className="noimg">No preview</span>) : (s.crop ? <img src={s.crop} alt={s.file} loading="lazy" /> : <span className="noimg">No crop</span>)}
                      </div>
                      <div className="body">
                        <div className="spread">
                          <strong style={{ fontFamily: "var(--serif)", fontSize: 22 }}>{s.score.toFixed(2)}</strong>
                          <span className="hint">{overrides[s.id] ? "Manual" : s.body ? "Body found" : "No body"}</span>
                        </div>
                        <p className="mono" style={{ color: "var(--dust)" }}>{s.file}{s.date ? ` · ${s.date}` : ""}</p>
                        <p className="hint">{s.prompt.replace("a screenshot of ", "").replace("a photo of ", "")}</p>
                        <div className="row">
                          {(["keep", "review", "junk"] as Pile[]).map((p) => (
                            <button key={p} type="button" className={cn("chip", pile.id === p && "on")} onClick={() => setPile(s.id, p)}>{p}</button>
                          ))}
                          {overrides[s.id] && <button type="button" className="chip ghost" onClick={() => setPile(s.id, "auto")}>Auto</button>}
                        </div>
                      </div>
                    </article>
                  ))}
                  {cards.length > more[pile.id] && (
                    <button type="button" className="btn tiny" style={{ marginTop: 10 }} onClick={() => setMore({ ...more, [pile.id]: more[pile.id] + SHOW })}>
                      Show more ({cards.length - more[pile.id]} left, highest scores first)
                    </button>
                  )}
                  {!cards.length && <p className="hint" style={{ marginTop: 16 }}>Nothing in {pile.label.toLowerCase()} at this threshold.</p>}
                </section>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
