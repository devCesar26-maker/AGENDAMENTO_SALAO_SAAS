import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BarChart3,
  Bell,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Home,
  Menu,
  Scissors,
  Search,
  Settings,
  Sparkles,
  SunMoon,
  UserCircle2,
  Users,
  UsersRound,
  X,
} from "lucide-react";
import { AppearanceSettings } from "../AppearanceSettings";
import { BrandMark } from "../BrandMark";
import { OnboardingChecklist } from "../OnboardingChecklist";
import { useAuth } from "../../lib/auth-context";
import { applyAccentColor, getStoredScheme, setStoredScheme, type ColorScheme } from "../../lib/theme";
import { syncTenantPublicCacheFromOrg } from "../../hooks/usePublicTenantBranding";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

type NavItem = { label: string; to: string; icon: ReactNode; roles?: ("OWNER" | "MANAGER" | "PROFESSIONAL")[] };

const navGroups: { title: string; items: NavItem[] }[] = [
  {
    title: "Principal",
    items: [
      { label: "Início", to: "/app", icon: <Home size={18} strokeWidth={1.75} /> },
      { label: "Agenda", to: "/app/agenda", icon: <CalendarDays size={18} strokeWidth={1.75} /> },
    ],
  },
  {
    title: "Operação",
    items: [
      { label: "Serviços", to: "/app/servicos", icon: <Sparkles size={18} strokeWidth={1.75} />, roles: ["OWNER", "MANAGER"] },
      { label: "Profissionais", to: "/app/profissionais", icon: <Scissors size={18} strokeWidth={1.75} />, roles: ["OWNER", "MANAGER"] },
      { label: "Clientes", to: "/app/clientes", icon: <Users size={18} strokeWidth={1.75} />, roles: ["OWNER", "MANAGER"] },
    ],
  },
  {
    title: "Gestão",
    items: [
      { label: "Equipe", to: "/app/equipe", icon: <UsersRound size={18} strokeWidth={1.75} />, roles: ["OWNER", "MANAGER"] },
      { label: "Métricas", to: "/app/metricas", icon: <BarChart3 size={18} strokeWidth={1.75} /> },
      { label: "Lista de espera", to: "/app/notificacoes", icon: <Bell size={18} strokeWidth={1.75} />, roles: ["OWNER", "MANAGER"] },
      { label: "Plano", to: "/app/plano", icon: <CreditCard size={18} strokeWidth={1.75} />, roles: ["OWNER", "MANAGER"] },
      { label: "Configurações", to: "/app/configuracoes", icon: <Settings size={18} strokeWidth={1.75} /> },
    ],
  },
];

function canSee(item: NavItem, role: string | null | undefined) {
  if (!item.roles) return true;
  return !!role && item.roles.includes(role as "OWNER" | "MANAGER" | "PROFESSIONAL");
}

