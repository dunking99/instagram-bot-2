import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, post } from "./api";
import type {
  Account, CacheMode, ClipLengths, Item, Job, Mix, Model, Polarity, ResultMode, TagPick, View,
} from "./types";

const KEY = "postroom.v2";

export type Toast = { id: string; text: string };
export type RunMeta = {
  mode: ResultMode;
  polarity: Polarity;
  folder: string | null;
  warnings: string[];
  failed: boolean;
};
export type SlideState = { open: boolean; items: Item[]; index: number; play: boolean; more?: () => Promise<Item[]> };
export type Session = { authFile: boolean; loggedIn: boolean; userId: string | null; user: string | null; checkedAt: string | null };
export const EXPECTED_API = 4;
export type Config = { tags: Record<string, string[]>; clipLengths: ClipLengths; host: string; apiVersion?: number };

type Prefs = Partial<{
  model: Model; selectedAccounts: string[]; count: number; polarity: Polarity; resultMode: ResultMode; mix: Mix;
  baseDir: string; top: number; takeAll: boolean; cap: number; confidence: number; includeVideo: boolean;
  mixVideos: boolean; clipSeconds: number; allSlides: boolean; margin: number | null; expand: number;
  videoMix: number | null; imageWeight: number; mirrorPose: boolean; sceneTop: number; user: string | null;
  checkedAt: string | null;
}>;

function loadPrefs(): Prefs {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "{}") as Prefs;
  } catch {
    return {};
  }
}

function uid() {
  return Math.random().toString(36).slice(2, 8);
}

const DeskContext = createContext<any>(null);

export function useDesk() {
  const ctx = useContext(DeskContext);
  if (!ctx) throw new Error("Desk missing");
  return ctx;
}

type RunResponse = {
  status: "running" | "done" | "failed" | "cancelled";
  code: number | null;
  lines: string[];
  total: number;
  result?: { items: Item[]; folder: string | null; warnings: string[]; mode: ResultMode };
  folder?: string;
};

