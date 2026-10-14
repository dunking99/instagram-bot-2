// ------------------------------------------------------------------ seeded rng
export function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
export function mulberry(seed: number) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const R = mulberry(20260214);
export const ri = (min: number, max: number) => Math.floor(R() * (max - min + 1)) + min;
export const rf = (min: number, max: number) => R() * (max - min) + min;
export const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(R() * arr.length)];
const chance = (p: number) => R() < p;

export const NOW = Date.parse("2026-02-14T09:30:00Z");
const daysAgo = (n: number) => new Date(NOW - n * 864e5).toISOString();

// ------------------------------------------------------------------ vocabulary
export const POSITIONS = [
  { name: "Standing", subs: ["facing camera", "side profile", "back to camera", "bent forward", "one leg raised", "twisted torso"] },
  { name: "Seated", subs: ["on bed", "on chair", "on floor", "on edge of surface", "straddling", "cross-legged"] },
  { name: "Kneeling", subs: ["upright", "leaning back", "on one knee", "low kneel", "kneel on furniture"] },
  { name: "Reclining", subs: ["on back", "on side", "propped on arms", "over pillows", "half-reclined"] },
  { name: "Lying down", subs: ["flat", "curled", "spread", "on stomach"] },
  { name: "Bent over", subs: ["standing bend", "seated bend", "over furniture", "against wall"] },
  { name: "Carried", subs: ["cradled", "over shoulder", "piggyback", "lifted"] },
  { name: "Against wall", subs: ["standing", "lifted", "sliding down", "pinned"] },
  { name: "On edge of surface", subs: ["sitting", "lying", "perched", "leaning back on hands"] },
  { name: "Suspended", subs: ["held up", "hanging", "tied", "in sling"] },
];

export const ATTR_GROUPS = [
  { name: "Setting", values: ["studio", "bedroom", "hotel room", "outdoor", "bathroom", "office", "car", "kitchen", "rooftop", "basement"] },
  { name: "Outfit", values: ["lingerie", "casual", "formal", "athletic", "costume", "workwear", "dress", "nude"] },
  { name: "Shot type", values: ["close-up", "medium", "full body", "wide", "over-shoulder", "POV", "mirror shot", "low angle", "high angle"] },
  { name: "Pose", values: POSITIONS.map((p) => p.name) },
  { name: "Arms", values: ["raised", "behind back", "crossed", "on hips", "holding", "spread", "at sides", "on head"] },
];

export const LINK_CATEGORIES = ["interview", "behind the scenes", "studio set", "outdoor set", "photoshoot", "convention", "fitness", "lifestyle", "sponsor", "fan meet"];
export const LENGTH_BANDS = ["< 1 min", "1–5 min", "5–15 min", "15–30 min", "30 min +"];
export const SITES = ["clipjar", "vidwell", "streamnest", "mediary"];

const FIRST = ["Mara", "June", "Sable", "Iris", "Noor", "Vera", "Lena", "Petra", "Sana", "Mila", "Anouk", "Ruth", "Elin", "Kaia", "Sofia", "Ines", "Nadia", "Bree", "Talia", "Maren", "Odette", "Suki", "Wren", "Alba", "Nika", "Helga", "Mina", "Cora", "Faye", "Liv", "Sanna", "Mae", "Ilse", "Runa", "Zosia", "Bianca", "Oda", "Hana", "Pilar", "Remy", "Skye", "Noa", "Elif", "Aya", "Greta", "Tove", "Una", "Dara", "Freya", "Isolde"];
const LAST = ["vale", "fox", "marlowe", "okonkwo", "lindqvist", "marchetti", "duarte", "keller", "nakamura", "osei", "berg", "ferraro", "lund", "petrova", "silva", "haugen", "ibarra", "kovacs", "linden", "mera", "novak", "oster", "qureshi", "rossi", "santos", "thorne", "urban", "voss", "wester", "yamada", "zamora", "abel", "bloom", "crest", "draper", "ellis", "frost", "gale", "heath", "jules", "kestrel", "lark", "moss", "nyx", "oak", "pine", "reed", "sable", "thorn", "wren", "ash", "birch", "clover", "dune", "elm", "flint", "grove", "heather", "iris", "juniper", "lotus", "maple", "nettle", "oasis", "poppy", "quill", "rowan", "tansy", "umber", "violet", "willow", "yarrow", "zinnia"];
const FOLDER_NAMES = ["camera uploads", "2024 berlin", "2025 lisbon", "studio sessions", "phone dumps", "external ssd a", "archive 2023", "behind the scenes", "convention 2025", "scans", "screen captures", "drafts", "trip porto", "trip tokyo", "weekend 04", "weekend 11", "loft archive", "usb stick 3", "old phone", "tablet export", "mirror shots", "window light", "rainy day", "golden hour", "night series", "self timer", "tripod raws", "card 07", "card 12", "card 19", "import jan", "import feb", "unsorted", "to review", "keepers", "duplicates", "heic converts", "live photos", "bursts", "panos"];

