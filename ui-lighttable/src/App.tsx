import { Component, type ReactNode } from "react";
import { Chrome } from "./components/Chrome";
import { CollectionsView } from "./components/CollectionsView";
import { AnalysisView } from "./components/AnalysisView";
import { Data18View } from "./components/Data18View";
import { LibraryView } from "./components/LibraryView";
import { LinksView } from "./components/LinksView";
import { PilotView } from "./components/PilotView";
import { PositionsView } from "./components/PositionsView";
import { SearchView } from "./components/SearchView";
import { DeskProvider, useDesk } from "./store";

class Guard extends Component<{ children: ReactNode; view: string }, { error: Error | null; view: string }> {
  state = { error: null as Error | null, view: this.props.view };
  static getDerivedStateFromError(error: Error) { return { error }; }
  static getDerivedStateFromProps(p: { view: string }, s: { error: Error | null; view: string }) {
    return p.view !== s.view ? { error: null, view: p.view } : null;       // leaving the page clears the error
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="section" style={{ padding: 32 }}>
        <p className="kicker">Something went wrong on this page</p>
        <h3>The rest of the app is fine.</h3>
        <p className="hint" style={{ maxWidth: 640 }}>{this.state.error.message}</p>
        <button type="button" className="btn" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}

function Shell() {
  const { view } = useDesk();
  return (
    <Chrome>
      <Guard view={view}>
      {view === "search" && <SearchView />}
      {view === "library" && <LibraryView />}
      {view === "collections" && <CollectionsView />}
      {view === "pilot" && <PilotView />}
      {view === "positions" && <PositionsView />}
      {view === "analysis" && <AnalysisView />}
      {view === "data18" && <Data18View />}
      {view === "links" && <LinksView />}
      </Guard>
    </Chrome>
  );
}

export default function App() {
  return (
    <DeskProvider>
      <Shell />
    </DeskProvider>
  );
}
