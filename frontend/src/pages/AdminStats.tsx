import { CheckCircle2, CircleAlert, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AdminAuthError, admin } from "../api";
import { Button, Hash, PageTitle, Panel, fmtHours } from "../components/ui";

function Tile({ value, label, tone = "", to }: { value: string | number; label: string; tone?: string; to?: string }) {
  const body = (
    <>
      <p className={`text-[26px] font-semibold leading-none tracking-[-0.02em] sm:text-[28px] ${tone}`}>{value}</p>
      <p className="mt-1.5 text-[13px] text-ink-2">{label}</p>
    </>
  );
  return to ? <Link to={to} className="block px-4 py-4 hover:bg-paper sm:px-5">{body}</Link>
    : <div className="px-4 py-4 sm:px-5">{body}</div>;
}

const KIND = { photo: "Campus photos", roster: "Faculty rosters", financials: "Financial statements" } as const;

function clock(iso: string) {
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function AdminStats() {
  const nav = useNavigate();
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [reset, setReset] = useState<"idle" | "confirm" | "running">("idle");
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try { const s = await admin.stats(); if (live) { setD(s); setError(null); } }
      catch (e) {
        if (e instanceof AdminAuthError) nav("/admin/login");
        else if (live) setError(e instanceof Error ? e.message : String(e));
      }
    };
    load();
    const t = setInterval(load, 3000);
    return () => { live = false; clearInterval(t); };
  }, [nav]);

  async function onReset() {
    if (reset === "idle") {
      setReset("confirm");
      setTimeout(() => setReset((r) => (r === "confirm" ? "idle" : r)), 4000);
      return;
    }
    if (reset !== "confirm") return;
    setReset("running");
    setNote("Resetting the demo data. This takes about 20 seconds.");
    try { await admin.reset(); setNote("Demo data reset."); }
    catch (e) { setNote(`Reset didn't run: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setReset("idle"); }
  }

  if (!d) return error
    ? <p className="rounded-lg bg-stamp-soft px-4 py-3 text-sm text-stamp">Live stats are unavailable ({error}).</p>
    : <p className="text-sm text-ink-2">Loading live stats…</p>;

  const docs = d.documents, apps = d.applications, sys = d.system;
  const max = Math.max(1, ...apps.per_day.map((x: any) => x.count));

  return (
    <>
      <PageTitle title="Live stats"
        sub={<span className="inline-flex items-center gap-2"><span className="size-2 animate-pulse rounded-full bg-leaf" />
          Updated {clock(d.generated_at)}, refreshes every 3 seconds</span>}
        action={
          <Button kind={reset === "confirm" ? "danger" : "quiet"} disabled={reset === "running"} onClick={onReset}>
            <RefreshCcw size={16} className={reset === "running" ? "animate-spin" : ""} />
            {reset === "confirm" ? "Click again to reset everything" : reset === "running" ? "Resetting…" : "Reset demo data"}
          </Button>
        } />
      {note && <p className="mb-4 text-[14px] text-ink-2">{note}</p>}

      <section className="sheet mb-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 lg:divide-x lg:divide-rule">
        <Tile value={docs.pending} label={`Documents to verify, ${docs.pending_flagged} flagged`} tone={docs.pending_flagged ? "text-stamp" : "text-saffron"} to="/admin/documents" />
        <Tile value={docs.verified} label="Documents verified" tone="text-leaf" />
        <Tile value={docs.rejected} label="Documents rejected" tone={docs.rejected ? "text-stamp" : ""} />
        <Tile value={apps.in_flight} label="Applications being checked" tone="text-seal" />
        <Tile value={apps.awaiting_review} label="Waiting for a regulator" tone="text-saffron" />
        <Tile value={d.alerts.critical} label={`Critical alerts, ${d.alerts.open} open`} tone={d.alerts.critical ? "text-stamp" : ""} />
      </section>

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <div className="min-w-0 space-y-5">
          <Panel title="Applications per day, last 30 days"
            action={<span className="text-[13px] text-ink-3">{apps.submitted_today} today, {apps.decided_today} decided today</span>}>
            <div className="flex h-[120px] items-end gap-[3px]" role="img"
              aria-label={`Applications per day; ${apps.submitted_today} today`}>
              {apps.per_day.map((x: any) => (
                <div key={x.day} className="group relative flex-1" title={`${x.day}: ${x.count}`}>
                  <div className={`w-full rounded-t-sm ${x.count ? "bg-seal" : "bg-rule"}`}
                    style={{ height: `${Math.max(3, (100 * x.count) / max)}px` }} />
                </div>
              ))}
            </div>
            <div className="mt-2 flex justify-between text-[12px] text-ink-3">
              <span>{apps.per_day[0].day.slice(5)}</span><span>Today</span>
            </div>
            <p className="mt-3 text-[13px] text-ink-2">
              {apps.total} applications on file. Average time to a decision: {fmtHours(apps.avg_decision_hours)}.
            </p>
          </Panel>

          <Panel title="Verification backlog" action={<Link to="/admin/documents" className="text-[13px] text-seal">Open the queue</Link>}>
            {docs.pending === 0 ? <p className="text-sm text-ink-2">Every document has been reviewed.</p> : (
              <ul className="space-y-3">
                {(Object.keys(KIND) as (keyof typeof KIND)[]).map((k) => {
                  const n = docs.by_kind[k] ?? 0;
                  return (
                    <li key={k} className="grid grid-cols-[1fr_auto] items-center gap-x-3 text-[14px] sm:grid-cols-[180px_1fr_40px]">
                      <span>{KIND[k]}</span>
                      <span className="order-3 col-span-2 h-2 rounded-full bg-paper sm:order-none sm:col-span-1">
                        <span className="block h-full rounded-full bg-saffron" style={{ width: `${(100 * n) / docs.pending}%` }} />
                      </span>
                      <span className="text-right font-medium">{n}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        </div>

        <div className="min-w-0 space-y-5">
          <Panel title="System health">
            <dl className="space-y-2.5 text-[14px]">
              <div className="flex justify-between gap-4"><dt className="text-ink-2">Database</dt>
                <dd>{sys.database === "postgresql" ? "Postgres" : "SQLite"}, {sys.db_ms} ms per query</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-ink-2">Server region</dt><dd>{sys.region}</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-ink-2">Audit log</dt>
                <dd className={`flex items-center gap-1.5 ${sys.audit_ok ? "text-leaf" : "text-stamp"}`}>
                  {sys.audit_ok ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}
                  {sys.audit_ok ? `${sys.audit_size} entries verified` : "Verification failed"}
                </dd></div>
              <div className="flex justify-between gap-4"><dt className="text-ink-2">Signed root</dt><dd><Hash value={sys.signed_root} n={14} /></dd></div>
            </dl>
          </Panel>

          <Panel title="Live activity">
            <ol className="space-y-2.5">
              {d.activity.map((e: any) => (
                <li key={e.id} className="grid grid-cols-[64px_1fr] gap-2 text-[13px]">
                  <span className="text-ink-3">{clock(e.ts)}</span>
                  <span className="min-w-0">
                    <span className="font-medium">{e.action}</span>{" "}
                    <span className="break-all text-ink-2">{e.entity}</span>
                    <span className="block text-[12px] text-ink-3">{e.actor}</span>
                  </span>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </>
  );
}
