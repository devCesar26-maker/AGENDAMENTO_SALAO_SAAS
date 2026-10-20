import { useState } from "react";
import { Link } from "react-router-dom";
import { AppearanceSettings } from "./AppearanceSettings";
import { useAuth } from "../lib/auth-context";

const primaryLinks = [
  ["Agenda", "/app/agenda"],
  ["Serviços", "/app/servicos"],
  ["Profissionais", "/app/profissionais"],
  ["Clientes", "/app/clientes"],
];

const managementLinks = [
  ["Equipe", "/app/equipe"],
  ["Configurações", "/app/configuracoes"],
  ["Plano", "/app/plano"],
  ["Métricas", "/app/metricas"],
  ["Notificações", "/app/notificacoes"],
];

export function DashboardHeader({ current }: { current: string }) {
  const { user, logout } = useAuth();
  const [moreOpen, setMoreOpen] = useState(false);
  const canManage = user?.role !== "PROFESSIONAL";
  const mainLinks = canManage ? primaryLinks : primaryLinks.slice(0, 1);
  const moreLinks = canManage ? managementLinks : managementLinks.slice(1, 2);
  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase();

  return (
    <header className="topbar">
      <Link className="brand-lockup" to="/app/agenda" aria-label="Éclat, ir para a agenda">
        <span className="brand-mark">É</span>
        <span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span>
      </Link>
      <nav className="topnav" aria-label="Navegação principal">
        {mainLinks.map(([label, href]) => label === current ? (
          <span className="nav-current" key={href} aria-current="page">{label}</span>
        ) : (
          <Link to={href} key={href} onClick={() => setMoreOpen(false)}>{label}</Link>
        ))}
        {moreLinks.length > 0 && (
          <div className="nav-more">
            <button className={`nav-more-trigger ${moreOpen || moreLinks.some(([label]) => label === current) ? "is-active" : ""}`} type="button" aria-expanded={moreOpen} aria-haspopup="true" onClick={() => setMoreOpen(value => !value)}>
              Mais <span aria-hidden="true">⌄</span>
            </button>
            {moreOpen && <div className="nav-more-menu" role="menu">
              {moreLinks.map(([label, href]) => label === current ? (
                <span className="nav-more-current" key={href} role="menuitem" aria-current="page">{label}</span>
              ) : (
                <Link to={href} key={href} role="menuitem" onClick={() => setMoreOpen(false)}>{label}</Link>
              ))}
            </div>}
          </div>
        )}
      </nav>
      <div className="topbar-actions">
        <span className="user-avatar" aria-hidden="true">{initials || "É"}</span>
        <span className="user-chip">{user?.email}</span>
        <AppearanceSettings organizationSlug={user?.organization?.slug} />
        <button className="button-quiet logout-button" onClick={() => void logout()}>Sair</button>
      </div>
    </header>
  );
}
