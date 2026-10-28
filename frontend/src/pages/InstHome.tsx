import { FilePlus2 } from "lucide-react";
import { Link } from "react-router-dom";
import { getSession } from "../App";
import { api } from "../api";
import { ErrorNote, PageTitle, Panel, SEVERITY, Status, TierBadge, fmtDate, usePoll } from "../components/ui";

export default function InstHome() {
  const s = getSession() as { id: number };
  const { data: inst, error } = usePoll(() => api.institution(s.id), 3000);
  if (!inst) return <ErrorNote error={error} />;
  const active = inst.applications.find((a) => ["running", "awaiting_review"].includes(a.status));

  return (
    <>
      <PageTitle title={inst.name} sub={`${inst.city}, ${inst.state} · AICTE code ${inst.code} · established ${inst.established}`}
        action={!active && (
          <Link to="/inst/apply" className="inline-flex items-center gap-2 rounded-lg bg-seal px-4 py-2.5 text-[14px] font-medium text-white">
            <FilePlus2 size={17} /> Apply for 2027-28 approval
          </Link>
        )} />
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Applications">
          {inst.applications.length === 0 ? (
            <div className="py-6">
              <p className="text-[15px] font-medium">No applications yet.</p>
              <p className="mt-1 text-[14px] text-ink-2">
                Start one to upload your faculty roster, campus photos and audited statement. Low-risk applications are ratified without waiting for a scrutiny committee.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-rule">
              {inst.applications.map((a) => (
                <li key={a.id}>
                  <Link to={`/inst/cases/${a.id}`} className="flex flex-wrap items-center justify-between gap-3 py-3 hover:text-seal">
                    <div>
                      <p className="text-[15px] font-medium">{a.kind}, {a.academic_year}</p>
                      <p className="text-[13px] text-ink-3">Case {a.id}, submitted {fmtDate(a.submitted_at)}</p>
                    </div>
                    <div className="flex items-center gap-4"><TierBadge tier={a.tier} /><Status value={a.status} /></div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Notifications">
          {inst.alerts.length === 0 ? <p className="text-sm text-ink-2">Nothing needs your attention.</p> : (
            <ul className="space-y-3">
              {inst.alerts.slice(0, 8).map((a) => (
                <li key={a.id} className="flex gap-3">
                  <span className={`mt-1.5 size-2 shrink-0 rounded-full ${SEVERITY[a.severity].bar}`} />
                  <div>
                    <p className="text-[14px] font-medium">{a.title}</p>
                    <p className="text-[13px] text-ink-2">{a.message}</p>
                    <p className="text-[12px] text-ink-3">{fmtDate(a.created_at)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
