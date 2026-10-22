import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./lib/auth-provider";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AppLayout } from "./components/layout/AppLayout";
import { ToastContainer } from "./components/ui";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { tenantSlugForHostname } from "./lib/useTenantSlug";

const HomePage = lazy(() => import("./pages/HomePage").then(({ HomePage }) => ({ default: HomePage })));
const AgendaPage = lazy(() =>
  import("./pages/AgendaPage").then(({ AgendaPage }) => ({ default: AgendaPage })),
);
const PublicBookingPage = lazy(() =>
  import("./pages/PublicBookingPage").then(({ PublicBookingPage }) => ({ default: PublicBookingPage })),
);
const MagicLinkPage = lazy(() =>
  import("./pages/MagicLinkPage").then(({ MagicLinkPage }) => ({ default: MagicLinkPage })),
);
const ServicesPage = lazy(() =>
  import("./pages/ServicesPage").then(({ ServicesPage }) => ({ default: ServicesPage })),
);
const ProfessionalsPage = lazy(() => import("./pages/ProfessionalsPage").then(({ ProfessionalsPage }) => ({ default: ProfessionalsPage })));
const CustomersPage = lazy(() => import("./pages/CustomersPage").then(({ CustomersPage }) => ({ default: CustomersPage })));
const PlanPage = lazy(() => import("./pages/PlanPage").then(({ PlanPage }) => ({ default: PlanPage })));
const MetricsPage = lazy(() => import("./pages/MetricsPage").then(({ MetricsPage }) => ({ default: MetricsPage })));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage").then(({ NotificationsPage }) => ({ default: NotificationsPage })));
const TeamPage = lazy(() => import("./pages/TeamPage").then(({ TeamPage }) => ({ default: TeamPage })));
const OrganizationSettingsPage = lazy(() => import("./pages/OrganizationSettingsPage").then(({ OrganizationSettingsPage }) => ({ default: OrganizationSettingsPage })));
const DevUiPage = lazy(() => import("./pages/DevUiPage").then(({ DevUiPage }) => ({ default: DevUiPage })));
const InvitationAcceptPage = lazy(() => import("./pages/InvitationAcceptPage").then(({ InvitationAcceptPage }) => ({ default: InvitationAcceptPage })));
const PasswordResetRequestPage = lazy(() => import("./pages/PasswordResetPage").then(({ PasswordResetRequestPage }) => ({ default: PasswordResetRequestPage })));
const PasswordResetConfirmPage = lazy(() => import("./pages/PasswordResetPage").then(({ PasswordResetConfirmPage }) => ({ default: PasswordResetConfirmPage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

function AppLoading() {
  return <div className="loading-panel min-h-screen">Carregando…</div>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<AppLoading />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/esqueci-senha" element={<PasswordResetRequestPage />} />
              <Route path="/resetar-senha/:uidb64/:token" element={<PasswordResetConfirmPage />} />
              <Route path="/cadastro" element={<RegisterPage />} />
              <Route path="/convite/:token" element={<InvitationAcceptPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route
                path="/app"
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<HomePage />} />
                <Route path="agenda" element={<AgendaPage />} />
                <Route
                  path="servicos"
                  element={
                    <ProtectedRoute roles={["OWNER", "MANAGER"]}>
                      <ServicesPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="profissionais"
                  element={
                    <ProtectedRoute roles={["OWNER", "MANAGER"]}>
                      <ProfessionalsPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="clientes"
                  element={
                    <ProtectedRoute roles={["OWNER", "MANAGER"]}>
                      <CustomersPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="plano"
                  element={
                    <ProtectedRoute roles={["OWNER", "MANAGER"]}>
                      <PlanPage />
                    </ProtectedRoute>
                  }
                />
                <Route path="metricas" element={<MetricsPage />} />
                <Route
                  path="notificacoes"
                  element={
                    <ProtectedRoute roles={["OWNER", "MANAGER"]}>
                      <NotificationsPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="equipe"
                  element={
                    <ProtectedRoute roles={["OWNER", "MANAGER"]}>
                      <TeamPage />
                    </ProtectedRoute>
                  }
                />
                <Route path="configuracoes" element={<OrganizationSettingsPage />} />
                <Route path="dev/ui" element={<DevUiPage />} />
              </Route>
              <Route path="/b/:slug" element={<PublicBookingPage />} />
              <Route path="/a/:token" element={<MagicLinkPage />} />
              <Route
                path="/"
                element={
                  tenantSlugForHostname(window.location.hostname) ? (
                    <PublicBookingPage />
                  ) : (
                    <Navigate to="/app" replace />
                  )
                }
              />
              <Route path="*" element={<Navigate to="/app" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
        <ToastContainer />
      </AuthProvider>
    </QueryClientProvider>
  );
}
