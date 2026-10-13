import { useEffect, useMemo, useRef, useState } from "react";
import { api, post } from "../api";
import { formatDate, tagText, titleCase, type Account, type Breakdown, type Item, type TagPick } from "../types";
import { useDesk } from "../store";
import { cn } from "../utils/cn";
import { ContactSheet } from "./Frames";
import { Modal } from "./ui";

const ALL = "__all__";
const PAGE = 24;
const cache = new Map<string, Breakdown>();

function codeOf(path: string) {
  const m = path.match(/\/(?:p|reel|reels)\/([\w-]+)/);
  return m ? m[1] : "";
}

function merge(list: Breakdown[]): Breakdown {
  const out: Breakdown = { account: ALL, items: {}, photos: 0, slides: 0, carousels: null, expanded: 0, reels: 0, pose_ready: true, min_conf: list[0]?.min_conf ?? 0.5, facets: {} };
  for (const b of list) {
    out.photos += b.photos;
    out.slides += b.slides;
    out.reels += b.reels;
    out.expanded += b.expanded;
    if (b.carousels != null) out.carousels = (out.carousels ?? 0) + b.carousels;
    for (const [facet, f] of Object.entries(b.facets)) {
      const cur = (out.facets[facet] ||= { counts: {}, untagged: f.untagged == null ? null : 0 });
      for (const [label, n] of Object.entries(f.counts)) cur.counts[label] = (cur.counts[label] || 0) + n;
      if (f.untagged != null) cur.untagged = (cur.untagged ?? 0) + f.untagged;
    }
  }
  return out;
}

type Hit = { account: string; path: string; tags: Record<string, [string, number]>; conf: number };

