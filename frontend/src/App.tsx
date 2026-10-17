import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./lib/auth-provider";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { tenantSlugForHostname } from "./lib/useTenantSlug";

const AgendaPage = lazy(() =>
  import("./pages/AgendaPage").then(({ AgendaPage }) => ({ default: AgendaPage })),
);
const PublicBookingPage = lazy(() =>
  import("./pages/PublicBookingPage").then(({ PublicBookingPage }) => ({ default: PublicBookingPage })),
);

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
              <Route
                path="/app/agenda"
                element={
                  <ProtectedRoute>
                    <AgendaPage />
                  </ProtectedRoute>
                }
              />
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