export const fullName = () => `${pick(FIRST)} ${pick(LAST)}`;

// ------------------------------------------------------------------ formatting
export const fmt = (n: number) => (n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : String(n));
export const fmtDur = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
export const fmtBytes = (b: number) =>
  b >= 1e12 ? (b / 1e12).toFixed(2) + " TB" : b >= 1e9 ? (b / 1e9).toFixed(0) + " GB" : b >= 1e6 ? (b / 1e6).toFixed(0) + " MB" : b >= 1e3 ? (b / 1e3).toFixed(0) + " KB" : b + " B";
export const pct = (v: number) => Math.round(v * 100) + "%";
export const timeAgo = (iso: string | null) => {
  if (!iso) return "never";
  const d = Math.max(0, Math.round((NOW - Date.parse(iso)) / 864e5));
  if (d === 0) return "today";
  if (d === 1) return "1d ago";
  if (d < 30) return `${d}d ago`;
  if (d < 365) return `${Math.floor(d / 30)}mo ago`;
  return `${(d / 365).toFixed(1)}y ago`;
};

// ------------------------------------------------------------------ accounts
export interface Account {
  id: string; name: string; platform: string; kind: "social" | "folder";
  photos: number; reels: number; carousels: number; slides: number;
  idxSearch: boolean; idxPose: boolean; idxCarousel: boolean;
  lastPrepared: string | null; pending: number; indexed: number;
  status: "ready" | "indexing" | "queued" | "error" | "stale";
}
function makeAccounts(): Account[] {
  const out: Account[] = [];
  const used = new Set<string>();
  for (let i = 0; i < 200; i++) {
    const local = i >= 148;
    const platform = local ? "LOCAL" : pick(["IG", "IG", "IG", "IG", "TT", "TT", "TT", "X", "X", "RD", "BLOG"]);
    let name: string;
    if (local) {
      name = pick(FOLDER_NAMES);
      if (used.has(name)) name = name + " " + ri(2, 40);
    } else {
      name = "@" + pick(FIRST).toLowerCase() + "." + pick(LAST).toLowerCase() + (chance(0.4) ? ri(2, 99) : "");
    }
    used.add(name);
    const status: Account["status"] = chance(0.78) ? "ready" : pick(["stale", "error", "indexing", "queued"]);
    out.push({
      id: "a" + i, name, platform, kind: local ? "folder" : "social",
      photos: local ? ri(200, 9000) : ri(40, 1800),
      reels: local ? 0 : ri(0, 260),
      carousels: local ? 0 : ri(0, 140),
      slides: local ? 0 : ri(0, 420),
      idxSearch: chance(0.86), idxPose: chance(0.62), idxCarousel: chance(0.72),
      lastPrepared: chance(0.85) ? daysAgo(ri(0, 40)) : null,
      pending: status === "ready" ? ri(0, 300) : ri(50, 4000),
      indexed: ri(200, 22000),
      status,
    });
  }
  return out;
}
export const ACCOUNTS = makeAccounts();

