import { useQuery } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import { NavLink, Outlet } from "react-router-dom";
import { apiFetch } from "../api/client";
import { MeContext, type MeResponse } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";
import { ISSUES_URL, REPO_URL } from "../ui/contact";

function SiteFooter() {
  return (
    <footer className="site-footer">
      <span>RevenueFlow AI · synthetic data demo</span>
      <span>
        <a href="/help">Help</a> · <a href={ISSUES_URL} target="_blank" rel="noreferrer">Contact</a> ·{" "}
        <a href={REPO_URL} target="_blank" rel="noreferrer">Source</a>
      </span>
    </footer>
  );
}

/** Signs the user in, loads /me, and renders the nav + routed page once ready. */
export function AppLayout() {
  const auth = useAuth();
  const apiFetchAuthed = useApi();

  const healthQuery = useQuery({
    queryKey: ["healthz"],
    queryFn: () => apiFetch<{ status: string }>("/healthz", undefined),
  });

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetchAuthed<MeResponse>("/api/v1/me"),
    enabled: auth.isAuthenticated,
  });

  if (auth.isLoading) return <p>Loading authentication state…</p>;
  if (auth.error) return <p role="alert">Authentication error: {auth.error.message}</p>;

  if (!auth.isAuthenticated) {
    return (
      <div className="landing">
        <header className="landing__top">
          <span className="app-brand">RevenueFlow AI</span>
          <button type="button" onClick={() => auth.signinRedirect()}>Sign in</button>
        </header>
        <main className="landing__main">
          <section className="landing__hero">
            <h1>Find where billing and cash are blocked, and see the evidence.</h1>
            <p>
              RevenueFlow AI checks order-to-cash data for unbilled shipments, order holds, overdue invoices, and
              unmatched receipts. Every answer cites the records it is based on.
            </p>
            <button type="button" onClick={() => auth.signinRedirect()}>Sign in to continue</button>
            <p className="landing__status">
              Service status:{" "}
              {healthQuery.isLoading && "checking…"}
              {healthQuery.isError && <span role="alert">unreachable</span>}
              {healthQuery.data && <span className="landing__ok">{healthQuery.data.status}</span>}
            </p>
          </section>
          <section className="landing__features" aria-label="What you can do">
            <div className="card">
              <h3>Dashboard</h3>
              <p>Invoice aging by currency, with the as-of date.</p>
            </div>
            <div className="card">
              <h3>Investigate</h3>
              <p>Ask a question in plain English and check each cited record.</p>
            </div>
            <div className="card">
              <h3>Exceptions</h3>
              <p>Unbilled shipments and active order holds, with evidence for each row.</p>
            </div>
            <div className="card">
              <h3>Customers and Documents</h3>
              <p>One customer's full picture, and source documents that answers can cite.</p>
            </div>
          </section>
          <p className="landing__help">
            New here? Sign in, then open <strong>Help</strong> for a guide to every screen, or see the contact
            details there.
          </p>
        </main>
        <SiteFooter />
      </div>
    );
  }

  if (meQuery.isLoading) {
    return <p style={{ padding: "2rem" }}>Loading your access…</p>;
  }
  if (meQuery.isError) {
    return <p role="alert" style={{ padding: "2rem" }}>Could not load your account/business units.</p>;
  }

  const me = meQuery.data!;
  if (me.business_units.length === 0) {
    return <p style={{ padding: "2rem" }}>No business unit access yet — ask an admin to grant one.</p>;
  }

  return (
    <MeContext.Provider value={me}>
      <div>
        <header className="app-header">
          <span className="app-brand">RevenueFlow AI</span>
          <nav className="app-nav">
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/chat">Investigate</NavLink>
            <NavLink to="/workbench">Exceptions</NavLink>
            <NavLink to="/customers">Customers</NavLink>
            <NavLink to="/tasks">Tasks</NavLink>
            <NavLink to="/documents">Documents</NavLink>
            {me.role === "admin" && <NavLink to="/imports">Import</NavLink>}
            {me.role === "admin" && <NavLink to="/admin">Admin</NavLink>}
            <NavLink to="/help">Help</NavLink>
          </nav>
          <span className="app-user">
            {me.display_name} · {me.role}
          </span>
          <button onClick={() => auth.signoutRedirect()}>Sign out</button>
        </header>
        <main className="app-main">
          <Outlet />
        </main>
        <SiteFooter />
      </div>
    </MeContext.Provider>
  );
}
