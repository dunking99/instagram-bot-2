import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Can't reach the Postroom server. Is `python3 server.py` still running?");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail);
  }
  return (await res.json()) as T;
}

export const api = <T,>(path: string) => request<T>(path);

export const post = <T,>(path: string, body: unknown = {}) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });

/** A value kept in localStorage (a per-browser convenience; the page works without it). */
export function usePref<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(`postroom.${key}`);
      return raw == null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(`postroom.${key}`, JSON.stringify(value));
    } catch {
      /* storage may be unavailable */
    }
  }, [key, value]);
  return [value, useCallback((v) => setValue(v), [])];
}

export function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new ApiError("That file couldn't be read."));
    reader.readAsDataURL(file);
  });
}

export function fmtBytes(n: number): string {
  return n >= 1e8 ? `${(n / 1e9).toFixed(1)} GB` : `${(n / 1e6).toFixed(0)} MB`;
}

export function fmtDuration(sec: number): string {
  const s = Math.floor(sec);
  return s >= 3600
    ? `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
    : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