// ------------------------------------------------------------------ videos
export interface Section { pos: string; sub: string; start: number; end: number; conf: number; verified: boolean; }
export interface VideoItem {
  id: string; title: string; creator: string; duration: number;
  state: "verified" | "saved" | "current" | "older" | "none" | "failed" | "running" | "queued";
  error?: string; sections: Section[]; meanConf: number; analysedAt: string | null; model: string; size: number;
}
const SETTINGS = ["studio", "bedroom", "hotel room", "outdoor", "bathroom", "rooftop", "basement"];
const SHOTKINDS = ["overhead", "window light", "wide", "close-up", "medium", "mirror"];
function makeVideos(): VideoItem[] {
  const plan: VideoItem["state"][] = [
    ...Array(96).fill("verified"), ...Array(22).fill("saved"), ...Array(58).fill("current"),
    ...Array(24).fill("older"), ...Array(8).fill("none"), ...Array(6).fill("failed"),
    ...Array(2).fill("running"), ...Array(4).fill("queued"),
  ];
  return plan.map((state, i) => {
    const duration = ri(45, 900);
    const nSec = state === "none" || state === "failed" ? 0 : ri(1, 6);
    const sections: Section[] = [];
    let t = 0;
    for (let s = 0; s < nSec; s++) {
      const pos = pick(POSITIONS);
      const len = ri(Math.floor(duration / (nSec * 1.6)), Math.floor(duration / Math.max(1, nSec - s)));
      const start = Math.min(t, Math.max(0, duration - 10));
      const end = Math.min(duration, start + Math.max(8, len));
      sections.push({ pos: pos.name, sub: pick(pos.subs), start, end, conf: rf(0.34, 0.99), verified: state === "verified" });
      t = end + ri(2, 20);
      if (t >= duration) break;
    }
    const meanConf = sections.length ? sections.reduce((a, s) => a + s.conf, 0) / sections.length : 0;
    return {
      id: "v" + i,
      title: `S${String(i + 1).padStart(3, "0")} · ${pick(SETTINGS)}, ${pick(SHOTKINDS)} · 2025-${String(ri(1, 12)).padStart(2, "0")}-${String(ri(1, 28)).padStart(2, "0")}`,
      creator: pick(FIRST) + " " + pick(LAST),
      duration, state,
      error: state === "failed" ? pick(["browser closed during carousel pass", "frame extraction timeout after 120 s", "pose index write conflict", "source returned 403 twice"]) : undefined,
      sections, meanConf,
      analysedAt: state === "none" || state === "failed" ? null : daysAgo(ri(0, 90)),
      model: state === "older" ? "v2.8" : "v3.2",
      size: ri(80, 900),
    };
  });
}
export const VIDEOS = makeVideos();

