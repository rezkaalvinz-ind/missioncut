"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Node = { id: string; label: string; asset_type: string; criticality: string };
type Edge = { id: string; source: string; target: string; status: string; label?: string; change_cost?: number };
type Graph = { directed: boolean; allow_parallel_edges: boolean; nodes: Node[]; edges: Edge[] };
type Scenario = { id: string; name: string; kind: "full_isolation" | "selective" | "custom"; suspect_node_ids: string[]; edge_ids: string[] };
type PathResult = { source: string; target: string; count: number; paths: string[][] };
type Evaluation = { scenario: Scenario; blocked_connection_count: number; changed_asset_count: number; change_cost: number; before_reachable_asset_count: number; after_reachable_asset_count: number; lost_reachable_asset_count: number; paths_before: PathResult[]; paths_after: PathResult[]; paths_lost: PathResult[]; services: { id: string; label: string; reachable_before: boolean; reachable_after: boolean }[]; services_still_reachable: number; services_unreachable_after: number; path_counts_truncated: boolean; assumptions: string[] };
type Demo = { graph: Graph; scenarios: Scenario[]; expected_independent_result: Record<string, unknown> };
type Compare = { results: Evaluation[]; recommendation: { scenario_ids: string[]; tie: boolean; criteria: string[]; trade_off: string; limitations: string } };

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function icon(type: string) { return ({ endpoint: "[ ]", server: "[=]", database: "[#]", service: "<> ", identity: "O", network: "@", cloud: "~" } as Record<string, string>)[type] || "*"; }
function nodeLabel(graph: Graph | undefined, id: string) { return graph?.nodes.find((n) => n.id === id)?.label || id; }
function formatPath(graph: Graph | undefined, path: string[]) { return path.map((id) => nodeLabel(graph, id)).join(" -> "); }

