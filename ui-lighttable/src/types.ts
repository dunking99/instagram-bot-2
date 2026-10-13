export type Model = "siglip" | "clip";
export type Pile = "keep" | "review" | "junk";
export type View = "search" | "library" | "collections" | "pilot" | "links" | "positions" | "analysis" | "data18";

export type Account = {
  handle: string;
  kind: "instagram" | "local" | "videos";
  posts: number;
  videos: number;
  models: { siglip: boolean; clip: boolean };
  pose: boolean;
  carouselDetected: boolean;
  opened: number;
  toOpen: number;
  extraSlides: number;
  prepared: string | null;
  libraryBuilt: boolean;
  cover: string | null;
};

/** One picture: a search result, a library image or a favourite. */
export type Item = {
  id: string;
  rid?: string;
  account: string;
  url: string | null;
  slide: number | null;
  name: string;
  score: number | null;
  date: string | null;
  type: "instagram" | "local" | "watch";
  original: string | null;
  video: boolean;
  hasThumb: boolean;
  thumb: string | null;
  full: string | null;
  src: string;
  filename?: string;
  noFav?: boolean;
  caption?: string;
  at?: number;
  videoName?: string;
  clip?: { url: string; start: number; position: string; title: string; creator: string; range: string; source: "verified" | "model"; confidence: number | null };
};

export type Job = {
  id: string;
  kind: string;
  title: string;
  account: string | null;
  status: "running" | "done" | "failed" | "stopped";
  progress: number | null;
  progressText: string | null;
  log: string[];
  started: number;
  pid: number;
  logPath: string;
  exit: number | null;
  running: boolean;
};

export type TagPick = { group: string; tag: string | null };

export type Breakdown = {
  account: string;
  items: Record<string, Record<string, [string, number]>>;
  photos: number;
  slides: number;
  carousels: number | null;
  expanded: number;
  reels: number;
  pose_ready: boolean;
  min_conf: number;
  facets: Record<string, { counts: Record<string, number>; untagged: number | null }>;
};

export type ImportFolder = { name: string; folders: string[]; pending: number; indexed: number | null };
export type WatchVideo = { id: string; file: string; name: string; duration: number; added: number; poster: string | null; url: string; indexed: boolean };
export type WatchFolder = { name: string; folder: string; attached: boolean; count: number; frames: number; indexedVideos: number; todoSeconds: number; videos: WatchVideo[]; error?: string };

export type PilotShot = {
  id: string;
  file: string;
  date: string | null;
  score: number;
  body: boolean;
  prompt: string;
  crop: string | null;
  screenshot: string | null;
};

export type ClipLengths = Record<string, number>;

export type Polarity = "best" | "worst";
export type Mix = "each" | "pool" | "even";
export type ResultMode = "thumbs" | "full" | "links";
export type CacheMode = "cache" | "refresh" | "rebuild";

export function titleCase(s: string) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

export function formatDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${d} ${months[(m || 1) - 1]} ${y}`;
}

export function tagText(tags: TagPick[]) {
  return tags.map((t) => (t.tag == null ? `no confident ${t.group}` : t.tag)).join(" + ");
}

/** The three-way split of the Photos pilot, the same rule as photos_import.assign_pile. */
export function assignPile(score: number, body: boolean, keepAt: number, junkAt: number): Pile {
  if (score >= 0.9 || (score >= keepAt && body)) return "keep";
  if (score <= junkAt && !body) return "junk";
  return "review";
}

export function itemLabel(item: Item) {
  if (item.slide) return `slide ${item.slide}`;
  if (item.type === "watch") return "video";
  if (item.type === "local") return item.video ? "local clip" : "local";
  return "post";
}
