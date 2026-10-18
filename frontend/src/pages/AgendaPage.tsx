import { useMemo, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { AppearanceSettings } from "../components/AppearanceSettings";

type Row<T> = T[] | { results: T[] };
type Service = { id: number; name: string };
type Professional = { id: number; name: string };
type Customer = { id: number; name: string };
type Item = { service: number; service_name: string; professional: number; professional_name: string; start_at: string; end_at: string };
type Appointment = { id: number; customer: number; customer_name: string; status: string; items: Item[] };
type Slot = { start_at: string; items: { service: number; professional: number; start_at: string; end_at: string }[] };
const asRows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const schema = z.object({ customer: z.coerce.number().positive("Escolha um cliente"), service: z.coerce.number().positive("Escolha um serviço"), professional: z.coerce.number().positive("Escolha um profissional"), slot: z.string().min(1, "Escolha um horário") });
type FormValues = z.input<typeof schema>;
type ParsedFormValues = z.output<typeof schema>;
const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;

export function AgendaPage() {
  const { user, logout } = useAuth();
  const qc = useQueryClient();
  const [selectedDate, setSelectedDate] = useState(localDate(new Date()));
  const [formOpen, setFormOpen] = useState(false);
  const [active, setActive] = useState<Appointment | null>(null);
  const [formError, setFormError] = useState("");
  const { register, handleSubmit, watch, reset, formState: { errors } } = useForm<FormValues, unknown, ParsedFormValues>({ resolver: zodResolver(schema) });
  // RHF's watch API is read locally here and its unstable methods are not memoized or shared.
  // oxlint-disable-next-line react/incompatible-library
  const serviceId = watch("service");
  const professionalId = watch("professional");
  const appointmentQuery = useQuery({ queryKey: ["appointments", selectedDate], queryFn: async () => asRows((await api.get<Row<Appointment>>("/appointments/", { params: { date: selectedDate } })).data) });
  const servicesQuery = useQuery({ queryKey: ["services"], queryFn: async () => asRows((await api.get<Row<Service>>("/services/")).data) });
  const professionalsQuery = useQuery({ queryKey: ["professionals"], queryFn: async () => asRows((await api.get<Row<Professional>>("/professionals/")).data) });
  const customersQuery = useQuery({ queryKey: ["customers"], queryFn: async () => asRows((await api.get<Row<Customer>>("/customers/")).data) });
  const slotsQuery = useQuery({ queryKey: ["availability", serviceId, professionalId, selectedDate], enabled: formOpen && !!serviceId && !!professionalId, queryFn: async () => (await api.get<{ slots: Slot[] }>("/availability/", { params: { services: serviceId, professional: professionalId, date: selectedDate } })).data.slots });
  const create = useMutation({ mutationFn: (values: ParsedFormValues) => {
    const slot = slotsQuery.data?.find((candidate) => candidate.start_at === values.slot);
    if (!slot) throw new Error("Esse horário não está mais disponível. Atualize os horários.");
    return api.post("/appointments/", { customer: values.customer, start_at: values.slot, items: slot.items.map((item, order) => ({ service: item.service, professional: item.professional, order })) });
  }, onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); setFormOpen(false); reset(); setFormError(""); }, onError: (error) => setFormError(errorMessage(error)) });
  const statusMutation = useMutation({ mutationFn: ({ id, status }: { id: number; status: string }) => api.patch(`/appointments/${id}/status/`, { status }), onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); setActive(null); } });
  const reschedule = useMutation({ mutationFn: ({ id, start_at }: { id: number; start_at: string }) => api.patch(`/appointments/${id}/reschedule/`, { start_at }), onSuccess: () => { setFormError(""); void qc.invalidateQueries({ queryKey: ["appointments"] }); } });
  const cancel = useMutation({ mutationFn: (id: number) => api.post(`/appointments/${id}/cancel/`), onSuccess: () => { void qc.invalidateQueries({ queryKey: ["appointments"] }); setActive(null); } });
  const events = useMemo(() => (appointmentQuery.data ?? []).filter((a) => a.items.length).map((a) => ({ id: String(a.id), title: `${a.customer_name} · ${a.items.map((i) => i.service_name).join(", ")}`, start: a.items[0].start_at, end: a.items[a.items.length - 1].end_at, extendedProps: { appointment: a } })), [appointmentQuery.data]);
  const openCreate = (arg?: { start: Date }) => { setSelectedDate(arg ? localDate(arg.start) : localDate(new Date())); setFormOpen(true); setFormError(""); };
  const onDrop = (info: { event: { id: string; start: Date | null }; revert: () => void }) => {
    if (!info.event.start) { info.revert(); return; }
    reschedule.mutate({ id: Number(info.event.id), start_at: info.event.start.toISOString() }, { onError: (error) => {
      info.revert();
      setFormError(errorMessage(error));
    } });
  };
  const onClick = (info: { event: { extendedProps: Record<string, unknown> } }) => setActive(info.event.extendedProps.appointment as Appointment);
  const dataError = appointmentQuery.isError || servicesQuery.isError || professionalsQuery.isError || customersQuery.isError;
  return <div className="app-shell">
    <header className="topbar"><Link className="brand-lockup" to="/app/agenda"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>GESTÃO DO ESTÚDIO</small></span></Link><nav className="topnav"><span className="nav-current">Agenda</span>{user?.role !== "PROFESSIONAL" && <Link to="/app/servicos">Serviços</Link>}</nav><div className="topbar-actions"><span className="user-chip">{user?.email}</span><AppearanceSettings organizationSlug={user?.organization?.slug} /><button onClick={() => void logout()} className="button-quiet">Sair</button></div></header>
    <main className="page-content"><div className="page-heading"><div><p className="eyebrow">VISÃO GERAL</p><h1>Agenda</h1><p className="muted-copy">Acompanhe os atendimentos do seu espaço.</p></div><button onClick={() => openCreate()} className="button-primary">Novo agendamento</button></div>
      {appointmentQuery.isLoading ? <p role="status" className="rounded-xl bg-white p-8 text-center">Carregando agenda…</p> : dataError ? <p role="alert" className="rounded-xl bg-white p-8 text-center text-red-700">Não foi possível carregar dados da agenda. {errorMessage(appointmentQuery.error)}</p> : <><div className="overflow-x-auto rounded-xl bg-white p-2 shadow-sm sm:p-4"><FullCalendar plugins={[dayGridPlugin,timeGridPlugin,interactionPlugin]} initialView="timeGridWeek" headerToolbar={{ left:"prev,next today", center:"title", right:"timeGridDay,timeGridWeek,dayGridMonth" }} locale="pt-br" selectable select={openCreate} editable eventDrop={onDrop} eventClick={onClick} events={events} datesSet={(arg) => setSelectedDate(localDate(arg.view.currentStart))} height="auto" /></div>{events.length === 0 && <p className="mt-3 text-center text-sm text-slate-600">Nenhum agendamento neste período.</p>}</>}
    </main>
    {formOpen && <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"><section className="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white p-5 sm:max-w-lg sm:rounded-2xl" aria-labelledby="create-title"><div className="flex justify-between"><h2 id="create-title" className="text-lg font-semibold">Novo agendamento</h2><button aria-label="Fechar" onClick={() => setFormOpen(false)}>✕</button></div>{formError && <p role="alert" className="mt-3 text-sm text-red-700">{formError}</p>}<form className="mt-4 space-y-4" onSubmit={handleSubmit((v) => create.mutate(v))}>
      <label className="block text-sm">Cliente<select className="mt-1 w-full rounded-lg border p-2" {...register("customer")}><option value="">Selecione</option>{customersQuery.data?.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}</select>{errors.customer && <small className="text-red-600">{errors.customer.message}</small>}</label>
      <label className="block text-sm">Serviço<select className="mt-1 w-full rounded-lg border p-2" {...register("service")}><option value="">Selecione</option>{servicesQuery.data?.map(s => <option value={s.id} key={s.id}>{s.name}</option>)}</select>{errors.service && <small className="text-red-600">{errors.service.message}</small>}</label>
      <label className="block text-sm">Profissional<select className="mt-1 w-full rounded-lg border p-2" {...register("professional")}><option value="">Selecione</option>{professionalsQuery.data?.map(p => <option value={p.id} key={p.id}>{p.name}</option>)}</select>{errors.professional && <small className="text-red-600">{errors.professional.message}</small>}</label>
      <label className="block text-sm">Horários livres<select className="mt-1 w-full rounded-lg border p-2" {...register("slot")}><option value="">{slotsQuery.isFetching ? "Buscando horários…" : "Selecione"}</option>{slotsQuery.data?.map(s => <option key={s.start_at} value={s.start_at}>{new Date(s.start_at).toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})}</option>)}</select></label>
      {slotsQuery.isError && <p role="alert" className="text-sm text-red-700">{errorMessage(slotsQuery.error)}</p>}{slotsQuery.data?.length === 0 && <p className="text-sm text-slate-600">Nenhum horário livre para este dia.</p>}
      <button disabled={create.isPending} className="w-full rounded-lg bg-violet-700 px-4 py-2 font-medium text-white disabled:opacity-50">{create.isPending ? "Salvando…" : "Confirmar agendamento"}</button>
    </form></section></div>}
    {active && <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={() => setActive(null)}><aside className="h-full w-full max-w-sm bg-white p-5" onClick={e => e.stopPropagation()}><button className="float-right" aria-label="Fechar detalhes" onClick={() => setActive(null)}>✕</button><h2 className="text-lg font-semibold">{active.customer_name}</h2><p className="mt-1 text-sm text-slate-600">{active.items.map(i => `${i.service_name} · ${i.professional_name}`).join(" / ")}</p><p className="mt-2 text-sm">Status: {active.status}</p><div className="mt-5 space-y-2">{["CONFIRMED","COMPLETED","NO_SHOW"].map(status => <button key={status} onClick={() => statusMutation.mutate({id:active.id,status})} className="block w-full rounded-lg border p-2 text-sm">Marcar {status === "NO_SHOW" ? "não compareceu" : status.toLowerCase()}</button>)}<button onClick={() => cancel.mutate(active.id)} className="block w-full rounded-lg border border-red-200 p-2 text-sm text-red-700">Cancelar agendamento</button></div>{(statusMutation.isError || cancel.isError) && <p role="alert" className="mt-3 text-sm text-red-700">{errorMessage(statusMutation.error ?? cancel.error)}</p>}</aside></div>}
  </div>;
}
