export type Tier = "low" | "medium" | "high";

export interface Institution {
  id: number; code: string; name: string; city: string; state: string;
  lat: number; lon: number; established: number; status: string;
  risk_score: number | null; risk_tier: Tier | null; metrics: Record<string, number>;
}

export interface Node {
  id: number; key: string; label: string; seq: number; lane: number; state: string;
  depends_on: string[]; detail: string; started_at: string | null; finished_at: string | null;
}

export interface Finding {
  id: number; category: string; severity: "critical" | "warn" | "info";
  title: string; message: string; evidence: Record<string, unknown>;
}

export interface Alert {
  id: number; institution_id: number | null; application_id: number | null; kind: string;
  severity: "critical" | "warn" | "info"; title: string; message: string; created_at: string;
  acknowledged: boolean; institution?: string | null;
}

export interface Contribution { feature: string; label: string; value: number; impact: number }

export interface Application {
  id: number; institution_id: number; kind: string; academic_year: string; status: string;
  tier: Tier | null; risk_score: number | null; submitted_at: string; decided_at: string | null;
  decided_by: string | null; decision_note: string | null; inspection_date: string | null;
  metrics: Record<string, number>; turnaround_hours?: number;
  institution: { id: number; name: string; code: string; city: string; state: string; status: string };
  signals?: Record<string, any>; contributions?: Contribution[];
  nodes?: Node[]; findings?: Finding[]; alerts?: Alert[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, init);
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* body was not JSON */ }
    throw new Error(msg);
  }
  return r.json();
}

const post = <T,>(path: string, body?: unknown) =>
  req<T>(path, { method: "POST", headers: { "Content-Type": "application/json" },
                 body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  institutions: () => req<Institution[]>("/institutions"),
  institution: (id: number) => req<Institution & {
    applications: Application[]; alerts: Alert[]; norms: any[]; plan: any[];
    prefill: Record<string, number> | null }>(`/institutions/${id}`),
  applications: (status?: string) => req<Application[]>(`/applications${status ? `?status=${status}` : ""}`),
  application: (id: number) => req<Application>(`/applications/${id}`),
  submit: (form: FormData) => req<{ id: number }>("/applications", { method: "POST", body: form }),
  decide: (id: number, approve: boolean, note: string) =>
    post(`/applications/${id}/decision`, { approve, note }),
  dashboard: () => req<any>("/dashboard"),
  alerts: (institutionId?: number) => req<Alert[]>(`/alerts${institutionId ? `?institution_id=${institutionId}` : ""}`),
  ack: (id: number) => post(`/alerts/${id}/ack`),
  sweep: () => post<{ alerts_raised: number }>("/monitor/sweep"),
  collisions: () => req<any>("/collisions"),
  audit: () => req<any>("/audit"),
  verify: () => post<any>("/audit/verify"),
  proof: (id: number) => req<any>(`/audit/proof/${id}`),
  tamper: (id: number) => post(`/audit/tamper/${id}`),
  restore: () => post("/audit/restore"),
  policy: () => req<any>("/policy"),
  simulate: (overrides: Record<string, number>) => post<any>("/sandbox/simulate", { overrides }),
  reset: () => post("/admin/reset"),
};
