import { Cloud } from "lucide-react";

const LINK_COLORS = {
  black: "#d4d4d8",
  "black-double": "#f8fafc",
  brown: "#b87333",
  orange: "#f7941d",
  blue: "#38bdf8",
  red: "#fb7185",
  "green-dashed": "#22c55e",
};

const HEALTH = {
  healthy: "#34d399",
  warning: "#fbbf24",
  critical: "#fb7185",
  unknown: "#64748b",
};

const CANVAS = { width: 1740, height: 1360 };
const NODE = { width: 150, height: 104 };
const SMALL_NODE = { width: 124, height: 86 };

const ROUTES = {
  "INTERNET-CORE_LA2": [[120, 150], [380, 150], [380, 110], [406, 110]],
  "CORE_LA2-JNPR_LA": [[406, 132], [360, 132], [360, 280], [349, 280]],
  "CORE_LA2-SCR": [[470, 158], [470, 237]],
  "SCR-SDG01": [[534, 270], [805, 270], [805, 325], [826, 325]],
  "SCR-SCL": [[470, 333], [470, 437]],
  "SDG01-JNPR_SDG": [[954, 325], [1036, 325]],
  "SCL-SDG01": [[534, 470], [780, 470], [780, 325], [826, 325]],
  "SCL-LKS": [[534, 505], [1120, 505], [1120, 512]],
  "SCL-LND": [[534, 536], [940, 536], [940, 732], [990, 732]],
  "SCL-MTS": [[438, 533], [438, 650], [365, 650], [365, 707]],
  "SCL-FOMC": [[502, 533], [745, 533], [745, 900], [714, 900]],
  "MTS-FOMC": [[365, 803], [365, 850], [586, 850]],
  "FOMC-LND": [[714, 900], [990, 900], [990, 828]],
  "FOMC-GST": [[650, 948], [650, 1035], [735, 1035]],
  "LND-LKS": [[1032, 732], [1120, 650], [1120, 608]],
  "LND-BNA": [[1054, 780], [1168, 780], [1168, 900], [1216, 900]],
  "GST-TNP": [[799, 1085], [876, 1085]],
  "GST-IMC": [[710, 1133], [710, 1195], [610, 1195]],
  "TNP-PLD": [[984, 1085], [1071, 1085]],
  "PLD-BNA": [[1125, 1037], [1125, 980], [1280, 980], [1280, 948]],
  "BNA-SRA": [[1344, 900], [1370, 900], [1370, 1037]],
  "SRA-HUT": [[1424, 1085], [1546, 1085]],
  "IMC-MAX": [[674, 1245], [870, 1245], [870, 1188], [1096, 1188], [1096, 1245]],
};

