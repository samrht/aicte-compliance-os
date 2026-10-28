import { Building2, Landmark } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Seal, setSession } from "../App";
import { api } from "../api";
import { ErrorNote, Status, usePoll } from "../components/ui";

export default function Login() {
  const nav = useNavigate();
  const { data: insts, error } = usePoll(() => api.institutions());
  const [instId, setInstId] = useState<number | "">("");
  const fresh = (insts ?? []).filter((i) => i.status === "new");
  const rest = (insts ?? []).filter((i) => i.status !== "new");

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-[880px]">
        <div className="mb-10 flex items-center gap-3">
          <Seal className="size-11 text-seal" />
          <div>
            <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.015em]">AICTE Compliance OS</h1>
            <p className="text-[15px] text-ink-2">Approval workflow, compliance monitoring and alerts for technical institutions</p>
          </div>
        </div>
        <ErrorNote error={error} />
        <div className="grid gap-5 md:grid-cols-2">
          <section className="sheet flex flex-col p-6">
            <Building2 className="text-seal" />
            <h2 className="mt-3 text-[18px] font-semibold">Institution</h2>
            <p className="mt-1 text-[14px] text-ink-2">Apply for approval, upload evidence and follow your case as it is verified.</p>
            <label className="mt-5 text-[13px] font-medium text-ink-2" htmlFor="inst">Sign in as</label>
            <select id="inst" value={instId} onChange={(e) => setInstId(Number(e.target.value) || "")}
              className="mt-1.5 rounded-lg border border-rule bg-sheet px-3 py-2.5 text-[14px]">
              <option value="">Choose an institution</option>
              <optgroup label="New applicants">
                {fresh.map((i) => <option key={i.id} value={i.id}>{i.name}, {i.city}</option>)}
              </optgroup>
              <optgroup label="Approved and existing">
                {rest.map((i) => <option key={i.id} value={i.id}>{i.name}, {i.city}</option>)}
              </optgroup>
            </select>
            {instId !== "" && (
              <p className="mt-2 text-[13px]">Current status: <Status value={insts!.find((i) => i.id === instId)!.status} /></p>
            )}
            <button disabled={instId === ""}
              onClick={() => {
                const i = insts!.find((x) => x.id === instId)!;
                setSession({ role: "inst", id: i.id, name: i.name });
                nav("/inst");
              }}
              className="mt-auto rounded-lg bg-seal px-4 py-2.5 text-[14px] font-medium text-white disabled:opacity-40 max-md:mt-5 md:mt-6">
              Open institution portal
            </button>
          </section>
          <section className="sheet flex flex-col bg-ink p-6 text-white">
            <Landmark className="text-[#9db4ff]" />
            <h2 className="mt-3 text-[18px] font-semibold">AICTE regulator</h2>
            <p className="mt-1 text-[14px] text-white/70">
              Watch every case route by risk, act on the review queue and alerts, trace ghost faculty, verify the audit log and test new norms before they apply.
            </p>
            <button onClick={() => { setSession({ role: "aicte" }); nav("/aicte"); }}
              className="mt-6 rounded-lg bg-white px-4 py-2.5 text-[14px] font-medium text-ink md:mt-auto">
              Open regulator console
            </button>
          </section>
        </div>
        <p className="mt-8 text-[13px] text-ink-3">Prototype for Smart India Hackathon 2026, problem statement SIH26262. All institutions and people are fictional.</p>
      </div>
    </div>
  );
}
