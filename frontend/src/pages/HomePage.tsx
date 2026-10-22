import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, Clock3, Sparkles, Users } from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { Button, Card, SkeletonList } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth-context";

type Row<T> = T[] | { count: number; results: T[] };
type Appointment = { id: number; customer_name: string; status: string; items: { start_at: string; service_name: string }[] };

const rows = <T,>(data: Row<T>) => (Array.isArray(data) ? data : data.results);
const count = <T,>(data: Row<T>) => (Array.isArray(data) ? data.length : data.count);
const localDate = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

export function HomePage() {
  const { user } = useAuth();
  const today = localDate(new Date());
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const canManage = user?.role === "OWNER" || user?.role === "MANAGER";

  const appointments = useQuery({
    queryKey: ["appointments", "home", today],
    queryFn: async () =>
      rows(
        (
          await api.get<Row<Appointment>>("/appointments/", {
            params: { date: today, page_size: 50 },
          })
        ).data,
      ),
  });

  const customers = useQuery({
    queryKey: ["customers", "count"],
    enabled: canManage,
    queryFn: async () => count((await api.get<Row<{ id: number }>>("/customers/", { params: { page_size: 1 } })).data),
  });

  const services = useQuery({
    queryKey: ["services", "count"],
    enabled: canManage,
    queryFn: async () => count((await api.get<Row<{ id: number }>>("/services/", { params: { page_size: 1 } })).data),
  });

  const todayList = useMemo(() => {
    const list = appointments.data ?? [];
    return [...list]
      .filter(item => item.items.length && item.status !== "CANCELED")
      .sort((a, b) => (a.items[0]?.start_at ?? "").localeCompare(b.items[0]?.start_at ?? ""));
  }, [appointments.data]);

  const upcoming = todayList.filter(
    item =>
      (item.status === "SCHEDULED" || item.status === "CONFIRMED") &&
      new Date(item.items[0]?.start_at ?? 0).getTime() >= now,
  );
  const pending = todayList.filter(item => item.status === "SCHEDULED").length;

  return (
    <main className="page-content">
      <PageHeader
        eyebrow="VISÃO GERAL"
        title={`Olá, ${user?.first_name || "equipe"}`}
        description="Resumo do dia e atalhos para o que importa agora."
        actions={
          <Link to="/app/agenda">
            <Button className="agenda-new-button">
              <CalendarPlus size={18} aria-hidden />
              Abrir agenda
            </Button>
          </Link>
        }
      />

      {appointments.isError && (
        <p role="alert" className="notice-error panel p-4">
          {errorMessage(appointments.error)}
        </p>
      )}

      <section className="agenda-stats" aria-label="Indicadores do dia">
        <Card className="agenda-stat card-hover">
          <span className="agenda-stat-icon"><Clock3 size={20} /></span>
          <div>
            <small>Hoje</small>
            <strong>{appointments.isLoading ? "—" : todayList.length}</strong>
            <span>atendimento(s)</span>
          </div>
        </Card>
        <Card className="agenda-stat card-hover">
          <span className="agenda-stat-icon"><Sparkles size={20} /></span>
          <div>
            <small>Próximos</small>
            <strong>{appointments.isLoading ? "—" : upcoming.length}</strong>
            <span>restantes hoje</span>
          </div>
        </Card>
        <Card className="agenda-stat card-hover">
          <span className="agenda-stat-icon"><Users size={20} /></span>
          <div>
            <small>Pendentes</small>
            <strong>{appointments.isLoading ? "—" : pending}</strong>
            <span>aguardando confirmação</span>
          </div>
        </Card>
        {canManage && (
          <Card className="agenda-stat card-hover">
            <span className="agenda-stat-icon"><Users size={20} /></span>
            <div>
              <small>Base</small>
              <strong>{customers.isLoading ? "—" : (customers.data ?? "•")}</strong>
              <span>clientes ativos</span>
            </div>
          </Card>
        )}
      </section>

      <section className="panel p-5 home-upcoming">
        <div className="agenda-section-heading">
          <div>
            <p className="eyebrow">HOJE</p>
            <h2>Próximos horários</h2>
          </div>
          <Link to="/app/agenda" className="button-quiet">
            Ver calendário
          </Link>
        </div>
        {appointments.isLoading ? (
          <SkeletonList count={3} />
        ) : upcoming.length ? (
          <ul className="home-upcoming-list">
            {upcoming.slice(0, 6).map(item => {
              const start = new Date(item.items[0]?.start_at ?? "");
              return (
                <li key={item.id}>
                  <strong>{start.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</strong>
                  <span>{item.customer_name}</span>
                  <small>{item.items.map(i => i.service_name).join(", ")}</small>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="empty-state compact-empty">
            <h2>Agenda livre por enquanto</h2>
            <p>Crie um horário ou compartilhe o link de reserva com seus clientes.</p>
            <Link to="/app/agenda">
              <Button variant="secondary">Novo agendamento</Button>
            </Link>
          </div>
        )}
      </section>

      {canManage && services.data === 0 && (
        <p className="notice-card mt-4">
          Seu catálogo ainda está vazio.{" "}
          <Link to="/app/servicos" className="text-accent-strong underline">
            Cadastre o primeiro serviço
          </Link>
          .
        </p>
      )}
    </main>
  );
}
