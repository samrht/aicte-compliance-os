import { Bell, FileSearch, FlaskConical, LayoutDashboard, LogOut, Network, ScrollText } from "lucide-react";
import { Navigate, NavLink, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import { usePoll } from "./components/ui";
import Alerts from "./pages/Alerts";
import Apply from "./pages/Apply";
import Audit from "./pages/Audit";
import CaseDetail from "./pages/CaseDetail";
import Dashboard from "./pages/Dashboard";
import InstCase from "./pages/InstCase";
import InstHome from "./pages/InstHome";
import Login from "./pages/Login";
import Queue from "./pages/Queue";
import Radar from "./pages/Radar";
import Sandbox from "./pages/Sandbox";

export type Session = { role: "aicte" } | { role: "inst"; id: number; name: string };

export function getSession(): Session | null {
  try { return JSON.parse(localStorage.getItem("acos-session") ?? "null"); } catch { return null; }
}
export function setSession(s: Session | null) {
  try {
    if (s) localStorage.setItem("acos-session", JSON.stringify(s));
    else localStorage.removeItem("acos-session");
  } catch { /* storage blocked: session lasts for this page only */ }
}

function Seal({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="10.5" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="2 2" />
      <path d="M11 16.5l3.2 3.2L21.5 12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SignOut() {
  const nav = useNavigate();
  return (
    <button onClick={() => { setSession(null); nav("/"); }}
      className="flex items-center gap-2 rounded-md px-3 py-2 text-sm opacity-80 hover:opacity-100">
      <LogOut size={16} /> Sign out
    </button>
  );
}

function AicteLayout() {
  const s = getSession();
  const { data } = usePoll(() => api.dashboard(), 4000);
  if (s?.role !== "aicte") return <Navigate to="/" replace />;
  const links = [
    { to: "/aicte", end: true, icon: LayoutDashboard, label: "Overview" },
    { to: "/aicte/queue", icon: FileSearch, label: "Review queue", count: data?.awaiting_review },
    { to: "/aicte/alerts", icon: Bell, label: "Alerts", count: data?.open_alerts },
    { to: "/aicte/radar", icon: Network, label: "Collision radar" },
    { to: "/aicte/audit", icon: ScrollText, label: "Audit log" },
    { to: "/aicte/sandbox", icon: FlaskConical, label: "Shadow sandbox" },
  ];
  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 flex h-screen w-[236px] shrink-0 flex-col bg-ink px-3 py-5 text-white max-md:hidden">
        <div className="mb-7 flex items-center gap-2.5 px-3">
          <Seal className="size-8 text-[#9db4ff]" />
          <div className="leading-tight">
            <p className="text-[15px] font-semibold">Compliance OS</p>
            <p className="text-[12px] text-white/60">AICTE regulator console</p>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5">
          {links.map(({ to, end, icon: Icon, label, count }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `flex items-center gap-2.5 rounded-md px-3 py-2 text-[14px] ${isActive ? "bg-white/12 font-medium" : "text-white/75 hover:bg-white/6 hover:text-white"}`}>
              <Icon size={17} /> <span className="flex-1">{label}</span>
              {count ? <span className="rounded-full bg-white/15 px-2 text-[12px]">{count}</span> : null}
            </NavLink>
          ))}
        </nav>
        <SignOut />
      </aside>
      <main className="min-w-0 flex-1 px-4 py-7 md:px-9">
        <Outlet />
      </main>
    </div>
  );
}

function InstLayout() {
  const s = getSession();
  if (s?.role !== "inst") return <Navigate to="/" replace />;
  return (
    <div className="min-h-full">
      <header className="border-b border-rule bg-sheet">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-4 px-4 py-3 md:px-8">
          <NavLink to="/inst" className="flex items-center gap-2.5">
            <Seal className="size-7 text-seal" />
            <div className="leading-tight">
              <p className="text-[15px] font-semibold">AICTE approval portal</p>
              <p className="text-[12px] text-ink-3">{s.name}</p>
            </div>
          </NavLink>
          <div className="text-ink"><SignOut /></div>
        </div>
      </header>
      <main className="mx-auto max-w-[1200px] px-4 py-7 md:px-8">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/aicte" element={<AicteLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="queue" element={<Queue />} />
        <Route path="cases/:id" element={<CaseDetail />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="radar" element={<Radar />} />
        <Route path="audit" element={<Audit />} />
        <Route path="sandbox" element={<Sandbox />} />
      </Route>
      <Route path="/inst" element={<InstLayout />}>
        <Route index element={<InstHome />} />
        <Route path="apply" element={<Apply />} />
        <Route path="cases/:id" element={<InstCase />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export { Seal };
