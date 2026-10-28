import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, PageTitle, Panel, Status, TierBadge, fmtDate, fmtHours, usePoll } from "../components/ui";

export default function Queue() {
  const { data: waiting, error } = usePoll(() => api.applications("awaiting_review"), 2500);
  const { data: all } = usePoll(() => api.applications(), 5000);
  if (!waiting) return <ErrorNote error={error} />;
  const done = (all ?? []).filter((a) => a.decided_at);

  return (
    <>
      <PageTitle title="Review queue" sub="Medium- and high-risk cases, plus low-risk cases a check escalated. Everything else was decided without you." />
      <Panel title={`Waiting for a decision (${waiting.length})`} className="mb-5">
        {waiting.length === 0 ? <p className="text-sm text-ink-2">The queue is empty.</p> : (
          <ul className="divide-y divide-rule">
            {waiting.map((a) => (
              <li key={a.id}>
                <Link to={`/aicte/cases/${a.id}`} className="flex flex-wrap items-center justify-between gap-3 py-3 hover:text-seal">
                  <div>
                    <p className="text-[15px] font-medium">{a.institution.name}</p>
                    <p className="text-[13px] text-ink-3">{a.institution.city}, case {a.id}, submitted {fmtDate(a.submitted_at)}{a.inspection_date ? `, inspection ${a.inspection_date}` : ""}</p>
                  </div>
                  <div className="flex items-center gap-4"><TierBadge tier={a.tier} score={a.risk_score} /><Status value={a.institution.status} /></div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel title="Decided">
        <table className="w-full text-[14px]">
          <thead className="text-left text-[13px] text-ink-3">
            <tr><th className="pb-2 font-medium">Institution</th><th className="pb-2 font-medium">Risk</th><th className="pb-2 font-medium">Outcome</th><th className="pb-2 font-medium">Decided by</th><th className="pb-2 text-right font-medium">Took</th></tr>
          </thead>
          <tbody>
            {done.map((a) => (
              <tr key={a.id} className="border-t border-rule">
                <td className="py-2.5 pr-3"><Link to={`/aicte/cases/${a.id}`} className="hover:text-seal">{a.institution.name}</Link></td>
                <td className="py-2.5 pr-3"><TierBadge tier={a.tier} /></td>
                <td className="py-2.5 pr-3"><Status value={a.status} /></td>
                <td className="py-2.5 pr-3 text-[13px] text-ink-2">{a.decided_by?.startsWith("auto") ? "Batch ratification" : "Regional officer"}</td>
                <td className="py-2.5 text-right text-[13px]">{fmtHours(a.turnaround_hours)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </>
  );
}
