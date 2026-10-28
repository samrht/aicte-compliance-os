import { ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { Button, ErrorNote, Hash, PageTitle, Panel, fmtDate, usePoll } from "../components/ui";

export default function Audit() {
  const { data, error, refresh } = usePoll(() => api.audit(), 3000);
  const [proof, setProof] = useState<any>(null);
  if (!data) return <ErrorNote error={error} />;
  const v = data.verification;

  return (
    <>
      <PageTitle title="Audit log"
        sub="Every state change is a leaf in a Merkle tree, and every new root is signed with Ed25519. Editing any past row is detectable."
        action={
          <div className="flex gap-2">
            <Button kind="quiet" onClick={refresh}>Verify again</Button>
            {!v.ok && <Button kind="good" onClick={async () => { await api.restore(); refresh(); }}>Restore original rows</Button>}
          </div>
        } />

      <section className={`mb-5 flex flex-wrap items-start gap-4 rounded-[10px] border p-5 ${v.ok ? "border-leaf/40 bg-leaf-soft" : "border-stamp/50 bg-stamp-soft"}`}>
        {v.ok ? <ShieldCheck className="text-leaf" size={30} /> : <ShieldAlert className="text-stamp" size={30} />}
        <div className="min-w-0 flex-1">
          <p className={`text-[18px] font-semibold ${v.ok ? "text-leaf" : "text-stamp"}`}>
            {v.ok ? `All ${v.size} entries verified` : `Tampering detected in entry ${v.tampered.join(", ")}`}
          </p>
          <p className="mt-1 text-[13px] text-ink-2">
            {v.ok
              ? "Each row's hash matches what was recorded, and the rebuilt root matches the signed checkpoint."
              : "The edited row no longer hashes to its recorded leaf, so the rebuilt root differs from the signed one. The signature itself is still valid, which proves the original was different."}
          </p>
          <dl className="mt-3 grid gap-x-6 gap-y-1 text-[12.5px] sm:grid-cols-2">
            <div><dt className="inline text-ink-3">Signed root </dt><dd className="inline"><Hash value={v.signed_root} n={24} /></dd></div>
            <div><dt className="inline text-ink-3">Rebuilt root </dt><dd className="inline"><Hash value={v.recomputed_root} n={24} /></dd></div>
            <div><dt className="inline text-ink-3">Signature </dt><dd className="inline">{v.signature_valid ? "valid" : "invalid"}</dd></div>
            <div><dt className="inline text-ink-3">Public key </dt><dd className="inline"><Hash value={v.public_key} n={24} /></dd></div>
          </dl>
        </div>
      </section>

      {proof && (
        <Panel title={`Inclusion proof for entry ${proof.entry_id}`} className="mb-5"
          action={<button className="text-[13px] text-seal" onClick={() => setProof(null)}>Close</button>}>
          <p className={`mb-3 text-[14px] font-medium ${proof.verified ? "text-leaf" : "text-stamp"}`}>
            {proof.verified ? "This entry is provably part of the signed log." : "This entry does not hash into the signed root."}
          </p>
          <p className="text-[13px] text-ink-2">Leaf <Hash value={proof.leaf} n={64} /></p>
          <p className="mt-2 text-[13px] text-ink-2">{proof.path.length} sibling hashes up to the root of {proof.tree_size} entries:</p>
          <ol className="mt-1 space-y-0.5">
            {proof.path.map((p: string, i: number) => <li key={i}><Hash value={p} n={64} /></li>)}
          </ol>
        </Panel>
      )}

      <section className="sheet overflow-x-auto">
        <table className="w-full min-w-[820px] text-[13px]">
          <thead className="text-left text-ink-3">
            <tr className="border-b border-rule">
              <th className="px-4 py-2.5 font-medium">#</th><th className="py-2.5 font-medium">Time</th><th className="py-2.5 font-medium">Actor</th>
              <th className="py-2.5 font-medium">Event</th><th className="py-2.5 font-medium">Subject</th><th className="py-2.5 font-medium">Leaf hash</th><th />
            </tr>
          </thead>
          <tbody>
            {data.entries.map((e: any) => (
              <tr key={e.id} className={`border-b border-rule last:border-0 ${e.tampered ? "bg-stamp-soft" : ""}`}>
                <td className="px-4 py-2 text-ink-3">{e.id}</td>
                <td className="py-2 pr-3 text-ink-2">{fmtDate(e.ts)}</td>
                <td className="py-2 pr-3">{e.actor}</td>
                <td className="py-2 pr-3 font-medium">
                  {e.action}
                  {e.payload.decision && <span className="ml-1.5 font-normal text-ink-2">({e.payload.decision})</span>}
                  {e.payload.forged && <span className="ml-1.5 font-normal text-stamp">(edited)</span>}
                </td>
                <td className="py-2 pr-3 text-ink-2">{e.entity}</td>
                <td className="py-2 pr-3"><Hash value={e.leaf_hash} n={14} /></td>
                <td className="whitespace-nowrap py-2 pr-4 text-right">
                  <button className="text-seal" onClick={async () => setProof(await api.proof(e.id))}>Proof</button>
                  <button className="ml-3 text-stamp/80 hover:text-stamp" onClick={async () => { await api.tamper(e.id); refresh(); }}
                    title="Demo: change this row directly in the database">Tamper</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
