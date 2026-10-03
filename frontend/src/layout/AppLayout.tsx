import { useQuery } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import { Link, Outlet } from "react-router-dom";
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
      <div style={{ fontFamily: "system-ui" }}>
        <header style={{ padding: "1rem 2rem", borderBottom: "1px solid #ddd", display: "flex", gap: "1.5rem", alignItems: "center" }}>
          <strong>RevenueFlow AI</strong>
          <nav style={{ display: "flex", gap: "1rem" }}>
            <Link to="/">Dashboard</Link>
            <Link to="/chat">Investigate</Link>
            <Link to="/workbench">Exceptions</Link>
            <Link to="/customers">Customers</Link>
            <Link to="/tasks">Tasks</Link>
            {me.role === "admin" && <Link to="/imports">Import</Link>}
          </nav>
          <span style={{ marginLeft: "auto" }}>
            {me.display_name} ({me.role})
          </span>
          <button onClick={() => auth.signoutRedirect()}>Sign out</button>
        </header>
        <main style={{ padding: "2rem", maxWidth: 960 }}>
          <Outlet />
        </main>
      </div>
    </MeContext.Provider>
  );
}