// ------------------------------------------------------------------ jobs
export interface Job {
  id: string; label: string; kind: string; status: "running" | "queued" | "done" | "failed" | "stopped";
  progress: number; total: number; log: string[]; startedAt: string; warn?: boolean;
}
export const SEED_JOBS: Job[] = [
  { id: "j1", label: "Index carousel images · @mara.vale", kind: "carousel", status: "running", progress: 61, total: 100, log: ["opened 74 of 121 slides", "batch 12/20 · window 2", "rate limit respected (1.2 s)"], startedAt: daysAgo(0), warn: true },
  { id: "j2", label: "Build pose index · 6 folders", kind: "pose", status: "running", progress: 34, total: 100, log: ["sampling frames every 4 s", "412 / 1,204 frames labelled"], startedAt: daysAgo(0) },
  { id: "j3", label: "Download batch · 14 links", kind: "download", status: "running", progress: 78, total: 100, log: ["9/14 complete", "clipjar: 2.1 GB written"], startedAt: daysAgo(0) },
  { id: "j4", label: "Detect carousels · @june.fox", kind: "carousel", status: "queued", progress: 0, total: 100, log: ["waiting for browser window"], startedAt: daysAgo(0) },
  { id: "j5", label: "Import folder · /media/usb stick 3", kind: "import", status: "queued", progress: 0, total: 100, log: ["queued behind 1 job"], startedAt: daysAgo(0) },
  { id: "j6", label: "Prepare index · @sable.fox", kind: "prepare", status: "done", progress: 100, total: 100, log: ["search index: 1,204 images", "pose index: 1,180", "carousel map: 38 posts"], startedAt: daysAgo(0) },
  { id: "j7", label: "Analyse video · S041", kind: "analyse", status: "done", progress: 100, total: 100, log: ["6 sections · mean conf 0.81"], startedAt: daysAgo(0) },
  { id: "j8", label: "Index carousel images · @nadia.osei", kind: "carousel", status: "failed", progress: 44, total: 100, log: ["opened 52 of 118 slides", "source returned 403 twice", "paused — will resume on next prepare"], startedAt: daysAgo(1) },
  { id: "j9", label: "Build categorised folders", kind: "folders", status: "done", progress: 100, total: 100, log: ["1,204 files → 38 folders", "0 conflicts"], startedAt: daysAgo(1) },
  { id: "j10", label: "Download batch · 6 links", kind: "download", status: "done", progress: 100, total: 100, log: ["6/6 complete", "1.4 GB written"], startedAt: daysAgo(1) },
  { id: "j11", label: "Prepare index · @wren.lark", kind: "prepare", status: "done", progress: 100, total: 100, log: ["search index: 842 images"], startedAt: daysAgo(2) },
  { id: "j12", label: "Import folder · /media/card 12", kind: "import", status: "done", progress: 100, total: 100, log: ["1,140 new files", "0 duplicates"], startedAt: daysAgo(2) },
  { id: "j13", label: "Analyse video · S038", kind: "analyse", status: "failed", progress: 70, total: 100, log: ["frame extraction timeout after 120 s"], startedAt: daysAgo(2) },
  { id: "j14", label: "Detect carousels · @iris.kestrel", kind: "carousel", status: "done", progress: 100, total: 100, log: ["22 carousels found"], startedAt: daysAgo(3) },
  { id: "j15", label: "Build pose index · 3 folders", kind: "pose", status: "done", progress: 100, total: 100, log: ["940 frames labelled"], startedAt: daysAgo(3) },
  { id: "j16", label: "Download batch · 9 links", kind: "download", status: "stopped", progress: 55, total: 100, log: ["5/9 complete", "stopped by owner"], startedAt: daysAgo(3) },
  { id: "j17", label: "Prepare index · @talia.moss", kind: "prepare", status: "done", progress: 100, total: 100, log: ["search index: 1,530 images"], startedAt: daysAgo(4) },
  { id: "j18", label: "Import folder · /media/tablet export", kind: "import", status: "done", progress: 100, total: 100, log: ["620 new files"], startedAt: daysAgo(4) },
  { id: "j19", label: "Analyse video · S033", kind: "analyse", status: "done", progress: 100, total: 100, log: ["4 sections · mean conf 0.77"], startedAt: daysAgo(5) },
  { id: "j20", label: "Build categorised folders", kind: "folders", status: "done", progress: 100, total: 100, log: ["842 files → 21 folders"], startedAt: daysAgo(5) },
];

// ------------------------------------------------------------------ favourites
export interface FavItem { id: string; seed: string; kind: "image" | "clip"; title: string; account: string; added: string; }
export const FAVOURITES: FavItem[] = Array.from({ length: 120 }, (_, i) => ({
  id: "f" + i,
  seed: "fav" + i,
  kind: i % 5 === 0 ? "clip" : "image",
  title: `${pick(ATTR_GROUPS[0].values)} · ${pick(ATTR_GROUPS[2].values)} · ${pick(POSITIONS).name.toLowerCase()}`,
  account: pick(ACCOUNTS).name,
  added: daysAgo(ri(0, 120)),
}));

// ------------------------------------------------------------------ creators / links
export interface CreatorSite { site: string; status: "scraped" | "unscraped" | "error" | "checking"; links: number; last: string | null; }
export interface Creator { id: string; name: string; handle: string; folder: string; totalLinks: number; lastScraped: string | null; picturesFound: 1 | 2; sites: CreatorSite[]; }
export const CREATORS: Creator[] = Array.from({ length: 340 }, (_, i) => {
  const name = pick(FIRST) + " " + pick(LAST);
  const sites = SITES.filter(() => chance(0.55)).map((s) => ({
    site: s,
    status: pick(["scraped", "scraped", "scraped", "unscraped", "error"] as const),
    links: ri(0, 60),
    last: chance(0.7) ? daysAgo(ri(0, 60)) : null,
  }));
  return {
    id: "c" + i, name, handle: "@" + name.split(" ")[0].toLowerCase() + "." + name.split(" ")[1].toLowerCase(),
    folder: name.toLowerCase().replace(" ", ".") + (chance(0.3) ? " " + ri(2, 9) : ""),
    totalLinks: sites.reduce((a, s) => a + s.links, 0) || ri(2, 120),
    lastScraped: chance(0.8) ? daysAgo(ri(0, 45)) : null,
    picturesFound: chance(0.24) ? 2 : 1,
    sites,
  };
});
export const LINK_TOTALS = {
  total: 1900,
  byCategory: LINK_CATEGORIES.map((c) => ({ name: c, count: ri(60, 320) })),
  byLength: LENGTH_BANDS.map((b) => ({ name: b, count: ri(80, 420) })),
};

