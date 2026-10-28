import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Application } from "../api";
import Dag from "./Dag";
import { Hash, Panel, SEVERITY, Status, TierBadge, fmtDate, fmtHours, useMedia } from "./ui";

const STAMPS: Record<string, [string, string]> = {
  ratified: ["Ratified", "text-leaf"],
  approved: ["Approved", "text-leaf"],
  rejected: ["Rejected", "text-stamp"],
};

export function Verdict({ app }: { app: Application }) {
  const lockdown = app.institution.status === "lockdown" && app.status === "awaiting_review";
  const s = STAMPS[app.status] ?? (lockdown ? ["Lockdown", "text-stamp"] : null);
  if (!s) return null;
  return <span key={s[0]} className={`stamp uppercase ${s[1]}`}>{s[0]}</span>;
}

export function CaseHeader({ app }: { app: Application }) {
  return (
    <div className="sheet relative flex flex-wrap items-start justify-between gap-6 overflow-hidden p-6">
      <div className="min-w-0">
        <p className="text-sm text-ink-3">Case {app.id} · {app.kind} · {app.academic_year}</p>
        <h1 className="mt-1 text-[26px] font-semibold leading-tight tracking-[-0.01em]">{app.institution.name}</h1>
        <p className="mt-1 text-ink-2">{app.institution.city}, {app.institution.state} · {app.institution.code}</p>
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <TierBadge tier={app.tier} score={app.risk_score} />
          <span>Status: <Status value={app.status} /></span>
          <span className="text-ink-2">Submitted {fmtDate(app.submitted_at)}</span>
          {app.decided_at && <span className="text-ink-2">Decided in {fmtHours(app.turnaround_hours)}</span>}
          {app.inspection_date && <span className="text-saffron">Inspection on {app.inspection_date}</span>}
        </div>
      </div>
      <div className="pr-4 pt-2"><Verdict app={app} /></div>
    </div>
  );
}

