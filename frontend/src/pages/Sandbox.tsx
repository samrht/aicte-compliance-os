import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, ErrorNote, PageTitle, Panel, usePoll } from "../components/ui";

export default function Sandbox() {
  const { data: pol, error } = usePoll(() => api.policy());
  const [values, setValues] = useState<Record<string, number>>({});
  const [result, setResult] = useState<any>(null);
  const [showRego, setShowRego] = useState(false);

  useEffect(() => {
    if (pol && !Object.keys(values).length) {
      setValues(Object.fromEntries(pol.policy.rules.map((r: any) => [r.id, r.value])));
    }
  }, [pol, values]);

  useEffect(() => {
    if (!Object.keys(values).length) return;
    const t = setTimeout(() => api.simulate(values).then(setResult).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [values]);

  if (!pol) return <ErrorNote error={error} />;
  const base = Object.fromEntries(pol.policy.rules.map((r: any) => [r.id, r.value]));
  const changed = pol.policy.rules.filter((r: any) => values[r.id] !== r.value);
  const failing = (result?.rows ?? []).filter((r: any) => !r.after);

  return (
    <>
      <PageTitle title="Shadow sandbox"
        sub="Try a change to the norms against every institution on file before it takes effect. Nothing here touches live approvals."
        action={changed.length > 0 && <Button kind="quiet" onClick={() => setValues(base)}>Back to current norms</Button>} />
      <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
        <Panel title="Proposed norms">
          <div className="space-y-5">
            {pol.policy.rules.map((r: any) => {
              const span = r.value * 0.6 || 5;
              const v = values[r.id] ?? r.value;
              return (
                <div key={r.id}>
                  <div className="flex items-baseline justify-between gap-3">
                    <label htmlFor={r.id} className="text-[14px] font-medium">{r.title}</label>
                    <span className={`text-[14px] ${v !== r.value ? "font-semibold text-seal" : "text-ink-2"}`}>{r.op === "<=" ? "≤" : "≥"} {v}</span>
                  </div>
                  <input id={r.id} type="range" className="mt-1.5 w-full accent-[#1f4fd1]"
                    min={Math.max(0, r.value - span)} max={r.value + span} step={r.value < 20 ? 0.5 : 1} value={v}
                    onChange={(e) => setValues({ ...values, [r.id]: Number(e.target.value) })} />
                  <p className="text-[12px] text-ink-3">{r.unit}. Today: {r.op === "<=" ? "≤" : "≥"} {r.value}</p>
                </div>
              );
            })}
          </div>
        </Panel>

        <div className="space-y-5">
          {result && (
            <section className="sheet grid grid-cols-3 divide-x divide-rule">
              <div className="px-5 py-4">
                <p className="text-[28px] font-semibold leading-none">{result.compliant_before}<span className="text-[16px] text-ink-3"> / {result.total}</span></p>
                <p className="mt-1.5 text-[13px] text-ink-2">Compliant under current norms</p>
              </div>
              <div className="px-5 py-4">
                <p className={`text-[28px] font-semibold leading-none ${result.compliant_after < result.compliant_before ? "text-stamp" : result.compliant_after > result.compliant_before ? "text-leaf" : ""}`}>
                  {result.compliant_after}<span className="text-[16px] text-ink-3"> / {result.total}</span>
                </p>
                <p className="mt-1.5 text-[13px] text-ink-2">Compliant under proposed norms</p>
              </div>
              <div className="px-5 py-4">
                <p className="text-[28px] font-semibold leading-none">{result.flips.length}</p>
                <p className="mt-1.5 text-[13px] text-ink-2">Institutions that change status</p>
              </div>
            </section>
          )}

          {result?.flips.length > 0 && (
            <Panel title="Who changes status">
              <ul className="divide-y divide-rule">
                {result.flips.map((f: any) => (
                  <li key={f.institution_id} className="flex flex-wrap items-center justify-between gap-3 py-2.5 text-[14px]">
                    <span>{f.name} <span className="text-ink-3">({f.state})</span></span>
                    <span className={f.flip === "newly_compliant" ? "text-leaf" : "text-stamp"}>
                      {f.flip === "newly_compliant" ? "Becomes compliant" : `Falls out of compliance on ${f.failing.join(", ")}`}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title={`Remediation plans (${failing.length} non-compliant)`}>
            {failing.length === 0 ? <p className="text-sm text-ink-2">Every institution meets the proposed norms.</p> : (
              <ul className="space-y-4">
                {failing.map((r: any) => (
                  <li key={r.institution_id}>
                    <p className="text-[14px] font-semibold">{r.name}</p>
                    <ul className="mt-1 space-y-1 text-[13px]">
                      {r.plan.map((p: any) => (
                        <li key={p.rule} className="flex justify-between gap-4">
                          <span className="text-ink-2"><span className="text-ink">{p.rule}</span>: {p.best.action}
                            {p.options.length > 1 && <span className="text-ink-3"> (cheaper than: {p.options.filter((o: any) => o !== p.best && o.action !== p.best.action).map((o: any) => o.action).join(", ")})</span>}
                          </span>
                          <span className="shrink-0">₹{p.best.cost_lakh.toLocaleString("en-IN")} lakh</span>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Policy as code" action={<button className="text-[13px] text-seal" onClick={() => setShowRego(!showRego)}>{showRego ? "Hide" : "Show"} Rego</button>}>
            <p className="text-[13px] text-ink-2">The proposed norms compile to an Open Policy Agent policy, so the same rules that run here can be loaded into production unchanged.</p>
            {showRego && result && (
              <pre className="mt-3 max-h-[360px] overflow-auto rounded-lg bg-ink p-4 font-mono text-[12px] leading-relaxed text-white/90">{result.rego}</pre>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
