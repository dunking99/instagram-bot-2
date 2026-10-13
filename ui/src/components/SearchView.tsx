import { useEffect, useRef, useState } from "react";
import { api, fileToDataUrl } from "../api";
import { titleCase, type Account, type Item } from "../types";
import { useDesk } from "../store";
import { cn } from "../utils/cn";
import { ContactSheet, LinkList } from "./Frames";
import { Icon, Seg } from "./ui";

const IDEAS = ["smiling on a beach", "mirror selfie", "red dress, golden hour", "full body walking on a street", "cafe table, seated"];

function previewSrc(v: string | null) {
  if (!v) return null;
  return v.startsWith("data:") ? v : `/api/file?p=${encodeURIComponent(v)}&w=420`;
}

function Drop({ image, label, onFile, onClear }: {
  image: string | null;
  label: string;
  onFile: (file: File) => void;
  onClear: () => void;
}) {
  const src = previewSrc(image);
  return (
    <div
      className={cn("drop", image && "has")}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      {src && <img src={src} alt="" />}
      <span className="drop-ui">
        <label>
          {label}
          <input type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { const file = e.target.files?.[0]; if (file) onFile(file); e.target.value = ""; }} />
        </label>
        {image && (
          <button type="button" className="btn tiny" style={{ marginTop: 8 }} onClick={onClear}>Remove</button>
        )}
      </span>
    </div>
  );
}

/** A handful of saved pictures from the chosen accounts, to use as a reference. */
function SamplePicks({ onPick, label }: { onPick: (path: string) => void; label: string }) {
  const d = useDesk();
  const [items, setItems] = useState<{ name: string; src: string; path: string; account: string }[]>([]);
  const key = d.selectedAccounts.slice(0, 3).join(",");
  useEffect(() => {
    let live = true;
    Promise.all(
      d.selectedAccounts.slice(0, 3).map((a: string) =>
        api<{ items: { name: string; src: string; path: string }[] }>(`/api/accounts/${encodeURIComponent(a)}/sample?n=4`)
          .then((r) => r.items.map((i) => ({ ...i, account: a })))
          .catch(() => []),
      ),
    ).then((all) => live && setItems(all.flat()));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  if (!items.length) return null;
  return (
    <div className="pick-row">
      {items.map((it) => (
        <button type="button" key={it.path} onClick={() => onPick(it.path)} aria-label={label}>
          <img src={it.src} alt="" />
        </button>
      ))}
    </div>
  );
}

function AccountPicker() {
  const d = useDesk();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const accounts = d.accounts as Account[];
  const shown = accounts.filter((a) => a.handle.includes(q.trim().toLowerCase().replace(/^@/, "")));
  const ready = accounts.filter((a) => a.models[d.model as "siglip" | "clip"]).map((a) => a.handle);
  const typed = q.trim().replace(/^@/, "").toLowerCase();
  const isNew = typed && !accounts.some((a) => a.handle === typed);
  return (
    <div className="picker" ref={box}>
      <button type="button" className="btn tiny" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Choose accounts · {d.selectedAccounts.length} <Icon name="plus" size={12} />
      </button>
      {open && (
        <div className="picker-pop" role="dialog" aria-label="Choose accounts">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (isNew) {
                d.addAccount(typed);
                setQ("");
              }
            }}
          >
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter, or type a new @username and press Enter" aria-label="Filter or add account" />
          </form>
          <div className="row" style={{ margin: "8px 0" }}>
            <button type="button" className="btn tiny" disabled={!ready.length} onClick={() => d.setSelectedAccounts(ready)}>Select all ready</button>
            <button type="button" className="btn tiny" disabled={!d.selectedAccounts.length} onClick={() => d.setSelectedAccounts([])}>Clear</button>
            {isNew && <button type="button" className="btn tiny primary" onClick={() => { d.addAccount(typed); setQ(""); }}>Add @{typed}</button>}
          </div>
          <div className="picker-list">
            {shown.map((a) => {
              const on = d.selectedAccounts.includes(a.handle);
              const isReady = a.models[d.model as "siglip" | "clip"];
              return (
                <button type="button" key={a.handle} className={cn("pick-item", on && "on")} onClick={() => d.toggleAccount(a.handle)} aria-pressed={on}>
                  <span className="pick-box">{on ? <Icon name="check" size={12} /> : null}</span>
                  {a.cover ? <img src={a.cover} alt="" /> : <span className="pick-ph" />}
                  <span className="pick-name">@{a.handle}</span>
                  <em>{a.kind === "videos" ? "video folder" : a.kind === "local" ? "folder" : ""}{!isReady ? " · not indexed" : ""}</em>
                </button>
              );
            })}
            {!shown.length && <p className="hint" style={{ padding: 8 }}>No account matches. {typed ? "Press Enter to add it." : ""}</p>}
          </div>
        </div>
      )}
    </div>
  );
}

