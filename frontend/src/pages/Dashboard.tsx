import { RefreshCcw, Radar as RadarIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Button, ErrorNote, PageTitle, Panel, Status, TierBadge, fmtDate, fmtHours, usePoll } from "../components/ui";

function Stat({ value, label, tone = "" }: { value: string | number; label: string; tone?: string }) {
  return (
    <div className="px-5 py-4">
      <p className={`text-[28px] font-semibold leading-none tracking-[-0.02em] ${tone}`}>{value}</p>
      <p className="mt-1.5 text-[13px] text-ink-2">{label}</p>
    </div>
  );
}

const TIER_COLOUR: Record<string, string> = { low: "#1d7f4a", medium: "#d9771a", high: "#c2302b" };

export default function Dashboard() {
  const { data: d, error, refresh } = usePoll(() => api.dashboard(), 2000);
  const [note, setNote] = useState<string | null>(null);
  if (!d) return <ErrorNote error={error} />;

  const turnaround = ["low", "medium", "high"].map((t) => ({ tier: t, hours: d.turnaround_hours[t] ?? 0 }));

  return (
    <>
      <PageTitle title="Overview" sub="Every application is scored on arrival and routed by risk. Humans only see what needs them."
        action={
          <div className="flex gap-2">
            <Button kind="quiet" onClick={async () => { const r = await api.sweep(); setNote(`Compliance sweep finished: ${r.alerts_raised} new alert(s).`); refresh(); }}>
              <RadarIcon size={16} /> Run compliance sweep
            </Button>
            <Button kind="quiet" onClick={async () => { setNote("Resetting demo data…"); await api.reset(); setNote("Demo data reset."); refresh(); }}>
              <RefreshCcw size={16} /> Reset demo
            </Button>
          </div>
        } />
      {note && <p className="mb-4 text-[14px] text-ink-2">{note}</p>}

      <section className="sheet mb-5 grid grid-cols-2 divide-rule sm:grid-cols-3 lg:grid-cols-6 lg:divide-x">
        <Stat value={d.institutions} label="Institutions monitored" />
        <Stat value={d.in_flight} label="Being verified now" tone="text-seal" />
        <Stat value={d.awaiting_review} label="Waiting for a regulator" tone="text-saffron" />
        <Stat value={`${d.auto_ratified_pct}%`} label="Decided with no human step" tone="text-leaf" />
        <Stat value={d.open_alerts} label={`Open alerts, ${d.critical_alerts} critical`} tone={d.critical_alerts ? "text-stamp" : ""} />
        <Stat value={d.lockdowns} label="Institutions in lockdown" tone={d.lockdowns ? "text-stamp" : ""} />
      </section>

      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <Panel title="Latest cases" action={<Link to="/aicte/queue" className="text-[13px] text-seal">Open review queue</Link>}>
          <table className="w-full text-[14px]">
            <thead className="text-left text-[13px] text-ink-3">
              <tr><th className="pb-2 font-medium">Institution</th><th className="pb-2 font-medium">Risk</th><th className="pb-2 font-medium">Status</th><th className="pb-2 text-right font-medium">Submitted</th></tr>
            </thead>
            <tbody>
              {d.recent.map((a: any) => (
                <tr key={a.id} className="border-t border-rule">
                  <td className="py-2.5 pr-3">
                    <Link to={`/aicte/cases/${a.id}`} className="font-medium hover:text-seal">{a.institution.name}</Link>
                    <p className="text-[12px] text-ink-3">{a.institution.city}</p>
                  </td>
                  <td className="py-2.5 pr-3"><TierBadge tier={a.tier} score={a.risk_score} /></td>
                  <td className="py-2.5 pr-3"><Status value={a.status} /></td>
                  <td className="py-2.5 text-right text-[13px] text-ink-2">{fmtDate(a.submitted_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <div className="space-y-5">
          <Panel title="Average time to decision">
            <div className="h-[150px]">
              <ResponsiveContainer>
                <BarChart data={turnaround} layout="vertical" margin={{ left: 0, right: 40 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="tier" width={70} tick={{ fontSize: 13, fill: "#3c4a66" }}
                    tickFormatter={(t) => `${t[0].toUpperCase()}${t.slice(1)} risk`} />
                  <Tooltip formatter={(v: any) => [fmtHours(Number(v)), "Average"]} />
                  <Bar dataKey="hours" radius={3} label={{ position: "right", fontSize: 12, fill: "#3c4a66", formatter: (v: any) => fmtHours(Number(v)) }}>
                    {turnaround.map((t) => <Cell key={t.tier} fill={TIER_COLOUR[t.tier]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="text-[13px] text-ink-2">Low-risk campuses are ratified in batches, inside the 48-hour target.</p>
          </Panel>
          <Panel title="What drives risk" action={d.model.auc && <span className="text-[13px] text-ink-3">Holdout AUC {d.model.auc.toFixed(2)}</span>}>
            <ul className="space-y-2">
              {d.model.importance.map((f: any) => (
                <li key={f.feature} className="text-[13px]">
                  <div className="flex justify-between"><span>{f.label}</span><span className="text-ink-3">{Math.round(f.share * 100)}%</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-paper"><div className="h-full rounded-full bg-seal" style={{ width: `${f.share * 100}%` }} /></div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </>
  );
}
