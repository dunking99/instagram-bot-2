import React, { createContext, useContext, useMemo } from "react";
import { hashStr, mulberry } from "./data";

// ------------------------------------------------------------------ context
export interface ViewerItem {
  seed: string; kind: "image" | "clip"; title: string; account?: string; creator?: string;
  score?: number; conf?: number; verified?: boolean; pos?: string; sub?: string;
  clipRange?: [number, number]; sectionRange?: [number, number]; duration?: number;
}
export interface JobLite { id: string; label: string; kind: string; status: string; progress: number; total: number; log: string[]; startedAt: string; warn?: boolean; }
export interface Ctx {
  go: (view: string, tab?: string) => void;
  openViewer: (items: ViewerItem[], index: number, endless?: boolean) => void;
  notify: (title: string, body?: string, tone?: "ok" | "err" | "info") => void;
  isFav: (id: string) => boolean;
  toggleFav: (id: string) => void;
  pushJob: (label: string, kind: string, opts?: { total?: number; warn?: boolean }) => void;
  jobs: JobLite[];
}
export const Ctx = createContext<Ctx | null>(null);
export const useCtx = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error("ctx missing");
  return c;
};

// ------------------------------------------------------------------ icons
const P: Record<string, React.ReactNode> = {
  search: <><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>,
  film: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" /></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>,
  activity: <path d="M3 12h4l3 8 4-16 3 8h4" />,
  sliders: <><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3" /><circle cx="4" cy="12" r="2" /><circle cx="12" cy="10" r="2" /><circle cx="20" cy="14" r="2" /></>,
  layers: <><path d="m12 2 8.5 4.5L12 11 3.5 6.5 12 2z" /><path d="m3 12 9 5 9-5" /><path d="m3 17 9 5 9-5" /></>,
  folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />,
  link: <><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" /><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" /></>,
  download: <><path d="M12 3v12" /><path d="m7 11 5 5 5-5" /><path d="M4 21h16" /></>,
  upload: <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 21h16" /></>,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18" /><path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18Z" /></>,
  heart: <path d="M12 20.5C7 16.5 3 13.3 3 9.3 3 6.4 5.2 4.5 7.7 4.5c1.7 0 3.3.9 4.3 2.4 1-1.5 2.6-2.4 4.3-2.4 2.5 0 4.7 1.9 4.7 4.8 0 4-4 7.2-9 11.2Z" />,
  command: <path d="M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3" />,
  bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></>,
  harddrive: <><path d="M4 14 6.5 6a2 2 0 0 1 1.9-1.4h7.2A2 2 0 0 1 17.5 6L20 14" /><path d="M2 14h20v4a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-4Z" /><path d="M6 17h.01M10 17h.01" /></>,
  play: <path d="m6 4 14 8-14 8V4Z" />,
  pause: <><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></>,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  check: <path d="m4 12.5 5 5L20 6.5" />,
  chevD: <path d="m6 9 6 6 6-6" />,
  chevR: <path d="m9 6 6 6-6 6" />,
  chevL: <path d="m15 6-6 6 6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  refresh: <><path d="M21 12a9 9 0 1 1-2.6-6.4" /><path d="M21 3v6h-6" /></>,
  trash: <><path d="M3 6h18" /><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M10 11v6M14 11v6" /></>,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  alert: <><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 10v4M12 17.5h.01" /></>,
  zap: <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />,
  tag: <><path d="M3 3h7l11 11-7 7L3 10V3Z" /><circle cx="8" cy="8" r="1.5" /></>,
  users: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8" /><path d="M17.5 14.5a6.5 6.5 0 0 1 4 5.5" /></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="m4 18 5-5 3 3 4-4 4 4" /></>,
  copy: <><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>,
  external: <><path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M20 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5" /></>,
  folderOpen: <><path d="m3 8 2.5-4h13L21 8" /><path d="M3 8h18v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8Z" /><path d="m3 8 2 8h14l2-8" /></>,
  shuffle: <><path d="M2 18h3.6c1.2 0 2.3-.6 2.9-1.6l6.4-9.2c.6-1 1.7-1.6 2.9-1.6H22" /><path d="m18 2 4 4-4 4" /><path d="M2 6h3.6c1.2 0 2.3.6 2.9 1.6l.6.8" /><path d="m18 14 4 4-4 4" /></>,
  maximize: <><path d="M8 3H5a2 2 0 0 0-2 2v3" /><path d="M21 8V5a2 2 0 0 0-2-2h-3" /><path d="M3 16v3a2 2 0 0 0 2 2h3" /><path d="M16 21h3a2 2 0 0 0 2-2v-3" /></>,
  arrowL: <><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></>,
  arrowR: <><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></>,
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  terminal: <><path d="m4 17 6-6-6-6" /><path d="M12 19h8" /></>,
  key: <><circle cx="8" cy="15" r="4.5" /><path d="m11.5 11.5 8.5-8.5" /><path d="M17 5l2.5 2.5" /><path d="M14 8l2 2" /></>,
  list: <><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" /></>,
  filter: <path d="M3 5h18l-7 8v5.5L10 21v-8L3 5Z" />,
  save: <><path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M8 3v5h7V3" /><rect x="8" y="13" width="8" height="6" rx="1" /></>,
  merge: <><circle cx="6" cy="6" r="2.5" /><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="8" r="2.5" /><path d="M6 8.5v7" /><path d="M18 10.5c0 4-4 4.5-8 5" /></>,
  columns: <><rect x="3" y="4" width="7" height="16" rx="1.5" /><rect x="14" y="4" width="7" height="16" rx="1.5" /></>,
  scan: <><path d="M3 8V5a2 2 0 0 1 2-2h3" /><path d="M16 3h3a2 2 0 0 1 2 2v3" /><path d="M21 16v3a2 2 0 0 1-2 2h-3" /><path d="M8 21H5a2 2 0 0 1-2-2v-3" /><path d="M3 12h18" /></>,
  cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><rect x="10" y="10" width="4" height="4" /><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" /></>,
  lock: <><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>,
  pencil: <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3Z" />,
  dots: <><circle cx="5" cy="12" r="1.2" fill="currentColor" /><circle cx="12" cy="12" r="1.2" fill="currentColor" /><circle cx="19" cy="12" r="1.2" fill="currentColor" /></>,
  wand: <><path d="m5 19 10-10" /><path d="M15 4l.9 2.1L18 7l-2.1.9L15 10l-.9-2.1L12 7l2.1-.9L15 4Z" /><path d="M19 11l.6 1.4L21 13l-1.4.6L19 15l-.6-1.4L17 13l1.4-.6L19 11Z" /></>,
  logIn: <><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" /><path d="m10 17 5-5-5-5" /><path d="M15 12H3" /></>,
  logOut: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5" /><path d="M21 12H9" /></>,
  wifi: <><path d="M5 12.5a10 10 0 0 1 14 0" /><path d="M8.5 16a5 5 0 0 1 7 0" /><path d="M2 9.5a14 14 0 0 1 20 0" /><circle cx="12" cy="19.5" r="1" fill="currentColor" /></>,
  box: <><path d="m12 2 8 4.5v9L12 20l-8-4.5v-9L12 2Z" /><path d="M4 6.5 12 11l8-4.5" /><path d="M12 11v9" /></>,
  book: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15Z" /><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" /></>,
  gauge: <><path d="m12 15 3.5-5.5" /><path d="M20.2 15a8.5 8.5 0 1 0-16.4 0" /></>,
  swap: <><path d="M8 3 4 7l4 4" /><path d="M4 7h16" /><path d="m16 21 4-4-4-4" /><path d="M20 17H4" /></>,
  fileText: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" /><path d="M14 2v6h6" /><path d="M8 13h8M8 17h5" /></>,
  sparkles: <><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4L12 3Z" /><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></>,
  video: <><rect x="2" y="6" width="13" height="12" rx="2" /><path d="m15 10 6-3v10l-6-3" /></>,
  camera: <><rect x="2" y="6" width="15" height="12" rx="2" /><circle cx="9.5" cy="12" r="3" /><path d="m17 10 5-3v10l-5-3" /></>,
  pose: <><circle cx="12" cy="5" r="2.5" /><path d="M12 8v6" /><path d="m12 14-4 7" /><path d="m12 14 4 7" /><path d="M12 10l-4 3" /><path d="m12 10 4 3" /></>,
  flip: <><path d="M12 3v18" /><path d="m8 7-4 5 4 5" /><path d="m16 7 4 5-4 5" /></>,
  hash: <path d="M9 3 7 21M17 3l-2 18M4 8h17M3 16h17" />,
  percent: <><path d="M19 5 5 19" /><circle cx="7" cy="7" r="2.5" /><circle cx="17" cy="17" r="2.5" /></>,
  type: <><path d="M5 7V5h14v2" /><path d="M12 5v14" /><path d="M9 19h6" /></>,
  alignLeft: <path d="M4 6h16M4 10h10M4 14h16M4 18h10" />,
  table: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M3 15h18M9 4v16M15 4v16" /></>,
  chart: <><path d="M4 20V4" /><path d="M4 20h16" /><path d="m8 16 4-6 4 3 4-7" /></>,
  flag: <><path d="M5 21V4" /><path d="M5 4h12l-2.5 4L17 12H5" /></>,
  star: <path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6-5.4-3-5.4 3 1.1-6L3.2 9.4l6.1-.8L12 3Z" />,
  bookmark: <path d="M6 3h12v18l-6-4-6 4V3Z" />,
  shieldCheck: <><path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z" /><path d="m9 12 2 2 4-4.5" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  helpCircle: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 0 1 5 .3c0 1.7-2.5 2-2.5 3.7" /><path d="M12 17h.01" /></>,
  ban: <><circle cx="12" cy="12" r="9" /><path d="m5.5 5.5 13 13" /></>,
  server: <><rect x="3" y="4" width="18" height="7" rx="2" /><rect x="3" y="13" width="18" height="7" rx="2" /><path d="M7 7.5h.01M7 16.5h.01" /></>,
  monitor: <><rect x="2" y="4" width="20" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></>,
  smartphone: <><rect x="7" y="2" width="10" height="20" rx="2" /><path d="M11 18.5h2" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M8 3v4M16 3v4M3 10h18" /></>,
  timer: <><circle cx="12" cy="13" r="8" /><path d="M12 9v4l2.5 2.5" /><path d="M9 2h6" /></>,
  user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
  userPlus: <><circle cx="10" cy="8" r="3.5" /><path d="M3 20a7 7 0 0 1 14 0" /><path d="M19 5v6M16 8h6" /></>,
  rotateCcw: <><path d="M3 12a9 9 0 1 0 2.6-6.4" /><path d="M3 4v5h5" /></>,
  rotateCw: <><path d="M21 12a9 9 0 1 1-2.6-6.4" /><path d="M21 4v5h-5" /></>,
  history: <><path d="M3 12a9 9 0 1 0 2.6-6.4" /><path d="M3 4v5h5" /><path d="M12 7v5l3 2" /></>,
  undo: <><path d="M9 14 4 9l5-5" /><path d="M4 9h10a6 6 0 0 1 0 12h-3" /></>,
  redo: <><path d="m15 14 5-5-5-5" /><path d="M20 9H10a6 6 0 0 0 0 12h3" /></>,
  clipboard: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4a3 3 0 0 1 6 0" /><path d="M9 11h6M9 15h4" /></>,
  panelLeft: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  eyeOff: <><path d="m3 3 18 18" /><path d="M10.6 5.1A9.8 9.8 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-2.9 3.9M6.6 6.6A16.6 16.6 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 4-.8" /><path d="m9.9 9.9.3.3A3 3 0 0 0 12 15" /></>,
  crop: <><path d="M6 2v16a2 2 0 0 0 2 2h14" /><path d="M2 6h16a2 2 0 0 1 2 2v14" /></>,
  circleDot: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2" fill="currentColor" /></>,
  target: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></>,
  inbox: <><path d="M3 13h5l2 3h4l2-3h5" /><path d="M5 5h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" /></>,
  split: <><path d="M12 3v6" /><path d="m12 9-5 5" /><path d="m12 9 5 5" /><path d="M5 17v4M19 17v4" /></>,
  arrowUpDown: <><path d="m7 4-3 3 3 3" /><path d="M4 7h13" /><path d="m17 20 3-3-3-3" /><path d="M20 17H7" /></>,
  barChart: <><path d="M4 20h16" /><path d="M7 20v-6M12 20V6M17 20v-9" /></>,
};
export type IconName = keyof typeof P;
export function Icon({ name, size = 14, className = "" }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" width={size} height={size} className={className} aria-hidden>
      {P[name]}
    </svg>
  );
}

