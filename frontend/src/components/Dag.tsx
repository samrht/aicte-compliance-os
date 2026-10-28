import { Background, Handle, Position, ReactFlow, type Edge, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Check, Circle, Clock, Loader2, Lock, TriangleAlert, X } from "lucide-react";
import type { ReactElement } from "react";
import type { Node as WNode } from "../api";
import { useMedia } from "./ui";

const STATE: Record<string, { ring: string; icon: ReactElement; text: string }> = {
  pending: { ring: "border-rule bg-paper", icon: <Circle size={14} className="text-ink-3" />, text: "Queued" },
  running: { ring: "border-seal bg-seal-soft node-running", icon: <Loader2 size={14} className="animate-spin text-seal" />, text: "Running" },
  passed: { ring: "border-leaf/50 bg-leaf-soft", icon: <Check size={14} className="text-leaf" />, text: "Passed" },
  flagged: { ring: "border-stamp/50 bg-stamp-soft", icon: <TriangleAlert size={14} className="text-stamp" />, text: "Flagged" },
  failed: { ring: "border-stamp bg-stamp-soft", icon: <X size={14} className="text-stamp" />, text: "Rejected" },
  waiting: { ring: "border-saffron bg-saffron-soft", icon: <Clock size={14} className="text-saffron" />, text: "Waiting on regulator" },
  skipped: { ring: "border-rule bg-paper opacity-60", icon: <Circle size={14} />, text: "Skipped" },
};

type Data = { node: WNode };

function StepNode({ data }: NodeProps) {
  const n = (data as Data).node;
  const s = STATE[n.state] ?? STATE.pending;
  return (
    <div className={`w-[200px] rounded-lg border-2 px-3 py-2 ${s.ring}`} title={n.detail}>
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
        {n.key === "lockdown" ? <Lock size={14} className="text-stamp" /> : s.icon}
        <span className="truncate">{n.label}</span>
      </div>
      <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-snug text-ink-2">{n.detail || s.text}</p>
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
    </div>
  );
}

const nodeTypes = { step: StepNode };

export function layout(nodes: WNode[]) {
  const maxSeq = Math.max(0, ...nodes.map((n) => n.seq));
  const wrap = maxSeq > 5 ? 5 : Infinity;              // the sequential high-risk path wraps
  const lanes: Record<number, number> = {};
  nodes.forEach((n) => { lanes[n.seq] = Math.max(lanes[n.seq] ?? 0, n.lane + 1); });
  return nodes.map((n) => {
    const row = Math.floor(n.seq / wrap) || 0;
    const col = wrap === Infinity ? n.seq : n.seq % wrap;
    const span = lanes[n.seq];
    return {
      id: n.key, type: "step", data: { node: n },
      position: { x: col * 240, y: row * 130 + (n.lane - (span - 1) / 2) * 92 },
      draggable: false,
    };
  });
}

/** Phones: the same graph as a vertical list, steps that run in parallel side by side. */
function Steps({ nodes }: { nodes: WNode[] }) {
  const groups = Object.values(nodes.reduce<Record<number, WNode[]>>((acc, n) => {
    (acc[n.seq] ??= []).push(n);
    return acc;
  }, {}));
  return (
    <ol className="relative space-y-2.5 before:absolute before:inset-y-3 before:left-[9px] before:w-px before:bg-rule">
      {groups.map((g) => (
        <li key={g[0].seq} className="relative pl-7">
          <span className="absolute left-[5px] top-3 size-[9px] rounded-full border-2 border-sheet bg-ink-3" />
          {g.length > 1 && <p className="mb-1 text-[12px] text-ink-3">{g.length} checks in parallel</p>}
          <div className={g.length > 1 ? "grid grid-cols-1 gap-2 min-[420px]:grid-cols-2" : ""}>
            {g.map((n) => {
              const s = STATE[n.state] ?? STATE.pending;
              return (
                <div key={n.key} className={`rounded-lg border-2 px-3 py-2 ${s.ring}`}>
                  <div className="flex items-center gap-1.5 text-[13px] font-semibold">
                    {n.key === "lockdown" ? <Lock size={14} className="text-stamp" /> : s.icon}
                    <span>{n.label}</span>
                  </div>
                  <p className="mt-0.5 text-[12px] leading-snug text-ink-2">{n.detail || s.text}</p>
                </div>
              );
            })}
          </div>
        </li>
      ))}
    </ol>
  );
}

export default function Dag({ nodes }: { nodes: WNode[] }) {
  const narrow = useMedia("(max-width: 767px)");
  if (narrow) return <Steps nodes={nodes} />;
  const state = Object.fromEntries(nodes.map((n) => [n.key, n.state]));
  const edges: Edge[] = nodes.flatMap((n) => n.depends_on.map((d) => ({
    id: `${d}-${n.key}`, source: d, target: n.key, animated: state[n.key] === "running",
    style: { stroke: ["passed", "flagged", "failed"].includes(state[d]) ? "#6b7790" : "#cfd5df", strokeWidth: 1.5 },
  })));
  const wide = nodes.some((n) => n.seq > 5);
  return (
    <div className={wide ? "h-[300px]" : "h-[440px]"}>
      <ReactFlow key={nodes.length} nodes={layout(nodes)} edges={edges} nodeTypes={nodeTypes}
        fitView fitViewOptions={{ padding: 0.12, maxZoom: 1 }} maxZoom={1.2} nodesConnectable={false} elementsSelectable={false}
        nodesDraggable={false} panOnDrag={false} panOnScroll={false} zoomOnScroll={false} zoomOnPinch={false}
        zoomOnDoubleClick={false} preventScrolling={false} proOptions={{ hideAttribution: true }}>
        <Background gap={20} size={1} color="#e3e7ee" />
      </ReactFlow>
    </div>
  );
}
