import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "react-oidc-context";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { oidcConfig } from "./auth/oidcConfig";
import { AppLayout } from "./layout/AppLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { ExceptionWorkbenchPage } from "./pages/ExceptionWorkbenchPage";
import { ImportPage } from "./pages/ImportPage";
import { TaskQueuePage } from "./pages/TaskQueuePage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <AuthProvider {...oidcConfig}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="workbench" element={<ExceptionWorkbenchPage />} />
              <Route path="tasks" element={<TaskQueuePage />} />
              <Route path="imports" element={<ImportPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </AuthProvider>
  );
}
