import { useState } from "react";
import type { Item } from "../types";
import { useDesk } from "../store";
import { Icon, Seg } from "./ui";

type Kind = "all" | "photo" | "video";

/** The tray on the right: your favourites, always at hand. It is the same list as Collections > Favourites. */
export function Lightbox() {
  const d = useDesk();
  const [kind, setKind] = useState<Kind>("all");
  const favs: Item[] = d.favs;
  const items = favs.filter((f) => kind === "all" || (kind === "video") === !!f.video);
  const viewable = items.filter((f) => f.thumb || f.full).map((f) => ({ ...f, rid: f.id }));
  return (
    <aside className="lightbox" id="lightbox" aria-label="Lightbox">
      <div className="lb-h">
        <h2>Lightbox <b>{favs.length}</b></h2>
        <Seg
          label="Type"
          value={kind}
          onChange={setKind}
          options={[{ id: "all", label: "All" }, { id: "photo", label: "Photos" }, { id: "video", label: "Videos" }]}
        />
      </div>
      <div className="lb-grid">
        {items.map((f) => (
          <div className="lb-it" key={f.id} title={`@${f.account}${f.date ? ` · ${f.date}` : ""}`}>
            <button
              type="button"
              className="lb-open"
              aria-label={`Preview @${f.account}`}
              onClick={() => { const at = viewable.findIndex((v) => v.id === f.id); if (at >= 0) d.openSlides(viewable, at, false); }}
            >
              {f.thumb ? <img src={f.thumb} alt="" loading="lazy" /> : <span className="noimg" style={{ display: "grid", placeItems: "center", height: "100%", color: "#9aa3aa", fontSize: 11 }}>No image</span>}
            </button>
            <button type="button" className="lb-x" aria-label="Remove from Lightbox" onClick={() => d.toggleFav(f)}><Icon name="x" size={12} /></button>
          </div>
        ))}
        {!items.length && (
          <p className="lb-empty">
            {favs.length ? "Nothing of this type in your Lightbox." : "Nothing here yet. Press the star on any frame to keep it in the Lightbox."}
          </p>
        )}
      </div>
      <div className="lb-foot">
        <button type="button" className="btn tiny" disabled={!viewable.length} onClick={() => d.openSlides(viewable, 0, true)}><Icon name="play" size={14} />Slides</button>
        <button type="button" className="btn tiny" onClick={() => d.openFolder("favourites")}><Icon name="folder" size={14} />Open folder</button>
        <button type="button" className="btn tiny" onClick={() => { d.setCollectionsTab("favourites"); d.setView("collections"); }}>Manage</button>
      </div>
    </aside>
  );
}
