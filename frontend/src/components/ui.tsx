import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { Tier } from "../api";

export const TIER: Record<Tier, { label: string; fg: string; bg: string }> = {
  low: { label: "Low risk", fg: "text-leaf", bg: "bg-leaf-soft" },
  medium: { label: "Medium risk", fg: "text-saffron", bg: "bg-saffron-soft" },
  high: { label: "High risk", fg: "text-stamp", bg: "bg-stamp-soft" },
};

export function TierBadge({ tier, score }: { tier: Tier | null; score?: number | null }) {
  if (!tier) return <span className="text-ink-3 text-sm">Not scored</span>;
  const t = TIER[tier];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[13px] font-medium ${t.fg} ${t.bg}`}>
      <span className="size-1.5 rounded-full bg-current" />
      {t.label}
      {score != null && <span className="opacity-75">{Math.round(score * 100)}%</span>}
    </span>
  );
}

const STATUS: Record<string, [string, string]> = {
  approved: ["Approved", "text-leaf"], ratified: ["Ratified", "text-leaf"],
  rejected: ["Rejected", "text-stamp"], lockdown: ["Lockdown", "text-stamp"],
  awaiting_review: ["Awaiting review", "text-saffron"], under_review: ["Under review", "text-saffron"],
  running: ["Verifying", "text-seal"], pending: ["Submitted", "text-seal"], new: ["No application yet", "text-ink-3"],
};

export function Status({ value }: { value: string }) {
  const [label, cls] = STATUS[value] ?? [value, "text-ink-2"];
  return <span className={`text-sm font-medium ${cls}`}>{label}</span>;
}

export const SEVERITY = {
  critical: { label: "Critical", fg: "text-stamp", bg: "bg-stamp-soft", bar: "bg-stamp" },
  warn: { label: "Warning", fg: "text-saffron", bg: "bg-saffron-soft", bar: "bg-saffron" },
  info: { label: "Info", fg: "text-seal", bg: "bg-seal-soft", bar: "bg-seal" },
} as const;

export function Panel({ title, action, children, className = "" }:
  { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`sheet ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-4 border-b border-rule px-5 py-3">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Button({ children, onClick, kind = "primary", disabled, type = "button" }: {
  children: ReactNode; onClick?: () => void; kind?: "primary" | "quiet" | "danger" | "good";
  disabled?: boolean; type?: "button" | "submit";
}) {
  const styles = {
    primary: "bg-seal text-white hover:bg-[#1a43b5]",
    quiet: "bg-sheet text-ink border border-rule hover:bg-paper",
    danger: "bg-stamp text-white hover:bg-[#a82822]",
    good: "bg-leaf text-white hover:bg-[#186b3e]",
  }[kind];
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${styles}`}>
      {children}
    </button>
  );
}

export function Hash({ value, n = 16 }: { value: string | null | undefined; n?: number }) {
  if (!value) return <span className="text-ink-3">none</span>;
  return <code className="font-mono text-[12px] text-ink-2">{value.length > n ? `${value.slice(0, n)}…` : value}</code>;
}

export function fmtDate(iso: string | null | undefined) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function fmtHours(h: number | null | undefined) {
  if (h == null) return "–";
  return h < 48 ? `${h.toFixed(0)} h` : `${(h / 24).toFixed(1)} days`;
}

/** Fetch on mount and every `interval` ms; returns data, error and a manual refresh. */
export function usePoll<T>(fn: () => Promise<T>, interval = 0, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const load = useCallback(async () => {
    try { setData(await fnRef.current()); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, []);
  useEffect(() => {
    load();
    if (!interval) return;
    const t = setInterval(load, interval);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, interval, ...deps]);
  return { data, error, refresh: load };
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p className="rounded-lg bg-stamp-soft px-4 py-3 text-sm text-stamp">
      Can't reach the compliance service ({error}). Start the backend on port 8000, then refresh.
    </p>
  );
}

export function PageTitle({ title, sub, action }: { title: string; sub?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.01em]">{title}</h1>
        {sub && <p className="mt-1 text-[15px] text-ink-2">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

/** True while the viewport matches `query`; follows resizes and rotation. */
export function useMedia(query: string) {
  const get = () => typeof window !== "undefined" && window.matchMedia(query).matches;
  const [match, setMatch] = useState(get);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setMatch(m.matches);
    on();
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return match;
}
