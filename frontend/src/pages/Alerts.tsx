import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Button, ErrorNote, PageTitle, SEVERITY, fmtDate, usePoll } from "../components/ui";

const FILTERS = [["open", "Open"], ["critical", "Critical"], ["all", "All"]] as const;

export default function Alerts() {
  const { data, error, refresh } = usePoll(() => api.alerts(), 2500);
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("open");
  if (!data) return <ErrorNote error={error} />;
  const shown = data.filter((a) => filter === "all" ? true : filter === "open" ? !a.acknowledged : !a.acknowledged && a.severity === "critical");

  return (
    <>
      <PageTitle title="Alerts" sub="Raised by the workflow, the compliance sweep and the filing calendar. Acknowledging one is logged." />
      <div className="mb-4 flex gap-2">
        {FILTERS.map(([k, label]) => (
          <button key={k} onClick={() => setFilter(k)}
            className={`rounded-full px-3.5 py-1.5 text-[13px] font-medium ${filter === k ? "bg-ink text-white" : "border border-rule bg-sheet text-ink-2"}`}>
            {label}
          </button>
        ))}
      </div>
      <section className="sheet divide-y divide-rule">
        {shown.length === 0 && <p className="p-5 text-sm text-ink-2">No alerts match this filter.</p>}
        {shown.map((a) => {
          const s = SEVERITY[a.severity];
          return (
            <article key={a.id} className={`flex flex-wrap items-start gap-4 p-4 ${a.acknowledged ? "opacity-55" : ""}`}>
              <span className={`mt-0.5 rounded-md px-2 py-0.5 text-[12px] font-medium ${s.fg} ${s.bg}`}>{s.label}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[15px] font-medium">{a.title}</p>
                <p className="text-[13px] text-ink-2">{a.message}</p>
                <p className="mt-1 text-[12px] text-ink-3">
                  {fmtDate(a.created_at)}{a.institution ? `, ${a.institution}` : ""}
                  {a.application_id && <> , <Link to={`/aicte/cases/${a.application_id}`} className="text-seal">case {a.application_id}</Link></>}
                </p>
              </div>
              {!a.acknowledged && <Button kind="quiet" onClick={async () => { await api.ack(a.id); refresh(); }}>Acknowledge</Button>}
            </article>
          );
        })}
      </section>
    </>
  );
}