export function SearchView() {
  const d = useDesk();
  const [tagsOpen, setTagsOpen] = useState(d.tags.length > 0 || d.takeAll);
  const accounts = d.accounts as Account[];
  const hasSignal = (d.useText && d.text.trim()) || (d.useImage && d.refImage) || (d.usePose && d.poseImage) || d.tags.length > 0;
  const both = d.useText && d.text.trim() && d.useImage && d.refImage;
  const missing = d.selectedAccounts.filter((h: string) => !accounts.find((a) => a.handle === h)?.models[d.model as "siglip" | "clip"]);
  const tagGroups = Object.keys(d.config.tags);
  const sameGroup = tagGroups.some((g) => d.tags.filter((t: { group: string }) => t.group === g).length > 1);
  const shownSel = d.selectedAccounts.slice(0, 14);
  const typedErr = !d.session.loggedIn || !d.session.authFile;

  return (
    <div>
      {d.results == null && !d.searching && (
        <header className="search-intro">
          <p className="kicker">Search desk</p>
          <h1>Find a frame in the index.</h1>
          <p className="lede">
            Describe a scene, drop a reference, match a pose, or require tags. Postroom ranks the saved index. Leave everything empty for a fully random draw.
          </p>
        </header>
      )}

      {typedErr && (
        <div className="banner">
          <p>{d.session.authFile ? "The saved Instagram session has no login." : "Not logged in yet."} Searches on saved indexes still work. Refreshing, rebuilding and new accounts need a login.</p>
          <button type="button" className="btn tiny" onClick={() => d.setSessionOpen(true)}>Session</button>
        </div>
      )}

      <section className={cn("composer", !d.composerOpen && "slim")}>
        {!d.composerOpen ? (
          <div className="slim">
            <div>
              <strong>{d.lastSummary || "Last search"}</strong>
              <span>{d.results ? `${d.results.length} ${d.results.length === 1 ? "frame" : "frames"}` : "No cut yet"} · {d.model}</span>
            </div>
            <div className="row">
              <button type="button" className="btn tiny" onClick={() => d.setComposerOpen(true)}>Edit</button>
              <button type="button" className="btn primary" onClick={() => d.find()} disabled={d.searching}>Run again</button>
            </div>
          </div>
        ) : (
          <>
            <div className="spread">
              <p className="kicker" style={{ margin: 0 }}>Accounts</p>
              <div className="row">
                <AccountPicker />
                <button type="button" className="btn tiny" onClick={() => d.setPrepareFor("")}>Prepare indexes</button>
              </div>
            </div>
            <div className="acct-row" style={{ marginTop: 8 }}>
              {shownSel.map((h: string) => {
                const a = accounts.find((x) => x.handle === h);
                return (
                  <button key={h} type="button" className="acct on" onClick={() => d.toggleAccount(h)} title="Click to remove">
                    {a?.cover ? <img src={a.cover} alt="" /> : <span className="pick-ph" />}
                    <span>@{h}</span>
                    {a && !a.models[d.model as "siglip" | "clip"] && <i className="mini-dot" title={`No ${d.model} index`} />}
                    <span aria-hidden>×</span>
                  </button>
                );
              })}
              {d.selectedAccounts.length > shownSel.length && <span className="hint">+{d.selectedAccounts.length - shownSel.length} more</span>}
              {!d.selectedAccounts.length && <span className="hint">{d.accountsLoaded ? "No account chosen yet. Use Choose accounts." : "Loading accounts..."}</span>}
            </div>

            <div className={cn("query", !d.useText && "off")}>
              <textarea
                id="query"
                value={d.text}
                onChange={(e) => d.setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) d.find();
                }}
                placeholder={d.useText ? "Describe the frame you want... (empty = fully random)" : "Text ranking is off"}
                rows={2}
                readOnly={!d.useText}
              />
            </div>
            <div className="signals">
              <button type="button" className={cn("signal", d.useText && "on")} onClick={() => d.setUseText(!d.useText)}>Scene text</button>
              <button type="button" className={cn("signal", d.useImage && "on")} onClick={() => d.setUseImage(!d.useImage)}>Reference</button>
              <button type="button" className={cn("signal", d.usePose && "on")} onClick={() => d.setUsePose(!d.usePose)}>Pose</button>
              {!hasSignal && d.results == null && IDEAS.map((idea) => (
                <button type="button" key={idea} className="signal ghost" onClick={() => { d.setText(idea); d.setUseText(true); }}>{idea}</button>
              ))}
            </div>

            {d.useImage && (
              <div className="drop-grid">
                <Drop
                  image={d.refImage}
                  label="Drop a look-alike photo, or choose one"
                  onFile={async (f) => d.setRefImage(await fileToDataUrl(f))}
                  onClear={() => d.setRefImage(null)}
                />
                <div>
                  <p className="hint">Finds posts that look like this photo: the same scene, setting and style. It can be combined with the text above.</p>
                  <SamplePicks onPick={d.setRefImage} label="Use as reference" />
                  {both && (
                    <div className="weight">
                      <div className="ends">
                        <span>Text {Math.round((1 - d.imageWeight) * 100)}</span>
                        <span>Image {Math.round(d.imageWeight * 100)}</span>
                      </div>
                      <input type="range" min={0} max={1} step={0.05} value={d.imageWeight} onChange={(e) => d.setImageWeight(Number(e.target.value))} aria-label="Text and image weight" />
                    </div>
                  )}
                </div>
              </div>
            )}

            {d.usePose && (
              <div className="drop-grid">
                <Drop
                  image={d.poseImage}
                  label="Drop a pose reference, or choose one"
                  onFile={async (f) => d.setPoseImage(await fileToDataUrl(f))}
                  onClear={() => d.setPoseImage(null)}
                />
                <div className="stack">
                  <button type="button" className={cn("toggle", d.mirrorPose && "on")} onClick={() => d.setMirrorPose(!d.mirrorPose)}>
                    <span className="track"><span className="knob" /></span>
                    <span>
                      <strong>Count a left-right flipped pose as a match</strong>
                      <small>Unusual angles are less reliable. Scene text or a reference can still steer the rank.</small>
                    </span>
                  </button>
                  {(both || (d.useText && d.text.trim()) || (d.useImage && d.refImage)) && (
                    <label className="field">
                      <span>Scene strictness · best {d.sceneTop}% for the scene, then ordered by pose</span>
                      <input type="range" min={5} max={100} step={5} value={d.sceneTop} onChange={(e) => d.setSceneTop(Number(e.target.value))} />
                    </label>
                  )}
                  <p className="hint warn">The first time on an account it analyses every photo's pose (a few minutes). Accounts without a pose index are built on the fly.</p>
                  <SamplePicks onPick={d.setPoseImage} label="Use as pose" />
                </div>
              </div>
            )}

            <div className="tag-block">
              <button type="button" className="spread" onClick={() => setTagsOpen((v: boolean) => !v)} style={{ width: "100%", background: "none", border: 0, color: "inherit", padding: 0 }}>
                <span className="kicker" style={{ margin: 0 }}>Must match</span>
                <span className="hint">{d.tags.length ? `${d.tags.length} tag${d.tags.length === 1 ? "" : "s"} · all required` : "Tags optional (edit them in labels.json)"}</span>
              </button>
              {!!d.tags.length && (
                <div className="chips" style={{ marginTop: 8 }}>
                  {d.tags.map((t: { group: string; tag: string }) => (
                    <button type="button" key={`${t.group}-${t.tag}`} className="chip on" onClick={() => d.toggleTag(t.group, t.tag)}>
                      {t.tag} ×
                    </button>
                  ))}
                  <button type="button" className="chip ghost" onClick={() => d.setTags([])}>Clear</button>
                </div>
              )}
              {tagsOpen && (
                <div className="tag-groups">
                  {tagGroups.map((g) => (
                    <div key={g}>
                      <div className="tag-label">{titleCase(g)}{g === "pose" || g === "arms" ? " · from the pose index, built the first time (a few minutes)" : ""}</div>
                      <div className="chips">
                        {d.config.tags[g].map((tag: string) => (
                          <button
                            type="button"
                            key={tag}
                            className={cn("chip", d.tags.some((t: { group: string; tag: string }) => t.group === g && t.tag === tag) && "on")}
                            onClick={() => d.toggleTag(g, tag)}
                          >
                            {titleCase(tag)}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                  {sameGroup && <p className="hint warn">Two tags in one group almost never match: a photo has a single setting, outfit, shot and pose.</p>}
                  <label className="field">
                    <span>How sure a tag must be · {d.confidence.toFixed(2)} · applies to the scene, outfit and shot tags</span>
                    <input type="range" min={0.3} max={0.95} step={0.05} value={d.confidence} disabled={!d.tags.length} onChange={(e) => d.setConfidence(Number(e.target.value))} />
                  </label>
                </div>
              )}
            </div>

            {!!missing.length && (
              <p className="hint warn" style={{ marginTop: 10 }}>
                No {d.model.toUpperCase()} index for {missing.slice(0, 6).map((h: string) => `@${h}`).join(", ")}{missing.length > 6 ? ` and ${missing.length - 6} more` : ""}. Prepare {missing.length === 1 ? "it" : "them"}, or the first search can take several minutes.
              </p>
            )}

            <FilterChips />

            <div className="footbar">
              <Seg
                label="Result mode"
                value={d.resultMode}
                onChange={d.setResultMode}
                options={[{ id: "thumbs", label: "Instant thumbs" }, { id: "full", label: "Save full size" }, { id: "links", label: "Links" }]}
              />
              <div className="row">
                <Seg label="Polarity" value={d.polarity} onChange={d.setPolarity} options={[{ id: "best", label: "Best" }, { id: "worst", label: "Worst" }]} />
                {d.takeAll ? (
                  <label className="inline-num" title="A safety cap on how many matching posts to take">
                    Everything, up to
                    <input type="number" min={1} max={2000} value={d.cap} onChange={(e) => d.setCap(Math.max(1, Math.min(2000, Number(e.target.value) || 1)))} />
                  </label>
                ) : (
                  <label className="inline-num">
                    Posts
                    <input type="number" min={1} max={1000} value={d.count} onChange={(e) => d.setCount(Math.max(1, Math.min(1000, Number(e.target.value) || 1)))} />
                  </label>
                )}
                <button type="button" className={cn("signal", d.takeAll && "on")} onClick={() => { d.setTakeAll(!d.takeAll); if (!d.takeAll) setTagsOpen(true); }} title="Take every post carrying the chosen tags, instead of a random handful">
                  Everything matching
                </button>
                <Seg
                  label="Account mixing"
                  value={d.mix}
                  onChange={d.setMix}
                  options={[{ id: "each", label: "Each" }, { id: "pool", label: "Pool" }, { id: "even", label: "Even" }]}
                />
              </div>
              <div className="row">
                <button type="button" className="btn" onClick={() => d.setRefineOpen(true)}>Refine</button>
                {d.searching ? (
                  <button type="button" className="btn danger" onClick={d.cancelFind}>Cancel</button>
                ) : (
                  <button type="button" className="btn primary" onClick={() => d.find()}>{hasSignal ? "Find posts" : "Draw random"}</button>
                )}
              </div>
            </div>
            <p className="hint" style={{ marginTop: 8 }}>{mixHint(d)}</p>
            {d.takeAll && d.resultMode === "full" && (
              <p className="hint warn" style={{ marginTop: 6 }}>
                Saving up to {d.cap} full-size photos visits each post on Instagram (about 5 seconds each): roughly {Math.floor((d.cap * 5) / 60) + 1} minutes. Instant thumbs need no waiting.
              </p>
            )}
          </>
        )}
      </section>

      {(d.searching || d.logs.length > 0) && (
        <div className="log">
          <button type="button" onClick={() => d.setShowLog(!d.showLog)}>
            <span>{d.searching ? "Running random_post.py" : "Search log"}</span>
            <span className="mono">{d.logs[d.logs.length - 1]}</span>
          </button>
          {(d.showLog || d.searching) && <pre>{d.logs.join("\n")}</pre>}
        </div>
      )}

      {d.searching && (
        <div className="sheet-wrap" style={{ marginTop: 16 }}>
          <div className="sheet">
            {Array.from({ length: 8 }).map((_, i) => <div key={i} className="skel" />)}
          </div>
        </div>
      )}

      {!d.searching && d.results && <Results />}

      {!d.searching && d.results == null && (
        <p className="hint" style={{ marginTop: 14 }}>
          An empty query draws at random from the indexed posts. Scores are similarities, not proof.
        </p>
      )}
    </div>
  );
}

function mixHint(d: any) {
  const n = d.selectedAccounts.length;
  const total = d.takeAll ? `everything matching (up to ${d.cap})` : `${d.count} post${d.count === 1 ? "" : "s"}`;
  const how = d.mix === "pool" ? "chosen from all accounts pooled together"
    : d.mix === "even" && n > 1
      ? (d.takeAll ? "" : `shared equally: about ${Math.floor(d.count / n)} from each of ${n} accounts${d.count % n ? `, plus ${d.count % n} extra` : ""}`)
      : n > 1 ? "from each account" : "";
  return `${n} account${n === 1 ? "" : "s"} · ${total}${how ? ` · ${how}` : ""}${d.mix === "even" && n < 2 ? " · Even needs two or more accounts" : ""}`;
}

function FilterChips() {
  const d = useDesk();
  const chips: { label: string; clear: () => void }[] = [];
  if (d.dateFrom || d.dateTo) chips.push({ label: `${d.dateFrom || "..."} → ${d.dateTo || "..."}`, clear: () => { d.setDateFrom(""); d.setDateTo(""); } });
  if (d.includeVideo) chips.push({ label: "Reels and videos", clear: () => d.setIncludeVideo(false) });
  if (d.videoMix != null) chips.push({ label: `${d.videoMix}% videos`, clear: () => d.setVideoMix(null) });
  if (d.allSlides) chips.push({ label: "Every carousel photo", clear: () => d.setAllSlides(false) });
  if (d.expand) chips.push({ label: `Look inside ${d.expand} carousels`, clear: () => d.setExpand(0) });
  if (d.cacheMode !== "cache") chips.push({ label: d.cacheMode === "refresh" ? "Check for new posts" : "Rebuild from scratch", clear: () => d.setCacheMode("cache") });
  if (d.top !== 50) chips.push({ label: `Top ${d.top} matches`, clear: () => d.setTop(50) });
  if (!chips.length) return null;
  return (
    <div className="filters">
      {chips.map((c) => (
        <button type="button" key={c.label} className="chip on" onClick={c.clear}>{c.label} ×</button>
      ))}
    </div>
  );
}

function Results() {
  const d = useDesk();
  const items: Item[] = d.results || [];
  const meta = d.runMeta;
  const selected = items.filter((r) => d.selectedIds.includes(r.rid));
  const withImage = selected.filter((r) => r.thumb);
  const sub = meta?.mode === "full"
    ? `Saved to ${meta.folder ?? "the picks folder"}/. Links back to Instagram are on each photo.`
    : !(d.useText && d.text.trim()) && !d.tags.length && !d.refImage && !d.poseImage
      ? "A random draw from the indexed posts. Best and worst do not apply."
      : meta?.polarity === "worst"
        ? "Lowest scores, for testing the ranker, not a recommendation."
        : "Highest scores in this cut. A score is a similarity, not proof.";
  return (
    <div>
      <div className="results-head">
        <div>
          <h2>{items.length} {meta?.mode === "links" ? (items.length === 1 ? "link" : "links") : meta?.mode === "full" ? (items.length === 1 ? "photo saved" : "photos saved") : (items.length === 1 ? "frame" : "frames")}</h2>
          <p>{sub}</p>
          {meta?.warnings?.map((w: string) => <p key={w} className="hint warn">{w}</p>)}
        </div>
        <div className="row">
          {meta?.mode === "full" && meta.folder && <button type="button" className="btn tiny" onClick={() => d.openFolder(meta.folder)}>Open folder in Finder</button>}
          {meta?.mode === "thumbs" && items.length > 0 && (
            <>
              <button type="button" className="btn tiny" onClick={() => d.setSelectedIds(items.map((r) => r.rid))}>Select all</button>
              <button type="button" className="btn tiny" onClick={() => d.setSelectedIds([])}>Select none</button>
            </>
          )}
        </div>
      </div>
      {items.length === 0 ? (
        <div className="empty">
          <h2>Nothing in this cut.</h2>
          <p className="hint">Try fewer filters, another account, or a different description. Tags may be too strict, confidence may be high, a date filter may have hidden imported files, or an account has no index for this model.</p>
          <div className="row" style={{ marginTop: 12 }}>
            <button type="button" className="btn tiny" onClick={() => d.find({ tags: [], dateFrom: "", dateTo: "" })}>Clear tags and dates</button>
            <button type="button" className="btn tiny" onClick={() => d.setPrepareFor(d.selectedAccounts[0] || "")}>Prepare account</button>
          </div>
        </div>
      ) : meta?.mode === "links" ? (
        <LinkList items={items} />
      ) : (
        <ContactSheet items={items} showSelect={meta?.mode === "thumbs"} />
      )}
      {meta?.mode === "thumbs" && items.length > 0 && (
        <div className="dock">
          <span className="count">{selected.length} selected</span>
          <button type="button" className="btn tiny primary" disabled={!withImage.length} onClick={() => d.openSlides(withImage, 0, true)}>Slideshow ({withImage.length})</button>
          <button type="button" className="btn tiny" disabled={!selected.length} onClick={() => d.saveSelected("thumbs")} title="Instant: copies the saved thumbnails">Save thumbnails</button>
          <button type="button" className="btn tiny" disabled={!selected.length} onClick={() => d.saveSelected("full")} title="Fetches the full-size photos from Instagram">Save full size</button>
          <button type="button" className="btn tiny" disabled={!withImage.length} onClick={async () => {
            const fresh = withImage.filter((r) => !d.isFav(r.id) && !r.noFav);
            for (const r of fresh) await d.toggleFav(r, true);
            d.toast(fresh.length ? `Copied ${fresh.length} to favourites/` : "Already in favourites");
          }}>Favourite</button>
          {d.savedDir && <button type="button" className="btn tiny" onClick={() => d.openFolder(d.savedDir)}>Open folder</button>}
        </div>
      )}
    </div>
  );
}