export function Findings({ app }: { app: Application }) {
  const findings = app.findings ?? [];
  return (
    <Panel title={`Findings (${findings.length})`}>
      {findings.length === 0 ? (
        <p className="text-sm text-ink-2">
          {app.status === "running" ? "Checks are still running." : "Every check came back clean."}
        </p>
      ) : (
        <ul className="space-y-3">
          {findings.map((f) => {
            const s = SEVERITY[f.severity];
            return (
              <li key={f.id} className="flex gap-3">
                <span className={`mt-1 w-1 shrink-0 self-stretch rounded-full ${s.bar}`} />
                <div className="min-w-0">
                  <p className="text-[14px] font-semibold">
                    {f.title} <span className={`ml-1 text-xs font-medium ${s.fg}`}>{s.label}</span>
                  </p>
                  <p className="text-[13px] text-ink-2">{f.message}</p>
                  {Array.isArray((f.evidence as any).tokens) && (
                    <p className="mt-1 flex flex-wrap gap-2">
                      {((f.evidence as any).tokens as string[]).map((t) => <Hash key={t} value={t} n={12} />)}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

export function RiskExplain({ app }: { app: Application }) {
  const narrow = useMedia("(max-width: 639px)");
  const rows = (app.contributions ?? []).slice(0, 7).map((c) => ({ ...c, name: c.label }));
  if (!rows.length) return <Panel title="Why this risk score"><p className="text-sm text-ink-2">Scoring after ingestion.</p></Panel>;
  return (
    <Panel title="Why this risk score">
      <p className="mb-3 text-[13px] text-ink-2">
        Exact TreeSHAP contributions from the LightGBM model. Bars to the right raise the failure risk; bars to the left lower it.
      </p>
      <div className="h-[250px]">
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
            <XAxis type="number" tick={{ fontSize: 11, fill: "#6b7790" }} />
            <YAxis type="category" dataKey="name" width={narrow ? 118 : 190} tick={{ fontSize: narrow ? 10.5 : 12, fill: "#3c4a66" }} />
            <ReferenceLine x={0} stroke="#9aa3b5" />
            <Tooltip formatter={(v: any, _n: any, p: any) => [`${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(2)} log-odds (value ${p.payload.value})`, "Impact"]} />
            <Bar dataKey="impact" radius={3}>
              {rows.map((r) => <Cell key={r.feature} fill={r.impact > 0 ? "#c2302b" : "#1d7f4a"} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export function Norms({ app }: { app: Application }) {
  const norms: any[] = app.signals?.norms ?? [];
  const plan: any[] = app.signals?.plan ?? [];
  if (!norms.length) return null;
  return (
    <Panel title="Norms check">
      <table className="w-full text-[13px]">
        <thead className="text-left text-ink-3">
          <tr><th className="pb-2 pr-3 font-medium">Rule</th><th className="pb-2 pr-3 font-medium">Measured</th><th className="pb-2 pr-3 font-medium">Required</th><th /></tr>
        </thead>
        <tbody>
          {norms.map((r) => (
            <tr key={r.id} className="border-t border-rule">
              <td className="py-2 pr-3">{r.title}</td>
              <td className="py-2 pr-3">{r.measured ?? "–"}</td>
              <td className="py-2 pr-3 text-ink-2">{r.op === "<=" ? "≤" : "≥"} {r.value} {r.unit}</td>
              <td className={`py-2 text-right font-medium ${r.passed === false ? (r.severity === "critical" ? "text-stamp" : "text-saffron") : "text-leaf"}`}>
                {r.passed === false ? "Fails" : r.passed ? "Meets" : "No data"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {plan.length > 0 && (
        <div className="mt-5 rounded-lg bg-paper p-4">
          <p className="mb-2 text-[14px] font-semibold">Cheapest path to compliance</p>
          <ul className="space-y-1.5 text-[13px]">
            {plan.map((p) => (
              <li key={p.rule} className="flex justify-between gap-4">
                <span>{p.best.action}</span>
                <span className="shrink-0 text-ink-2">₹{p.best.cost_lakh.toLocaleString("en-IN")} lakh</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

export function Evidence({ app }: { app: Application }) {
  const s = app.signals ?? {};
  const photos: any[] = s.photos ?? [];
  const doc = s.doc ?? {};
  return (
    <Panel title="Evidence extracted">
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <p className="mb-2 text-[13px] font-semibold">Campus photos</p>
          <ul className="space-y-1.5 text-[13px]">
            {photos.map((p) => (
              <li key={p.file} className="flex justify-between gap-3">
                <span className="truncate">{p.file}</span>
                <span className={p.distance_km == null ? "text-saffron" : p.distance_km > 1 ? "text-stamp" : "text-leaf"}>
                  {p.distance_km == null ? "no GPS" : `${p.distance_km} km from campus`}
                </span>
              </li>
            ))}
          </ul>
          {photos[0] && <p className="mt-2 text-xs text-ink-3">pHash <Hash value={photos[0].phash} /></p>}
        </div>
        <div>
          <p className="mb-2 text-[13px] font-semibold">Financial statement (DocAI)</p>
          <ul className="space-y-1.5 text-[13px]">
            {Object.entries(doc.fields ?? {}).map(([k, v]) => (
              <li key={k} className="flex justify-between gap-3">
                <span className="text-ink-2">{k.replace("_lakh", "").replace("_pct", " %").replace("_", " ")}</span>
                <span>{k.endsWith("_pct") ? `${v}%` : `₹${Number(v).toLocaleString("en-IN")} L`}</span>
              </li>
            ))}
          </ul>
          {doc.confidence != null && <p className="mt-2 text-xs text-ink-3">Extraction confidence {Math.round(doc.confidence * 100)}%</p>}
        </div>
      </div>
    </Panel>
  );
}

export default function CaseFile({ app, side }: { app: Application; side?: React.ReactNode }) {
  return (
    <div className="space-y-5">
      <CaseHeader app={app} />
      <Panel title="Workflow" action={<span className="text-[13px] text-ink-3">Every transition is written to the Merkle audit log</span>}>
        <Dag nodes={app.nodes ?? []} />
      </Panel>
      <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
        <div className="space-y-5">
          {side}
          <Findings app={app} />
          <Evidence app={app} />
        </div>
        <div className="space-y-5">
          <RiskExplain app={app} />
          <Norms app={app} />
        </div>
      </div>
    </div>
  );
}
