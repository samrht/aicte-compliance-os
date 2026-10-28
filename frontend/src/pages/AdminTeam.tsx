import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AdminAuthError, admin, getAdmin } from "../api";
import { Button, PageTitle, Panel, fmtDate } from "../components/ui";

type Account = {
  id: number; username: string; name: string; email: string; status: "pending" | "active" | "disabled";
  created_at: string; approved_by: string | null; approved_at: string | null;
};

const STATUS = {
  pending: ["Waiting for approval", "text-saffron bg-saffron-soft"],
  active: ["Active", "text-leaf bg-leaf-soft"],
  disabled: ["Disabled", "text-ink-3 bg-paper"],
} as const;

export default function AdminTeam() {
  const nav = useNavigate();
  const me = getAdmin()?.username;
  const [data, setData] = useState<{ owner: string; accounts: Account[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    try { setData(await admin.accounts()); setError(null); }
    catch (e) {
      if (e instanceof AdminAuthError) nav("/admin/login");
      else setError(e instanceof Error ? e.message : String(e));
    }
  }, [nav]);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  async function act(id: number, action: "approve" | "disable") {
    setBusy(id);
    try { await admin.accountAction(id, action); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }

  const pending = data?.accounts.filter((a) => a.status === "pending") ?? [];
  const others = data?.accounts.filter((a) => a.status !== "pending") ?? [];

  const row = (a: Account) => (
    <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-[15px] font-medium">{a.name} <span className="font-normal text-ink-3">@{a.username}</span></p>
        <p className="truncate text-[13px] text-ink-2">{a.email}</p>
        <p className="text-[12px] text-ink-3">
          Requested {fmtDate(a.created_at)}{a.approved_by ? `, approved by ${a.approved_by}` : ""}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-medium ${STATUS[a.status][1]}`}>{STATUS[a.status][0]}</span>
        {a.status !== "active" && <Button kind="good" disabled={busy === a.id} onClick={() => act(a.id, "approve")}>Approve</Button>}
        {a.status === "active" && a.username !== me &&
          <Button kind="quiet" disabled={busy === a.id} onClick={() => act(a.id, "disable")}>Disable</Button>}
      </div>
    </li>
  );

  return (
    <>
      <PageTitle title="Team" sub="Who can sign in to the admin panel. New sign-ups wait here until someone approves them." />
      {error && <p className="mb-4 rounded-lg bg-stamp-soft px-4 py-3 text-sm text-stamp">{error}</p>}
      <div className="space-y-5">
        <Panel title={`Waiting for approval (${pending.length})`}>
          {pending.length === 0 ? <p className="text-sm text-ink-2">No pending requests. New sign-ups appear here.</p>
            : <ul className="divide-y divide-rule">{pending.map(row)}</ul>}
        </Panel>
        <Panel title="Administrators">
          <ul className="divide-y divide-rule">
            {data && (
              <li className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-[15px] font-medium">Built-in administrator <span className="font-normal text-ink-3">@{data.owner}</span></p>
                  <p className="text-[12px] text-ink-3">Set on the server; can't be disabled here</p>
                </div>
                <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-medium ${STATUS.active[1]}`}>Active</span>
              </li>
            )}
            {others.map(row)}
          </ul>
        </Panel>
      </div>
    </>
  );
}