export function TopologyMap({ topology, nodes, links, selectedIds, onSelectNode }) {
  if (!topology) {
    return <div className="grid min-h-[620px] place-items-center rounded-md border border-white/10 bg-white/[0.03] text-slate-400">Loading topology...</div>;
  }
  const nodeMap = new Map((nodes.length ? nodes : topology.nodes).map((node) => [node.id, node]));
  const selected = new Set(selectedIds);
  const viewBox = `0 0 ${CANVAS.width} ${CANVAS.height}`;

  return (
    <div className="topology-shell">
      <svg viewBox={viewBox} role="img" aria-label={topology.meta.title} preserveAspectRatio="xMidYMid meet" className="h-full w-full">
        <defs>
          {Object.entries(HEALTH).map(([key, color]) => (
            <filter key={key} id={`glow-${key}`} x="-60%" y="-60%" width="220%" height="220%">
              <feDropShadow dx="0" dy="0" stdDeviation={key === "unknown" ? "1.5" : "4"} floodColor={color} floodOpacity="0.75" />
            </filter>
          ))}
          <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect x="0" y="0" width={CANVAS.width} height={CANVAS.height} fill="#0a1218" />
        <rect x="0" y="0" width={CANVAS.width} height={CANVAS.height} fill="url(#grid)" />
        <rect x="22" y="22" width={CANVAS.width - 44} height={CANVAS.height - 44} fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth="2" />
        <MapTitle topology={topology} />
        <text x="70" y="1288" fill="#64748b" fontSize="18">{topology.meta.version}</text>

        <g className="links">
          {links.map((link) => {
            const from = nodeMap.get(link.from);
            const to = nodeMap.get(link.to);
            if (!from || !to) return null;
            return <LinkPath key={link.id} link={link} from={from} to={to} />;
          })}
        </g>

        <g className="nodes">
          {(nodes.length ? nodes : topology.nodes).map((node) => (
            <Node
              key={node.id}
              node={node}
              selected={selected.has(node.id)}
              onSelect={() => onSelectNode(node)}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}

function LinkPath({ link, from, to }) {
  const color = LINK_COLORS[link.color] || "#cbd5e1";
  const health = link.health || "unknown";
  const double = link.color === "black-double";
  const dashed = link.color === "green-dashed";
  const points = ROUTES[link.id] || [[from.x, from.y], [to.x, to.y]];
  const path = pointsToPath(points);
  return (
    <g className="topology-link">
      <path d={path} fill="none" stroke={HEALTH[health]} strokeWidth={double ? 16 : 13} opacity="0.3" filter={`url(#glow-${health})`} strokeLinecap="round" strokeLinejoin="round" />
      {double ? (
        <>
          <path d={path} fill="none" stroke={color} strokeWidth="5" strokeDasharray={dashed ? "16 10" : ""} transform="translate(0,-6)" strokeLinecap="round" strokeLinejoin="round" />
          <path d={path} fill="none" stroke={color} strokeWidth="5" strokeDasharray={dashed ? "16 10" : ""} transform="translate(0,6)" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ) : (
        <path d={path} fill="none" stroke={color} strokeWidth={link.type === "zr" ? "6" : "7"} strokeDasharray={dashed ? "18 12" : ""} strokeLinecap="round" strokeLinejoin="round" />
      )}
      <title>{`${link.id}\n${link.transport || link.speed}\nRX ${fmt(link.rx_dbm)}\n${health}`}</title>
    </g>
  );
}

function pointsToPath(points) {
  return points.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x} ${y}`).join(" ");
}

function Node({ node, selected, onSelect }) {
  if (node.type === "cloud") {
    return (
      <g transform={`translate(${node.x},${node.y})`} className="cursor-pointer" onClick={onSelect}>
        <foreignObject x="-90" y="-105" width="180" height="210">
          <div className="grid h-full place-items-center rounded-md border border-sky-300/30 bg-sky-300/10 text-sky-100">
            <Cloud size={92} strokeWidth={1.25} />
          </div>
        </foreignObject>
        <text x="0" y="-15" textAnchor="middle" fill="#cbd5e1" fontSize="16" fontWeight="700">Hurricane</text>
        <text x="0" y="8" textAnchor="middle" fill="#cbd5e1" fontSize="16" fontWeight="700">Lumen / Zayo</text>
        <text x="0" y="50" textAnchor="middle" fill="#cbd5e1" fontSize="18" fontWeight="800">Internet</text>
      </g>
    );
  }
  const small = node.id.includes("JNPR") || node.id === "BSTST";
  const width = small ? SMALL_NODE.width : NODE.width;
  const height = small ? SMALL_NODE.height : NODE.height;
  const health = node.health || "unknown";
  const nameParts = splitName(node.name, node.id);
  return (
    <g transform={`translate(${node.x - width / 2},${node.y - height / 2})`} className="cursor-pointer" onClick={onSelect}>
      <rect
        width={width}
        height={height}
        rx="7"
        fill={selected ? "#1f2a32" : "#111b23"}
        stroke={selected ? "#F7941D" : HEALTH[health]}
        strokeWidth={selected ? "2.5" : "1.6"}
        filter={`url(#glow-${health})`}
      />
      <rect x="0" y="0" width="6" height={height} rx="3" fill={HEALTH[health]} opacity="0.95" />
      <text x={width - 9} y="16" textAnchor="end" fill="#d1d5db" fontSize={small ? "10" : "12"} fontWeight="800">{node.suffix || ""}</text>
      {nameParts.map((part, index) => (
        <text key={part} x="16" y={small ? 30 + index * 18 : 34 + index * 23} fill="#f8fafc" fontSize={small ? "17" : "21"} fontWeight="900">{part}</text>
      ))}
      <text x="16" y={height - 27} fill="#94a3b8" fontSize={small ? "11" : "13"}>{node.clli || node.tier || ""}</text>
      <text x="16" y={height - 10} fill="#f7941d" fontSize={small ? "11" : "13"} fontWeight="700">{node.id === "FOMC" ? ".202-.203" : node.suffix || ""}</text>
      <title>{`${node.name}\n${node.equipment || node.details || ""}`}</title>
    </g>
  );
}

function splitName(name, id) {
  const map = {
    CORE_LA2: ["CoreSite", "LA2"],
    JNPR_LA: ["JNPR", "MX304"],
    SCR: ["Scranton", "LightEdge"],
    SDG01: ["SDG01", "EdgeConneX"],
    JNPR_SDG: ["JNPR", "MX304"],
    SCL: ["Scale", "KearnyVilla"],
    MTS: ["MTS", "12-S-13th"],
    FOMC: ["4MC", "MileOfCars"],
    GST: ["GST", "G-Street"],
    TNP: ["3NP", "Naples"],
    PLD: ["PLD", "P.Ladera"],
    BNA: ["BNA", "Bonita"],
    SRA: ["SRA", "SantaRosa"],
    HUT: ["HUT", "Hunte"],
    IMC: ["IMC", "Imperial"],
    MAX: ["MAX", "Maxwell"],
  };
  return map[id] || [name];
}

function MapTitle({ topology }) {
  return (
    <g>
      <text x="1415" y="140" textAnchor="middle" fill="#f8fafc" fontSize="58" fontWeight="900">
        Wyyerd
      </text>
      <text x="1415" y="212" textAnchor="middle" fill="#f8fafc" fontSize="46" fontWeight="900">
        Pacific IP Backbone
      </text>
      <text x="1415" y="260" textAnchor="middle" fill="#cbd5e1" fontSize="26">
        Ciena Router view
      </text>
      <text x="1415" y="340" textAnchor="middle" fill="#94a3b8" fontSize="28" fontStyle="italic">
        Feb 2026
      </text>
      <text x="1415" y="382" textAnchor="middle" fill="#94a3b8" fontSize="28" fontStyle="italic">
        CoreSite LA2 addition (2)
      </text>
      <g transform="translate(1370 470)">
        <line x1="0" y1="0" x2="60" y2="0" stroke="#d4d4d8" strokeWidth="7" strokeLinecap="round" />
        <text x="82" y="9" fill="#e2e8f0" fontSize="24">100G</text>
        <line x1="0" y1="48" x2="60" y2="48" stroke="#b87333" strokeWidth="12" strokeLinecap="round" />
        <text x="82" y="57" fill="#e2e8f0" fontSize="24">200G</text>
        <line x1="0" y1="95" x2="60" y2="95" stroke="#f8fafc" strokeWidth="5" strokeLinecap="round" transform="translate(0,-5)" />
        <line x1="0" y1="95" x2="60" y2="95" stroke="#f8fafc" strokeWidth="5" strokeLinecap="round" transform="translate(0,5)" />
        <text x="82" y="104" fill="#e2e8f0" fontSize="24">2x100G LAG</text>
      </g>
      <text x="1415" y="630" textAnchor="middle" fill="#cbd5e1" fontSize="18">
        Core-prefix {topology.meta.core_prefix}
      </text>
      <text x="1415" y="662" textAnchor="middle" fill="#cbd5e1" fontSize="18">
        Mgmt-prefix {topology.meta.mgmt_prefix}
      </text>
    </g>
  );
}

function fmt(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} dBm` : "n/a";
}
