import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth, type Role } from "../lib/auth";

export function ProtectedRoute({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">Carregando…</div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  // PROFESSIONAL vê apenas a própria agenda/comissões: rotas de gestão exigem OWNER/MANAGER.
  if (roles && (!user.role || !roles.includes(user.role))) {
    return <Navigate to="/app/agenda" replace />;
  }
  return <>{children}</>;
}
