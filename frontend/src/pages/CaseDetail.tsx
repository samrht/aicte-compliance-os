import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import CaseFile from "../components/CaseFile";
import { Button, ErrorNote, Panel, usePoll } from "../components/ui";

export default function CaseDetail() {
  const id = Number(useParams().id);
  const { data, error, refresh } = usePoll(() => api.application(id), 900, [id]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  if (!data) return <ErrorNote error={error} />;

  const waiting = data.nodes?.some((n) => n.state === "waiting");
  const decide = async (approve: boolean) => {
    setBusy(true);
    setFailure(null);
    try { await api.decide(id, approve, note); await refresh(); }
    catch (e) { setFailure(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const decision = waiting ? (
    <Panel title="Your decision" className="border-saffron/60">
      <p className="text-[14px] text-ink-2">
        This case needs a regulator. The findings, the risk explanation and the norms check below are the full record; your decision and note are signed into the audit log.
      </p>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Note for the institution (optional)"
        className="mt-3 w-full rounded-lg border border-rule px-3 py-2 text-[14px]" />
      {failure && <p className="mt-2 text-[13px] text-stamp">{failure}</p>}
      <div className="mt-3 flex gap-2">
        <Button kind="good" disabled={busy} onClick={() => decide(true)}>Approve</Button>
        <Button kind="danger" disabled={busy} onClick={() => decide(false)}>Reject</Button>
      </div>
    </Panel>
  ) : null;

  return (
    <>
      <Link to="/aicte/queue" className="mb-4 inline-block text-[14px] text-seal">Back to the review queue</Link>
      <CaseFile app={data} side={decision} />
    </>
  );
}
