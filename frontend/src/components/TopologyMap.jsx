import { Cloud } from "lucide-react";

const LINK_COLORS = {
  black: "#d4d4d8",
  "black-double": "#f8fafc",
  "black-triple": "#f8fafc",
  brown: "#b87333",
  orange: "#f7941d",
  blue: "#38bdf8",
  "blue-double": "#38bdf8",
  red: "#fb7185",
  green: "#22c55e",
  "green-dashed": "#22c55e",
  purple: "#c084fc",
  "purple-double": "#c084fc",
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
  "HE_INTERNET-CORE_LA2": [[210, 110], [395, 110]],
  "ZAYO_INTERNET-JNPR_SNDACAWA": [[160, 485], [210, 485]],
  "JNPR_SNDGCAJW-SCR": [[302, 285], [395, 285]],
  "JNPR_SNDACAWA-SCL": [[302, 485], [395, 485]],
  "CORE_LA2-SCR": [[470, 162], [470, 233]],
  "SCR-SDG01": [[545, 285], [810, 285]],
  "SCR-SCL": [[470, 337], [470, 433]],
  "SCR-GST": [[505, 310], [735, 310], [735, 990]],
  "SCL-SDG01": [[545, 450], [760, 450], [760, 325], [815, 325]],
  "SCL-LKS": [[545, 485], [1045, 485]],
  "SCL-LND": [[545, 525], [885, 525], [885, 700], [915, 700]],
  "SCL-4MC": [[470, 537], [470, 810], [540, 810]],
  "SDG01-JNPR_SDG": [[965, 275], [1028, 275]],
  "LKS-LND": [[1120, 562], [1120, 700], [1065, 700]],
  "LND-4MC": [[990, 752], [990, 840], [700, 840]],
  "GST-4MC": [[715, 998], [715, 880], [600, 880]],
  "4MC-IMC": [[575, 840], [500, 840], [500, 1220], [535, 1220]],
  "GST-3NP": [[810, 1050], [855, 1050]],
  "3NP-PLD": [[1005, 1050], [1050, 1050]],
  "PLD-BNA": [[1125, 998], [1125, 840], [1160, 840]],
  "BNA-SRA": [[1325, 840], [1370, 840], [1370, 998]],
  "SRA-HUT": [[1445, 1050], [1525, 1050]],
  "IMC-MAX": [[685, 1220], [1085, 1220]],
  "MAX-HUT": [[1235, 1220], [1600, 1220], [1600, 1100]],
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
  const baseColor = LINK_COLORS[link.color] || "#cbd5e1";
  const health = link.health || "unknown";
  // Override the foreground color to be yellow/red if the link is degraded
  const color = (health === "warning" || health === "critical") ? HEALTH[health] : baseColor;
  const triple = link.color === "black-triple";
  const double = link.color && link.color.endsWith("-double");
  const dashed = link.color === "green-dashed";
  const points = ROUTES[link.id] || [[from.x, from.y], [to.x, to.y]];
  const path = pointsToPath(points);
  return (
    <g className="topology-link">
      <path d={path} fill="none" stroke={HEALTH[health]} strokeWidth={triple ? 20 : double ? 16 : 13} opacity="0.3" filter={`url(#glow-${health})`} strokeLinecap="round" strokeLinejoin="round" />
      {triple ? (
        <>
          <path d={pointsToPath(getOffsetPoints(points, -7))} fill="none" stroke={color} strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d={path} fill="none" stroke={color} strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d={pointsToPath(getOffsetPoints(points, 7))} fill="none" stroke={color} strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ) : double ? (
        <>
          <path d={pointsToPath(getOffsetPoints(points, -6))} fill="none" stroke={color} strokeWidth="5.2" strokeLinecap="round" strokeLinejoin="round" />
          <path d={pointsToPath(getOffsetPoints(points, 6))} fill="none" stroke={color} strokeWidth="5.2" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ) : (
        <path d={path} fill="none" stroke={color} strokeWidth={link.type === "zr" ? "6.2" : "7.2"} strokeDasharray={dashed ? "18 12" : ""} strokeLinecap="round" strokeLinejoin="round" />
      )}
      <title>{`${link.id}\n${link.transport || link.speed}\nRX ${fmt(link.rx_dbm)}\n${health}`}</title>
    </g>
  );
}

