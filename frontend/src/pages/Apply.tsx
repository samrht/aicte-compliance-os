import { FileText, ImagePlus, ShieldCheck, Users } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { getSession } from "../App";
import { api } from "../api";
import { Button, PageTitle, Panel } from "../components/ui";

const STEPS = ["Institution details", "Evidence", "Review and submit"];

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[13px] font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-ink-3">{hint}</span>}
    </label>
  );
}

function Drop({ icon, label, hint, accept, multiple, files, onFiles }: {
  icon: ReactNode; label: string; hint: string; accept: string; multiple?: boolean;
  files: File[]; onFiles: (f: File[]) => void;
}) {
  return (
    <label className={`flex cursor-pointer gap-4 rounded-lg border-2 border-dashed p-4 transition-colors ${files.length ? "border-leaf/50 bg-leaf-soft" : "border-rule hover:border-seal/50"}`}>
      <span className="mt-0.5 text-seal">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-semibold">{label}</span>
        <span className="block text-[13px] text-ink-2">{files.length ? files.map((f) => f.name).join(", ") : hint}</span>
      </span>
      <input type="file" className="sr-only" accept={accept} multiple={multiple}
        onChange={(e) => onFiles(Array.from(e.target.files ?? []))} />
    </label>
  );
}

export default function Apply() {
  const s = getSession() as { id: number; name: string };
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({ students: "", land_acres: "", builtup_sqm: "", labs: "" });
  const [roster, setRoster] = useState<File[]>([]);
  const [photos, setPhotos] = useState<File[]>([]);
  const [pdf, setPdf] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.institution(s.id).then((i) => {
      if (i.prefill) setForm(Object.fromEntries(Object.entries(i.prefill).map(([k, v]) => [k, String(v)])) as typeof form);
    }).catch(() => {});
  }, [s.id]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const detailsOk = Object.values(form).every((v) => v !== "" && Number(v) >= 0);
  const evidenceOk = roster.length && photos.length && pdf.length;

  async function submit() {
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.append("institution_id", String(s.id));
    Object.entries(form).forEach(([k, v]) => fd.append(k, v));
    fd.append("faculty_csv", roster[0]);
    fd.append("financials", pdf[0]);
    photos.forEach((p) => fd.append("photos", p));
    try {
      const { id } = await api.submit(fd);
      nav(`/inst/cases/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const input = "mt-1.5 w-full rounded-lg border border-rule bg-sheet px-3 py-2.5 text-[15px]";
  return (
    <>
      <PageTitle title="Apply for approval" sub={`${s.name}, academic year 2027-28`} />
      <ol className="mb-6 flex flex-wrap gap-2">
        {STEPS.map((t, i) => (
          <li key={t} className={`rounded-full px-3.5 py-1.5 text-[13px] font-medium ${i === step ? "bg-ink text-white" : i < step ? "bg-leaf-soft text-leaf" : "bg-sheet text-ink-3 border border-rule"}`}>
            {i + 1}. {t}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <Panel title="Declared infrastructure">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Total sanctioned intake (students)"><input className={input} type="number" value={form.students} onChange={set("students")} /></Field>
            <Field label="Land area (acres)"><input className={input} type="number" step="0.1" value={form.land_acres} onChange={set("land_acres")} /></Field>
            <Field label="Built-up area (m²)"><input className={input} type="number" value={form.builtup_sqm} onChange={set("builtup_sqm")} /></Field>
            <Field label="Laboratories" hint="Instructional labs with equipment lists on file"><input className={input} type="number" value={form.labs} onChange={set("labs")} /></Field>
          </div>
          <div className="mt-6 flex justify-end"><Button disabled={!detailsOk} onClick={() => setStep(1)}>Continue to evidence</Button></div>
        </Panel>
      )}

      {step === 1 && (
        <Panel title="Upload evidence">
          <div className="space-y-3">
            <Drop icon={<Users />} label="Faculty roster (CSV)" accept=".csv" files={roster} onFiles={setRoster}
              hint="Columns: name, pan, dob, designation, qualification. Identities are converted to blinded tokens on arrival." />
            <Drop icon={<ImagePlus />} label="Geo-tagged campus photos" accept="image/*" multiple files={photos} onFiles={setPhotos}
              hint="Phone photos with location on. Each is checked against your registered campus location." />
            <Drop icon={<FileText />} label="Audited income and expenditure statement (PDF)" accept=".pdf" files={pdf} onFiles={setPdf}
              hint="Revenue, expenditure and corpus fund are read automatically." />
          </div>
          <p className="mt-4 text-[13px] text-ink-3">
            No files to hand? Download a sample set, unzip it and upload its contents:{" "}
            <a className="text-seal underline" href="/demo-assets/1-clean-indrayani-pune.zip">Indrayani (clean)</a>,{" "}
            <a className="text-seal underline" href="/demo-assets/2-shady-thar-jaipur.zip">Thar Desert (suspicious)</a>.
          </p>
          <div className="mt-6 flex justify-between">
            <Button kind="quiet" onClick={() => setStep(0)}>Back</Button>
            <Button disabled={!evidenceOk} onClick={() => setStep(2)}>Review application</Button>
          </div>
        </Panel>
      )}

      {step === 2 && (
        <Panel title="Review and submit">
          <dl className="grid gap-x-8 gap-y-3 text-[14px] sm:grid-cols-2">
            <div><dt className="text-ink-3">Intake</dt><dd>{form.students} students</dd></div>
            <div><dt className="text-ink-3">Land</dt><dd>{form.land_acres} acres</dd></div>
            <div><dt className="text-ink-3">Built-up area</dt><dd>{Number(form.builtup_sqm).toLocaleString("en-IN")} m²</dd></div>
            <div><dt className="text-ink-3">Laboratories</dt><dd>{form.labs}</dd></div>
            <div><dt className="text-ink-3">Faculty roster</dt><dd>{roster[0]?.name}</dd></div>
            <div><dt className="text-ink-3">Photos</dt><dd>{photos.length} files</dd></div>
            <div><dt className="text-ink-3">Financial statement</dt><dd>{pdf[0]?.name}</dd></div>
          </dl>
          <p className="mt-6 flex gap-2 rounded-lg bg-seal-soft p-3.5 text-[13px] text-ink-2">
            <ShieldCheck size={18} className="shrink-0 text-seal" />
            Uploads are encrypted in transit. Faculty names and PAN numbers are never stored; only keyed hashes are kept for cross-institution checks.
          </p>
          {error && <p className="mt-4 text-[14px] text-stamp">Submission failed: {error}</p>}
          <div className="mt-6 flex justify-between">
            <Button kind="quiet" onClick={() => setStep(1)}>Back</Button>
            <Button disabled={busy} onClick={submit}>{busy ? "Submitting…" : "Submit application"}</Button>
          </div>
        </Panel>
      )}
    </>
  );
}
