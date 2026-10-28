import { CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Seal } from "../App";
import { admin } from "../api";

export default function AdminSignup() {
  const [form, setForm] = useState({ name: "", username: "", email: "", password: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.password !== form.confirm) { setError("The two passwords don't match."); return; }
    setBusy(true);
    setError(null);
    try {
      await admin.signup(form.name, form.username, form.email, form.password);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const input = "mt-1.5 w-full rounded-lg border border-rule bg-sheet px-3 py-2.5 text-[15px]";
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-[420px]">
        <div className="mb-6 flex items-center gap-3">
          <Seal className="size-10 shrink-0 text-seal" />
          <div>
            <h1 className="text-[22px] font-semibold leading-tight">Request an admin account</h1>
            <p className="text-[14px] text-ink-2">An existing administrator approves every new account</p>
          </div>
        </div>

        {done ? (
          <div className="sheet p-6">
            <CheckCircle2 className="text-leaf" />
            <p className="mt-3 text-[16px] font-semibold">Request sent</p>
            <p className="mt-1 text-[14px] text-ink-2">
              You can sign in as <strong>{form.username.trim().toLowerCase()}</strong> once an administrator approves the
              account from the Team page.
            </p>
            <Link to="/admin/login" className="mt-5 inline-block rounded-lg bg-ink px-4 py-2.5 text-[14px] font-medium text-white">
              Go to sign-in
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="sheet space-y-4 p-6">
            <label className="block">
              <span className="text-[13px] font-medium text-ink-2">Full name</span>
              <input className={input} autoComplete="name" value={form.name} onChange={set("name")} required />
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-ink-2">Work email</span>
              <input className={input} type="email" autoComplete="email" value={form.email} onChange={set("email")} required />
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-ink-2">Username</span>
              <input className={input} autoComplete="username" value={form.username} onChange={set("username")}
                minLength={3} maxLength={32} required />
              <span className="mt-1 block text-[12px] text-ink-3">Lowercase letters, digits, dot, dash or underscore.</span>
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-ink-2">Password</span>
              <input className={input} type="password" autoComplete="new-password" value={form.password}
                onChange={set("password")} minLength={8} required />
              <span className="mt-1 block text-[12px] text-ink-3">At least 8 characters, with a letter and a number or symbol.</span>
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-ink-2">Confirm password</span>
              <input className={input} type="password" autoComplete="new-password" value={form.confirm}
                onChange={set("confirm")} required />
            </label>
            {error && <p className="rounded-lg bg-stamp-soft px-3 py-2 text-[13px] text-stamp">{error}</p>}
            <button type="submit" disabled={busy}
              className="w-full rounded-lg bg-ink px-4 py-2.5 text-[14px] font-medium text-white disabled:opacity-50">
              {busy ? "Sending request…" : "Request account"}
            </button>
          </form>
        )}
        <p className="mt-4 text-[14px] text-ink-2">
          Already have an account? <Link to="/admin/login" className="text-seal">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
