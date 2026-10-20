import { AppearanceSettings } from "./AppearanceSettings";
import { useAuth } from "../lib/auth-context";

export function DashboardHeader({ current }: { current: string }) {
  const { user, logout } = useAuth();
  const management = user?.role !== "PROFESSIONAL";
  const items = [
    ["Agenda", "/app/agenda"], ["Serviços", "/app/servicos"], ["Profissionais", "/app/profissionais"],
    ["Clientes", "/app/clientes"], ["Equipe", "/app/equipe"], ["Configurações", "/app/configuracoes"],
    ["Plano", "/app/plano"], ["Métricas", "/app/metricas"], ["Notificações", "/app/notificacoes"],
  ].filter(([label]) => management || label === "Agenda" || label === "Configurações");
  return <header className="topbar"><a className="brand-lockup" href="/app/agenda"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></a><nav className="topnav">{items.map(([label, href]) => current === label ? <span className="nav-current" key={href}>{label}</span> : <a href={href} key={href}>{label}</a>)}</nav><div className="topbar-actions"><span className="user-chip">{user?.email}</span><AppearanceSettings organizationSlug={user?.organization?.slug} /><button className="button-quiet" onClick={() => void logout()}>Sair</button></div></header>;
}
