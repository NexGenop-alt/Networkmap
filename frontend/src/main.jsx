import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, AlertTriangle, CheckCircle2, Clock, RadioTower, ServerCrash } from "lucide-react";
import { TopologyMap } from "./components/TopologyMap.jsx";
import "./styles.css";

const API = "";

function App() {
  const [topology, setTopology] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
  const [health, setHealth] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [selectedDetails, setSelectedDetails] = useState({});
  const [asOfInput, setAsOfInput] = useState("");
  const [error, setError] = useState("");
  const asOfIso = asOfInput ? new Date(asOfInput).toISOString() : "";
  const query = asOfIso ? `?at=${encodeURIComponent(asOfIso)}` : "";

  async function refresh() {
    try {
      const [topologyRes, nodesRes, linksRes, healthRes] = await Promise.all([
        fetch(`${API}/api/topology`),
        fetch(`${API}/api/nodes${query}`),
        fetch(`${API}/api/links${query}`),
        fetch(`${API}/api/health${query}`),
      ]);
      setTopology(await topologyRes.json());
      setNodes(await nodesRes.json());
      setLinks(await linksRes.json());
      setHealth(await healthRes.json());
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, [asOfIso]);

  useEffect(() => {
    if (!selectedIds.length) {
      setSelectedDetails({});
      return;
    }
    Promise.all(
      selectedIds.map((id) =>
        fetch(`${API}/api/nodes/${id}${query}`)
          .then((response) => response.json())
          .then((detail) => [id, detail])
      )
    )
      .then((entries) => setSelectedDetails(Object.fromEntries(entries)))
      .catch((err) => setError(err.message));
  }, [selectedIds, asOfIso]);

  const counts = health?.summary || { nodes: 0, links: 0, healthy: 0, warning: 0, critical: 0, unknown: 0 };
  const lastRefresh = asOfIso ? health?.latest_reading_at : health?.latest_reading_at || health?.collector?.last_poll || "";
  const criticalLinks = useMemo(() => links.filter((link) => link.health === "critical"), [links]);

  // Build a lookup: "NodeId_portNum" → { remoteNode, remotePort }
  // Uses positional pairing of from/to port lists so p35→p34, p36→p36, etc.
  const portConnections = useMemo(() => {
    const map = {};
    for (const link of links) {
      const fromPorts = parsePortList(link.ports?.from || "");
      const toPorts = parsePortList(link.ports?.to || "");
      const count = Math.min(fromPorts.length, toPorts.length);
      for (let i = 0; i < count; i++) {
        map[`${link.from}_${fromPorts[i]}`] = { remoteNode: link.to, remotePort: toPorts[i] };
        map[`${link.to}_${toPorts[i]}`] = { remoteNode: link.from, remotePort: fromPorts[i] };
      }
    }
    return map;
  }, [links]);
  const selectedNodes = selectedIds
    .map((id) => nodes.find((node) => node.id === id))
    .filter(Boolean);

  function toggleNode(node) {
    setSelectedIds((ids) =>
      ids.includes(node.id)
        ? ids.filter((id) => id !== node.id)
        : [...ids, node.id]
    );
  }

  return (
    <main className="grid h-screen grid-rows-[auto_minmax(0,1fr)] bg-[#091015] text-slate-100">
      <header className="grid gap-4 border-b border-white/10 bg-[#0c141b]/95 px-5 py-4 lg:grid-cols-[minmax(320px,1fr)_auto] lg:items-center">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold tracking-normal text-white">
              Cabinet Router Topology — Live Optical Monitor
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1"><Clock size={14} /> {asOfIso ? `Snapshot: ${lastRefresh ? formatTime(lastRefresh) : "No readings before selected date"}` : formatTime(lastRefresh)}</span>
              <span className="inline-flex items-center gap-1"><RadioTower size={14} /> {health?.collector?.mode || "waiting"}</span>
              {error ? <span className="text-red-300">{error}</span> : null}
            </div>
          </div>
        </div>
        <section className="grid grid-cols-[minmax(280px,auto)_repeat(5,minmax(76px,1fr))] gap-2">
          <TimeTravel value={asOfInput} onChange={setAsOfInput} />
          <Metric icon={Activity} label="Links" value={counts.links} />
          <Metric icon={CheckCircle2} label="Healthy" value={counts.healthy} tone="healthy" />
          <Metric icon={AlertTriangle} label="Warning" value={counts.warning} tone="warning" />
          <Metric icon={ServerCrash} label="Critical" value={counts.critical} tone="critical" />
          <Metric icon={RadioTower} label="Nodes" value={counts.nodes} />
        </section>
      </header>

      <div className="grid min-h-0 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="min-h-0 min-w-0 p-4">
          <TopologyMap
            topology={topology}
            nodes={nodes}
            links={links}
            selectedIds={selectedIds}
            onSelectNode={toggleNode}
          />
        </section>
        <aside className="min-h-0 overflow-y-auto border-t border-white/10 bg-[#0e171e] p-4 xl:border-l xl:border-t-0">
          <NodePanel
            details={selectedDetails}
            selectedNodes={selectedNodes}
            criticalLinks={criticalLinks}
            portConnections={portConnections}
            onClearNode={(id) => setSelectedIds((ids) => ids.filter((item) => item !== id))}
            onClearAll={() => setSelectedIds([])}
          />
        </aside>
      </div>
    </main>
  );
}

function TimeTravel({ value, onChange }) {
  function setRelative(days) {
    const date = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
    onChange(toLocalInputValue(date));
  }

  return (
    <div className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs font-semibold text-slate-300">Data date</label>
        <button className="text-xs font-semibold text-wyyerd hover:text-orange-200" onClick={() => onChange("")}>
          Live
        </button>
      </div>
      <div className="mt-2 flex gap-1">
        {[1, 7, 30, 90].map((days) => (
          <button key={days} className="rounded border border-white/10 px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10" onClick={() => setRelative(days)}>
            {days === 1 ? "24h" : `${days}d`}
          </button>
        ))}
      </div>
      <input
        className="mt-2 w-full rounded border border-white/10 bg-black/20 px-2 py-1 font-mono text-xs text-slate-100 outline-none focus:border-wyyerd"
        type="datetime-local"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function Metric({ icon: Icon, label, value, tone = "neutral" }) {
  const tones = {
    neutral: "border-white/10 bg-white/[0.04] text-slate-200",
    healthy: "border-emerald-400/20 bg-emerald-400/10 text-emerald-200",
    warning: "border-amber-400/20 bg-amber-400/10 text-amber-200",
    critical: "border-red-400/25 bg-red-400/10 text-red-200",
  };
  return (
    <div className={`rounded-md border px-3 py-2 ${tones[tone]}`}>
      <div className="flex items-center gap-2 text-xs text-current/80"><Icon size={14} /> {label}</div>
      <div className="mt-1 font-mono text-xl font-semibold">{value}</div>
    </div>
  );
}

function NodePanel({ details, selectedNodes, criticalLinks, portConnections, onClearNode, onClearAll }) {
  if (!selectedNodes.length) {
    return (
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-400">Network Watch</h2>
        <div className="mt-4 rounded-md border border-white/10 bg-white/[0.03] p-4">
          <div className="text-lg font-semibold text-white">Select a node</div>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Click one or more sites on the SVG topology to inspect ports, lane optics, CRC counts, and optic-reported thresholds together.
          </p>
        </div>
        <div className="mt-5">
          <h3 className="text-sm font-semibold text-slate-200">Critical Links</h3>
          <div className="mt-2 space-y-2">
            {criticalLinks.length ? criticalLinks.map((link) => (
              <div key={link.id} className="rounded-md border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm text-red-100">
                <div className="font-semibold">{link.id}</div>
                <div className="text-xs text-red-100/70">RX {fmtDbm(link.rx_dbm)} · {link.transport}</div>
              </div>
            )) : <div className="text-sm text-slate-500">No critical optics in the latest poll.</div>}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-400">Selected Sites</h2>
            <div className="mt-1 text-xs text-slate-500">{selectedNodes.length} selected</div>
          </div>
          <button className="rounded-md border border-white/10 px-2 py-1 text-xs font-semibold text-slate-300 hover:bg-white/10" onClick={onClearAll}>
            Clear
          </button>
        </div>
      </div>
      {selectedNodes.map((node) => {
        const detail = details[node.id];
        const ports = detail?.ports || node.ports || [];
        return (
          <section key={node.id} className="rounded-md border border-white/10 bg-white/[0.025] p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-lg font-semibold text-white">{node.name}</h3>
                <div className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-400">
                  {node.clli || "cloud"} {node.suffix || ""}
                </div>
              </div>
              <button className={`status-pill ${node.health || "unknown"}`} onClick={() => onClearNode(node.id)} title="Remove from selected sites">
                {node.health || "unknown"}
              </button>
            </div>
            <div className="mt-2 text-sm leading-5 text-slate-400">{node.equipment || node.details}</div>
            <div className="mt-4 space-y-3">
              {ports.map((port) => <PortCard key={`${port.node_id}-${port.port}`} port={port} portConnections={portConnections} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function PortCard({ port, portConnections }) {
  const conn = portConnections?.[`${port.node_id}_${port.port}`];
  return (
    <article className="rounded-md border border-white/10 bg-white/[0.035] p-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-mono text-sm font-semibold text-white">
            Port {port.port}
            {conn && (
              <span className="ml-2 font-normal text-slate-400">
                → p{conn.remotePort} <span className="text-sky-400">{conn.remoteNode}</span>
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-slate-500">{port.spec_compliance || port.port_speed || "optic"}</div>
        </div>
        <span className={`status-pill ${port.health}`}>{port.health}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <Reading label="RX avg" value={fmtDbm(port.rx_dbm)} />
        <Reading label="TX avg" value={fmtDbm(port.tx_dbm)} />
        <Reading label="CRC" value={port.in_crc_errors ?? 0} />
        <Reading label="Out discards" value={port.out_discards ?? 0} />
      </div>
      {port.lanes?.length ? (
        <div className="mt-3 grid grid-cols-4 gap-1">
          {port.lanes.map((lane) => (
            <div key={lane.lane} className="rounded border border-white/10 bg-black/20 p-2 text-center">
              <div className="text-[10px] text-slate-500">L{lane.lane}</div>
              <div className="font-mono text-xs text-slate-100">{fmtDbm(lane.rx_dbm)}</div>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function Reading({ label, value }) {
  return (
    <div className="rounded border border-white/10 bg-black/20 px-2 py-1">
      <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">{label}</div>
      <div className="font-mono text-slate-100">{value}</div>
    </div>
  );
}

// Parse a port string like "p33/p34", "p35 p36", "2p35" into ["33", "34"]
function parsePortList(str) {
  return str
    .split(/[\s/]+/)
    .map((t) => t.trim().replace(/^\d*p/i, ""))
    .filter((t) => /^\d+$/.test(t));
}

function fmtDbm(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} dBm` : "n/a";
}

function formatTime(value) {
  if (!value) return "Waiting for first poll";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function toLocalInputValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

createRoot(document.getElementById("root")).render(<App />);