// ------------------------------------------------------------------ atoms
export const Kbd = ({ children }: { children: React.ReactNode }) => (
  <kbd className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded border border-edge2 bg-panel3 text-[10px] font-mono text-dim">{children}</kbd>
);

export const Micro = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <div className={`text-[10px] font-mono uppercase tracking-[0.14em] text-faint ${className}`}>{children}</div>
);

type BtnVariant = "primary" | "ghost" | "outline" | "danger" | "subtle";
export function Btn({ variant = "ghost", size = "md", children, onClick, disabled, className = "", title, active }: {
  variant?: BtnVariant; size?: "sm" | "md"; children: React.ReactNode; onClick?: (e?: React.MouseEvent<HTMLButtonElement>) => void; disabled?: boolean; className?: string; title?: string; active?: boolean;
}) {
  const base = "inline-flex items-center gap-1.5 rounded font-medium transition-colors select-none whitespace-nowrap disabled:opacity-40 disabled:pointer-events-none";
  const sz = size === "sm" ? "text-[11px] px-2 h-7" : "text-[12px] px-3 h-8";
  const v: Record<BtnVariant, string> = {
    primary: "bg-amber text-ink hover:bg-amber2",
    ghost: "text-dim hover:text-cream hover:bg-panel3",
    outline: "border border-edge2 text-dim hover:text-cream hover:border-faint",
    danger: "border border-brick/40 text-brick hover:bg-brick/10",
    subtle: "text-faint hover:text-dim hover:bg-panel3",
  };
  return (
    <button title={title} disabled={disabled} onClick={onClick} className={`${base} ${sz} ${v[variant]} ${active ? "ring-1 ring-amber/60 text-amber" : ""} ${className}`}>
      {children}
    </button>
  );
}

