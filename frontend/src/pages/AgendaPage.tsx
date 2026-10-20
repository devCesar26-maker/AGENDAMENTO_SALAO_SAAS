import { useMemo, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppointmentWizard, type BookingData } from "../components/AppointmentWizard";
import { DashboardHeader } from "../components/DashboardHeader";
import { api, errorMessage } from "../lib/api";

type Row<T> = T[] | { results: T[] };
type Item = { service: number; service_name: string; professional: number; professional_name: string; start_at: string; end_at: string };
type Appointment = { id: number; customer: number; customer_name: string; status: string; items: Item[] };
type CalendarRange = { from: string; to: string };
const asRows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const EMPTY_APPOINTMENTS: Appointment[] = [];
const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const appointmentStart = (appointment: Appointment) => appointment.items[0]?.start_at ?? "";
const statusLabel: Record<string, string> = { SCHEDULED: "Agendado", CONFIRMED: "Confirmado", COMPLETED: "Concluído", CANCELED: "Cancelado", NO_SHOW: "Não compareceu" };

export function AgendaPage() {
  const qc = useQueryClient();
  const today = localDate(new Date());
  const [nowTimestamp] = useState(() => Date.now());
  const [selectedDate, setSelectedDate] = useState(today);
  const [range, setRange] = useState<CalendarRange>(() => {
    const start = new Date(`${today}T12:00:00`);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    const end = new Date(start);
    end.setDate(end.getDate() + 7);
    return { from: localDate(start), to: localDate(end) };
  });
  const [wizardOpen, setWizardOpen] = useState(false);
  const [active, setActive] = useState<Appointment | null>(null);
  const [formError, setFormError] = useState("");
  const appointmentQuery = useQuery({
    queryKey: ["appointments", range.from, range.to],
    queryFn: async () => asRows((await api.get<Row<Appointment>>("/appointments/", { params: { date_from: range.from, date_to: range.to, page_size: 100 } })).data),
  });
  const create = useMutation({
    mutationFn: (data: BookingData) => api.post("/appointments/", data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); void qc.invalidateQueries({ queryKey: ["customers"] }); setWizardOpen(false); setFormError(""); },
    onError: error => setFormError(errorMessage(error)),
  });
  const statusMutation = useMutation({ mutationFn: ({ id, status }: { id: number; status: string }) => api.patch(`/appointments/${id}/status/`, { status }), onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); setActive(null); } });
  const reschedule = useMutation({ mutationFn: ({ id, start_at }: { id: number; start_at: string }) => api.patch(`/appointments/${id}/reschedule/`, { start_at }), onSuccess: () => { setFormError(""); void qc.invalidateQueries({ queryKey: ["appointments"] }); }, onError: error => setFormError(errorMessage(error)) });
  const cancel = useMutation({ mutationFn: (id: number) => api.post(`/appointments/${id}/cancel/`), onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); setActive(null); } });
  const appointments = appointmentQuery.data ?? EMPTY_APPOINTMENTS;
  const events = useMemo(() => appointments.filter(appointment => appointment.items.length).map(appointment => ({
    id: String(appointment.id),
    title: `${appointment.customer_name} · ${appointment.items.map(item => item.service_name).join(", ")}`,
    start: appointment.items[0].start_at,
    end: appointment.items[appointment.items.length - 1].end_at,
    extendedProps: { appointment },
  })), [appointments]);
  const sortedAppointments = [...appointments].filter(appointment => appointment.items.length).sort((a, b) => appointmentStart(a).localeCompare(appointmentStart(b)));
  const upcoming = sortedAppointments.filter(item => new Date(appointmentStart(item)).getTime() >= nowTimestamp).slice(0, 6);
  const todayAppointments = sortedAppointments.filter(item => localDate(new Date(appointmentStart(item))) === today);
  const pendingCount = appointments.filter(item => item.status === "SCHEDULED").length;
  const openCreate = (arg?: { start: Date }) => { const date = arg ? localDate(arg.start) : today; setSelectedDate(date); setWizardOpen(true); setFormError(""); };
  const onDrop = (info: { event: { id: string; start: Date | null }; revert: () => void }) => {
    if (!info.event.start) { info.revert(); return; }
    reschedule.mutate({ id: Number(info.event.id), start_at: info.event.start.toISOString() }, { onError: () => info.revert() });
  };
  const onClick = (info: { event: { extendedProps: Record<string, unknown> } }) => setActive(info.event.extendedProps.appointment as Appointment);
  const setCalendarRange = (start: string, end: string) => {
    const from = start.slice(0, 10);
    const to = end.slice(0, 10);
    if (from && to) setRange(current => current.from === from && current.to === to ? current : { from, to });
  };

  return <div className="app-shell">
    <DashboardHeader current="Agenda" />
    <main className="page-content agenda-page">
      <section className="agenda-hero">
        <div className="agenda-hero-copy"><p className="eyebrow">SEU ESPAÇO, EM HARMONIA</p><h1>Agenda</h1><p className="muted-copy">Uma visão clara dos atendimentos e do ritmo da sua semana.</p></div>
        <button onClick={() => openCreate()} className="button-primary agenda-new-button"><span aria-hidden="true">＋</span> Novo agendamento</button>
      </section>
      {formError && <p role="alert" className="notice-error agenda-alert">{formError}</p>}
      <section className="agenda-stats" aria-label="Resumo da agenda">
        <article className="agenda-stat panel"><span className="agenda-stat-icon">◷</span><div><small>Período visível</small><strong>{appointments.length}</strong><span>atendimento(s)</span></div></article>
        <article className="agenda-stat panel"><span className="agenda-stat-icon">✦</span><div><small>Hoje</small><strong>{todayAppointments.length}</strong><span>na agenda</span></div></article>
        <article className="agenda-stat panel"><span className="agenda-stat-icon">◌</span><div><small>Aguardando confirmação</small><strong>{pendingCount}</strong><span>pendente(s)</span></div></article>
      </section>
      {appointmentQuery.isError && <p role="alert" className="panel loading-panel notice-error">Não foi possível carregar a agenda. {errorMessage(appointmentQuery.error)}</p>}
      <div className="agenda-layout">
        <section className="agenda-calendar panel" aria-label="Calendário de atendimentos">
          <div className="agenda-section-heading"><div><p className="eyebrow">CALENDÁRIO</p><h2>Sua semana</h2></div><span className="agenda-timezone">Horário local</span></div>
          {appointmentQuery.isLoading ? <p role="status" className="loading-panel">Carregando atendimentos…</p> : <FullCalendar
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="timeGridWeek"
            headerToolbar={{ left: "prev,next today", center: "title", right: "timeGridWeek,timeGridDay,dayGridMonth" }}
            locale="pt-br"
            selectable
            select={openCreate}
            editable
            eventDrop={onDrop}
            eventClick={onClick}
            events={events}
            datesSet={arg => setCalendarRange(arg.startStr, arg.endStr)}
            height="auto"
            nowIndicator
            slotMinTime="07:00:00"
            slotMaxTime="22:00:00"
            allDaySlot={false}
            expandRows
            eventTimeFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
          />}
          {!appointmentQuery.isLoading && !appointmentQuery.isError && appointments.length === 0 && <div className="agenda-empty-hint"><span>✧</span><p>Sua agenda está livre neste período.</p><button className="button-quiet" onClick={() => openCreate()}>Criar o primeiro horário</button></div>}
        </section>
        <aside className="agenda-upcoming panel">
          <div className="agenda-section-heading"><div><p className="eyebrow">EM SEGUIDA</p><h2>Próximos atendimentos</h2></div><span className="agenda-count">{upcoming.length}</span></div>
          {appointmentQuery.isLoading ? <p role="status" className="helper-copy">Carregando…</p> : upcoming.length ? <div className="agenda-upcoming-list">{upcoming.map(appointment => {
            const start = new Date(appointmentStart(appointment));
            return <button className="agenda-upcoming-item" key={appointment.id} onClick={() => setActive(appointment)}><span className="agenda-upcoming-date"><strong>{start.toLocaleDateString("pt-BR", { day: "2-digit" })}</strong><small>{start.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "")}</small></span><span className="agenda-upcoming-info"><strong>{appointment.customer_name}</strong><small>{start.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })} · {appointment.items.map(item => item.service_name).join(", ")}</small><small>{appointment.items[0]?.professional_name}</small></span><i className={`agenda-status agenda-status-${appointment.status.toLowerCase()}`}>{statusLabel[appointment.status] ?? appointment.status}</i></button>;
          })}</div> : <div className="agenda-upcoming-empty"><span>☼</span><p>Nenhum atendimento próximo nesta semana.</p><small>Os horários marcados aparecerão aqui.</small></div>}
          <div className="agenda-tip"><strong>Dica rápida</strong><p>Selecione um espaço vazio no calendário para começar um agendamento nesse dia e horário.</p></div>
        </aside>
      </div>
    </main>
    {wizardOpen && <div className="modal-backdrop"><section className="modal-card panel wizard-modal" aria-labelledby="create-title"><div className="panel-heading"><div><p className="eyebrow">NOVO HORÁRIO</p><h2 id="create-title">Agendar atendimento</h2><p className="helper-copy">{new Date(`${selectedDate}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" })}</p></div><button className="icon-button" aria-label="Fechar" onClick={() => setWizardOpen(false)}>×</button></div>{formError && <p role="alert" className="notice-error">{formError}</p>}<AppointmentWizard key={selectedDate} mode="dashboard" initialDate={selectedDate} onConfirm={data => create.mutate(data)} />{create.isPending && <p role="status" className="helper-copy">Criando agendamento…</p>}</section></div>}
    {active && <div className="fixed inset-0 z-40 flex justify-end bg-black/60" onClick={() => setActive(null)}><aside className="panel h-full w-full max-w-sm rounded-none p-5" onClick={event => event.stopPropagation()}><button className="float-right button-quiet" aria-label="Fechar detalhes" onClick={() => setActive(null)}>✕</button><p className="eyebrow">AGENDAMENTO #{active.id}</p><h2 className="mt-3 font-serif text-2xl">{active.customer_name}</h2><p className="mt-2 text-sm text-slate-600">{active.items.map(item => `${item.service_name} · ${item.professional_name}`).join(" / ")}</p><p className="mt-2 text-sm">Status: {statusLabel[active.status] ?? active.status}</p><div className="mt-5 space-y-2">{["CONFIRMED", "COMPLETED", "NO_SHOW"].map(status => <button key={status} onClick={() => statusMutation.mutate({ id: active.id, status })} className="button-quiet block w-full">Marcar {status === "NO_SHOW" ? "não compareceu" : (statusLabel[status] ?? status.toLowerCase())}</button>)}<button onClick={() => cancel.mutate(active.id)} className="button-quiet block w-full border-red-400/40 text-red-300">Cancelar agendamento</button></div>{(statusMutation.isError || cancel.isError) && <p role="alert" className="notice-error mt-3">{errorMessage(statusMutation.error ?? cancel.error)}</p>}</aside></div>}
  </div>;
}
