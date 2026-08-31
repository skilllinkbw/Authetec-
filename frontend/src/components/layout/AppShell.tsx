/**
 * AppShell — responsive layout: fixed sidebar (desktop), slide-in drawer
 * (mobile), sticky topbar with live API status and dev session context.
 *
 * NOTE ON TENANCY: the workspace field below is a DEVELOPMENT convenience
 * because the platform does not yet issue user sessions. In production it
 * is replaced by authenticated identity; the UI never offers arbitrary
 * tenant switching on a deployed, authenticated system.
 */
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  getMaskedApiKey, getTenantId, hasApiKey, setApiKey, setTenantId,
} from "../../lib/api/client";
import { getHealth } from "../../lib/api/endpoints";
import { StatusDot } from "../ui";
import type { HealthOut } from "../../types/api";

interface NavItem { to: string; label: string; end?: boolean }
interface NavGroup { group: string; items: NavItem[] }

const NAV: NavGroup[] = [
  { group: "Overview", items: [
    { to: "/", label: "Dashboard", end: true },
  ]},
  { group: "Verification", items: [
    { to: "/documents", label: "Document Verification" },
    { to: "/signatures", label: "Signature Verification" },
  ]},
  { group: "Intelligence", items: [
    { to: "/payments", label: "Payment Fraud" },
    { to: "/risk", label: "Risk Intelligence" },
  ]},
  { group: "Operations", items: [
    { to: "/alerts", label: "Alerts" },
    { to: "/evidence", label: "Evidence" },
    { to: "/audit", label: "Audit" },
    { to: "/developers", label: "Developers" },
  ]},
];

export default function AppShell() {
  const [open, setOpen] = useState(false);
  const [health, setHealth] = useState<HealthOut | null>(null);
  const location = useLocation();

  useEffect(() => { setOpen(false); }, [location.pathname]);

  useEffect(() => {
    let live = true;
    const load = () => getHealth()
      .then((h) => { if (live) setHealth(h); })
      .catch(() => { if (live) setHealth(null); });
    load();
    const id = setInterval(load, 60_000); // polling fallback for live status
    return () => { live = false; clearInterval(id); };
  }, []);

  const title = NAV.flatMap((g) => g.items)
    .find((i) => (i.end ? location.pathname === i.to : location.pathname.startsWith(i.to)))
    ?.label ?? "Authetec";

  return (
    <div className="shell">
      {open && (
        <button className="scrim" aria-label="Close navigation"
          onClick={() => setOpen(false)} />
      )}
      <nav className={`sidebar ${open ? "open" : ""}`} aria-label="Primary">
        <div className="sidebar-brand">
          <img src="/authetec_logo.png" alt="Authetec logo" />
          <div>
            <span className="brand-name">AUTHETEC</span>
            <span className="brand-tag">VERIFY · PROTECT · TRUST</span>
          </div>
        </div>
        <div className="nav-group">
          {NAV.map((g) => (
            <div key={g.group}>
              <h3>{g.group}</h3>
              {g.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `nav-link${isActive ? " active" : ""}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </div>
      </nav>

      <div className="main">
        <header className="topbar">
          <button className="menu-btn" aria-label="Open navigation"
            aria-expanded={open} onClick={() => setOpen(true)}>
            ☰
          </button>
          <span className="page-title">{title}</span>
          <span className="muted" style={{ fontSize: 12.5 }}
            title="Live API component status">
            <StatusDot status={health ? health.status : "error"} />{" "}
            {health ? `API ${health.status}` : "API unreachable"}
          </span>
          <DevSession />
        </header>
        <main className="content" id="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function DevSession() {
  const [tenant, setTenant] = useState(getTenantId());
  const [key, setKey] = useState("");
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}
      title="Development session context — replaced by authenticated login in production">
      <label style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <span className="muted" style={{ fontSize: 11.5 }}>Workspace</span>
        <input
          aria-label="Workspace tenant identifier (development session)"
          value={tenant}
          onChange={(e) => { setTenant(e.target.value); setTenantId(e.target.value); }}
          style={{ width: 110, padding: "4px 8px", fontSize: 12.5 }}
        />
      </label>
      <label style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <span className="muted" style={{ fontSize: 11.5 }}>API key</span>
        <input
          aria-label="API key (stored for this browser session only)"
          type="password"
          value={key}
          placeholder={hasApiKey() ? getMaskedApiKey() : "not set"}
          onChange={(e) => setKey(e.target.value)}
          onBlur={() => { setApiKey(key); setKey(""); }}
          style={{ width: 110, padding: "4px 8px", fontSize: 12.5 }}
        />
      </label>
    </span>
  );
}