export function DeskProvider({ children }: { children: ReactNode }) {
  const prefs = useRef(loadPrefs()).current;
  const [view, setView] = useState<View>("search");
  const [model, setModelState] = useState<Model>(prefs.model || "siglip");
  const [config, setConfig] = useState<Config>({ tags: {}, clipLengths: { "15 seconds": 15 }, host: "" });
  const [session, setSession] = useState<Session>({
    authFile: true, loggedIn: true, userId: null, user: prefs.user ?? null, checkedAt: prefs.checkedAt ?? null,
  });
  const [accountList, setAccounts] = useState<Account[]>([]);
  const [accountsLoaded, setAccountsLoaded] = useState(false);
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>(prefs.selectedAccounts || []);
  const [favs, setFavs] = useState<Item[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsOpen, setJobsOpen] = useState(false);
  const [activeJob, setActiveJob] = useState<string | null>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [autoImport, setAutoImportState] = useState(false);

  const [text, setText] = useState("");
  const [useText, setUseText] = useState(true);
  const [useImage, setUseImage] = useState(false);
  const [usePose, setUsePose] = useState(false);
  const [refImage, setRefImage] = useState<string | null>(null);
  const [poseImage, setPoseImage] = useState<string | null>(null);
  const [imageWeight, setImageWeight] = useState(prefs.imageWeight ?? 0.5);
  const [mirrorPose, setMirrorPose] = useState(prefs.mirrorPose ?? true);
  const [sceneTop, setSceneTop] = useState(prefs.sceneTop ?? 30);
  const [tags, setTags] = useState<TagPick[]>([]);
  const [confidence, setConfidence] = useState(prefs.confidence ?? 0.5);
  const [polarity, setPolarity] = useState<Polarity>(prefs.polarity || "best");
  const [count, setCount] = useState(prefs.count ?? 5);
  const [takeAll, setTakeAll] = useState(prefs.takeAll ?? false);
  const [cap, setCap] = useState(prefs.cap ?? 100);
  const [mix, setMix] = useState<Mix>(prefs.mix || "each");
  const [top, setTop] = useState(prefs.top ?? 50);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [includeVideo, setIncludeVideo] = useState(prefs.includeVideo ?? false);
  const [mixVideos, setMixVideos] = useState(prefs.mixVideos ?? true);
  const [videoMix, setVideoMix] = useState<number | null>(prefs.videoMix ?? null);
  const [clipSeconds, setClipSeconds] = useState(prefs.clipSeconds ?? 15);
  const [allSlides, setAllSlides] = useState(prefs.allSlides ?? false);
  const [margin, setMargin] = useState<number | null>(prefs.margin ?? null);
  const [expand, setExpand] = useState(prefs.expand ?? 0);
  const [cacheMode, setCacheMode] = useState<CacheMode>("cache");
  const [resultMode, setResultMode] = useState<ResultMode>(prefs.resultMode || "thumbs");
  const [baseDir, setBaseDir] = useState(prefs.baseDir || "picks");

  const [searching, setSearching] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [showLog, setShowLog] = useState(false);
  const [results, setResults] = useState<Item[] | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [runMeta, setRunMeta] = useState<RunMeta | null>(null);
  const [lastSummary, setLastSummary] = useState("");
  const [composerOpen, setComposerOpen] = useState(true);
  const [savedDir, setSavedDir] = useState<string | null>(null);
  const [slides, setSlides] = useState<SlideState>({ open: false, items: [], index: 0, play: false });

  const [collectionsTab, setCollectionsTab] = useState<"images" | "videos" | "favourites">("images");
  const [favFilter, setFavFilter] = useState("all");
  const [libraryAccount, setLibraryAccount] = useState<string>("");

  const [toasts, setToasts] = useState<Toast[]>([]);
  const [refineOpen, setRefineOpen] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [prepareFor, setPrepareFor] = useState<string | null>(null);
  const [importKind, setImportKind] = useState<null | "images" | "videos" | "bulk">(null);

  const toast = useCallback((t: string) => {
    const id = uid();
    setToasts((prev) => [...prev.slice(-3), { id, text: t }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 3600);
  }, []);
  const fail = useCallback((e: unknown) => toast(e instanceof Error ? e.message : String(e)), [toast]);

  // accounts the server knows, plus any typed names that haven't been prepared yet
  const accounts = useMemo(() => {
    const known = new Set(accountList.map((a) => a.handle));
    const extra = selectedAccounts.filter((h) => !known.has(h)).map((handle): Account => ({
      handle, kind: "instagram", posts: 0, videos: 0, models: { siglip: false, clip: false }, pose: false,
      carouselDetected: false, opened: 0, toOpen: 0, extraSlides: 0, prepared: null, libraryBuilt: false, cover: null,
    }));
    return [...accountList, ...extra];
  }, [accountList, selectedAccounts]);

  const live = useRef({} as Record<string, any>);
  live.current = {
    accounts, selectedAccounts, model, text, useText, useImage, usePose, refImage, poseImage, imageWeight, mirrorPose,
    sceneTop, tags, confidence, polarity, count, takeAll, cap, mix, top, dateFrom, dateTo, includeVideo, mixVideos,
    videoMix, clipSeconds, allSlides, margin, expand, cacheMode, resultMode, baseDir, session,
  };

  // --- remember the form between visits (per browser; the page works without it) ---
  useEffect(() => {
    const p: Prefs = {
      model, selectedAccounts, count, polarity, resultMode, mix, baseDir, top, takeAll, cap, confidence, includeVideo,
      mixVideos, clipSeconds, allSlides, margin, expand, videoMix, imageWeight, mirrorPose, sceneTop,
      user: session.user, checkedAt: session.checkedAt,
    };
    try {
      localStorage.setItem(KEY, JSON.stringify(p));
    } catch {
      /* storage may be unavailable */
    }
  }, [model, selectedAccounts, count, polarity, resultMode, mix, baseDir, top, takeAll, cap, confidence, includeVideo,
    mixVideos, clipSeconds, allSlides, margin, expand, videoMix, imageWeight, mirrorPose, sceneTop, session.user, session.checkedAt]);

  // --- loading from the server ---
  const refreshAccounts = useCallback(async () => {
    try {
      const r = await api<{ accounts: Account[] }>("/api/accounts");
      setAccounts(r.accounts);
    } catch (e) {
      fail(e);
    } finally {
      setAccountsLoaded(true);
    }
  }, [fail]);

  const refreshFavs = useCallback(async () => {
    try {
      setFavs((await api<{ items: Item[] }>("/api/favs")).items);
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  const refreshSession = useCallback(async () => {
    try {
      const s = await api<{ authFile: boolean; loggedIn: boolean; userId: string | null }>("/api/session");
      setSession((prev) => ({ ...prev, ...s }));
    } catch {
      /* the server may be restarting */
    }
  }, []);

  const bump = useCallback(() => setDataVersion((v) => v + 1), []);

  useEffect(() => {
    (async () => {
      try {
        const c = await api<Config & { autoImport: boolean }>("/api/config");
        setConfig({ tags: c.tags, clipLengths: c.clipLengths, host: c.host, apiVersion: c.apiVersion });
        setAutoImportState(c.autoImport);
        if (c.autoImport && !sessionStorage.getItem("postroom.autoimport")) {
          sessionStorage.setItem("postroom.autoimport", "1");
          const r = await post<{ started: boolean; pending?: number }>("/api/imports/auto-run", { model });
          if (r.started) toast(`Importing ${r.pending} new file${r.pending === 1 ? "" : "s"} from your folders`);
        }
      } catch (e) {
        fail(e);
      }
    })();
    refreshAccounts();
    refreshFavs();
    refreshSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- background jobs: poll, and notice when one finishes ---
  const seen = useRef(new Map<string, string>());
  const anyRunning = useRef(false);
  useEffect(() => {
    let timer = 0;
    let stop = false;
    const tick = async () => {
      try {
        const r = await api<{ jobs: Job[] }>("/api/jobs");
        setJobs(r.jobs);
        anyRunning.current = r.jobs.some((j) => j.running);
        let changed = false;
        for (const j of r.jobs) {
          const was = seen.current.get(j.id);
          seen.current.set(j.id, j.status);
          if (was === "running" && j.status !== "running") {
            changed = true;
            toast(j.status === "done" ? `${j.title} finished` : j.status === "stopped" ? `${j.title} stopped` : `${j.title} ended with errors`);
            if (j.kind === "login") refreshSession();
          }
        }
        if (changed) {
          refreshAccounts();
          bump();
        }
      } catch {
        /* ignore a missed poll */
      }
      if (!stop) timer = window.setTimeout(tick, anyRunning.current ? 1500 : 6000);
    };
    tick();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [toast, refreshAccounts, refreshSession, bump]);

  const startJob = useCallback(async (body: Record<string, unknown>): Promise<boolean> => {
    try {
      const job = await post<Job>("/api/jobs", { model: live.current.model, ...body });
      setJobs((prev) => [job, ...prev.filter((j) => j.id !== job.id)]);
      seen.current.set(job.id, "running");
      anyRunning.current = true;
      setActiveJob(job.id);
      setJobsOpen(true);
      toast(`${job.title} started`);
      return true;
    } catch (e) {
      fail(e);
      return false;
    }
  }, [toast, fail]);

  const stopJob = async (id: string) => {
    try {
      await post(`/api/jobs/${id}/stop`);
    } catch (e) {
      fail(e);
    }
  };
  const dismissJob = async (id: string) => {
    setJobs((prev) => prev.filter((j) => j.id !== id));
    try {
      await post(`/api/jobs/${id}/dismiss`);
    } catch (e) {
      fail(e);
    }
  };

  // --- settings ---
  const setModel = (next: Model) => {
    setModelState(next);
    toast(next === "siglip" ? "Using the SigLIP index" : "Using the older CLIP index");
  };

  const setAutoImport = async (on: boolean) => {
    setAutoImportState(on);
    try {
      await post("/api/settings/auto-import", { on });
    } catch (e) {
      fail(e);
    }
  };

  const checkSession = async () => {
    try {
      const r = await post<{ ok: boolean; text: string; user: string | null }>("/api/session/check");
      const at = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      setSession((prev) => ({ ...prev, user: r.user ?? prev.user, checkedAt: at, loggedIn: r.ok }));
      toast(r.text || (r.ok ? "Session ok" : "Session check failed"));
      return r;
    } catch (e) {
      fail(e);
      return null;
    }
  };

  // --- accounts ---
  const toggleAccount = (handle: string) =>
    setSelectedAccounts((prev) => (prev.includes(handle) ? prev.filter((h) => h !== handle) : [...prev, handle]));

  const addAccount = (raw: string) => {
    const handle = raw.replace(/^@/, "").trim().replace(/\/+$/, "").toLowerCase();
    if (!handle) return;
    setSelectedAccounts((prev) => (prev.includes(handle) ? prev : [...prev, handle]));
    if (!accountList.some((a) => a.handle === handle)) toast(`@${handle} added. Prepare it before the first long search.`);
  };

  const toggleTag = (group: string, tag: string) =>
    setTags((prev) =>
      prev.some((t) => t.group === group && t.tag === tag)
        ? prev.filter((t) => !(t.group === group && t.tag === tag))
        : [...prev, { group, tag }],
    );

  // --- searching ---
  const runToken = useRef(0);
  const runId = useRef<string | null>(null);

  const finishRun = useCallback((r: RunResponse, s: Record<string, any>, patch?: { forceRandom?: boolean }) => {
    const items = (r.result?.items || []).map((it, i) => ({ ...it, rid: `${i}:${it.id}` }));
    setResults(items);
    setSelectedIds(s.resultMode === "thumbs" ? items.map((i) => i.rid as string) : []);
    setRunMeta({
      mode: s.resultMode, polarity: s.polarity, folder: r.result?.folder ?? null,
      warnings: r.result?.warnings || [], failed: r.status === "failed",
    });
    const random = patch?.forceRandom || !((s.useText && s.text.trim()) || (s.useImage && s.refImage) || (s.usePose && s.poseImage) || s.tags.length);
    const label = random ? "Random draw" : (s.useText && s.text.trim()) || (s.useImage && s.refImage ? "Reference" : s.usePose && s.poseImage ? "Pose" : "Tags");
    setLastSummary(`${s.selectedAccounts.map((h: string) => "@" + h).join("  ")} · ${label}`);
    setSearching(false);
    setShowLog(false);
    if (r.status === "failed" && !items.length) {
      setShowLog(true);
      toast("The search finished with errors. See the log.");
    }
  }, [toast]);

  const find = useCallback(async (patch?: Record<string, any>) => {
    const s = { ...live.current, ...patch };
    if (!s.selectedAccounts.length) {
      toast("Choose at least one account.");
      return;
    }
    if (!patch?.forceRandom && s.useImage && !s.refImage) {
      toast("Add a reference image, or turn Reference off.");
      return;
    }
    if (!patch?.forceRandom && s.usePose && !s.poseImage) {
      toast("Add a pose reference, or turn Pose off.");
      return;
    }
    if (patch?.text != null) setText(patch.text);
    if (patch?.selected) setSelectedAccounts(patch.selected);
    if (patch?.useText != null) setUseText(patch.useText);
    if (patch?.useImage != null) setUseImage(patch.useImage);
    if (patch?.usePose != null) setUsePose(patch.usePose);
    if (patch?.tags) setTags(patch.tags);
    if (patch?.dateFrom != null) setDateFrom(patch.dateFrom);
    if (patch?.dateTo != null) setDateTo(patch.dateTo);
    if (patch?.includeVideo != null) setIncludeVideo(patch.includeVideo);

    const force = !!patch?.forceRandom;
    const tagStrings = force ? [] : (s.tags as TagPick[]).filter((t) => t.tag != null).map((t) => `${t.group}:${t.tag}`);
    const payload = {
      accounts: s.selectedAccounts, model: s.model, text: force ? "" : s.text, useText: force ? false : s.useText,
      useImage: !force && s.useImage, refImage: s.refImage, usePose: !force && s.usePose, poseImage: s.poseImage,
      imageWeight: s.imageWeight, mirror: s.mirrorPose, sceneTop: s.sceneTop, tags: tagStrings, confidence: s.confidence,
      polarity: s.polarity, count: s.count, takeAll: s.takeAll && !force, cap: s.cap, mix: s.mix, top: s.top,
      dateFrom: s.dateFrom || null, dateTo: s.dateTo || null, includeVideo: s.includeVideo, mixVideos: s.mixVideos,
      videoMix: s.videoMix, clipSeconds: s.clipSeconds, allSlides: s.allSlides, margin: s.margin, expand: s.expand,
      cacheMode: s.cacheMode, resultMode: s.resultMode, baseDir: s.baseDir,
    };
    const token = ++runToken.current;
    setSearching(true);
    setShowLog(true);
    setComposerOpen(false);
    setView("search");
    setLogs(["Starting random_post.py ..."]);
    setSavedDir(null);
    let id: string;
    try {
      id = (await post<{ id: string }>("/api/search", payload)).id;
    } catch (e) {
      if (token === runToken.current) {
        setSearching(false);
        setComposerOpen(true);
        setLogs([]);
      }
      fail(e);
      return;
    }
    runId.current = id;
    let since = 0;
    let lines: string[] = [];
    const poll = async () => {
      if (token !== runToken.current) return;
      try {
        const r = await api<RunResponse>(`/api/runs/${id}?since=${since}`);
        if (token !== runToken.current) return;
        since = r.total;
        lines = [...lines, ...r.lines];
        setLogs(lines.length ? lines : ["Working... the first search on an account can take a few minutes while it reads the whole profile."]);
        if (r.status === "running") {
          window.setTimeout(poll, 600);
          return;
        }
        if (r.status === "cancelled") {
          setSearching(false);
          setLogs([...lines, "cancelled"]);
          return;
        }
        finishRun(r, s, patch);
      } catch (e) {
        if (token === runToken.current) {
          setSearching(false);
          fail(e);
        }
      }
    };
    poll();
  }, [toast, fail, finishRun]);

  const cancelFind = async () => {
    runToken.current += 1;
    setSearching(false);
    setLogs((prev) => [...prev, "cancelled"]);
    if (runId.current) {
      try {
        await post(`/api/runs/${runId.current}/cancel`);
      } catch {
        /* already finished */
      }
    }
  };

  const toggleSelected = (rid: string) =>
    setSelectedIds((prev) => (prev.includes(rid) ? prev.filter((x) => x !== rid) : [...prev, rid]));

  // --- favourites ---
  const favIds = useMemo(() => new Set(favs.map((f) => f.id)), [favs]);
  const isFav = useCallback((id: string) => favIds.has(id), [favIds]);

  const toggleFav = useCallback(async (item: Item, silent = false) => {
    try {
      const r = await post<{ starred: boolean }>("/api/favs/toggle", {
        account: item.account, stem: item.name, url: item.url || "", src: item.src,
      });
      await refreshFavs();
      if (!silent) toast(r.starred ? `Copied to favourites/${item.account.toLowerCase()}/` : "Removed from favourites");
      return r.starred;
    } catch (e) {
      fail(e);
      return null;
    }
  }, [refreshFavs, toast, fail]);

  // --- saving results ---
  const saveSelected = async (kind: "thumbs" | "full") => {
    const picked = (results || []).filter((r) => selectedIds.includes(r.rid as string));
    if (!picked.length) {
      toast("Nothing selected.");
      return;
    }
    try {
      const r = await post<{ dir: string; saved: number; runId?: string }>("/api/save", {
        kind, baseDir, model, items: picked.map((p) => ({ account: p.account, name: p.name, url: p.url, slide: p.slide, score: p.score })),
      });
      if (!r.runId) {
        setSavedDir(r.dir);
        toast(`Saved ${r.saved} ${kind === "thumbs" ? "thumbnail" : "photo"}${r.saved === 1 ? "" : "s"} to ${r.dir}/`);
        return;
      }
      toast("Fetching the full-size photos from Instagram...");
      const poll = async () => {
        try {
          const rr = await api<RunResponse>(`/api/runs/${r.runId}?since=0`);
          if (rr.status === "running") {
            window.setTimeout(poll, 1500);
            return;
          }
          setSavedDir(r.dir);
          toast(rr.status === "done" ? `Saved to ${r.dir}/` : "The fetch finished with errors. Some photos may be missing.");
        } catch (e) {
          fail(e);
        }
      };
      poll();
    } catch (e) {
      fail(e);
    }
  };

  const openFolder = async (path: string) => {
    try {
      await post("/api/open-folder", { path });
    } catch (e) {
      fail(e);
    }
  };

  const revealPath = async (path: string) => {
    try {
      await post("/api/reveal", { path });
    } catch (e) {
      fail(e);
    }
  };

  // --- the viewer ---
  const openSlides = (items: Item[], index: number, play = false, more?: () => Promise<Item[]>) =>
    setSlides({ open: true, items, index, play, more });
  const appendSlides = (items: Item[]) => setSlides((s) => (s.open ? { ...s, items: [...s.items, ...items] } : s));
  const closeSlides = () => setSlides((s) => ({ ...s, open: false }));
  const stepSlides = (dir: number) =>
    setSlides((s) => (s.items.length ? { ...s, index: (s.index + dir + s.items.length) % s.items.length } : s));

  const copyText = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      /* clipboard may be blocked */
    }
    toast(`Copied ${value}`);
  };

  const value = {
    view, setView, model, setModel, config, session, setSession, refreshSession, checkSession, accounts, accountsLoaded,
    refreshAccounts, selectedAccounts, setSelectedAccounts, toggleAccount, addAccount, favs, isFav, toggleFav, refreshFavs,
    jobs, jobsOpen, setJobsOpen, activeJob, setActiveJob, startJob, stopJob, dismissJob, dataVersion, bump,
    autoImport, setAutoImport,
    text, setText, useText, setUseText, useImage, setUseImage, usePose, setUsePose, refImage, setRefImage, poseImage,
    setPoseImage, imageWeight, setImageWeight, mirrorPose, setMirrorPose, sceneTop, setSceneTop, tags, toggleTag, setTags,
    confidence, setConfidence, polarity, setPolarity, count, setCount, takeAll, setTakeAll, cap, setCap, mix, setMix,
    top, setTop, dateFrom, setDateFrom, dateTo, setDateTo, includeVideo, setIncludeVideo, mixVideos, setMixVideos,
    videoMix, setVideoMix, clipSeconds, setClipSeconds, allSlides, setAllSlides, margin, setMargin, expand, setExpand,
    cacheMode, setCacheMode, resultMode, setResultMode, baseDir, setBaseDir,
    searching, logs, showLog, setShowLog, results, selectedIds, setSelectedIds, toggleSelected, runMeta, lastSummary,
    composerOpen, setComposerOpen, find, cancelFind, saveSelected, savedDir, openFolder, revealPath,
    slides, openSlides, appendSlides, closeSlides, stepSlides, collectionsTab, setCollectionsTab, favFilter, setFavFilter,
    libraryAccount, setLibraryAccount, toasts, toast, fail, refineOpen, setRefineOpen, sessionOpen, setSessionOpen,
    paletteOpen, setPaletteOpen, prepareFor, setPrepareFor, importKind, setImportKind, copyText,
  };

  return <DeskContext.Provider value={value}>{children}</DeskContext.Provider>;
}

