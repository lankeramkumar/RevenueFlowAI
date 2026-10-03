import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "react-oidc-context";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { oidcConfig } from "./auth/oidcConfig";
import { AppLayout } from "./layout/AppLayout";
import { AdminPage } from "./pages/AdminPage";
import { ChatPage } from "./pages/ChatPage";
import { CustomerDetailPage } from "./pages/CustomerDetailPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ExceptionWorkbenchPage } from "./pages/ExceptionWorkbenchPage";
import { GuidePage } from "./pages/GuidePage";
import { HelpPage } from "./pages/HelpPage";
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
              <Route path="chat" element={<ChatPage />} />
              <Route path="workbench" element={<ExceptionWorkbenchPage />} />
              <Route path="customers" element={<CustomerDetailPage />} />
              <Route path="documents" element={<DocumentsPage />} />
              <Route path="customers/:customerId" element={<CustomerDetailPage />} />
              <Route path="tasks" element={<TaskQueuePage />} />
              <Route path="imports" element={<ImportPage />} />
              <Route path="admin" element={<AdminPage />} />
              <Route path="help" element={<HelpPage />} />
              <Route path="guide" element={<GuidePage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </AuthProvider>
  );
}
