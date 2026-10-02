import type { AuthProviderProps } from "react-oidc-context";

/**
 * Real OIDC config against the Keycloak realm started in docker-compose —
 * no auth bypass. VITE_* vars are build-time, non-secret (public client).
 */
export const oidcConfig: AuthProviderProps = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY ?? "http://localhost:8080/realms/revenueflow",
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID ?? "revenueflow-frontend",
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  scope: "openid profile email",
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};
