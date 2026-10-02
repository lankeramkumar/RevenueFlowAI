import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "react-oidc-context";
import { oidcConfig } from "./auth/oidcConfig";
import { StatusPage } from "./pages/StatusPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <AuthProvider {...oidcConfig}>
      <QueryClientProvider client={queryClient}>
        <StatusPage />
      </QueryClientProvider>
    </AuthProvider>
  );
}
