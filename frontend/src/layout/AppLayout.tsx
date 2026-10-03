import { useQuery } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import { NavLink, Outlet } from "react-router-dom";
import { apiFetch } from "../api/client";
import { MeContext, type MeResponse } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";

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
      <main style={{ fontFamily: "system-ui", padding: "2rem", maxWidth: 640 }}>
        <h1>RevenueFlow AI</h1>
        <p>
          Backend health:{" "}
          {healthQuery.isLoading && "checking…"}
          {healthQuery.isError && <span role="alert">unreachable</span>}
          {healthQuery.data && <span>{healthQuery.data.status}</span>}
        </p>
        <button onClick={() => auth.signinRedirect()}>Sign in with Keycloak</button>
      </main>
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
            {me.role === "admin" && <NavLink to="/imports">Import</NavLink>}
            {me.role === "admin" && <NavLink to="/admin">Admin</NavLink>}
          </nav>
          <span className="app-user">
            {me.display_name} · {me.role}
          </span>
          <button onClick={() => auth.signoutRedirect()}>Sign out</button>
        </header>
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </MeContext.Provider>
  );
}