function getOffsetPoints(points, offset) {
  if (points.length < 2) return points;
  const newPoints = [];

  for (let i = 0; i < points.length; i++) {
    const curr = points[i];

    // Determine direction of incoming segment (prev -> curr)
    let prevDir = null; // 'H' or 'V' or null
    if (i > 0) {
      const prev = points[i - 1];
      if (Math.abs(curr[0] - prev[0]) > Math.abs(curr[1] - prev[1])) {
        prevDir = 'H';
      } else {
        prevDir = 'V';
      }
    }

    // Determine direction of outgoing segment (curr -> next)
    let nextDir = null; // 'H' or 'V' or null
    if (i < points.length - 1) {
      const next = points[i + 1];
      if (Math.abs(next[0] - curr[0]) > Math.abs(next[1] - curr[1])) {
        nextDir = 'H';
      } else {
        nextDir = 'V';
      }
    }

    let dx = 0;
    let dy = 0;

    if (prevDir === 'H' && nextDir === 'V') {
      const prev = points[i - 1];
      const next = points[i + 1];
      const s1_sign_y = (curr[0] > prev[0]) ? 1 : -1;
      const s2_sign_x = (next[1] > curr[1]) ? -1 : 1;
      dx = s2_sign_x * offset;
      dy = s1_sign_y * offset;
    } else if (prevDir === 'V' && nextDir === 'H') {
      const prev = points[i - 1];
      const next = points[i + 1];
      const s1_sign_x = (curr[1] > prev[1]) ? -1 : 1;
      const s2_sign_y = (next[0] > curr[0]) ? 1 : -1;
      dx = s1_sign_x * offset;
      dy = s2_sign_y * offset;
    } else if (nextDir) {
      const next = points[i + 1];
      if (nextDir === 'H') {
        dy = (next[0] > curr[0]) ? offset : -offset;
      } else {
        dx = (next[1] > curr[1]) ? -offset : offset;
      }
    } else if (prevDir) {
      const prev = points[i - 1];
      if (prevDir === 'H') {
        dy = (curr[0] > prev[0]) ? offset : -offset;
      } else {
        dx = (curr[1] > prev[1]) ? -offset : offset;
      }
    }

    newPoints.push([curr[0] + dx, curr[1] + dy]);
  }
  return newPoints;
}

function pointsToPath(points) {
  return points.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x} ${y}`).join(" ");
}

function Node({ node, selected, onSelect }) {
  if (node.type === "cloud") {
    const isHE = node.id === "HE_INTERNET";
    return (
      <g transform={`translate(${node.x},${node.y})`} className="cursor-pointer" onClick={onSelect}>
        <foreignObject x="-90" y="-105" width="180" height="180">
          <div className="grid h-full place-items-center rounded-md border border-sky-300/30 bg-sky-300/10 text-sky-100">
          </div>
        </foreignObject>
        {isHE ? (
          <>
            <text x="0" y="-25" textAnchor="middle" fill="#cbd5e1" fontSize="14" fontWeight="700">Hurricane</text>
            <text x="0" y="-5" textAnchor="middle" fill="#cbd5e1" fontSize="14" fontWeight="700">Electric</text>
            <text x="0" y="15" textAnchor="middle" fill="#94a3b8" fontSize="12" fontWeight="500">[AS 6939]</text>
          </>
        ) : (
          <>
            <text x="0" y="-15" textAnchor="middle" fill="#cbd5e1" fontSize="16" fontWeight="700">Zayo</text>
            <text x="0" y="10" textAnchor="middle" fill="#94a3b8" fontSize="13" fontWeight="500">[AS 6461]</text>
          </>
        )}
      </g>
    );
  }
  const small = node.id.startsWith("JNPR") || node.id === "BSTST";
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
      {small && node.suffix && (
        <text x={width - 9} y="16" textAnchor="end" fill="#d1d5db" fontSize="10" fontWeight="800">{node.suffix}</text>
      )}
      {nameParts.map((part, index) => (
        <text key={part} x="16" y={small ? 30 + index * 18 : 34 + index * 23} fill="#f8fafc" fontSize={small ? "17" : "21"} fontWeight="900">{part}</text>
      ))}
      <text x="16" y={!small && node.suffix ? height - 27 : height - 16} fill="#94a3b8" fontSize={small ? "11" : "13"}>{node.clli || ""}</text>
      {!small && node.suffix && (
        <text x="16" y={height - 10} fill="#94a3b8" fontSize="13" fontWeight="500">{node.suffix}</text>
      )}
      <title>{`${node.name}\n${node.equipment || node.details || ""}`}</title>
    </g>
  );
}

function splitName(name, id) {
  const map = {
    CORE_LA2: ["CoreSite", "LA2"],
    JNPR_SNDGCAJW: ["JNPR", "MX304"],
    JNPR_SNDACAWA: ["JNPR", "MX304"],
    SCR: ["Scranton", "LightEdge"],
    SDG01: ["SDG01", "EdgeConneX"],
    JNPR_SDG: ["JNPR", "MX304"],
    SCL: ["Scale", "KearnyVilla"],
    LKS: ["LKS", "Lakeside"],
    LND: ["LND", "El Cajon"],
    "4MC": ["4MC", "MileOfCars"],
    GST: ["GST", "G-Street"],
    "3NP": ["3NP", "Naples"],
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
        California
      </text>
      <text x="1415" y="212" textAnchor="middle" fill="#f8fafc" fontSize="46" fontWeight="900">
        Node Topology
      </text>
      <text x="1415" y="260" textAnchor="middle" fill="#cbd5e1" fontSize="26">
        something else here
      </text>
    </g>
  );
}

function fmt(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} dBm` : "n/a";
}
