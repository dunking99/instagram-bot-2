import { useMemo, useRef, useState } from "react";
import { ACCOUNTS, ATTR_GROUPS, EMPTY_HELP, POSITIONS, STARTER_PROMPTS, hashStr, mulberry } from "../lib/data";
import { Btn, Chip, ConfTag, EmptyState, Field, Icon, Micro, Num, Panel, ScoreBar, Seg, Slider, Text, Thumb, Toggle, useCtx } from "../lib/ui";

interface Result { id: string; seed: string; score: number; conf: number; verified: boolean; account: string; kind: "image" | "clip"; }

export default function SearchView() {
  const ctx = useCtx();
  const [text, setText] = useState("");
  const [modeText, setModeText] = useState(true);
  const [modePhoto, setModePhoto] = useState(false);
  const [modePose, setModePose] = useState(false);
  const [pose, setPose] = useState(POSITIONS[0].name);
  const [poseSub, setPoseSub] = useState(POSITIONS[0].subs[0]);
  const [weight, setWeight] = useState(60);
  const [strict, setStrict] = useState(50);
  const [mirror, setMirror] = useState(true);
  const [attrs, setAttrs] = useState<Record<string, string[]>>({});
  const [reqConf, setReqConf] = useState(60);
  const [matchMode, setMatchMode] = useState<"best" | "worst">("best");
  const [countMode, setCountMode] = useState<"n" | "all">("n");
  const [count, setCount] = useState(24);
  const [share, setShare] = useState<"each" | "pooled" | "even">("pooled");
  const [form, setForm] = useState<"thumbs" | "full" | "links">("thumbs");
  const [more, setMore] = useState(false);
  const [dateFrom, setDateFrom] = useState("2024-01-01");
  const [dateTo, setDateTo] = useState("2026-02-14");
  const [includeVideos, setIncludeVideos] = useState(true);
  const [mix, setMix] = useState(50);
  const [clipLen, setClipLen] = useState(30);
  const [carousel, setCarousel] = useState<"first" | "every" | "promising">("promising");
  const [poolSize, setPoolSize] = useState(5);
  const [freshness, setFreshness] = useState<"saved" | "check" | "rebuild">("saved");
  const [saveLoc, setSaveLoc] = useState("~/postroom/exports");
  const [acctQuery, setAcctQuery] = useState("");
  const [selectedAccts, setSelectedAccts] = useState<Set<string>>(new Set(ACCOUNTS.slice(0, 40).map((a) => a.id)));
  const [newAcct, setNewAcct] = useState("");
  const [running, setRunning] = useState(false);
  const [runProg, setRunProg] = useState(0);
  const [runLog, setRunLog] = useState<string[]>([]);
  const [results, setResults] = useState<Result[] | null>(null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const filteredAccts = useMemo(
    () => ACCOUNTS.filter((a) => !acctQuery || a.name.toLowerCase().includes(acctQuery.toLowerCase())).slice(0, 60),
    [acctQuery]
  );

  const attrCount = Object.values(attrs).reduce((a, v) => a + v.length, 0);
  const emptyRequest = !text.trim() && !modePhoto && !modePose && attrCount === 0;

  const toggleAttr = (g: string, v: string) =>
    setAttrs((m) => ({ ...m, [g]: m[g]?.includes(v) ? m[g].filter((x) => x !== v) : [...(m[g] ?? []), v] }));

  const run = () => {
    if (running) return;
    setRunning(true); setRunProg(0); setRunLog([]); setResults(null); setSel(new Set());
    const seed = hashStr(text + attrCount + matchMode + countMode + share + form + freshness);
    const r = mulberry(seed);
    const n = countMode === "all" ? 48 : Math.min(48, Math.max(6, count));
    const items: Result[] = Array.from({ length: n }, (_, i) => {
      const score = matchMode === "best" ? 99 - r() * 40 - i * 0.4 : 40 + r() * 30 + i * 0.3;
      const acct = ACCOUNTS[Math.floor(r() * 60)];
      return {
        id: "r" + i, seed: "s" + seed + i, score: Math.max(2, Math.min(99, score)),
        conf: 0.4 + r() * 0.59, verified: r() > 0.6, account: acct.name, kind: r() > 0.8 ? "clip" : "image",
      };
    });
    const lines = ["parsing request", `${selectedAccts.size} accounts in scope`, "weighting text/photo", "matching attributes", "scoring candidates"];
    let p = 0;
    timer.current = setInterval(() => {
      p += 4 + Math.random() * 9;
      if (p > 100) p = 100;
      setRunProg(p);
      if (Math.random() > 0.6 && lines.length) setRunLog((l) => [...l, lines.shift()!]);
      if (p >= 100) {
        if (timer.current) clearInterval(timer.current);
        setRunning(false);
        setResults(items);
        ctx.notify("Search complete", `${items.length} matches · ${selectedAccts.size} accounts`, "ok");
      }
    }, 180);
  };
  const cancel = () => { if (timer.current) clearInterval(timer.current); setRunning(false); ctx.notify("Search cancelled", "partial work discarded", "info"); };

  const activeOptions = [
    ...(modeText ? ["text"] : []), ...(modePhoto ? ["photo ref"] : []), ...(modePose ? [`pose: ${pose}`] : []),
    attrCount ? `${attrCount} attrs ≥${reqConf}%` : null,
    matchMode, countMode === "all" ? "everything (cap 500)" : `n=${count}`, share, form,
    freshness === "saved" ? "saved data" : freshness === "check" ? "check for new" : "rebuild",
    includeVideos ? `videos (${mix}% video)` : "images only",
    carousel === "first" ? "carousel: first" : carousel === "every" ? "carousel: every slide" : "carousel: promising",
    `pool ${poolSize}`, dateFrom !== "2024-01-01" || dateTo !== "2026-02-14" ? `${dateFrom} → ${dateTo}` : null,
    saveLoc !== "~/postroom/exports" ? saveLoc : null,
  ].filter(Boolean) as string[];

  return (
    <div className="flex h-full min-h-0">
      {/* -------- config column -------- */}
      <div className="w-[330px] shrink-0 border-r border-edge overflow-y-auto p-3 space-y-3 hidden md:block">
        <Panel title="Describe" pad={false}>
          <div className="p-3 space-y-2">
            <div className="flex gap-1">
              <Chip active={modeText} onClick={() => setModeText(!modeText)}><Icon name="type" size={11} /> text</Chip>
              <Chip active={modePhoto} onClick={() => setModePhoto(!modePhoto)}><Icon name="image" size={11} /> reference photo</Chip>
              <Chip active={modePose} onClick={() => setModePose(!modePose)}><Icon name="pose" size={11} /> body pose</Chip>
            </div>
            {modeText && (
              <>
                <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder="describe what you want in words…"
                  className="w-full bg-ink border border-edge rounded p-2 text-[12px] text-cream outline-none focus:border-amber/50 placeholder:text-faint resize-none" />
                {!text && (
                  <div className="flex flex-wrap gap-1">
                    {STARTER_PROMPTS.slice(0, 4).map((p) => (
                      <button key={p} onClick={() => setText(p)} className="text-[10px] font-mono text-faint hover:text-amber border border-edge hover:border-amber/40 rounded-full px-2 py-0.5">{p}</button>
                    ))}
                  </div>
                )}
              </>
            )}
            {modePhoto && (
              <div className="border border-dashed border-edge2 rounded p-2 flex items-center gap-2">
                <Thumb seed="refphoto" ratio="3:4" className="w-10 h-12 rounded-sm" />
                <div className="text-[10px] text-faint leading-tight">reference photo loaded<br />swap / remove</div>
              </div>
            )}
            {modePose && (
              <div className="space-y-1.5">
                <select value={pose} onChange={(e) => { setPose(e.target.value); setPoseSub(POSITIONS.find((p) => p.name === e.target.value)!.subs[0]); }}
                  className="w-full bg-ink border border-edge rounded px-2 h-7 text-[11px] text-cream outline-none">
                  {POSITIONS.map((p) => <option key={p.name}>{p.name}</option>)}
                </select>
                <select value={poseSub} onChange={(e) => setPoseSub(e.target.value)}
                  className="w-full bg-ink border border-edge rounded px-2 h-7 text-[11px] text-cream outline-none">
                  {POSITIONS.find((p) => p.name === pose)!.subs.map((s) => <option key={s}>{s}</option>)}
                </select>
                <Toggle on={mirror} onChange={setMirror} label="allow left-right mirror" />
              </div>
            )}
            {modePhoto && (
              <div className="space-y-1.5">
                <Micro>text ↔ photo weight</Micro>
                <Slider value={weight} min={0} max={100} onChange={setWeight} format={(v) => v + "%"} />
              </div>
            )}
            {modePose && modeText && (
              <div className="space-y-1.5">
                <Micro>scene-match strictness with pose</Micro>
                <Slider value={strict} min={0} max={100} onChange={setStrict} format={(v) => v + "%"} />
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Attributes" pad={false}>
          <div className="p-3 space-y-2.5">
            {ATTR_GROUPS.map((g) => (
              <div key={g.name}>
                <Micro className="mb-1">{g.name}</Micro>
                <div className="flex flex-wrap gap-1">
                  {g.values.map((v) => (
                    <Chip key={v} active={attrs[g.name]?.includes(v)} onClick={() => toggleAttr(g.name, v)}>{v}</Chip>
                  ))}
                </div>
              </div>
            ))}
            <div className="space-y-1">
              <Micro>required confidence</Micro>
              <Slider value={reqConf} min={0} max={100} onChange={setReqConf} format={(v) => "≥ " + v + "%"} />
            </div>
          </div>
        </Panel>

        <Panel title="Match & share" pad={false}>
          <div className="p-3 space-y-2.5">
            <div className="flex items-center justify-between">
              <Micro>mode</Micro>
              <Seg value={matchMode} onChange={setMatchMode} options={[{ value: "best", label: "best matches" }, { value: "worst", label: "worst (testing)" }]} />
            </div>
            <div className="flex items-center justify-between gap-2">
              <Micro>count</Micro>
              <div className="flex items-center gap-1.5">
                <Seg value={countMode} onChange={setCountMode} options={[{ value: "n", label: "n" }, { value: "all", label: "everything" }]} />
                {countMode === "n" && <Num value={count} onChange={setCount} max={500} />}
                {countMode === "all" && <span className="text-[10px] font-mono text-faint">cap 500</span>}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <Micro>account sharing</Micro>
              <Seg value={share} onChange={setShare} options={[{ value: "each", label: "each" }, { value: "pooled", label: "pooled" }, { value: "even", label: "even split" }]} />
            </div>
            <div className="flex items-center justify-between">
              <Micro>result form</Micro>
              <Seg value={form} onChange={setForm} options={[{ value: "thumbs", label: "thumbnails" }, { value: "full", label: "full-size" }, { value: "links", label: "links only" }]} />
            </div>
          </div>
        </Panel>

        <Panel title="Secondary options" pad={false}>
          <button onClick={() => setMore(!more)} className="w-full flex items-center justify-between px-3 h-8 text-faint hover:text-dim">
            <Micro>{more ? "hide" : "show"}</Micro>
            <Icon name="chevD" size={12} className={more ? "rotate-180 transition-transform" : "transition-transform"} />
          </button>
          {more && (
            <div className="p-3 pt-0 space-y-2.5">
              <div className="grid grid-cols-2 gap-1.5">
                <Field label="from"><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-full bg-ink border border-edge rounded px-1.5 h-7 text-[11px] font-mono text-cream outline-none" /></Field>
                <Field label="to"><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-full bg-ink border border-edge rounded px-1.5 h-7 text-[11px] font-mono text-cream outline-none" /></Field>
              </div>
              <Toggle on={includeVideos} onChange={setIncludeVideos} label="include videos" />
              {includeVideos && <div className="space-y-1"><Micro>video / photo mix</Micro><Slider value={mix} min={0} max={100} onChange={setMix} format={(v) => v + "% video"} /></div>}
              {includeVideos && <div className="space-y-1"><Micro>clip length</Micro><Slider value={clipLen} min={5} max={120} onChange={setClipLen} format={(v) => v + " s"} /></div>}
              <div className="space-y-1">
                <Micro>carousel posts</Micro>
                <Seg value={carousel} onChange={setCarousel} options={[{ value: "first", label: "first only" }, { value: "every", label: "every slide" }, { value: "promising", label: "look inside N" }]} />
                {carousel === "promising" && <div className="mt-1"><Slider value={poolSize} min={1} max={10} onChange={setPoolSize} format={(v) => "top " + v} /></div>}
              </div>
              <div className="space-y-1">
                <Micro>random pool among top matches</Micro>
                <Slider value={poolSize} min={1} max={20} onChange={setPoolSize} format={(v) => String(v)} />
              </div>
              <div className="space-y-1">
                <Micro>data freshness</Micro>
                <Seg value={freshness} onChange={setFreshness} options={[{ value: "saved", label: "use saved" }, { value: "check", label: "check for new" }, { value: "rebuild", label: "rebuild" }]} />
              </div>
              <Field label="save location"><Text value={saveLoc} onChange={setSaveLoc} className="w-full font-mono text-[11px]" /></Field>
            </div>
          )}
        </Panel>

        <Panel title="Accounts" pad={false}>
          <div className="p-3 space-y-2">
            <div className="flex gap-1.5">
              <Text value={newAcct} onChange={setNewAcct} placeholder="add by name…" className="flex-1" />
              <Btn size="sm" variant="outline" onClick={() => { if (newAcct.trim()) { ctx.notify("Account added", newAcct.trim() + " — not yet indexed", "info"); setNewAcct(""); } }}><Icon name="plus" size={12} /></Btn>
            </div>
            <Text value={acctQuery} onChange={setAcctQuery} placeholder="filter accounts…" className="w-full" />
            <div className="max-h-[220px] overflow-y-auto space-y-0.5 border border-edge rounded">
              {filteredAccts.map((a) => {
                const on = selectedAccts.has(a.id);
                return (
                  <div key={a.id} className={`flex items-center gap-2 px-2 h-7 cursor-pointer hover:bg-panel3 ${on ? "text-cream" : "text-faint"}`}
                    onClick={() => setSelectedAccts((s) => { const n = new Set(s); n.has(a.id) ? n.delete(a.id) : n.add(a.id); return n; })}>
                    <span className={`w-3 h-3 rounded-sm border flex items-center justify-center ${on ? "bg-amber border-amber text-ink" : "border-edge2"}`}>
                      {on && <Icon name="check" size={9} />}
                    </span>
                    <span className="text-[11px] truncate flex-1">{a.name}</span>
                    {!a.idxSearch && <span className="text-[9px] font-mono text-brick border border-brick/40 rounded-full px-1">not indexed</span>}
                    {a.status === "indexing" && <span className="w-1.5 h-1.5 rounded-full bg-amber pulse-dot" />}
                  </div>
                );
              })}
            </div>
            <div className="flex items-center justify-between text-[10px] font-mono text-faint">
              <span>{selectedAccts.size} selected</span>
              <button className="hover:text-amber" onClick={() => ctx.pushJob("Prepare selected accounts", "prepare", { total: 100, warn: true })}>prepare not-indexed</button>
            </div>
          </div>
        </Panel>
      </div>

      {/* -------- results column -------- */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* active options record */}
        <div className="border-b border-edge px-3 py-2 flex flex-wrap items-center gap-1.5">
          <Micro className="mr-1">active options</Micro>
          {activeOptions.slice(0, 8).map((o) => (
            <span key={o} className="text-[10px] font-mono text-dim border border-edge rounded-full px-1.5 py-px bg-panel2">{o}</span>
          ))}
          {activeOptions.length > 8 && <span className="text-[10px] font-mono text-faint">+{activeOptions.length - 8} more</span>}
          {emptyRequest && <span className="text-[10px] font-mono text-amber border border-amber/40 bg-amber/10 rounded-full px-1.5 py-px">empty request → fully random draw</span>}
        </div>

        {/* run bar */}
        <div className="border-b border-edge px-3 py-2 flex items-center gap-2">
          <Btn variant="primary" onClick={run} disabled={running}><Icon name="zap" size={13} /> {running ? "running…" : results ? "run again" : "run search"} <span className="opacity-60 font-mono text-[10px]">⌘↵</span></Btn>
          {running && <Btn variant="danger" size="sm" onClick={cancel}><Icon name="stop" size={12} /> cancel</Btn>}
          {running && (
            <div className="flex-1 flex items-center gap-2">
              <div className="flex-1 h-[3px] rounded bg-panel3 overflow-hidden"><div className="h-full bg-amber" style={{ width: runProg + "%" }} /></div>
              <span className="text-[10px] font-mono text-dim w-8 text-right">{Math.round(runProg)}%</span>
            </div>
          )}
          {results && <span className="text-[11px] font-mono text-faint">{results.length} matches · {form === "links" ? "links only" : form === "full" ? "full-size files" : "thumbnails"}</span>}
        </div>

        {running && (
          <div className="px-3 py-2 border-b border-edge font-mono text-[10px] text-faint space-y-0.5 max-h-24 overflow-y-auto">
            {runLog.map((l, i) => <div key={i}>· {l}</div>)}
            <div className="text-amber">· scoring candidates…</div>
          </div>
        )}

        {/* bulk bar */}
        {sel.size > 0 && (
          <div className="border-b border-edge bg-panel2 px-3 py-1.5 flex items-center gap-2 anim-fade">
            <span className="text-[11px] font-mono text-amber">{sel.size} selected</span>
            <Btn size="sm" variant="outline" onClick={() => ctx.notify("Saved as thumbnails", sel.size + " items → ~/postroom/exports/thumbs", "ok")}>save as thumbnails</Btn>
            <Btn size="sm" variant="outline" onClick={() => ctx.notify("Saved full-size", sel.size + " files queued as a job", "ok")}>save full size</Btn>
            <Btn size="sm" variant="outline" onClick={() => ctx.notify("Download started", sel.size + " items", "ok")}>download</Btn>
            <Btn size="sm" variant="subtle" onClick={() => setSel(new Set())}>clear</Btn>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-3">
          {!results && !running && (
            <div className="h-full flex flex-col items-center justify-center gap-3 text-center">
              <div className="w-12 h-12 rounded-full border border-edge flex items-center justify-center text-faint"><Icon name="search" size={20} /></div>
              <div className="text-[13px] text-dim">Describe it, point at it, or pose it</div>
              <div className="text-[11px] text-faint max-w-[340px]">Any combination of words, a reference photo and a body pose. An empty request runs a fully random draw across selected accounts.</div>
              <div className="flex flex-wrap justify-center gap-1 mt-1">
                {STARTER_PROMPTS.slice(4).map((p) => (
                  <button key={p} onClick={() => { setText(p); }} className="text-[10px] font-mono text-faint hover:text-amber border border-edge hover:border-amber/40 rounded-full px-2 py-0.5">{p}</button>
                ))}
              </div>
            </div>
          )}
          {results && results.length === 0 && (
            <EmptyState icon="search" title="No matches" body={EMPTY_HELP[0]}
              action={<Btn size="sm" variant="outline" onClick={() => setResults(null)}>adjust request</Btn>} />
          )}
          {results && results.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-2">
              {results.map((r) => (
                <div key={r.id} className={`group relative rounded border overflow-hidden cursor-pointer transition-colors ${sel.has(r.id) ? "border-amber/60" : "border-edge hover:border-edge2"}`}
                  onClick={() => setSel((s) => { const n = new Set(s); n.has(r.id) ? n.delete(r.id) : n.add(r.id); return n; })}>
                  <Thumb seed={r.seed} ratio="3:4" className="aspect-[3/4] w-full" />
                  <div className="absolute top-1 left-1"><ConfTag kind={r.verified ? "verified" : "model"} conf={r.conf} /></div>
                  <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button className="w-6 h-6 rounded-full bg-ink/80 border border-edge2 flex items-center justify-center text-dim hover:text-amber"
                      onClick={(e) => { e.stopPropagation(); ctx.toggleFav(r.id); }}>
                      <Icon name="heart" size={11} className={ctx.isFav(r.id) ? "text-amber fill-amber" : ""} />
                    </button>
                  </div>
                  <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-ink/90 to-transparent p-1.5 pt-4">
                    <div className="flex items-center justify-between gap-1">
                      <ScoreBar value={r.score / 100} />
                      <span className="text-[9px] font-mono text-faint truncate">{r.account}</span>
                    </div>
                  </div>
                  {/* hover actions */}
                  <div className="absolute inset-0 bg-ink/70 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-1 p-2">
                    <Btn size="sm" variant="primary" onClick={(e) => { e?.stopPropagation(); ctx.openViewer(results.map((x) => ({ seed: x.seed, kind: x.kind, title: x.account, score: x.score, conf: x.conf, verified: x.verified })), results.indexOf(r)); }}>
                      <Icon name="maximize" size={11} /> view
                    </Btn>
                    <div className="flex gap-1">
                      <Btn size="sm" variant="outline" onClick={(e) => { e?.stopPropagation(); ctx.notify("Slideshow started", results.length + " items", "info"); }}><Icon name="play" size={10} /> slideshow</Btn>
                      <Btn size="sm" variant="outline" onClick={(e) => { e?.stopPropagation(); ctx.notify("Downloaded", r.account + " · full size", "ok"); }}><Icon name="download" size={10} /></Btn>
                      <Btn size="sm" variant="outline" onClick={(e) => { e?.stopPropagation(); ctx.notify("Link copied", "https://" + r.account.replace("@", "") + "/p/" + r.id, "info"); }}><Icon name="copy" size={10} /></Btn>
                    </div>
                    <div className="flex gap-1">
                      <Btn size="sm" variant="subtle" onClick={(e) => { e?.stopPropagation(); ctx.notify("Opened original post", r.account, "info"); }}><Icon name="external" size={10} /> original</Btn>
                      <Btn size="sm" variant="subtle" onClick={(e) => { e?.stopPropagation(); ctx.notify("Revealed in file manager", "~/postroom/media/" + r.id, "info"); }}><Icon name="folderOpen" size={10} /> file</Btn>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          {results && results.length > 0 && (
            <div className="text-center py-6 text-[11px] font-mono text-faint">end of results · {results.length} shown</div>
          )}
        </div>
      </div>
    </div>
  );
}
