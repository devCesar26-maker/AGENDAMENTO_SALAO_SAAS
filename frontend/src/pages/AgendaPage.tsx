import { useMemo, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppointmentWizard, type BookingData } from "../components/AppointmentWizard";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth-context";

type Row<T> = T[] | { results: T[] };
type Item = { service: number; service_name: string; professional: number; professional_name: string; start_at: string; end_at: string };
type Appointment = { id: number; customer: number; customer_name: string; status: string; items: Item[] };
const asRows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

export function AgendaPage() {
  const { user, logout } = useAuth();
  const qc = useQueryClient();
  const [selectedDate, setSelectedDate] = useState(localDate(new Date()));
  const [wizardOpen, setWizardOpen] = useState(false);
  const [active, setActive] = useState<Appointment | null>(null);
  const [formError, setFormError] = useState("");
  const appointmentQuery = useQuery({ queryKey: ["appointments", selectedDate], queryFn: async () => asRows((await api.get<Row<Appointment>>("/appointments/", { params: { date: selectedDate } })).data) });
  const create = useMutation({ mutationFn: (data: BookingData) => api.post("/appointments/", data), onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); void qc.invalidateQueries({ queryKey: ["customers"] }); setWizardOpen(false); setFormError(""); }, onError: error => setFormError(errorMessage(error)) });
  const statusMutation = useMutation({ mutationFn: ({ id, status }: { id: number; status: string }) => api.patch(`/appointments/${id}/status/`, { status }), onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); setActive(null); } });
  const reschedule = useMutation({ mutationFn: ({ id, start_at }: { id: number; start_at: string }) => api.patch(`/appointments/${id}/reschedule/`, { start_at }), onSuccess: () => { setFormError(""); void qc.invalidateQueries({ queryKey: ["appointments"] }); }, onError: error => setFormError(errorMessage(error)) });
  const cancel = useMutation({ mutationFn: (id: number) => api.post(`/appointments/${id}/cancel/`), onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); setActive(null); } });
  const events = useMemo(() => (appointmentQuery.data ?? []).filter(appointment => appointment.items.length).map(appointment => ({ id: String(appointment.id), title: `${appointment.customer_name} · ${appointment.items.map(item => item.service_name).join(", ")}`, start: appointment.items[0].start_at, end: appointment.items[appointment.items.length - 1].end_at, extendedProps: { appointment } })), [appointmentQuery.data]);
  const openCreate = (arg?: { start: Date }) => { setSelectedDate(arg ? localDate(arg.start) : localDate(new Date())); setWizardOpen(true); setFormError(""); };
  const onDrop = (info: { event: { id: string; start: Date | null }; revert: () => void }) => {
    if (!info.event.start) { info.revert(); return; }
    reschedule.mutate({ id: Number(info.event.id), start_at: info.event.start.toISOString() }, { onError: () => info.revert() });
  };
  const onClick = (info: { event: { extendedProps: Record<string, unknown> } }) => setActive(info.event.extendedProps.appointment as Appointment);
  return <div className="app-shell">
    <header className="topbar"><a className="brand-lockup" href="/app/agenda"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></a><nav className="topnav"><span className="nav-current">Agenda</span>{user?.role !== "PROFESSIONAL" && <><a href="/app/servicos">Serviços</a><a href="/app/profissionais">Profissionais</a><a href="/app/clientes">Clientes</a><a href="/app/plano">Plano</a><a href="/app/metricas">Métricas</a><a href="/app/notificacoes">Notificações</a></>}</nav><div className="topbar-actions"><span className="user-chip">{user?.email}</span><AppearanceSettings organizationSlug={user?.organization?.slug} /><button onClick={() => void logout()} className="button-quiet">Sair</button></div></header>
    <main className="page-content"><div className="page-heading"><div><p className="eyebrow">VISÃO GERAL</p><h1>Agenda</h1><p className="muted-copy">Acompanhe os atendimentos do seu espaço.</p></div><button onClick={() => openCreate()} className="button-primary">Novo agendamento</button></div>
      {formError && <p role="alert" className="notice-error mb-3">{formError}</p>}
      {appointmentQuery.isLoading ? <p role="status" className="panel loading-panel">Carregando agenda…</p> : appointmentQuery.isError ? <p role="alert" className="panel loading-panel notice-error">Não foi possível carregar dados da agenda. {errorMessage(appointmentQuery.error)}</p> : <><div className="panel overflow-x-auto p-2 sm:p-4"><FullCalendar plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]} initialView="timeGridWeek" headerToolbar={{ left: "prev,next today", center: "title", right: "timeGridDay,timeGridWeek,dayGridMonth" }} locale="pt-br" selectable select={openCreate} editable eventDrop={onDrop} eventClick={onClick} events={events} datesSet={arg => setSelectedDate(localDate(arg.view.currentStart))} height="auto" /></div>{events.length === 0 && <p className="mt-3 text-center text-sm text-slate-600">Nenhum agendamento neste período.</p>}</>}
    </main>
    {wizardOpen && <div className="modal-backdrop"><section className="modal-card panel wizard-modal" aria-labelledby="create-title"><div className="panel-heading"><div><p className="eyebrow">AGENDA</p><h2 id="create-title">Novo agendamento</h2></div><button className="icon-button" aria-label="Fechar" onClick={() => setWizardOpen(false)}>×</button></div>{formError && <p role="alert" className="notice-error">{formError}</p>}<AppointmentWizard mode="dashboard" initialDate={selectedDate} onConfirm={data => create.mutate(data)} />{create.isPending && <p role="status" className="helper-copy">Criando agendamento…</p>}</section></div>}
    {active && <div className="fixed inset-0 z-40 flex justify-end bg-black/60" onClick={() => setActive(null)}><aside className="panel h-full w-full max-w-sm rounded-none p-5" onClick={event => event.stopPropagation()}><button className="float-right button-quiet" aria-label="Fechar detalhes" onClick={() => setActive(null)}>✕</button><p className="eyebrow">AGENDAMENTO #{active.id}</p><h2 className="mt-3 font-serif text-2xl">{active.customer_name}</h2><p className="mt-2 text-sm text-slate-600">{active.items.map(item => `${item.service_name} · ${item.professional_name}`).join(" / ")}</p><p className="mt-2 text-sm">Status: {active.status}</p><div className="mt-5 space-y-2">{["CONFIRMED", "COMPLETED", "NO_SHOW"].map(status => <button key={status} onClick={() => statusMutation.mutate({ id: active.id, status })} className="button-quiet block w-full">Marcar {status === "NO_SHOW" ? "não compareceu" : status.toLowerCase()}</button>)}<button onClick={() => cancel.mutate(active.id)} className="button-quiet block w-full border-red-400/40 text-red-300">Cancelar agendamento</button></div>{(statusMutation.isError || cancel.isError) && <p role="alert" className="notice-error mt-3">{errorMessage(statusMutation.error ?? cancel.error)}</p>}</aside></div>}
  </div>;
}
