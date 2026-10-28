import { ArrowLeft, Check, FileImage, FileSpreadsheet, FileText, Minus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AdminAuthError, admin, type AdminDoc } from "../api";
import { Button, PageTitle, fmtDate } from "../components/ui";

const TABS = [["pending", "To verify"], ["verified", "Verified"], ["rejected", "Rejected"], ["all", "All"]] as const;
const KINDS = [["", "All types"], ["photo", "Photos"], ["roster", "Rosters"], ["financials", "Financials"]] as const;
const ICON = { photo: FileImage, roster: FileSpreadsheet, financials: FileText };

function AutoBadge({ doc }: { doc: AdminDoc }) {
  const map = {
    flagged: ["Flagged by checks", "text-stamp bg-stamp-soft"],
    clear: ["Checks clear", "text-leaf bg-leaf-soft"],
    processing: ["Processing", "text-seal bg-seal-soft"],
  } as const;
  const [label, cls] = map[doc.auto];
  return <span className={`rounded-full px-2 py-0.5 text-[12px] font-medium ${cls}`}>{label}</span>;
}

function ReviewBadge({ doc }: { doc: AdminDoc }) {
  if (!doc.review) return <span className="text-[12px] text-saffron">Not reviewed</span>;
  return doc.review.status === "verified"
    ? <span className="text-[12px] font-medium text-leaf">Verified</span>
    : <span className="text-[12px] font-medium text-stamp">Rejected</span>;
}