/** two-step safeguard for destructive / overwriting actions */
export function ArmBtn({ label, confirmLabel = "confirm", onConfirm, className = "", danger = true }: {
  label: React.ReactNode; confirmLabel?: string; onConfirm: () => void; className?: string; danger?: boolean;
}) {
  const [armed, setArmed] = React.useState(false);
  return (
    <button
      className={`${armed ? (danger ? "bg-brick text-cream" : "bg-amber text-ink") : ""} ${className}`}
      onClick={() => {
        if (armed) { onConfirm(); setArmed(false); }
        else { setArmed(true); setTimeout(() => setArmed(false), 3000); }
      }}
    >
      {armed ? confirmLabel : label}
    </button>
  );
}

export function Seg<T extends string>({ options, value, onChange }: {
  options: { value: T; label: React.ReactNode }[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded border border-edge bg-ink overflow-hidden text-[11px]">
      {options.map((o) => (
        <button key={o.value} onClick={() => onChange(o.value)}
          className={`px-2.5 h-7 flex items-center gap-1 transition-colors ${value === o.value ? "bg-panel3 text-cream" : "text-faint hover:text-dim"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Chip({ active, onClick, children, title, className = "" }: {
  active?: boolean; onClick?: () => void; children: React.ReactNode; title?: string; className?: string;
}) {
  return (
    <button title={title} onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-full border px-2 h-6 text-[11px] transition-colors select-none ${active ? "border-amber/60 bg-amber/10 text-amber" : "border-edge bg-panel2 text-dim hover:border-edge2 hover:text-cream"} ${className}`}>
      {children}
    </button>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button onClick={() => onChange(!on)} className="inline-flex items-center gap-2 select-none">
      <span className={`w-8 h-[18px] rounded-full border transition-colors relative ${on ? "bg-amber/20 border-amber/50" : "bg-panel3 border-edge2"}`}>
        <span className={`absolute top-[2px] w-[12px] h-[12px] rounded-full transition-all ${on ? "left-[17px] bg-amber" : "left-[3px] bg-faint"}`} />
      </span>
      {label && <span className="text-[11px] text-dim">{label}</span>}
    </button>
  );
}

export function Slider({ value, min, max, step = 1, onChange, format }: {
  value: number; min: number; max: number; step?: number; onChange: (v: number) => void; format?: (v: number) => string;
}) {
  return (
    <div className="flex items-center gap-2">
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="flex-1" />
      <span className="text-[11px] font-mono text-amber w-12 text-right">{format ? format(value) : value}</span>
    </div>
  );
}

export function Num({ value, onChange, min = 0, max = 9999, className = "" }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; className?: string;
}) {
  return (
    <input type="number" value={value} min={min} max={max}
      onChange={(e) => onChange(Math.max(min, Math.min(max, Number(e.target.value) || 0)))}
      className={`bg-ink border border-edge rounded px-2 h-7 text-[11px] font-mono text-cream w-16 outline-none focus:border-amber/50 ${className}`} />
  );
}

export function Text({ value, onChange, placeholder, className = "" }: {
  value: string; onChange: (v: string) => void; placeholder?: string; className?: string;
}) {
  return (
    <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      className={`bg-ink border border-edge rounded px-2 h-7 text-[12px] text-cream outline-none focus:border-amber/50 placeholder:text-faint ${className}`} />
  );
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <Micro className="mb-1.5">{label}</Micro>
      {children}
      {hint && <div className="text-[10px] text-faint mt-1">{hint}</div>}
    </div>
  );
}

export function Panel({ title, right, children, className = "", pad = true }: {
  title?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={`rounded border border-edge bg-panel ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-2 px-3 h-9 border-b border-edge">
          <Micro>{title}</Micro>
          {right}
        </header>
      )}
      <div className={pad ? "p-3" : ""}>{children}</div>
    </section>
  );
}

const tones: Record<string, string> = {
  ok: "text-sage border-sage/30 bg-sage/10",
  warn: "text-amber border-amber/30 bg-amber/10",
  err: "text-brick border-brick/30 bg-brick/10",
  info: "text-steel border-steel/30 bg-steel/10",
  neutral: "text-dim border-edge2 bg-panel3",
};
export function Badge({ tone = "neutral", children, className = "" }: { tone?: keyof typeof tones; children: React.ReactNode; className?: string }) {
  return <span className={`inline-flex items-center gap-1 rounded-full border px-1.5 h-[18px] text-[10px] font-mono ${tones[tone]} ${className}`}>{children}</span>;
}

/** model output vs owner-verified — the product-wide visual contract */
export function ConfTag({ kind, conf, label }: { kind: "model" | "verified"; conf?: number; label?: string }) {
  if (kind === "verified")
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-amber bg-amber/15 px-1.5 h-[18px] text-[10px] font-mono text-amber">
        <Icon name="check" size={9} /> {label ?? "verified"}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-edge2 px-1.5 h-[18px] text-[10px] font-mono text-dim" title="model output — not yet verified">
      <span className="text-amber">~</span> {label ?? "model"}{conf != null && <span className="text-faint">{Math.round(conf * 100)}%</span>}
    </span>
  );
}

export function ScoreBar({ value, tone }: { value: number; tone?: "auto" | "amber" }) {
  const c = tone === "amber" ? "bg-amber" : value >= 0.75 ? "bg-sage" : value >= 0.5 ? "bg-amber" : "bg-brick";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-10 h-[3px] rounded bg-panel3 overflow-hidden">
        <div className={`h-full rounded ${c}`} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-[10px] font-mono text-dim">{Math.round(value * 100)}</span>
    </div>
  );
}

export function Progress({ value, tone = "amber" }: { value: number; tone?: "amber" | "sage" | "brick" }) {
  return (
    <div className="h-[3px] rounded bg-panel3 overflow-hidden">
      <div className={`h-full rounded ${tone === "amber" ? "bg-amber" : tone === "sage" ? "bg-sage" : "bg-brick"}`} style={{ width: `${Math.min(100, Math.round(value))}%` }} />
    </div>
  );
}

/** timeline of sections along a video; verified sections solid, model sections dashed */
export function Timeline({ duration, sections, clipRange, className = "" }: {
  duration: number; sections: { start: number; end: number; conf: number; verified: boolean; pos?: string }[]; clipRange?: [number, number]; className?: string;
}) {
  return (
    <div className={`relative h-[14px] rounded-sm bg-panel3 overflow-hidden ${className}`} title={sections.map((s) => `${s.pos ?? "section"} ${Math.round(s.start)}–${Math.round(s.end)}s · ${Math.round(s.conf * 100)}%`).join("\n")}>
      {sections.map((s, i) => (
        <div key={i} className={`absolute top-0 bottom-0 ${s.verified ? "bg-amber/70" : "border border-dashed border-amber/50 bg-amber/10"}`}
          style={{ left: `${(s.start / duration) * 100}%`, width: `${Math.max(0.8, ((s.end - s.start) / duration) * 100)}%` }} />
      ))}
      {clipRange && (
        <div className="absolute top-0 bottom-0 bg-cream/25 border-x border-cream"
          style={{ left: `${(clipRange[0] / duration) * 100}%`, width: `${Math.max(1, ((clipRange[1] - clipRange[0]) / duration) * 100)}%` }} />
      )}
    </div>
  );
}

// ------------------------------------------------------------------ procedural media placeholder
export function Thumb({ seed, ratio = "3:4", figure = true, className = "" }: {
  seed: string; ratio?: "3:4" | "16:9" | "1:1"; figure?: boolean; className?: string;
}) {
  const svg = useMemo(() => {
    const h = hashStr(seed);
    const r = mulberry(h);
    const warm = r() > 0.35;
    const hue1 = warm ? 18 + r() * 40 : 200 + r() * 30;
    const hue2 = warm ? 30 + r() * 30 : 220 + r() * 40;
    const l1 = 14 + r() * 14, l2 = 22 + r() * 16;
    const fx = 20 + r() * 60, fy = 30 + r() * 40, fs = 0.5 + r() * 0.9;
    const horizon = 55 + r() * 25;
    const light = r() > 0.5;
    const id = "g" + (h % 100000);
    const fig = figure ? (
      <g opacity="0.9">
        <ellipse cx={fx} cy={fy} rx={9 * fs} ry={11 * fs} fill="#0c0a08" />
        <path d={`M ${fx - 14 * fs} ${fy + 34 * fs} Q ${fx - 15 * fs} ${fy + 12 * fs} ${fx} ${fy + 10 * fs} Q ${fx + 15 * fs} ${fy + 12 * fs} ${fx + 14 * fs} ${fy + 34 * fs} Z`} fill="#0c0a08" />
        <ellipse cx={fx} cy={fy} rx={9 * fs} ry={11 * fs} fill="none" stroke={`hsl(${hue2} 30% 60% / 0.35)`} strokeWidth="0.8" />
      </g>
    ) : null;
    return (
      <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" className="w-full h-full block">
        <defs>
          <linearGradient id={id} x1={light ? 0 : 1} y1="0" x2={light ? 1 : 0} y2="1">
            <stop offset="0%" stopColor={`hsl(${hue1} 24% ${l2}%)`} />
            <stop offset="100%" stopColor={`hsl(${hue2} 20% ${l1}%)`} />
          </linearGradient>
          <radialGradient id={id + "r"} cx={light ? "70%" : "30%"} cy="30%" r="80%">
            <stop offset="0%" stopColor={`hsl(${hue2} 40% 55% / 0.25)`} />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
        </defs>
        <rect width="100" height="100" fill={`url(#${id})`} />
        <rect y={horizon} width="100" height={100 - horizon} fill={`hsl(${hue1} 18% ${Math.max(6, l1 - 4)}%)`} opacity="0.8" />
        <rect width="100" height="100" fill={`url(#${id}r)`} />
        {fig}
        <rect width="100" height="100" fill="black" opacity="0.12" />
        <rect x="0" y="0" width="100" height="100" fill="none" stroke="#000" strokeOpacity="0.4" strokeWidth="0.5" />
      </svg>
    );
  }, [seed, ratio, figure]);
  return <div className={`relative overflow-hidden bg-panel2 ${className} grain`}>{svg}</div>;
}

export function EmptyState({ icon, title, body, action }: { icon: IconName; title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      <div className="w-10 h-10 rounded-full border border-edge flex items-center justify-center text-faint"><Icon name={icon} size={18} /></div>
      <div className="text-[13px] text-dim">{title}</div>
      {body && <div className="text-[11px] text-faint max-w-[300px]">{body}</div>}
      {action}
    </div>
  );
}

export function SectionHead({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-2">
      <Micro>{title}</Micro>
      {right}
    </div>
  );
}
