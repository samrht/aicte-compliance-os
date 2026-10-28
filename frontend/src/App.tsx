import { Bell, FileCheck2, FileSearch, FlaskConical, LayoutDashboard, LogOut, Menu, Network, ScrollText, Activity, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, getAdmin, setAdmin } from "./api";
import { usePoll } from "./components/ui";
import AdminDocuments from "./pages/AdminDocuments";
import AdminLogin from "./pages/AdminLogin";
import AdminStats from "./pages/AdminStats";
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

function SignOut({ onDone }: { onDone?: () => void }) {
  const nav = useNavigate();
  return (
    <button onClick={() => { setSession(null); onDone?.(); nav("/"); }}
      className="flex items-center gap-2 rounded-md px-3 py-2 text-sm opacity-80 hover:opacity-100">
      <LogOut size={16} /> Sign out
    </button>
  );
}

type NavItem = { to: string; end?: boolean; icon: typeof Bell; label: string; count?: number };

function NavList({ links, onPick }: { links: NavItem[]; onPick?: () => void }) {
  return (
    <nav className="flex flex-1 flex-col gap-0.5">
      {links.map(({ to, end, icon: Icon, label, count }) => (
        <NavLink key={to} to={to} end={end} onClick={onPick}
          className={({ isActive }) => `flex items-center gap-2.5 rounded-md px-3 py-2.5 text-[14px] ${isActive ? "bg-white/12 font-medium" : "text-white/75 hover:bg-white/6 hover:text-white"}`}>
          <Icon size={17} /> <span className="flex-1">{label}</span>
          {count ? <span className="rounded-full bg-white/15 px-2 text-[12px]">{count}</span> : null}
        </NavLink>
      ))}
    </nav>
  );
}

/** Desktop: fixed sidebar. Phone: top bar with a menu that slides in over the page. */
function ConsoleShell({ title, subtitle, links, footer }: {
  title: string; subtitle: string; links: NavItem[]; footer: (close: () => void) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  const current = links.find((l) => (l.end ? loc.pathname === l.to : loc.pathname.startsWith(l.to)));
  const brand = (
    <div className="flex items-center gap-2.5">
      <Seal className="size-8 shrink-0 text-[#9db4ff]" />
      <div className="leading-tight">
        <p className="text-[15px] font-semibold">{title}</p>
        <p className="text-[12px] text-white/60">{subtitle}</p>
      </div>
    </div>
  );
  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-[236px] shrink-0 flex-col bg-ink px-3 py-5 text-white md:flex">
        <div className="mb-7 px-3">{brand}</div>
        <NavList links={links} />
        {footer(() => {})}
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 bg-ink px-4 py-3 text-white md:hidden">
          {brand}
          <button aria-label="Open menu" onClick={() => setOpen(true)} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px]">
            <span className="max-w-[120px] truncate text-white/70">{current?.label}</span>
            <Menu size={22} />
          </button>
        </header>
        {open && (
          <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true">
            <button aria-label="Close menu" className="absolute inset-0 bg-ink/50" onClick={() => setOpen(false)} />
            <div className="absolute inset-y-0 right-0 flex w-[min(300px,85vw)] flex-col bg-ink px-3 py-4 text-white shadow-xl">
              <div className="mb-5 flex items-center justify-between px-3">
                <p className="text-[15px] font-semibold">Menu</p>
                <button aria-label="Close menu" onClick={() => setOpen(false)}><X size={22} /></button>
              </div>
              <NavList links={links} onPick={() => setOpen(false)} />
              {footer(() => setOpen(false))}
            </div>
          </div>
        )}
        <main className="min-w-0 px-4 py-6 md:px-9 md:py-7">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function AicteLayout() {
  const s = getSession();
  const { data } = usePoll(() => api.dashboard(), 4000);
  if (s?.role !== "aicte") return <Navigate to="/" replace />;
  const links: NavItem[] = [
    { to: "/aicte", end: true, icon: LayoutDashboard, label: "Overview" },
    { to: "/aicte/queue", icon: FileSearch, label: "Review queue", count: data?.awaiting_review },
    { to: "/aicte/alerts", icon: Bell, label: "Alerts", count: data?.open_alerts },
    { to: "/aicte/radar", icon: Network, label: "Collision radar" },
    { to: "/aicte/audit", icon: ScrollText, label: "Audit log" },
    { to: "/aicte/sandbox", icon: FlaskConical, label: "Shadow sandbox" },
  ];
  return <ConsoleShell title="Compliance OS" subtitle="AICTE regulator console" links={links}
    footer={(close) => <SignOut onDone={close} />} />;
}

function AdminSignOut({ onDone }: { onDone?: () => void }) {
  const nav = useNavigate();
  return (
    <button onClick={() => { setAdmin(null); onDone?.(); nav("/admin/login"); }}
      className="flex items-center gap-2 rounded-md px-3 py-2 text-sm opacity-80 hover:opacity-100">
      <LogOut size={16} /> Sign out
    </button>
  );
}

function AdminLayout() {
  const who = getAdmin();
  if (!who) return <Navigate to="/admin/login" replace />;
  const links: NavItem[] = [
    { to: "/admin", end: true, icon: Activity, label: "Live stats" },
    { to: "/admin/documents", icon: FileCheck2, label: "Verify documents" },
  ];
  return <ConsoleShell title="Compliance OS" subtitle={`Admin · ${who.username}`} links={links}
    footer={(close) => <AdminSignOut onDone={close} />} />;
}

function InstLayout() {
  const s = getSession();
  if (s?.role !== "inst") return <Navigate to="/" replace />;
  return (
    <div className="min-h-full">
      <header className="border-b border-rule bg-sheet">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-3 px-4 py-3 md:px-8">
          <NavLink to="/inst" className="flex min-w-0 items-center gap-2.5">
            <Seal className="size-7 shrink-0 text-seal" />
            <div className="min-w-0 leading-tight">
              <p className="text-[15px] font-semibold">AICTE approval portal</p>
              <p className="truncate text-[12px] text-ink-3">{s.name}</p>
            </div>
          </NavLink>
          <div className="shrink-0 text-ink"><SignOut /></div>
        </div>
      </header>
      <main className="mx-auto max-w-[1200px] px-4 py-6 md:px-8 md:py-7">
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
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<AdminStats />} />
        <Route path="documents" element={<AdminDocuments />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export { Seal };