export function LibraryView() {
  const d = useDesk();
  const accounts = (d.accounts as Account[]).filter((a) => a.kind !== "videos");
  const account: string = d.libraryAccount && (d.libraryAccount === ALL || accounts.some((a) => a.handle === d.libraryAccount))
    ? d.libraryAccount : accounts.find((a) => a.models[d.model as "siglip" | "clip"])?.handle || accounts[0]?.handle || "";
  const row = accounts.find((a) => a.handle === account);
  const [conf, setConf] = useState(0.5);
  const [confDraft, setConfDraft] = useState(0.5);
  const [info, setInfo] = useState<Breakdown | null>(null);
  const [parts, setParts] = useState<Record<string, Breakdown>>({});
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<TagPick[]>([]);
  const [pending, setPending] = useState<TagPick | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const [tree, setTree] = useState(false);
  const [described, setDescribed] = useState<Record<string, Partial<Item>>>({});
  const [cap, setCap] = useState(10);
  const [workers, setWorkers] = useState(1);
  const [until, setUntil] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setConf(confDraft), 450);
    return () => window.clearTimeout(t);
  }, [confDraft]);

  // load the tag counts (the server runs random_post.py --list-tags and caches the answer)
  useEffect(() => {
    if (!account) return;
    let live = true;
    const targets = account === ALL ? accounts.filter((a) => a.models.siglip || a.models.clip).map((a) => a.handle) : [account];
    setError("");
    setPicked([]);
    setPending(null);
    setLimit(PAGE);
    (async () => {
      const got: Breakdown[] = [];
      const byAcct: Record<string, Breakdown> = {};
      for (let i = 0; i < targets.length; i++) {
        const key = `${targets[i]}|${conf}|${d.model}|${d.dataVersion}`;
        let b = cache.get(key);
        if (!b) {
          setLoading(targets.length > 1 ? `Sorting posts: ${i + 1} of ${targets.length} (@${targets[i]})...` : `Sorting @${targets[i]}'s posts (about 20 seconds the first time)...`);
          try {
            b = await api<Breakdown>(`/api/breakdown?account=${encodeURIComponent(targets[i])}&conf=${conf}&model=${d.model}`);
            cache.set(key, b);
          } catch (e) {
            if (!live) return;
            if (targets.length === 1) {
              setError(e instanceof Error ? e.message : String(e));
              setInfo(null);
              setLoading("");
              return;
            }
            continue;
          }
        }
        if (!live) return;
        got.push(b);
        byAcct[targets[i]] = b;
      }
      if (!live) return;
      setParts(byAcct);
      setInfo(got.length ? (account === ALL ? merge(got) : got[0]) : null);
      setLoading("");
    })();
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, conf, d.model, d.dataVersion, accounts.length]);

  const total = info ? info.photos + info.slides : 0;

  const pickTag = (group: string, tag: string | null) => {
    setLimit(PAGE);
    setPending(null);
    const has = picked.some((t) => t.group === group && t.tag === tag);
    if (has) setPicked(picked.filter((t) => !(t.group === group && t.tag === tag)));
    else if (!picked.length) setPicked([{ group, tag }]);
    else if (picked.some((t) => t.group === group)) setPicked([...picked.filter((t) => t.group !== group), { group, tag }]);
    else setPending({ group, tag });
  };
  const resolvePending = (both: boolean) => {
    if (pending) setPicked(both ? [...picked, pending] : [pending]);
    setPending(null);
    setLimit(PAGE);
  };

  const matches: Hit[] = useMemo(() => {
    if (!picked.length) return [];
    const out: Hit[] = [];
    for (const [acct, b] of Object.entries(parts)) {
      for (const [path, tags] of Object.entries(b.items)) {
        const confs: number[] = [];
        let ok = true;
        for (const { group, tag } of picked) {
          const got = tags[group];
          if (tag == null) {
            if (got) { ok = false; break; }
          } else if (!got || got[0] !== tag) { ok = false; break; } else confs.push(got[1]);
        }
        if (ok) out.push({ account: acct, path, tags, conf: confs.length ? Math.min(...confs) : 0 });
      }
    }
    return out.sort((a, b) => b.conf - a.conf);
  }, [picked, parts]);

  const shownHits = matches.slice(0, limit);
  // enrich the visible batch with where each image came from (Instagram, a folder, a video)
  const lastBatch = useRef("");
  useEffect(() => {
    const need = shownHits.filter((h) => !described[`${h.account}|${h.path}`]);
    const sig = need.map((h) => h.account + h.path).join(",");
    if (!need.length || sig === lastBatch.current) return;
    lastBatch.current = sig;
    const byAcct: Record<string, string[]> = {};
    need.forEach((h) => (byAcct[h.account] ||= []).push(h.path));
    Object.entries(byAcct).forEach(([acct, paths]) => {
      post<{ items: Item[] }>("/api/describe", { account: acct, paths }).then((r) => {
        setDescribed((prev) => {
          const next = { ...prev };
          paths.forEach((p, i) => (next[`${acct}|${p}`] = r.items[i]));
          return next;
        });
      }).catch(() => undefined);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shownHits.length, matches]);

  const shown: Item[] = shownHits.map((h, i) => {
    const slide = h.path.match(/\/@(\d+)$/);
    const name = codeOf(h.path) + (slide ? `@${slide[1]}` : "");
    const acct = h.account.toLowerCase();
    const extra = described[`${h.account}|${h.path}`] || {};
    return {
      id: `${acct}:${name}`, rid: `${i}:${acct}:${name}`, account: h.account, name, slide: slide ? Number(slide[1]) : null,
      url: "https://www.instagram.com" + h.path.replace(/\/@\d+$/, "/"), score: null, date: null, type: "instagram",
      original: null, video: false, hasThumb: true, thumb: `/api/thumb/${acct}/${name}.jpg?w=560`,
      full: `/api/thumb/${acct}/${name}.jpg?w=1400`, src: `cache/thumbs/${acct}/${name}.jpg`,
      caption: Object.entries(h.tags).filter(([k]) => k !== "arms").map(([, v]) => v[0]).join(" · "), ...extra,
    } as Item;
  });

  const job = (d.jobs as { account: string | null; running: boolean; title: string; progress: number | null }[]).find((j) => j.running && j.account === account);
  const layout = [["setting"], ["outfit", "shot"], ["pose", "arms"]];
  const facets = info?.facets || {};
  const otherFacets = Object.keys(facets).filter((f) => !layout.flat().includes(f));
  const columns = [...layout.map((g) => g.filter((f) => facets[f])), otherFacets].filter((c) => c.length);
  const single = account !== ALL && !!row;
  const doneAll = !!row && row.toOpen > 0 && row.opened >= row.toOpen;

  return (
    <div>
      <p className="kicker">Library</p>
      <div className="spread">
        <h1 style={{ fontSize: "clamp(32px, 4vw, 48px)" }}>What's in the index.</h1>
        <div className="row">
          <button type="button" className="btn" onClick={() => d.setPrepareFor(single ? account : "")}>Prepare</button>
          {single && <button type="button" className="btn" onClick={() => setTree(true)}>{row?.libraryBuilt ? "Open library" : "Preview folders"}</button>}
        </div>
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        <label className="field" style={{ minWidth: 240 }}>
          <span>Account</span>
          <select className="quiet" value={account} onChange={(e) => d.setLibraryAccount(e.target.value)} aria-label="Account">
            {accounts.map((a) => <option key={a.handle} value={a.handle}>@{a.handle}{a.models[d.model as "siglip" | "clip"] ? "" : " (not indexed)"}</option>)}
            {accounts.length > 1 && <option value={ALL}>All accounts</option>}
          </select>
        </label>
        <label className="field" style={{ minWidth: 260, flex: "0 1 320px" }}>
          <span>How sure a tag must be · {confDraft.toFixed(2)}</span>
          <input type="range" min={0.3} max={0.95} step={0.05} value={confDraft} onChange={(e) => setConfDraft(Number(e.target.value))} />
        </label>
      </div>

      {!accounts.length && (
        <div className="empty">
          <h2>No accounts to break down yet.</h2>
          <p className="hint">Once an account has been read (prepare it, or run any photo search on it), its breakdown shows here.</p>
          <button type="button" className="btn tiny" style={{ marginTop: 10 }} onClick={() => d.setPrepareFor("")}>Prepare an account</button>
        </div>
      )}

      {loading && <p className="hint" style={{ margin: "16px 0" }}><span className="spinner" /> {loading}</p>}
      {error && <div className="callout"><p>{error}</p><button type="button" className="btn tiny" onClick={() => d.bump()}>Try again</button></div>}

      {info && (
        <>
          <div className="stats">
            <div className="stat"><b>{info.photos.toLocaleString()}</b><span>Photo posts</span></div>
            <div className="stat"><b>{info.reels.toLocaleString()}</b><span>Reels (not counted)</span></div>
            <div className="stat"><b>{info.carousels == null ? "?" : info.carousels.toLocaleString()}</b><span>Carousels{info.carousels == null ? " · not detected yet" : ` · ${info.expanded} looked inside`}</span></div>
            <div className="stat"><b>{info.slides.toLocaleString()}</b><span>Extra slide photos indexed</span></div>
          </div>
          <div className="meter" aria-hidden>
            <i style={{ width: `${(info.photos / Math.max(1, info.photos + info.reels + (info.carousels || 0))) * 100}%` }} />
            <i style={{ width: `${(info.reels / Math.max(1, info.photos + info.reels + (info.carousels || 0))) * 100}%` }} />
            <i style={{ width: `${((info.carousels || 0) / Math.max(1, info.photos + info.reels + (info.carousels || 0))) * 100}%` }} />
          </div>
          <p className="hint" style={{ margin: "8px 0 16px" }}>
            {total.toLocaleString()} images in total · {d.model.toUpperCase()} index
            {single && row?.prepared ? ` · prepared ${formatDate(row.prepared)}` : single ? " · not prepared" : ""}
            {single ? (info.pose_ready ? " · pose ready" : " · pose missing") : ""}
            {" · click a tag to see its images"}
          </p>
        </>
      )}

      {job && (
        <div className="callout">
          <p>{job.title}{job.progress != null ? ` · ${Math.round(job.progress)}%` : ""}</p>
          <button type="button" className="btn tiny" onClick={() => d.setJobsOpen(true)}>Show job</button>
        </div>
      )}

      {single && info && info.carousels == null && (
        <div className="callout">
          <p>Carousels aren't detected yet, so only each post's first photo is searched. It reads the profile once (about 2 minutes).</p>
          <button type="button" className="btn tiny" onClick={() => d.startJob({ kind: "detect", account })}>Detect carousels</button>
        </div>
      )}
      {single && info && !info.pose_ready && (
        <div className="callout">
          <p>No pose index yet, so the pose and arms tags are missing here. Building it takes a few minutes.</p>
          <button type="button" className="btn tiny" onClick={() => d.startJob({ kind: "pose", account })}>Build pose index</button>
        </div>
      )}

      {single && row && row.kind === "instagram" && row.carouselDetected && row.toOpen > 0 && (
        <div className="panel panelbox">
          <div className="spread">
            <div>
              <p className="kicker">Index every image</p>
              <h3>{row.opened} of {row.toOpen} carousel posts opened</h3>
              <p className="hint">{row.extraSlides} extra photos indexed. Opens every carousel so each slide can be found by search. Progress is saved after every post, so you can stop any time and continue later.</p>
            </div>
          </div>
          <div className="progress" style={{ margin: "10px 0" }}><i style={{ width: `${(row.opened / Math.max(1, row.toOpen)) * 100}%` }} /></div>
          <div className="row">
            <label className="inline-num">Open at most
              <input type="number" min={5} max={2000} value={cap} disabled={until} onChange={(e) => setCap(Math.max(5, Math.min(2000, Number(e.target.value) || 5)))} />
              posts this time
            </label>
            <label className="inline-num">Browser windows
              <select value={workers} onChange={(e) => setWorkers(Number(e.target.value))}>
                {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <button type="button" className={cn("signal", until && "on")} onClick={() => setUntil(!until)}>Keep going until done</button>
            <button type="button" className="btn primary" disabled={doneAll} onClick={() => d.startJob({ kind: "index", account, cap, workers, untilDone: until })}>
              {doneAll ? "All opened" : "Start / continue"}
            </button>
          </div>
          {until && <p className="hint" style={{ marginTop: 6 }}>Works through every remaining post in batches with short breaks, and stops by itself if Instagram starts failing to load pages.</p>}
          {workers > 1 && <p className="hint warn" style={{ marginTop: 8 }}>{workers} windows means about {workers} times the page loads per minute from your login. If Instagram starts failing pages, the job stops by itself; wait a few hours before trying again.</p>}
        </div>
      )}

      {info && (
        <div className="split">
          <aside className="tag-col">
            {columns.flat().map((facet) => {
              const f = facets[facet];
              const rows: [string | null, number][] = Object.entries(f.counts).sort((a, b) => b[1] - a[1]);
              if (f.untagged != null) rows.push([null, f.untagged]);
              const peak = Math.max(...rows.map(([, n]) => n), 0.25 * total, 1);
              return (
                <div key={facet} style={{ marginBottom: 14 }}>
                  <div className="tag-label">{titleCase(facet)}</div>
                  {rows.map(([label, n]) => {
                    const on = picked.some((t) => t.group === facet && t.tag === label);
                    return (
                      <button type="button" key={String(label)} disabled={n === 0} className={cn("count-line", on && "on")} onClick={() => pickTag(facet, label)}>
                        <span><i className="bar" style={{ width: 8 + (n / peak) * 42 }} />{label == null ? "No confident tag" : titleCase(label)}</span>
                        <em>{n.toLocaleString()} · {total ? Math.round((n / total) * 100) : 0}%</em>
                      </button>
                    );
                  })}
                </div>
              );
            })}
            <p className="hint">A second tag from another group asks whether to show it alone or require both. A tag from the same group replaces the first.</p>
          </aside>
          <div>
            {!picked.length ? (
              <div className="empty">
                <h2>Pick a tag.</h2>
                <p className="hint">Click a tag on the left to see the images carrying it, best matches first.</p>
              </div>
            ) : (
              <>
                <div className="spread" style={{ marginBottom: 10 }}>
                  <div>
                    <h2 style={{ fontSize: 26 }}>{matches.length.toLocaleString()} images · {tagText(picked)}</h2>
                    <p className="hint">All selected tags required · highest confidence first</p>
                  </div>
                  <button type="button" className="btn tiny" onClick={() => { setPicked([]); setPending(null); }}>Clear</button>
                </div>
                {shown.length ? <ContactSheet items={shown} /> : <div className="empty"><h2>No images for that combination.</h2></div>}
                {matches.length > shown.length && (
                  <button type="button" className="btn" style={{ marginTop: 12 }} onClick={() => setLimit(limit + PAGE)}>
                    Show more ({(matches.length - shown.length).toLocaleString()} left)
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <details className="acct-table">
        <summary>All saved accounts ({(d.accounts as Account[]).length})</summary>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Account</th><th>Posts</th><th>Videos</th><th>Status</th></tr></thead>
            <tbody>
              {(d.accounts as Account[]).map((a) => (
                <tr key={a.handle} onClick={() => a.kind !== "videos" && d.setLibraryAccount(a.handle)} className={cn(a.kind !== "videos" && "click")}>
                  <td>@{a.handle}</td>
                  <td>{a.posts}</td>
                  <td>{a.videos || ""}</td>
                  <td>{a.kind === "videos" ? "video folder" : a.models.siglip || a.models.clip ? "ready" : "not indexed yet"}{a.kind === "local" ? " · imported folder" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {pending && (
        <Modal kicker="Combine tags" title={`Add ${tagText([pending])}?`} onClose={() => setPending(null)}>
          <p className="hint">You picked {tagText(picked)}. Now {tagText([pending])}: show it on its own, or only the images that have both?</p>
          <div className="row" style={{ marginTop: 16 }}>
            <button type="button" className="btn" onClick={() => resolvePending(false)}>Just {tagText([pending])}</button>
            <button type="button" className="btn primary" onClick={() => resolvePending(true)}>{tagText(picked)} + {tagText([pending])}</button>
            <button type="button" className="btn" onClick={() => setPending(null)}>Cancel</button>
          </div>
        </Modal>
      )}

      {tree && single && info && (
        <Modal kicker={`library/${account}`} title={row?.libraryBuilt ? "Categorised folders" : "Not written yet"} onClose={() => setTree(false)} wide>
          <p className="hint" style={{ marginBottom: 12 }}>
            {row?.libraryBuilt
              ? "Folders were built from the tag pass. The counts below are the current tags at this confidence."
              : "Rebuild sorts the saved thumbnails into folders by setting, outfit, shot and pose. The preview below is what that pass would file."}
          </p>
          <div className="tree">
            <b>library/{account}/</b>
            {Object.entries(info.facets).map(([facet, f]) => (
              <div key={facet}>
                <b>{"  "}{facet}/</b>
                {Object.entries(f.counts).filter(([, n]) => n).sort((a, b) => b[1] - a[1]).map(([label, n]) => <div key={label}>{"    "}{label}/ · {n}</div>)}
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            {row?.libraryBuilt && <button type="button" className="btn" onClick={() => d.openFolder(`library/${account}`)}>Open library in Finder</button>}
            <button type="button" className="btn primary" onClick={async () => { if (await d.startJob({ kind: "library", account, conf })) setTree(false); }}>
              {row?.libraryBuilt ? "Refresh library folders" : "Build library folders"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
