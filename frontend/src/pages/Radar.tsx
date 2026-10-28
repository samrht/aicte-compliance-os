import { Background, Handle, Position, ReactFlow, type Edge, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "../api";
import { ErrorNote, Hash, PageTitle, Panel, Status, usePoll } from "../components/ui";

function InstNode({ data }: NodeProps) {
  const d = data as any;
  const bad = ["lockdown", "rejected"].includes(d.status);
  return (
    <div className={`w-[190px] rounded-lg border-2 bg-sheet px-3 py-2 ${bad ? "border-stamp" : "border-saffron"}`}>
      <Handle type="target" position={Position.Top} className="!opacity-0" style={{ top: "50%" }} />
      <p className="text-[13px] font-semibold leading-snug">{d.name}</p>
      <p className="text-[12px] text-ink-3">{d.city}, {d.shared} shared</p>
      <Status value={d.status} />
      <Handle type="source" position={Position.Bottom} className="!opacity-0" style={{ top: "50%" }} />
    </div>
  );
}
const nodeTypes = { inst: InstNode };

export default function Radar() {
  const { data, error } = usePoll(() => api.collisions(), 4000);
  if (!data) return <ErrorNote error={error} />;
  const n = data.nodes.length;
  const R = 70 + n * 45;
  const nodes = data.nodes.map((x: any, i: number) => ({
    id: String(x.id), type: "inst", data: x, draggable: true,
    position: { x: R * Math.cos((2 * Math.PI * i) / n - Math.PI / 2), y: R * Math.sin((2 * Math.PI * i) / n - Math.PI / 2) },
  }));
  const edges: Edge[] = data.edges.map((e: any) => ({
    id: `${e.source}-${e.target}`, source: String(e.source), target: String(e.target),
    label: `${e.count} faculty`, type: "straight",
    style: { stroke: "#c2302b", strokeWidth: 1 + e.count * 0.6 },
    labelStyle: { fontSize: 12, fill: "#c2302b", fontWeight: 600 },
    labelBgStyle: { fill: "#fff" },
  }));

  return (
    <>
      <PageTitle title="Faculty collision radar"
        sub={`${data.total_tokens.toLocaleString("en-IN")} faculty identities on file as blinded tokens. ${data.shared_tokens} appear at more than one institution.`} />
      <div className="grid gap-5 xl:grid-cols-[1.7fr_1fr]">
        <Panel title="Institutions sharing faculty">
          {n === 0 ? <p className="text-sm text-ink-2">No faculty appears at two institutions.</p> : (
            <div className="h-[400px] sm:h-[520px]">
              <ReactFlow key={n} nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
                nodesConnectable={false} zoomOnScroll={false} preventScrolling={false} proOptions={{ hideAttribution: true }}>
                <Background gap={22} size={1} color="#e3e7ee" />
              </ReactFlow>
            </div>
          )}
        </Panel>
        <div className="space-y-5">
          <Panel title="How a match is found without seeing anyone">
            <ol className="list-decimal space-y-2 pl-5 text-[13.5px] text-ink-2">
              <li>The roster is read on arrival. PAN and date of birth are normalised, so spacing and date formats don't matter.</li>
              <li>Each identity becomes HMAC-SHA256 under a key held in the KMS. Without the key, a token can't be reversed or guessed from a PAN list.</li>
              <li>Names and PANs are discarded. Only tokens, designation and qualification are stored.</li>
              <li>The same person at two colleges gives the same token, which raises a ghost-faculty alert.</li>
            </ol>
          </Panel>
          <Panel title="Shared tokens">
            <ul className="space-y-2.5">
              {data.sample.map((s: any) => (
                <li key={s.token} className="text-[13px]">
                  <Hash value={s.token} n={40} />
                  <p className="text-ink-2">{s.institutions.join(" and ")}</p>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </>
  );
}