function Viewer({ doc }: { doc: AdminDoc }) {
  const [url, setUrl] = useState<string | null>(null);
  const [rows, setRows] = useState<string[][] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let revoke: string | null = null;
    setUrl(null); setRows(null); setError(null);
    (async () => {
      try {
        if (doc.kind === "roster") {
          const text = await admin.fileText(doc.id);
          setRows(text.trim().split(/\r?\n/).map((l) => l.split(",")));
        } else {
          revoke = await admin.file(doc.id);
          setUrl(revoke);
        }
      } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    })();
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [doc.id, doc.kind]);

  if (error) return <p className="text-sm text-stamp">Couldn't open the document: {error}</p>;
  if (doc.kind === "photo") {
    return url ? <img src={url} alt={doc.filename} className="max-h-[420px] w-full rounded-lg bg-paper object-contain" />
      : <div className="h-[240px] animate-pulse rounded-lg bg-paper" />;
  }
  if (doc.kind === "financials") {
    return url ? (
      <div>
        <object data={url} type="application/pdf" className="hidden h-[460px] w-full rounded-lg border border-rule sm:block">
          <p className="p-4 text-sm">This browser can't show PDFs inline.</p>
        </object>
        <a href={url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[14px] text-seal">Open the PDF in a new tab</a>
      </div>
    ) : <div className="h-[240px] animate-pulse rounded-lg bg-paper" />;
  }
  if (!rows) return <div className="h-[200px] animate-pulse rounded-lg bg-paper" />;
  const [head, ...body] = rows;
  return (
    <div className="max-h-[360px] overflow-auto rounded-lg border border-rule">
      <table className="w-full text-[12.5px]">
        <thead className="sticky top-0 bg-paper text-left text-ink-2">
          <tr>{head.map((h) => <th key={h} className="px-3 py-2 font-medium">{h.replace(/_/g, " ")}</th>)}</tr>
        </thead>
        <tbody>
          {body.slice(0, 200).map((r, i) => (
            <tr key={i} className="border-t border-rule">
              {r.map((c, j) => <td key={j} className={`px-3 py-1.5 ${j === 0 ? "font-mono text-[11.5px] text-ink-2" : ""}`}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-rule px-3 py-2 text-[12px] text-ink-3">{body.length} faculty. Names and PANs were removed on arrival.</p>
    </div>
  );
}

function Detail({ doc, onBack, onDone }: { doc: AdminDoc; onBack: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setNote(""); setError(null); }, [doc.id]);

  async function decide(status: "verified" | "rejected") {
    if (status === "rejected" && !note.trim()) { setError("Add a note saying what's wrong; the institution sees it."); return; }
    setBusy(true); setError(null);
    try { await admin.review(doc.id, status, note.trim()); onDone(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return (
    <section className="sheet min-w-0 p-4 sm:p-5">
      <button onClick={onBack} className="mb-3 inline-flex items-center gap-1.5 text-[14px] text-seal lg:hidden">
        <ArrowLeft size={16} /> Back to the list
      </button>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] text-ink-3">{doc.kind_label}, case {doc.application_id}</p>
          <h2 className="break-all text-[18px] font-semibold leading-snug">{doc.filename}</h2>
          <p className="text-[14px] text-ink-2">{doc.institution.name}, {doc.institution.city}</p>
        </div>
        <div className="flex flex-col items-end gap-1"><AutoBadge doc={doc} /><ReviewBadge doc={doc} /></div>
      </div>

      <Viewer doc={doc} />

      <h3 className="mb-2 mt-5 text-[14px] font-semibold">Automatic checks</h3>
      <ul className="space-y-2">
        {doc.checks.map((c) => (
          <li key={c.label} className="flex gap-2.5 text-[13.5px]">
            <span className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full ${c.ok === true ? "bg-leaf-soft text-leaf" : c.ok === false ? "bg-stamp-soft text-stamp" : "bg-paper text-ink-3"}`}>
              {c.ok === true ? <Check size={13} /> : c.ok === false ? <X size={13} /> : <Minus size={13} />}
            </span>
            <span><strong className="font-medium">{c.label}.</strong> <span className="text-ink-2">{c.detail}</span></span>
          </li>
        ))}
      </ul>

      {doc.review ? (
        <p className={`mt-5 rounded-lg p-3 text-[13.5px] ${doc.review.status === "verified" ? "bg-leaf-soft" : "bg-stamp-soft"}`}>
          {doc.review.status === "verified" ? "Verified" : "Rejected"} by {doc.review.reviewer} on {fmtDate(doc.review.reviewed_at)}
          {doc.review.note ? `: ${doc.review.note}` : "."}
        </p>
      ) : (
        <div className="mt-5 border-t border-rule pt-4">
          <label className="block text-[13px] font-medium text-ink-2" htmlFor="note">Note (required to reject)</label>
          <textarea id="note" rows={2} value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="For example: photo taken off campus, please retake on site"
            className="mt-1.5 w-full rounded-lg border border-rule px-3 py-2 text-[14px]" />
          {error && <p className="mt-2 text-[13px] text-stamp">{error}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button kind="good" disabled={busy} onClick={() => decide("verified")}><Check size={16} /> Verify document</Button>
            <Button kind="danger" disabled={busy} onClick={() => decide("rejected")}><X size={16} /> Reject</Button>
          </div>
          <p className="mt-2 text-[12px] text-ink-3">Your decision is signed into the audit log. Rejections notify the institution.</p>
        </div>
      )}
    </section>
  );
}

export default function AdminDocuments() {
  const nav = useNavigate();
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("pending");
  const [kind, setKind] = useState("");
  const [docs, setDocs] = useState<AdminDoc[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setDocs(await admin.documents(tab, kind || undefined)); setError(null); }
    catch (e) {
      if (e instanceof AdminAuthError) nav("/admin/login");
      else setError(e instanceof Error ? e.message : String(e));
    }
  }, [tab, kind, nav]);

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  const current = docs?.find((d) => d.id === selected) ?? null;

  function afterReview() {
    // Move on to the next document still waiting, so a batch can be cleared quickly.
    const rest = (docs ?? []).filter((d) => d.id !== selected && !d.review);
    setSelected(tab === "pending" ? rest[0]?.id ?? null : selected);
    load();
  }

  return (
    <>
      <PageTitle title="Verify documents"
        sub="Every file an institution uploads, with what the automatic checks found. Flagged documents are listed first." />

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-1 overflow-x-auto rounded-lg border border-rule bg-sheet p-1">
          {TABS.map(([k, label]) => (
            <button key={k} onClick={() => { setTab(k); setSelected(null); }}
              className={`whitespace-nowrap rounded-md px-3 py-1.5 text-[13px] font-medium ${tab === k ? "bg-ink text-white" : "text-ink-2"}`}>
              {label}
            </button>
          ))}
        </div>
        <select value={kind} onChange={(e) => { setKind(e.target.value); setSelected(null); }}
          className="rounded-lg border border-rule bg-sheet px-3 py-2 text-[14px]" aria-label="Document type">
          {KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </div>

      {error && <p className="mb-4 rounded-lg bg-stamp-soft px-4 py-3 text-sm text-stamp">{error}</p>}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <section className={`sheet min-w-0 ${current ? "hidden lg:block" : ""}`}>
          {docs === null ? <p className="p-5 text-sm text-ink-2">Loading documents…</p>
            : docs.length === 0 ? <p className="p-5 text-sm text-ink-2">
              {tab === "pending" ? "Nothing waiting. New uploads appear here within seconds." : "No documents here."}</p>
            : (
              <ul className="divide-y divide-rule">
                {docs.map((d) => {
                  const Icon = ICON[d.kind];
                  return (
                    <li key={d.id}>
                      <button onClick={() => setSelected(d.id)}
                        className={`flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-paper ${selected === d.id ? "bg-seal-soft" : ""}`}>
                        <Icon size={20} className={`mt-0.5 shrink-0 ${d.auto === "flagged" ? "text-stamp" : "text-ink-3"}`} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[14px] font-medium">{d.filename}</span>
                          <span className="block truncate text-[13px] text-ink-2">{d.institution.name}</span>
                          <span className="mt-1 flex flex-wrap items-center gap-2"><AutoBadge doc={d} /><ReviewBadge doc={d} /></span>
                        </span>
                        <span className="hidden shrink-0 text-[12px] text-ink-3 sm:block">{(d.size / 1024).toFixed(0)} KB</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
        </section>

        {current ? <Detail doc={current} onBack={() => setSelected(null)} onDone={afterReview} />
          : <section className="sheet hidden items-center justify-center p-10 text-center text-[14px] text-ink-2 lg:flex">
              Pick a document to see it next to its automatic checks.
            </section>}
      </div>
    </>
  );
}
