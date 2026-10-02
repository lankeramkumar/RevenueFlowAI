import { useQuery } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import { apiFetch } from "../api/client";

/**
 * Foundation-milestone placeholder: proves the real login → API round trip
 * works (Keycloak-issued token sent to FastAPI's unauthenticated /healthz
 * and, once logged in, a real authenticated call). Replaced by the real
 * dashboard in Milestone 4.
 */
export function StatusPage() {
  const auth = useAuth();

  const healthQuery = useQuery({
    queryKey: ["healthz"],
    queryFn: () => apiFetch<{ status: string }>("/healthz", undefined),
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
        </>
      ) : (
        <button onClick={() => auth.signinRedirect()}>Sign in with Keycloak</button>
      )}
    </main>
  );
}
