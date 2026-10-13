import { useEffect, useState } from "react";
import { api } from "../api";

// The data18 scraper (performers, videos, photos, model results) runs as its own small server; this page starts it and shows it in place.
// It is reached through this app's own address (/d18/), so it also works from the phone.
export function Data18View() {
  const [state, setState] = useState<"starting" | "ready" | "failed">("starting");
  const [error, setError] = useState("");

  const start = async () => {
    setState("starting");
    setError("");
    try {
      await api<{ url: string }>("/lt/data18");
      setState("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState("failed");
    }
  };
  useEffect(() => { start(); }, []);

  if (state !== "ready") {
    return (
      <div className="section" style={{ padding: 32 }}>
        <p className="kicker">Data18 Scraper</p>
        <h3>{state === "starting" ? "Starting the Data18 scraper..." : "The Data18 scraper could not start"}</h3>
        {error && <p className="hint">{error}</p>}
        {state === "failed" && <button type="button" className="btn" onClick={start}>Try again</button>}
      </div>
    );
  }
  return <iframe title="Data18 Scraper" src="/d18/" className="links-frame" />;
}
