import { useAuth } from "react-oidc-context";
import { apiFetch } from "../api/client";

/** Returns a fetch function bound to the current user's access token. */
export function useApi() {
  const auth = useAuth();
  const accessToken = auth.user?.access_token;

  return <T,>(path: string, init?: RequestInit) => apiFetch<T>(path, accessToken, init);
}