// ------------------------------------------------------------------ directory
export interface Performer { name: string; rank: number; videos: number; views: number; verified: boolean; seed: string; country: string; }
const COUNTRIES = ["US", "CA", "UK", "DE", "FR", "ES", "IT", "BR", "MX", "AR", "CO", "AU", "JP", "KR", "NL", "SE", "PL", "UA", "CZ", "HU"];
export const DIRECTORY: Performer[] = Array.from({ length: 1200 }, (_, i) => ({
  name: pick(FIRST) + " " + pick(LAST), rank: i + 1, videos: ri(0, 240), views: ri(2, 900) * 1000,
  verified: chance(0.18), seed: "dir" + i, country: pick(COUNTRIES),
}));

// ------------------------------------------------------------------ triage
export interface Shot { id: string; seed: string; score: number; auto: "keep" | "review" | "junk"; manual?: "keep" | "review" | "junk"; }
export const SHOTS: Shot[] = Array.from({ length: 400 }, (_, i) => {
  const score = Math.round(rf(0, 100));
  return { id: "s" + i, seed: "shot" + i, score, auto: score >= 62 ? "keep" : score >= 34 ? "review" : "junk" };
});

// ------------------------------------------------------------------ reference site
export interface RefGallery { kind: "stills" | "photoset"; count: number; seed: string; }
export interface RefVideo { id: string; title: string; date: string; studio: string; categories: string[]; tags: string[]; cos: string[]; ethnicity: string; galleries: RefGallery[]; views: number; }
export interface RefPerformer { name: string; seed: string; country: string; scenes: number; movies: number; rank: number; videos: RefVideo[]; }
const REF_TAGS = ["interview", "bloopers", "making of", "fan q&a", "studio tour", "convention panel", "photo shoot", "behind the scenes", "live stream", "press junket", "audition tape", "rehearsal"];
const REF_STUDIOS = ["Northlight", "Halcyon", "Meridian", "Copperfield", "Vantage", "Lumen House", "Parallax", "Fieldnotes"];
export const REF_PERFORMERS: RefPerformer[] = Array.from({ length: 24 }, (_, i) => {
  const name = pick(FIRST) + " " + pick(LAST);
  return {
    name, seed: "ref" + i, country: pick(COUNTRIES), scenes: ri(4, 120), movies: ri(2, 40), rank: ri(1, 900),
    videos: Array.from({ length: ri(3, 9) }, (_, j) => ({
      id: "rv" + i + j,
      title: `${pick(["Scene", "Feature", "Special", "Release"])} ${ri(1, 40)} — ${pick(REF_STUDIOS)}`,
      date: daysAgo(ri(30, 900)), studio: pick(REF_STUDIOS),
      categories: Array.from({ length: ri(1, 3) }, () => pick(["drama", "comedy", "documentary", "variety", "music", "sports", "lifestyle", "interview"])),
      tags: Array.from({ length: ri(1, 4) }, () => pick(REF_TAGS)),
      cos: Array.from({ length: ri(0, 2) }, () => pick(FIRST) + " " + pick(LAST)),
      ethnicity: pick(["european", "east asian", "south asian", "african", "latino", "middle eastern", "mixed"]),
      galleries: Array.from({ length: ri(1, 3) }, (_, g) => ({ kind: (g === 0 ? "stills" : "photoset") as "stills" | "photoset", count: ri(4, 18), seed: "rg" + i + j + g })),
      views: ri(2, 900) * 1000,
    })),
  };
});
export const REF_STUDIO_TREE = ["Northlight", "Halcyon", "Meridian", "Copperfield"].map((p) => ({
  parent: p, subs: REF_STUDIOS.filter((s) => s !== p).slice(0, 3),
}));
export const REF_TAG_COUNTS = REF_TAGS.map((t) => ({ name: t, count: ri(4, 160) }));