export function AppLayout({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [scheme, setScheme] = useState<ColorScheme>(() => getStoredScheme());
  const [query, setQuery] = useState("");

  const slug = user?.organization?.slug ?? "";
  const org = useQuery({
    queryKey: ["organization", slug],
    enabled: !!slug,
    queryFn: async () =>
      (await api.get<{ slug: string; name: string; phone: string; address: string; tema_cor: string }>(`/organizations/${slug}/`)).data,
  });

  useEffect(() => {
    if (!org.data) return;
    if (org.data.tema_cor) applyAccentColor(org.data.tema_cor);
    syncTenantPublicCacheFromOrg(org.data);
  }, [org.data]);

  useEffect(() => {
    setMobileOpen(false);
    setQuery("");
  }, [location.pathname]);

  const visibleGroups = useMemo(
    () =>
      navGroups
        .map(group => ({ ...group, items: group.items.filter(item => canSee(item, user?.role)) }))
        .filter(group => group.items.length > 0),
    [user?.role],
  );

  const searchHits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return visibleGroups.flatMap(g => g.items).filter(item => item.label.toLowerCase().includes(q));
  }, [query, visibleGroups]);

  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase();

  function cycleScheme() {
    const next: ColorScheme = scheme === "dark" ? "light" : scheme === "light" ? "system" : "dark";
    setScheme(next);
    setStoredScheme(next);
  }

  const schemeLabel = scheme === "system" ? "Sistema" : scheme === "light" ? "Claro" : "Escuro";

  return (
    <div className={`app-shell app-shell-sidebar ${collapsed ? "is-collapsed" : ""}`}>
      {mobileOpen && <button type="button" className="sidebar-scrim" aria-label="Fechar menu" onClick={() => setMobileOpen(false)} />}
      <aside className={`app-sidebar ${mobileOpen ? "is-open" : ""}`} aria-label="Navegação do aplicativo">
        <div className="sidebar-brand">
          <Link to="/app" className="brand-lockup" aria-label="Éclat, ir para início">
            <BrandMark label={org.data?.name ?? "É"} />
            {!collapsed && (
              <span>
                <strong>{org.data?.name ?? "Éclat"}</strong>
                <small>GESTÃO DO ESTÚDIO</small>
              </span>
            )}
          </Link>
          <button type="button" className="icon-button sidebar-close-mobile" aria-label="Fechar menu" onClick={() => setMobileOpen(false)}>
            <X size={18} />
          </button>
        </div>

        <div className="sidebar-search">
          <Search size={16} className="sidebar-search-icon" aria-hidden />
          <input
            className="field-input sidebar-search-input"
            placeholder={collapsed ? "Buscar…" : "Buscar telas…"}
            value={query}
            onChange={event => setQuery(event.target.value)}
            aria-label="Buscar telas"
          />
        </div>
        {searchHits.length > 0 && (
          <div className="sidebar-search-results" role="listbox">
            {searchHits.map(item => (
              <Link key={item.to} to={item.to} className="sidebar-search-hit" role="option" onClick={() => setQuery("")}>
                {item.label}
              </Link>
            ))}
          </div>
        )}

        <nav className="sidebar-nav">
          {visibleGroups.map(group => (
            <div key={group.title} className="sidebar-group">
              {!collapsed && <p className="sidebar-group-title">{group.title}</p>}
              {group.items.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/app"}
                  className={({ isActive }) => `sidebar-link ${isActive ? "is-active" : ""}`.trim()}
                  title={collapsed ? item.label : undefined}
                >
                  <span className="sidebar-link-icon">{item.icon}</span>
                  {!collapsed && <span>{item.label}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button type="button" className="sidebar-link sidebar-link-button" onClick={cycleScheme} title={`Tema: ${schemeLabel}`}>
            <span className="sidebar-link-icon"><SunMoon size={18} strokeWidth={1.75} /></span>
            {!collapsed && <span>Tema · {schemeLabel}</span>}
          </button>
          {!collapsed && <AppearanceSettings organizationSlug={user?.organization?.slug} />}
          <div className="sidebar-user">
            <span className="user-avatar" aria-hidden="true">{initials || <UserCircle2 size={16} />}</span>
            {!collapsed && (
              <span className="user-chip" title={user?.email ?? ""}>
                {user?.email}
              </span>
            )}
          </div>
          <button type="button" className="button-quiet sidebar-logout" onClick={() => void logout()}>
            Sair
          </button>
          <button
            type="button"
            className="icon-button sidebar-collapse"
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
            onClick={() => setCollapsed(value => !value)}
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-mobile-topbar">
          <button type="button" className="icon-button" aria-label="Abrir menu" onClick={() => setMobileOpen(true)}>
            <Menu size={20} />
          </button>
          <Link to="/app" className="brand-lockup">
            <BrandMark />
            <strong>Éclat</strong>
          </Link>
        </header>
        <div className="app-main-inner">
          <OnboardingChecklist />
          {children ?? <Outlet />}
        </div>
      </div>
    </div>
  );
}
