import type { User } from "oidc-client-ts";

/**
 * Which token the API receives. Keycloak (local development) issues an access
 * token whose audience is the API. Cognito access tokens carry no email claim,
 * so the AWS build sends the ID token, whose audience is the app client.
 */
const KIND = import.meta.env.VITE_API_TOKEN_KIND === "id" ? "id" : "access";

export function apiToken(user: User | null | undefined): string | undefined {
  if (!user) return undefined;
  return KIND === "id" ? user.id_token : user.access_token;
}
