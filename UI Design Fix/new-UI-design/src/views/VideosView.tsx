import { useMemo, useState } from "react";
import { POSITION_COUNTS, POSITIONS, VIDEOS, fmtDur, hashStr, mulberry, ri } from "../lib/data";
import { Btn, ConfTag, Icon, Micro, Num, Panel, Seg, Slider, Thumb, Timeline, Toggle, useCtx } from "../lib/ui";

interface Clip { id: string; seed: string; pos: string; sub: string; title: string; creator: string; conf: number; verified: boolean; clip: [number, number]; section: [number, number]; duration: number; }

export default function VideosView() {
  const ctx = useCtx();
  const [chosen, setChosen] = useState<string[]>(["Standing", "Seated"]);
  const [expanded, setExpanded] = useState<string | null>("Standing");
  const [include, setInclude] = useState("");
  const [exclude, setExclude] = useState("");
  const [perCreator, setPerCreator] = useState(3);
  const [mode, setMode] = useState<"mix" | "exact">("mix");
  const [n, setN] = useState(12);
  const [clipLen, setClipLen] = useState(30);
  const [minConf, setMinConf] = useState(50);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [results, setResults] = useState<Clip[] | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [single, setSingle] = useState(false);

  const togglePos = (p: string) => setChosen((c) => (c.includes(p) ? c.filter((x) => x !== p) : [...c, p]));

  const run = () => {
    const r = mulberry(hashStr(chosen.join() + mode + n + clipLen + minConf + verifiedOnly));
    const items: Clip[] = [];
    const total = mode === "mix" ? n : n * chosen.length;
    for (let i = 0; i < Math.min(total, 60); i++) {
      const pos = chosen[i % chosen.length];
      const v = VIDEOS[Math.floor(r() * 120)];
      const sec = v.sections[0] ?? { start: 0, end: v.duration, conf: 0.8, verified: false };
      const dur = Math.min(clipLen * 4, v.duration);
      const start = Math.floor(r() * Math.max(1, v.duration - dur));
      items.push({
        id: "cl" + i, seed: "clip" + i + pos, pos,
        sub: POSITIONS.find((p) => p.name === pos)?.subs[Math.floor(r() * 5)] ?? "",
        title: v.title, creator: v.creator,
        conf: 0.4 + r() * 0.59, verified: verifiedOnly ? true : r() > 0.55,
        clip: [start, start + dur], section: [Math.floor(sec.start), Math.floor(sec.end)], duration: v.duration,
      });
    }
    setResults(items);
    ctx.notify("Clip set built", items.length + " playable clips · " + chosen.length + " positions", "ok");
  };

  const singlePos = chosen[0];
  const withPos = useMemo(() => VIDEOS.filter((v) => v.sections.some((s) => s.pos === singlePos)), [singlePos]);
  const withoutPos = useMemo(() => VIDEOS.filter((v) => !v.sections.some((s) => s.pos === singlePos)), [singlePos]);

  return (
    <div className="flex h-full min-h-0">
      {/* -------- config -------- */}
      <div className="w-[330px] shrink-0 border-r border-edge overflow-y-auto p-3 space-y-3 hidden md:block">
        <Panel title="Positions" pad={false}>
          <div className="p-3 space-y-1 max-h-[300px] overflow-y-auto">
            {POSITION_COUNTS.map((p) => (
              <div key={p.name}>
                <div className={`flex items-center gap-2 px-2 h-7 rounded cursor-pointer hover:bg-panel3 ${chosen.includes(p.name) ? "text-amber" : "text-dim"}`}
                  onClick={() => togglePos(p.name)}>
                  <span className={`w-3 h-3 rounded-sm border flex items-center justify-center ${chosen.includes(p.name) ? "bg-amber border-amber text-ink" : "border-edge2"}`}>
                    {chosen.includes(p.name) && <Icon name="check" size={9} />}
                  </span>
                  <span className="text-[12px] flex-1">{p.name}</span>
                  <span className="text-[10px] font-mono text-faint">{p.count} videos</span>
                  <button className="text-faint hover:text-cream" onClick={(e) => { e.stopPropagation(); setExpanded(expanded === p.name ? null : p.name); }}>
                    <Icon name="chevD" size={11} className={expanded === p.name ? "rotate-180" : ""} />
                  </button>
                </div>
                {expanded === p.name && (
                  <div className="ml-8 mt-0.5 space-y-0.5">
                    {p.subs.map((s) => (
                      <div key={s} className="flex items-center gap-2 px-2 h-6 text-[11px] text-faint hover:text-dim cursor-pointer">
                        <span className="w-2.5 h-2.5 rounded-sm border border-edge2" />
                        {s}
                        <span className="ml-auto font-mono text-[10px]">{ri(3, p.count)}</span>
                      </div>
                    ))}
                    <div className="flex items-center gap-1 px-2 pt-1">
                      <input placeholder="restrict to creators…" className="flex-1 bg-ink border border-edge rounded px-1.5 h-6 text-[10px] text-cream outline-none placeholder:text-faint" />
                      <button className="text-[9px] font-mono text-faint hover:text-amber" title="ask for this position again with different creators">+ again</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Creators" pad={false}>
          <div className="p-3 space-y-2">
            <input value={include} onChange={(e) => setInclude(e.target.value)} placeholder="include only…"
              className="w-full bg-ink border border-edge rounded px-2 h-7 text-[11px] text-cream outline-none placeholder:text-faint" />
            <input value={exclude} onChange={(e) => setExclude(e.target.value)} placeholder="exclude…"
              className="w-full bg-ink border border-edge rounded px-2 h-7 text-[11px] text-cream outline-none placeholder:text-faint" />
            <div className="flex items-center justify-between">
              <Micro>limit per creator</Micro>
              <Num value={perCreator} onChange={setPerCreator} max={20} />
            </div>
          </div>
        </Panel>

        <Panel title="Run shape" pad={false}>
          <div className="p-3 space-y-2.5">
            <Seg value={mode} onChange={setMode} options={[{ value: "mix", label: "random mix" }, { value: "exact", label: "exact per position" }]} />
            <div className="space-y-1">
              <Micro>{mode === "mix" ? "total videos" : "videos per position"}</Micro>
              <Slider value={n} min={1} max={40} onChange={setN} />
            </div>
            <div className="space-y-1">
              <Micro>clip length</Micro>
              <Seg value={clipLen === 0 ? "whole" : "fixed"} onChange={(v) => setClipLen(v === "whole" ? 0 : 30)}
                options={[{ value: "fixed", label: "15 s – 5 min" }, { value: "whole", label: "whole section" }]} />
            </div>
            <div className="space-y-1">
              <Micro>minimum model confidence</Micro>
              <Slider value={minConf} min={0} max={100} onChange={setMinConf} format={(v) => "≥ " + v + "%"} />
            </div>
            <Toggle on={verifiedOnly} onChange={setVerifiedOnly} label="verified only" />
          </div>
        </Panel>

        <Btn variant="primary" className="w-full justify-center" onClick={run} disabled={chosen.length === 0}>
          <Icon name="play" size={13} /> build clip set
        </Btn>
        <button className="w-full text-center text-[11px] text-faint hover:text-amber" onClick={() => { setSingle(!single); }}>
          {single ? "back to clip results" : "single-position view: who has it / who doesn't"}
        </button>
      </div>

      {/* -------- results -------- */}
      <div className="flex-1 min-w-0 overflow-y-auto p-3">
        {single ? (
          <div className="max-w-[900px]">
            <div className="mb-3 flex items-center gap-2">
              <Micro>single-position view</Micro>
              <select value={singlePos} onChange={(e) => setChosen([e.target.value])}
                className="bg-ink border border-edge rounded px-2 h-7 text-[12px] text-cream outline-none">
                {POSITION_COUNTS.map((p) => <option key={p.name}>{p.name}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="rounded border border-edge bg-panel p-3">
                <Micro className="mb-1">has “{singlePos}”</Micro>
                <div className="text-2xl font-mono text-sage">{withPos.length}</div>
                <div className="text-[10px] font-mono text-faint">videos · mean time in position {fmtDur(ri(40, 400))}</div>
              </div>
              <div className="rounded border border-edge bg-panel p-3">
                <Micro className="mb-1">does not have it</Micro>
                <div className="text-2xl font-mono text-brick">{withoutPos.length}</div>
                <div className="text-[10px] font-mono text-faint">videos · 0 s in position</div>
              </div>
            </div>
            <div className="rounded border border-edge overflow-hidden">
              {[...withPos.slice(0, 8), ...withoutPos.slice(0, 6)].map((v) => {
                const has = v.sections.some((s) => s.pos === singlePos);
                const secs = v.sections.filter((s) => s.pos === singlePos);
                const time = secs.reduce((a, s) => a + (s.end - s.start), 0);
                return (
                  <div key={v.id} className="flex items-center gap-3 px-3 h-9 border-b border-edge hover:bg-panel2">
                    <span className={`w-1.5 h-1.5 rounded-full ${has ? "bg-sage" : "bg-brick"}`} />
                    <span className="text-[12px] flex-1 truncate">{v.title}</span>
                    <span className="text-[11px] font-mono text-faint">{v.creator}</span>
                    <span className="text-[11px] font-mono text-dim">{has ? fmtDur(time) + " in position" : "—"}</span>
                    <Btn size="sm" variant="subtle" onClick={() => ctx.go("review")}>review</Btn>
                  </div>
                );
              })}
            </div>
          </div>
        ) : results ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Micro>{results.length} playable clips · {chosen.join(" + ")}</Micro>
              <Btn size="sm" variant="outline" onClick={() => ctx.openViewer(
                results.map((c) => ({ seed: c.seed, kind: "clip" as const, title: c.title, creator: c.creator, pos: c.pos, sub: c.sub, conf: c.conf, verified: c.verified, clipRange: c.clip, sectionRange: c.section, duration: c.duration })),
                0, true)}>
                <Icon name="refresh" size={11} /> endless full-screen slideshow
              </Btn>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {results.map((c) => (
                <div key={c.id} className="rounded border border-edge bg-panel overflow-hidden hover:border-edge2 transition-colors">
                  <div className="relative">
                    <Thumb seed={c.seed} ratio="16:9" className="aspect-video w-full" />
                    <button className="absolute inset-0 flex items-center justify-center"
                      onClick={() => setPlaying(playing === c.id ? null : c.id)}>
                      <span className="w-11 h-11 rounded-full bg-ink/70 border border-edge2 flex items-center justify-center text-cream hover:text-amber">
                        <Icon name={playing === c.id ? "pause" : "play"} size={16} />
                      </span>
                    </button>
                    {playing === c.id && <div className="absolute bottom-0 inset-x-0 h-[3px] bg-amber/80" style={{ animation: "shimmer 4s linear infinite", backgroundSize: "200% 100%" }} />}
                    <div className="absolute top-1 left-1"><ConfTag kind={c.verified ? "verified" : "model"} conf={c.conf} /></div>
                  </div>
                  <div className="p-2.5 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] text-amber font-medium">{c.pos}</span>
                      <span className="text-[11px] text-faint">{c.sub}</span>
                    </div>
                    <div className="text-[11px] text-dim truncate">{c.title} · <span className="text-faint">{c.creator}</span></div>
                    <Timeline duration={c.duration} sections={[{ start: c.section[0], end: c.section[1], conf: c.conf, verified: c.verified, pos: c.pos }]} clipRange={c.clip} className="w-full" />
                    <div className="flex items-center justify-between text-[10px] font-mono text-faint">
                      <span>clip {fmtDur(c.clip[0])}–{fmtDur(c.clip[1])}</span>
                      <span>section {fmtDur(c.section[0])}–{fmtDur(c.section[1])}</span>
                    </div>
                    <div className="flex items-center gap-1 pt-0.5">
                      <Btn size="sm" variant="outline" onClick={() => ctx.notify("Swapped", "replaced with a different video for " + c.pos, "info")}><Icon name="swap" size={11} /> swap</Btn>
                      <Btn size="sm" variant="outline" onClick={() => ctx.notify("Revealed", "~/postroom/media/" + c.id + ".mp4", "info")}><Icon name="folderOpen" size={11} /> file</Btn>
                      <Btn size="sm" variant="outline" onClick={() => ctx.toggleFav(c.id)}><Icon name="heart" size={11} className={ctx.isFav(c.id) ? "text-amber fill-amber" : ""} /></Btn>
                      <Btn size="sm" variant="subtle" className="ml-auto" onClick={() => ctx.go("review")}>review</Btn>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center gap-3 text-center">
            <div className="w-12 h-12 rounded-full border border-edge flex items-center justify-center text-faint"><Icon name="film" size={20} /></div>
            <div className="text-[13px] text-dim">Pick one or more positions, then build a clip set</div>
            <div className="text-[11px] text-faint max-w-[340px]">Clips are pulled by position along each video's timeline. Every clip shows its section range, model confidence and verified status.</div>
          </div>
        )}
      </div>
    </div>
  );
}
