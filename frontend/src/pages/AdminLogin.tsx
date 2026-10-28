import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Seal } from "../App";
import { admin, getAdmin } from "../api";

export default function AdminLogin() {
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<{ username: string; password: string } | null>(null);

  useEffect(() => { admin.config().then((c) => setDemo(c.demo_account)).catch(() => {}); }, []);
  if (getAdmin()) return <Navigate to="/admin" replace />;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await admin.login(username, password);
      nav("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  const input = "mt-1.5 w-full rounded-lg border border-rule bg-sheet px-3 py-2.5 text-[15px]";
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-[400px]">
        <div className="mb-6 flex items-center gap-3">
          <Seal className="size-10 text-seal" />
          <div>
            <h1 className="text-[22px] font-semibold leading-tight">Admin sign-in</h1>
            <p className="text-[14px] text-ink-2">Live operations and document verification</p>
          </div>
        </div>
        <form onSubmit={submit} className="sheet space-y-4 p-6">
          <label className="block">
            <span className="text-[13px] font-medium text-ink-2">Username</span>
            <input className={input} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="block">
            <span className="text-[13px] font-medium text-ink-2">Password</span>
            <input className={input} type="password" autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error && <p className="rounded-lg bg-stamp-soft px-3 py-2 text-[13px] text-stamp">{error}</p>}
          <button type="submit" disabled={busy}
            className="w-full rounded-lg bg-ink px-4 py-2.5 text-[14px] font-medium text-white disabled:opacity-50">
            {busy ? "Signing in…" : "Sign in"}
          </button>
          {demo && (
            <p className="flex gap-2 rounded-lg bg-seal-soft p-3 text-[13px] text-ink-2">
              <ShieldCheck size={18} className="shrink-0 text-seal" />
              <span>Demo account: <strong>{demo.username}</strong> / <strong>{demo.password}</strong>.
                Set <code className="font-mono text-[12px]">ADMIN_PASSWORD</code> on the server to replace it.</span>
            </p>
          )}
        </form>
        <div className="mt-4 flex flex-wrap justify-between gap-3 text-[14px]">
          <span className="text-ink-2">New here? <Link to="/admin/signup" className="font-medium text-seal">Request an admin account</Link></span>
          <Link to="/" className="text-seal">Portal sign-in</Link>
        </div>
      </div>
    </div>
  );
}
