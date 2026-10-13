import type { ReactNode } from "react";
import { cn } from "../utils/cn";

const ICONS: Record<string, string[]> = {
  search: ["M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16z", "M21 21l-4.2-4.2"],
  grid: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
  folder: ["M3 7h6l2 2h10v10H3z"],
  layers: ["M12 3.5l8.5 4.5-8.5 4.5L3.5 8z", "M3.5 12l8.5 4.5 8.5-4.5", "M3.5 16l8.5 4.5 8.5-4.5"],
  play: ["M5 4.5v15l14-7.5z"],
  link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
  aperture: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 3l2.5 7.5L12 21", "M3.5 8.5h17", "M4.5 15.5h15"],
  image: ["M4 5h16v14H4z", "M4 15l4.5-4.5 3 3L16 9l4 4"],
  pose: ["M12 5a2 2 0 1 0 0-4 2 2 0 0 0 0 4z", "M8 22l2-7-3-3 5-2 5 2-3 3 2 7", "M10 10h4"],
  sliders: ["M4 7h16", "M4 12h16", "M4 17h16", "M8 7v0", "M14 12v0", "M10 17v0"],
  download: ["M12 4v11", "M7 11l5 5 5-5", "M5 20h14"],
  link: ["M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1", "M14 11a5 5 0 0 0-7.1-.1l-2 2a5 5 0 0 0 7.1 7.1l1.1-1.1"],
  play: ["M8 5v14l12-7z"],
  x: ["M6 6l12 12", "M18 6L6 18"],
  plus: ["M12 5v14", "M5 12h14"],
  external: ["M14 4h6v6", "M20 4l-9 9", "M18 14v5H5V6h5"],
  pause: ["M8 5v14", "M16 5v14"],
  shuffle: ["M16 3h5v5", "M4 20L21 3", "M21 16v5h-5", "M15 15l6 6", "M4 4l5 5"],
  expand: ["M8 3H5a2 2 0 0 0-2 2v3", "M21 8V5a2 2 0 0 0-2-2h-3", "M3 16v3a2 2 0 0 0 2 2h3", "M16 21h3a2 2 0 0 0 2-2v-3"],
  disk: ["M4 7h16v10H4z", "M7 14h.01", "M11 14h4"],
  undo: ["M9 14L4 9l5-5", "M4 9h10a6 6 0 0 1 0 12h-3"],
  trash: ["M5 7h14", "M9 7V4h6v3", "M7 7l1 13h8l1-13"],
  check: ["M5 12.5l5 5 9-10"],
  video: ["M3 6h13v12H3z", "M16 10l5-3v10l-5-3"],
};

export function Icon({ name, size = 18 }: { name: keyof typeof ICONS | string; size?: number }) {
  const paths = ICONS[name];
  if (!paths) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths.map((d) => <path key={d} d={d} />)}
    </svg>
  );
}

export function Star({ filled, size = 15 }: { filled?: boolean; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.6" fill={filled ? "currentColor" : "none"} aria-hidden="true">
      <path d="m12 3 2.7 6.2 6.7.6-5.1 4.4 1.6 6.6L12 17.2 6.1 20.8l1.6-6.6L2.6 9.8l6.7-.6L12 3z" />
    </svg>
  );
}

export function Check({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden="true">
      <path d="M5 12.5 10 17.5 19 7" />
    </svg>
  );
}

export function Seg<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="seg" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" role="tab" aria-selected={value === o.id} className={value === o.id ? "on" : ""} onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({
  on,
  label,
  hint,
  onClick,
}: {
  on: boolean;
  label: string;
  hint?: string;
  onClick: () => void;
}) {
  return (
    <button type="button" role="switch" aria-checked={on} className={cn("toggle", on && "on")} onClick={onClick}>
      <span className="track"><span className="knob" /></span>
      <span>
        <strong>{label}</strong>
        {hint && <small>{hint}</small>}
      </span>
    </button>
  );
}

export function Modal({
  title,
  kicker,
  onClose,
  children,
  wide,
}: {
  title: string;
  kicker?: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="modal-back" onMouseDown={onClose}>
      <div className={cn("modal", wide && "wide")} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <header>
          <div>
            {kicker && <p className="kicker">{kicker}</p>}
            <h2>{title}</h2>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </header>
        {children}
      </div>
    </div>
  );
}