// ------------------------------------------------------------------ site definitions
export interface SiteDef { name: string; address: string; nextPages: string; linkPattern: string; durationSel: string; include: string; ignore: string; viewsSel: string; picSel: string; categories: string[]; dominant: string; forcedOther: string[]; findCreator: string; noCreator: string; delay: number; method: string; }
export const SITE_DEFS: SiteDef[] = [
  { name: "clipjar", address: "https://clipjar.example.com", nextPages: "?page={n}", linkPattern: "/watch/{id}", durationSel: "meta[itemprop=duration]", include: "div.video-list", ignore: "div.ads, nav", viewsSel: "span.views", picSel: "img.avatar", categories: ["interview: q&a, talk", "set: studio, shoot"], dominant: "interview", forcedOther: ["promo", "ad"], findCreator: "/creator/{name}", noCreator: "text=No profile found", delay: 1200, method: "browser" },
  { name: "vidwell", address: "https://vidwell.example.net", nextPages: "/page/{n}", linkPattern: "/v/{slug}", durationSel: "time.duration", include: "section.feed", ignore: "aside", viewsSel: "b.count", picSel: "img.portrait", categories: ["behind the scenes: bts, backstage"], dominant: "photoshoot", forcedOther: ["sponsor"], findCreator: "/@{name}", noCreator: "status=404", delay: 900, method: "browser" },
  { name: "streamnest", address: "https://streamnest.example.org", nextPages: "?p={n}", linkPattern: "/clip/{id}", durationSel: "[data-dur]", include: "main", ignore: "footer, .modal", viewsSel: ".views", picSel: ".thumb", categories: ["convention: panel, meet"], dominant: "lifestyle", forcedOther: ["teaser"], findCreator: "/talent/{name}", noCreator: "text=Not found", delay: 1500, method: "http" },
  { name: "mediary", address: "https://mediary.example.tv", nextPages: "/catalog/{n}", linkPattern: "/scene/{id}", durationSel: "span.len", include: "div.catalogue", ignore: "nav, .promo", viewsSel: "em.views", picSel: "img.face", categories: ["studio set: set, shoot"], dominant: "interview", forcedOther: ["trailer"], findCreator: "/people/{name}", noCreator: "text=No results", delay: 800, method: "browser" },
];

// ------------------------------------------------------------------ storage
export const STORAGE = {
  total: 2_000_000_000_000,
  free: 148_000_000_000,
  project: 612_000_000_000,
  folders: [
    { name: "/media/library", size: 402_000_000_000 },
    { name: "/media/downloads", size: 118_000_000_000 },
    { name: "/media/archive", size: 74_000_000_000 },
    { name: "/media/imports", size: 18_000_000_000 },
  ],
  thumbs: [
    { name: "~postroom/thumbs/full", size: 41_000_000_000 },
    { name: "~postroom/thumbs/small", size: 9_000_000_000 },
    { name: "~postroom/frames", size: 22_000_000_000 },
  ],
};

// ------------------------------------------------------------------ misc content
export const STARTER_PROMPTS = [
  "mirror selfie, hotel room, morning light",
  "full body, studio, white backdrop",
  "over-shoulder, laughing, window light",
  "reclining, linen, afternoon",
  "low angle, rooftop, golden hour",
  "close-up, wet hair, bathroom mirror",
  "seated on bed, casual, reading",
  "against wall, formal, evening",
];
export const EMPTY_HELP = [
  "No matches. Try widening the date range or lowering the required confidence.",
  "Switch match mode to “worst” to find near-misses and hard negatives.",
  "Add a reference photo or a pose reference — combining modes narrows fast.",
  "Check which accounts are indexed: unindexed accounts can't be searched.",
  "Loosen attributes: every required attribute multiplies the strictness.",
];
export const POSITION_COUNTS = POSITIONS.map((p) => ({ name: p.name, subs: p.subs, count: ri(12, 190) }));