export default function Home() {
  const [demo, setDemo] = useState<Demo | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [suspect, setSuspect] = useState("suspect");
  const [kind, setKind] = useState<Scenario["kind"]>("full_isolation");
  const [selectedEdges, setSelectedEdges] = useState<string[]>(["e2"]);
  const [comparison, setComparison] = useState<Compare | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [uploadName, setUploadName] = useState("");
  const [expandedPaths, setExpandedPaths] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [showLabels, setShowLabels] = useState(true);
  const [showWelcome, setShowWelcome] = useState(true);
  const [authStep, setAuthStep] = useState<"auth" | "app">("auth");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authName, setAuthName] = useState("");
  const [authError, setAuthError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState<{ id: number; email: string; name: string } | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => setShowWelcome(false), 2600);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    const token = window.localStorage.getItem("missioncut_token");
    if (!token) return;
    fetch(`${API}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => { if (!response.ok) throw new Error("Session expired"); return response.json(); })
      .then((user) => { setCurrentUser(user); setAuthStep("app"); })
      .catch(() => { window.localStorage.removeItem("missioncut_token"); });
  }, []);
  const graph = demo?.graph;

  const loadDemo = useCallback(async () => {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API}/api/demo`, { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const data: Demo = await response.json(); setDemo(data); setComparison(null);
    } catch (e) {
      const detail = e instanceof DOMException && e.name === "TimeoutError" ? "The API did not respond within 10 seconds." : e instanceof Error ? e.message : "";
      setError(`Could not reach MissionCut API at ${API}. Start the backend and reload the demo. ${detail}`);
    } finally { setBusy(false); }
  }, []);
  useEffect(() => { void loadDemo(); }, [loadDemo]);

  const scenarios = useMemo((): Scenario[] => {
    const selected = kind === "selective" ? selectedEdges : [];
    return [
      { id: "full-isolation", name: `Isolate ${graph?.nodes.find((n) => n.id === suspect)?.label || "suspect"}`, kind: "full_isolation", suspect_node_ids: [suspect], edge_ids: [] },
      { id: "selective", name: "Selected connection blocks", kind: "selective", suspect_node_ids: [suspect], edge_ids: selected.length ? selected : [graph?.edges[0]?.id || "e1"] },
      { id: "custom", name: "Custom selected links", kind: "custom", suspect_node_ids: [suspect], edge_ids: selectedEdges },
    ];
  }, [graph, kind, selectedEdges, suspect]);

  async function submitAuth(event: { preventDefault: () => void }) {
    event.preventDefault(); setAuthBusy(true); setAuthError("");
    try {
      const response = await fetch(`${API}/api/auth/${authMode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: authEmail, password: authPassword, name: authName }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || data?.detail || "Authentication failed");
      window.localStorage.setItem("missioncut_token", data.token);
      setCurrentUser(data.user); setAuthStep("app"); setAuthPassword("");
    } catch (error) { setAuthError(error instanceof Error ? error.message : "Authentication failed"); }
    finally { setAuthBusy(false); }
  }

  function signOut() { window.localStorage.removeItem("missioncut_token"); setCurrentUser(null); setSidebarOpen(false); setAuthStep("auth"); setAuthMode("login"); setAuthPassword(""); }

  async function compareScenarios() {
    if (!graph) return;
    setBusy(true); setError(""); setActiveTab("comparison");
    try {
      const response = await fetch(`${API}/api/scenarios/compare`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ graph, scenarios, sources: [suspect] }) });
      const data = await response.json(); if (!response.ok) throw new Error(data?.error?.message || `API returned ${response.status}`); setComparison(data);
    } catch (e) { setError(`Could not evaluate scenarios. ${e instanceof Error ? e.message : ""}`); }
    finally { setBusy(false); }
  }

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true); setError(""); setUploadName(file.name);
    try {
      const format = file.name.toLowerCase().endsWith(".csv") ? "csv" : "json";
      const response = await fetch(`${API}/api/graphs/load?format=${format}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
      const data = await response.json(); if (!response.ok) throw new Error(data?.error?.message || "Graph validation failed");
      setDemo({ graph: data.graph, scenarios: [], expected_independent_result: {} }); setSuspect(data.graph.nodes[0]?.id || ""); setComparison(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Upload failed"); }
    finally { setBusy(false); }
  }

  async function exportReport() {
    if (!comparison || !graph) return;
    try {
      const response = await fetch(`${API}/api/reports`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ graph, scenarios, sources: [suspect] }) });
      const data = await response.json(); if (!response.ok) throw new Error(data?.error?.message || `API returned ${response.status}`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = "missioncut-report.json"; link.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(`Could not generate the report. ${e instanceof Error ? e.message : ""}`); }
  }

  const pos = useMemo(() => {
    if (!graph) return new Map<string, { x: number; y: number }>();

    // Build adjacency for degree count
    const degree = new Map<string, number>(graph.nodes.map((nd) => [nd.id, 0]));
    graph.edges.forEach((e) => {
      degree.set(e.source, (degree.get(e.source) || 0) + 1);
      degree.set(e.target, (degree.get(e.target) || 0) + 1);
    });

    // BFS layers from highest-degree node (hub-and-spoke hierarchy)
    const sorted = [...graph.nodes].sort((a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0));
    const layers = new Map<string, number>();
    const queue: string[] = [];
    const root = sorted[0]?.id;
    if (root) { layers.set(root, 0); queue.push(root); }
    const adj = new Map<string, string[]>(graph.nodes.map((nd) => [nd.id, []]));
    graph.edges.forEach((e) => {
      adj.get(e.source)?.push(e.target);
      adj.get(e.target)?.push(e.source);
    });
    let qi = 0;
    while (qi < queue.length) {
      const cur = queue[qi++];
      const curLayer = layers.get(cur) || 0;
      (adj.get(cur) || []).forEach((nb) => {
        if (!layers.has(nb)) { layers.set(nb, curLayer + 1); queue.push(nb); }
      });
    }
    // Unconnected nodes get their own layer
    graph.nodes.forEach((nd) => { if (!layers.has(nd.id)) layers.set(nd.id, 99); });

    // Group nodes per layer
    const byLayer = new Map<number, string[]>();
    graph.nodes.forEach((nd) => {
      const l = layers.get(nd.id) ?? 0;
      if (!byLayer.has(l)) byLayer.set(l, []);
      byLayer.get(l)!.push(nd.id);
    });

    // Sort layer keys and assign positions
    const layerKeys = [...byLayer.keys()].sort((a, b) => a - b);
    const NODE_W = 110; const NODE_H = 56; const PAD_X = 60; const PAD_Y = 80;
    const maxPerRow = Math.max(...layerKeys.map((k) => byLayer.get(k)!.length));
    const totalW = Math.max(640, maxPerRow * (NODE_W + PAD_X) - PAD_X + 120);

    const result = new Map<string, { x: number; y: number }>();
    layerKeys.forEach((layer, li) => {
      const ids = byLayer.get(layer)!;
      // Sort within layer: critical nodes first, then by label
      ids.sort((a, b) => {
        const na = graph.nodes.find((nd) => nd.id === a)!;
        const nb = graph.nodes.find((nd) => nd.id === b)!;
        if (na.criticality === "critical" && nb.criticality !== "critical") return -1;
        if (nb.criticality === "critical" && na.criticality !== "critical") return 1;
        return na.label.localeCompare(nb.label);
      });
      const rowW = ids.length * (NODE_W + PAD_X) - PAD_X;
      const startX = (totalW - rowW) / 2 + NODE_W / 2;
      ids.forEach((id, idx) => {
        result.set(id, { x: startX + idx * (NODE_W + PAD_X), y: 80 + li * (NODE_H + PAD_Y) });
      });
    });
    return result;
  }, [graph]);

  const graphWidth = Math.max(640, (() => {
    if (!graph) return 640;
    const degree = new Map<string, number>(graph.nodes.map((nd) => [nd.id, 0]));
    graph.edges.forEach((e) => { degree.set(e.source, (degree.get(e.source)||0)+1); degree.set(e.target, (degree.get(e.target)||0)+1); });
    const layers = new Map<string, number>();
    const adj = new Map<string, string[]>(graph.nodes.map((nd) => [nd.id, []]));
    graph.edges.forEach((e) => { adj.get(e.source)?.push(e.target); adj.get(e.target)?.push(e.source); });
    const root = [...graph.nodes].sort((a,b)=>(degree.get(b.id)||0)-(degree.get(a.id)||0))[0]?.id;
    if (root) { const q=[root]; layers.set(root,0); let qi=0; while(qi<q.length){const c=q[qi++];const cl=layers.get(c)||0;(adj.get(c)||[]).forEach((nb)=>{if(!layers.has(nb)){layers.set(nb,cl+1);q.push(nb);}});} }
    graph.nodes.forEach((nd)=>{ if(!layers.has(nd.id)) layers.set(nd.id,99); });
    const byLayer = new Map<number,string[]>();
    graph.nodes.forEach((nd)=>{ const l=layers.get(nd.id)??0; if(!byLayer.has(l)) byLayer.set(l,[]); byLayer.get(l)!.push(nd.id); });
    const maxPR = Math.max(...[...byLayer.values()].map((v)=>v.length));
    return Math.max(640, maxPR * 170 - 60 + 120);
  })());
  const graphHeight = Math.max(360, (() => {
    if (!graph) return 360;
    const degree = new Map<string, number>(graph.nodes.map((nd) => [nd.id, 0]));
    graph.edges.forEach((e) => { degree.set(e.source, (degree.get(e.source)||0)+1); degree.set(e.target, (degree.get(e.target)||0)+1); });
    const layers = new Map<string, number>();
    const adj = new Map<string, string[]>(graph.nodes.map((nd) => [nd.id, []]));
    graph.edges.forEach((e) => { adj.get(e.source)?.push(e.target); adj.get(e.target)?.push(e.source); });
    const root = [...graph.nodes].sort((a,b)=>(degree.get(b.id)||0)-(degree.get(a.id)||0))[0]?.id;
    if (root) { const q=[root]; layers.set(root,0); let qi=0; while(qi<q.length){const c=q[qi++];const cl=layers.get(c)||0;(adj.get(c)||[]).forEach((nb)=>{if(!layers.has(nb)){layers.set(nb,cl+1);q.push(nb);}});} }
    graph.nodes.forEach((nd)=>{ if(!layers.has(nd.id)) layers.set(nd.id,99); });
    const layerCount = new Set([...layers.values()].filter((v)=>v<99)).size + (graph.nodes.some((_,__)=>layers.get(graph.nodes[__]?.id??"")=== 99)?1:0);
    return Math.max(360, layerCount * 136 + 80);
  })());
  const cardResults = comparison?.results;
  const goTo = (tab: string) => { setActiveTab(tab); setMenuOpen(false); document.getElementById("workspace")?.scrollIntoView({ behavior: "smooth", block: "start" }); setSidebarOpen(false); };

  return <main className="orbit-shell" id="main-content">
    <div className={`welcome-screen ${showWelcome ? "visible" : "hidden"}`} aria-hidden={!showWelcome}>
      <div className="welcome-stars" aria-hidden="true"/>
      <div className="welcome-content"><div className="welcome-logo"><span className="welcome-orbit"/><span>Mission<span>Cut</span></span></div><div className="welcome-kicker">OFFLINE DECISION SUPPORT</div><h1>Containment,<br/><em>with context.</em></h1><p>Loading your private topology workspace</p><div className="welcome-progress"><span/></div></div>
    </div>
    <div className={`auth-screen ${showWelcome || authStep === "app" ? "hidden" : "visible"}`} aria-hidden={showWelcome || authStep === "app"}>
      <div className="auth-card"><div className="auth-card-brand">Mission<span>Cut</span></div><div className="auth-kicker">PRIVATE WORKSPACE</div><h2>{authMode === "login" ? "Welcome back" : "Create your account"}</h2><p>{authMode === "login" ? "Sign in to continue to your containment workspace." : "Save your MissionCut workspace securely in the cloud."}</p><form onSubmit={submitAuth}>{authMode === "register" && <label>Display name<input value={authName} onChange={(event) => setAuthName(event.target.value)} placeholder="Your name" autoComplete="name" /></label>}<label>Email<input type="email" value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} placeholder="you@example.com" autoComplete="email" required /></label><label>Password<input type="password" value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} placeholder="At least 8 characters" autoComplete={authMode === "login" ? "current-password" : "new-password"} minLength={8} required /></label>{authError && <div className="auth-error" role="alert">{authError}</div>}<button className="btn solid auth-submit" type="submit" disabled={authBusy}>{authBusy ? "Connecting..." : authMode === "login" ? "Sign in" : "Create account"}<span>-&gt;</span></button></form><div className="auth-switch">{authMode === "login" ? "New to MissionCut?" : "Already have an account?"}<button onClick={() => { setAuthMode(authMode === "login" ? "register" : "login"); setAuthError(""); }}>{authMode === "login" ? "Register" : "Sign in"}</button></div><small className="auth-note">Your password is hashed before storage. Analysis remains simulation-only.</small></div>
    </div>
    {authStep === "app" && <><button className={`hamburger-btn${sidebarOpen ? " shifted" : ""}`} aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"} aria-expanded={sidebarOpen} onClick={() => setSidebarOpen((v) => !v)}><span className={`ham-line${sidebarOpen ? " open" : ""}`}/><span className={`ham-line${sidebarOpen ? " open" : ""}`}/><span className={`ham-line${sidebarOpen ? " open" : ""}`}/></button><div className={`sidebar-scrim ${sidebarOpen ? "open" : ""}`} onClick={() => setSidebarOpen(false)} aria-hidden="true"/><aside className={`app-sidebar ${sidebarOpen ? "open" : ""}`} aria-label="Workspace sidebar"><div className="sidebar-top"><div className="sidebar-brand">Mission<span>Cut</span></div></div><div className="profile-card"><div className="profile-avatar">{(currentUser?.name || "M").slice(0, 1).toUpperCase()}</div><div><strong>{currentUser?.name || "MissionCut user"}</strong><span>{currentUser?.email || "Local session"}</span></div></div><nav className="sidebar-nav" aria-label="Workspace navigation"><span className="sidebar-label">WORKSPACE</span><button className={activeTab === "overview" ? "active" : ""} onClick={() => goTo("overview")}><b>O</b> Topology <small>01</small></button><button className={activeTab === "setup" ? "active" : ""} onClick={() => goTo("setup")}><b>S</b> Scenarios <small>02</small></button><button className={activeTab === "comparison" ? "active" : ""} onClick={() => goTo("comparison")}><b>A</b> Analysis <small>03</small></button><span className="sidebar-label">ACCOUNT</span><button className={activeTab === "profile" ? "active" : ""} onClick={() => goTo("profile")}><b>P</b> Profile</button><button className={activeTab === "settings" ? "active" : ""} onClick={() => goTo("settings")}><b>G</b> Settings</button><span className="sidebar-label">QUICK ACTIONS</span><button onClick={() => { void loadDemo(); setSidebarOpen(false); }}><b>⟳</b> Load demo</button><label className="sidebar-nav-upload"><b>↑</b> Upload graph<input type="file" accept=".json,.csv,application/json,text/csv" onChange={(e) => { void upload(e.target.files?.[0]); setSidebarOpen(false); }}/></label></nav><div className="sidebar-bottom"><div className="sidebar-status"><i/> Simulation only<span>Read-only workspace</span></div><button className="sidebar-signout" onClick={() => { signOut(); setSidebarOpen(false); }}>Sign out <span>→</span></button></div></aside></>}
    <div className="cosmic-backdrop" aria-hidden="true"><div className="nebula nebula-a"/><div className="nebula nebula-b"/><div className="nebula nebula-c"/><div className="nebula nebula-d"/><div className="planet"><div className="planet-highlight"/><div className="planet-band-1"/><div className="planet-band-2"/><span className="planet-ring"/></div><div className="cloud cloud-a"/><div className="cloud cloud-b"/><div className="stars"/></div>
    <header className="orbit-bar">
      <a className="orbit-brand" href="#main-content" aria-label="MissionCut home"><span className="orbit-logo"><svg viewBox="0 0 27 17" aria-hidden="true"><ellipse cx="13.25" cy="8.4" rx="13.2" ry="2.9" transform="rotate(-25 13.25 8.4)"/><circle cx="13.25" cy="8.4" r="8.7" className="logo-planet"/><ellipse cx="13.25" cy="8.4" rx="13.2" ry="2.9" transform="rotate(-25 13.25 8.4)" className="logo-ring-front"/></svg></span><span>Mission<span className="brand-accent">Cut</span></span></a>
      <nav className="orbit-links" aria-label="Primary"><button onClick={() => goTo("overview")}>Overview</button><button onClick={() => goTo("setup")}>Scenarios</button><button onClick={() => goTo("comparison")}>Analysis</button></nav>
      <div className="orbit-actions"><span className="live-chip"><i/> offline simulator</span><button className="menu-button" aria-label="Menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}><span/><span/><span/></button></div>
      {menuOpen && <nav className="mobile-sheet" aria-label="Menu"><button onClick={() => goTo("overview")}>Overview</button><button onClick={() => goTo("setup")}>Scenarios</button><button onClick={() => goTo("comparison")}>Analysis</button></nav>}
    </header>

    <section className="orbit-hero"><a className="hero-pill" href="#workspace"><b>LIVE</b><span>Model the blast radius before you act</span><strong>        </strong></a><h1>Containment,<br/><em>with context.</em></h1><p>Explore what changes before a real-world response. MissionCut maps reachable assets, critical services, and route-level impact on a private graph copy.</p><div className="hero-cta"><button className="btn ghost" onClick={() => goTo("setup")}>Configure scenarios</button><button className="btn solid" onClick={() => goTo("overview")}>Explore topology <span>        </span></button></div></section>

    <section className="workspace-wrap" id="workspace">
      <div className="simulation-ribbon"><span><i/> Simulation only</span><small>Human-led    -  Read-only    -  No production actions</small><b>{uploadName || "SYNTHETIC DATASET"}</b></div>
      {error && <div className="error-banner" role="alert"><strong>Attention</strong><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error">     </button></div>}
      {activeTab === "profile" ? <section className="account-view"><div className="glass-panel account-panel"><span className="section-kicker">ACCOUNT / PROFILE</span><h2>Your profile</h2><p className="panel-copy">Account details for your MissionCut workspace.</p><div className="account-identity"><div className="profile-avatar large">{(currentUser?.name || "M").slice(0, 1).toUpperCase()}</div><div><strong>{currentUser?.name || "MissionCut user"}</strong><span>{currentUser?.email || "Local session"}</span></div></div><dl className="account-details"><div><dt>Display name</dt><dd>{currentUser?.name || "MissionCut user"}</dd></div><div><dt>Email address</dt><dd>{currentUser?.email || "Not available"}</dd></div><div><dt>Account ID</dt><dd>{currentUser?.id ?? "Local session"}</dd></div></dl><button className="btn ghost" onClick={signOut}>Sign out</button></div></section> : activeTab === "settings" ? <section className="account-view"><div className="glass-panel account-panel"><span className="section-kicker">WORKSPACE / PREFERENCES</span><h2>Settings</h2><p className="panel-copy">Adjust how the topology workspace is displayed.</p><label className="setting-row"><span><strong>Show asset labels</strong><small>Display names and asset details on the topology map.</small></span><input type="checkbox" checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)} /></label><div className="setting-row"><span><strong>Graph zoom</strong><small>Current zoom: {Math.round(zoom * 100)}%</small></span><button className="btn ghost" onClick={() => setZoom(1)}>Reset</button></div><div className="settings-note"><span className="section-kicker">SIMULATION MODE</span><p>MissionCut evaluates scenarios on an isolated graph copy. It does not apply changes to production systems.</p></div></div></section> : !graph ? <div className="loading-panel" aria-live="polite">{busy ? <><span className="spinner"/> Loading the synthetic topology       </> : <>No graph loaded. Load the demo or upload a JSON / CSV graph.</>}</div> : <>
        <nav className="workspace-tabs" aria-label="Workspace sections">{[["overview", "01    -  Topology"], ["setup", "02    -  Scenarios"], ["comparison", "03    -  Comparison"]].map(([id, label]) => <button key={id} className={activeTab === id ? "active" : ""} aria-current={activeTab === id ? "page" : undefined} onClick={() => setActiveTab(id)}>{label}</button>)}<span>{graph.nodes.length} assets <i/> {graph.edges.length} connections</span></nav>
        {activeTab === "overview" && <section className="workspace-grid">
          <div className="glass-panel graph-panel"><div className="panel-head"><div><span className="section-kicker">TOPOLOGY / {graph.directed ? "DIRECTED" : "UNDIRECTED"}</span><h2>Asset relationship map</h2></div><div className="graph-toolbar" aria-label="Graph controls"><button className="graph-control" onClick={() => setZoom((value) => Math.min(1.45, value + 0.12))} aria-label="Zoom in">+</button><button className="graph-control" onClick={() => setZoom((value) => Math.max(0.75, value - 0.12))} aria-label="Zoom out">-</button><button className={`graph-control ${showLabels ? "active" : ""}`} onClick={() => setShowLabels((value) => !value)} aria-pressed={showLabels}>Labels</button><button className="graph-control" onClick={() => { setZoom(1); setSelectedNode(null); }} aria-label="Reset graph view">Reset</button></div></div><div className="graph-canvas"><svg viewBox={`0 0 ${graphWidth} ${graphHeight}`} role="img" aria-label="Interactive graph showing asset connections" onClick={() => setSelectedNode(null)}><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#bbc2e9"/></marker></defs><g transform={`scale(${zoom})`}>{graph.edges.map((e) => { const a = pos.get(e.source), b = pos.get(e.target); if (!a || !b) return null; const blocked = e.status === "blocked"; const connected = selectedNode !== null && (e.source === selectedNode || e.target === selectedNode); const muted = selectedNode !== null && !connected; const chosen = comparison?.results.some((r) => (r.scenario.kind === "full_isolation" && (r.scenario.suspect_node_ids.includes(e.source) || r.scenario.suspect_node_ids.includes(e.target))) || (r.scenario.kind === "selective" && r.scenario.edge_ids.includes(e.id))); return <g key={e.id} className={`${muted ? "graph-muted" : ""} ${hoveredEdge === e.id ? "edge-hovered" : ""}`} onMouseEnter={() => setHoveredEdge(e.id)} onMouseLeave={() => setHoveredEdge(null)}><line x1={a.x + 55} y1={a.y + 28} x2={b.x - 55} y2={b.y + 28} className={blocked ? "edge blocked" : chosen ? "edge selected" : "edge"} markerEnd={graph.directed && !blocked ? "url(#arrow)" : undefined}/>{showLabels && <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 + 12} className="edge-label">{e.label || e.id}{e.change_cost !== undefined ? ` - ${e.change_cost}` : ""}</text>}</g>; })}{graph.nodes.map((n) => { const p = pos.get(n.id)!; const state = n.id === suspect ? "suspect" : n.criticality === "critical" ? "critical" : "normal"; const selected = selectedNode === n.id; const muted = selectedNode !== null && !selected; return <g key={n.id} className={`node ${state} ${selected ? "node-selected" : ""} ${muted ? "node-muted" : ""}`} transform={`translate(${p.x},${p.y})`} onClick={(event) => { event.stopPropagation(); setSelectedNode(n.id); }} role="button" tabIndex={0} aria-label={`Select ${n.label}`} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedNode(n.id); }}><rect x="-55" y="-28" width="110" height="56" rx="13"/><text className="node-icon" x="-40" y="8">{icon(n.asset_type)}</text><text className="node-name" x="-20" y="-4">{n.label.length > 14 ? `${n.label.slice(0, 13)}...` : n.label}</text><text className="node-type" x="-20" y="14">{n.criticality.toUpperCase()}</text></g>; })}</g></svg></div><div className="graph-selection" aria-live="polite">{selectedNode ? <><strong>{nodeLabel(graph, selectedNode)}</strong><span>Selected asset. Connected routes are highlighted.</span><button onClick={() => setSelectedNode(null)}>Clear</button></> : <span>Select a node to inspect its connected routes.</span>}</div><div className="legend"><span><i className="legend-dot suspect-dot"/> Suspected asset</span><span><i className="legend-dot critical-dot"/> Critical service</span><span><i className="legend-line"/> Active connection</span><span><i className="legend-line broken"/> Blocked connection</span></div></div>
          <aside className="glass-panel summary-panel"><div className="panel-head"><div><span className="section-kicker">CURRENT MODEL</span><h2>Graph snapshot</h2></div><span className="panel-orbit">   '  </span></div><div className="stat-row"><div><strong>{graph.nodes.length.toString().padStart(2, "0")}</strong><span>Assets</span></div><div><strong>{graph.edges.filter((e) => e.status === "active").length.toString().padStart(2, "0")}</strong><span>Active links</span></div></div><div className="critical-list"><div className="list-title">CRITICAL SERVICES <span>{graph.nodes.filter((n) => n.criticality === "critical").length}</span></div>{graph.nodes.filter((n) => n.criticality === "critical").map((n) => <div className="critical-item" key={n.id}><span className="service-glyph">        </span><span>{n.label}</span><small>IN MODEL</small></div>)}</div><div className="summary-footer"><span>Parallel links</span><strong>{graph.allow_parallel_edges ? "Allowed" : "Disabled"}</strong></div><button className="btn solid wide" onClick={() => setActiveTab("setup")}>Configure scenarios <span>        </span></button></aside>
        </section>}
        {activeTab === "setup" && <section className="setup-layout"><div className="glass-panel setup-panel"><div className="panel-head"><div><span className="section-kicker">SCENARIO BUILDER / STEP 1</span><h2>Choose a containment approach</h2></div><span className="panel-orbit">   "  </span></div><p className="panel-copy">Select the suspected asset and rules to evaluate. Every option is simulated on its own graph copy.</p><label className="field-label" htmlFor="suspect">SUSPECTED ASSET</label><select id="suspect" value={suspect} onChange={(e) => setSuspect(e.target.value)}>{graph.nodes.map((n) => <option key={n.id} value={n.id}>{n.label}    -  {n.asset_type}</option>)}</select><fieldset className="scenario-options"><legend className="field-label">SCENARIO TYPE</legend>{([ ["full_isolation", "Full isolation", "Block every active connection touching the selected asset."], ["selective", "Selective containment", "Block only the connections selected below."], ["custom", "Custom scenario", "Combine selected asset isolation and chosen links."] ] as [Scenario["kind"], string, string][]).map(([value, title, desc]) => <label className={`scenario-option ${kind === value ? "chosen" : ""}`} key={value}><input type="radio" name="kind" value={value} checked={kind === value} onChange={() => setKind(value)}/><span className="radio-dot"/><span className="option-copy"><strong>{title}</strong><small>{desc}</small></span><span className="option-code">{value === "full_isolation" ? "01" : value === "selective" ? "02" : "03"}</span></label>)}</fieldset><div className="field-label edge-label-head">CONNECTIONS TO BLOCK <span>Change cost shown when provided</span></div><div className="edge-picker">{graph.edges.map((e) => <label key={e.id} className="edge-choice"><input type="checkbox" checked={selectedEdges.includes(e.id)} onChange={(ev) => setSelectedEdges((current) => ev.target.checked ? [...current, e.id] : current.filter((id) => id !== e.id))}/><span className="checkmark"/><span className="edge-names">{nodeLabel(graph, e.source)} <b>        </b> {nodeLabel(graph, e.target)}<small>{e.id}    -  {e.status}</small></span><span className="cost-chip">{e.change_cost === undefined ? "        " : e.change_cost}</span></label>)}</div><button className="btn solid wide compare-cta" disabled={busy || !suspect || graph.nodes.length === 0} onClick={() => void compareScenarios()}>{busy ? <><span className="spinner small"/> Calculating       </> : <>Compare containment options <span>        </span></>}</button></div><aside className="glass-panel guidance-panel"><span className="section-kicker">HOW TO READ THIS</span><div className="guide-item"><b>A</b><div><strong>Reachability first</strong><p>Recommendations prioritize keeping critical services reachable.</p></div></div><div className="guide-item"><b>B</b><div><strong>Count distinct things</strong><p>Paths, assets, blocked links, and change cost are reported separately.</p></div></div><div className="guide-item"><b>C</b><div><strong>Review the trade-off</strong><p>Scenario scoring is explicit. Human responders make the final call.</p></div></div><div className="formula"><span>RANKING ORDER</span><p>Service reachability <b>        </b> paths lost <b>        </b> connections changed <b>        </b> cost</p></div></aside></section>}
        {activeTab === "comparison" && <section className="comparison-view"><div className="comparison-header"><div><span className="section-kicker">SCENARIO ANALYSIS / STEP 2</span><h2>Containment comparison</h2><p>Backend-calculated results for {suspect ? nodeLabel(graph, suspect) : "the selected graph"}.</p></div><div className="header-actions"><button className="btn ghost" onClick={() => void compareScenarios()} disabled={busy}>Recalculate</button><button className="btn solid" disabled={!comparison} onClick={() => void exportReport()}>Export report</button></div></div>{!comparison ? <div className="empty-state"><div className="empty-icon">~</div><h3>Run a comparison to see impact</h3><p>Set your suspected asset and scenario rules first.</p><button className="btn solid" onClick={() => setActiveTab("setup")}>Open scenario setup <span>-&gt;</span></button></div> : <><div className={`recommendation ${comparison.recommendation.tie ? "tie" : ""}`}><div className="rec-icon">{comparison.recommendation.tie ? "=" : "*"}</div><div className="rec-copy"><span className="section-kicker">{comparison.recommendation.tie ? "TIED RECOMMENDATION" : "RECOMMENDED OPTION"}</span><h3>{comparison.recommendation.tie ? "Several options share the top score" : comparison.results.find((r) => comparison.recommendation.scenario_ids.includes(r.scenario.id))?.scenario.name}</h3><p>{comparison.recommendation.trade_off}</p></div><div className="rec-rule"><span>RANKED BY</span><strong>Reachability first</strong><small>then disruption &amp; cost</small></div></div><div className="result-grid">{cardResults?.map((r, index) => { const recommended = comparison.recommendation.scenario_ids.includes(r.scenario.id); return <article className={`glass-panel result-card ${recommended ? "recommended" : ""}`} key={r.scenario.id}><div className="result-head"><div><span className="scenario-index">OPTION 0{index + 1}</span><h3>{r.scenario.name}</h3></div>{recommended && <span className="best-badge">TOP SCORE</span>}</div><div className="service-score"><div className="score-ring"><strong>{r.services_still_reachable}</strong><small>/{r.services.length}</small></div><div><strong>critical services reachable</strong><span>{r.services_unreachable_after} unreachable after containment</span></div></div><div className="metric-grid"><div className="metric"><strong>{r.paths_lost.reduce((sum, p) => sum + p.count, 0)}</strong><span>ROUTES LOST</span></div><div className="metric"><strong>{r.after_reachable_asset_count}</strong><span>ASSETS REACHABLE</span></div><div className="metric"><strong>{r.blocked_connection_count}</strong><span>LINKS BLOCKED</span></div><div className="metric"><strong>{r.changed_asset_count}</strong><span>ASSETS TOUCHED</span></div></div><div className="cost-row"><span>Explicit change cost</span><strong>{r.change_cost || "Not specified"}</strong></div><div className="service-breakdown"><span className="field-label">CRITICAL SERVICE IMPACT</span>{r.services.map((s) => <div className="service-impact" key={s.id}><span>{s.label}</span><strong className={s.reachable_after ? "reachable" : "unreachable"}>{s.reachable_after ? "REACHABLE" : "UNREACHABLE"}</strong></div>)}</div><div className="path-details"><button className="path-toggle" onClick={() => setExpandedPaths((current) => current === r.scenario.id ? null : r.scenario.id)} aria-expanded={expandedPaths === r.scenario.id}><span>Route analysis</span>{expandedPaths === r.scenario.id ? "v" : ">"}</button>{expandedPaths === r.scenario.id && <div className="path-pairs">{r.paths_before.map((bp, i) => { const ap = r.paths_after[i]; const lp = r.paths_lost[i]; return <div className="path-pair" key={i}><div className="path-pair-head"><span className="path-route">{nodeLabel(graph, bp.source)} -&gt; {nodeLabel(graph, bp.target)}</span><span className="path-counts"><b>{bp.count}</b> before <i/> <b>{ap.count}</b> after <i/> <b className="lost-count">{lp.count}</b> lost</span></div>{lp.paths.length > 0 && <div className="path-list"><span className="path-list-label cut">CUT ROUTES</span>{lp.paths.map((p, j) => <span className="path-item cut" key={j}>{formatPath(graph, p)}</span>)}</div>}{ap.paths.length > 0 && <div className="path-list"><span className="path-list-label kept">REMAINING ROUTES</span>{ap.paths.map((p, j) => <span className="path-item kept" key={j}>{formatPath(graph, p)}</span>)}</div>}{bp.count === 0 && ap.count === 0 && <div className="path-empty">No routes in this pair</div>}</div>; })}</div>}</div></article>; })}</div><div className="glass-panel criteria-panel"><div><span className="section-kicker">SCORING TRANSPARENCY</span><h3>Recommendation criteria</h3></div><ol>{comparison.recommendation.criteria.map((c) => <li key={c}>{c}</li>)}</ol><p>{comparison.recommendation.limitations}</p>{cardResults?.some((r) => r.path_counts_truncated) && <p className="truncated-note">Path enumeration reached its safety limit; path totals may be lower bounds.</p>}</div></>}</section>}
      </>}
    </section>
    <footer className="orbit-footer"><span>MissionCut <b>0.1</b></span><span>Offline decision support    -  No production actions</span><span>API <i/> connected when data loaded</span></footer>
  </main>;
}





