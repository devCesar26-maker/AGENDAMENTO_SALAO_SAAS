import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./lib/auth-provider";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { tenantSlugForHostname } from "./lib/useTenantSlug";

const AgendaPage = lazy(() =>
  import("./pages/AgendaPage").then(({ AgendaPage }) => ({ default: AgendaPage })),
);
const PublicBookingPage = lazy(() =>
  import("./pages/PublicBookingPage").then(({ PublicBookingPage }) => ({ default: PublicBookingPage })),
);
const ServicesPage = lazy(() =>
  import("./pages/ServicesPage").then(({ ServicesPage }) => ({ default: ServicesPage })),
);
const ProfessionalsPage = lazy(() => import("./pages/ProfessionalsPage").then(({ ProfessionalsPage }) => ({ default: ProfessionalsPage })));
const CustomersPage = lazy(() => import("./pages/CustomersPage").then(({ CustomersPage }) => ({ default: CustomersPage })));
const PlanPage = lazy(() => import("./pages/PlanPage").then(({ PlanPage }) => ({ default: PlanPage })));
const MetricsPage = lazy(() => import("./pages/MetricsPage").then(({ MetricsPage }) => ({ default: MetricsPage })));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage").then(({ NotificationsPage }) => ({ default: NotificationsPage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<div className="p-6 text-center text-slate-600">Carregando…</div>}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/cadastro" element={<RegisterPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route
                path="/app/agenda"
                element={
                  <ProtectedRoute>
                    <AgendaPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/app/servicos"
                element={
                  <ProtectedRoute roles={["OWNER", "MANAGER"]}>
                    <ServicesPage />
                  </ProtectedRoute>
                }
              />
              <Route path="/app/profissionais" element={<ProtectedRoute roles={["OWNER", "MANAGER"]}><ProfessionalsPage /></ProtectedRoute>} />
              <Route path="/app/clientes" element={<ProtectedRoute roles={["OWNER", "MANAGER"]}><CustomersPage /></ProtectedRoute>} />
              <Route path="/app/plano" element={<ProtectedRoute roles={["OWNER", "MANAGER"]}><PlanPage /></ProtectedRoute>} />
              <Route path="/app/metricas" element={<ProtectedRoute><MetricsPage /></ProtectedRoute>} />
              <Route path="/app/notificacoes" element={<ProtectedRoute roles={["OWNER", "MANAGER"]}><NotificationsPage /></ProtectedRoute>} />
              <Route path="/app" element={<Navigate to="/app/agenda" replace />} />
              <Route path="/b/:slug" element={<PublicBookingPage />} />
              <Route
                path="/"
                element={
                  tenantSlugForHostname(window.location.hostname) ? (
                    <PublicBookingPage />
                  ) : (
                    <Navigate to="/app/agenda" replace />
                  )
                }
              />
              <Route path="*" element={<Navigate to="/app/agenda" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
