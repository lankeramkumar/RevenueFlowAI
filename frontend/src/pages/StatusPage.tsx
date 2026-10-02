import { useQuery } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import { apiFetch } from "../api/client";
import { useApi } from "../hooks/useApi";
import { DashboardPage } from "./DashboardPage";

interface MeResponse {
  email: string;
  display_name: string;
  role: string;
  organization_id: string;
  business_units: { id: string; code: string; name: string }[];
}

export function StatusPage() {
  const auth = useAuth();
  const apiFetch2 = useApi();

  const healthQuery = useQuery({
    queryKey: ["healthz"],
    queryFn: () => apiFetch<{ status: string }>("/healthz", undefined),
  });

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch2<MeResponse>("/api/v1/me"),
    enabled: auth.isAuthenticated,
  });

  if (auth.isLoading) {
    return <p>Loading authentication state…</p>;
  }

  if (auth.error) {
    return <p role="alert">Authentication error: {auth.error.message}</p>;
  }

  return (
    <main style={{ fontFamily: "system-ui", padding: "2rem", maxWidth: 640 }}>
      <h1>RevenueFlow AI</h1>
      <p>
        Backend health:{" "}
        {healthQuery.isLoading && "checking…"}
        {healthQuery.isError && <span role="alert">unreachable</span>}
        {healthQuery.data && <span>{healthQuery.data.status}</span>}
      </p>

      {auth.isAuthenticated ? (
        <>
          <p>Signed in as {auth.user?.profile.email ?? auth.user?.profile.preferred_username}</p>
          <button onClick={() => auth.signoutRedirect()}>Sign out</button>

          {meQuery.isLoading && <p>Loading your access…</p>}
          {meQuery.isError && <p role="alert">Could not load your account/business units.</p>}
          {meQuery.data && meQuery.data.business_units.length === 0 && (
            <p>No business unit access yet — ask an admin to grant one.</p>
          )}
          {meQuery.data && meQuery.data.business_units.length > 0 && (
            <DashboardPage businessUnitId={meQuery.data.business_units[0].id} />
          )}
        </>
      ) : (
        <button onClick={() => auth.signinRedirect()}>Sign in with Keycloak</button>
      )}
    </main>
  );
}
