import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { DashboardHeader } from "../components/DashboardHeader";
import { api, errorMessage } from "../lib/api";
import { toast } from "../components/ui";

type Customer = { id: number; name: string; phone: string; email: string; responsavel: number | null; notes: string; lgpd_consent: boolean; lgpd_consent_at: string | null };
type Appointment = { id: number; customer_name: string; status: string; items: { service_name: string; start_at: string }[] };
type Row<T> = T[] | { results: T[] };
const rows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const schema = z.object({ name: z.string().trim().min(2, "Informe o nome."), phone: z.string().trim(), email: z.union([z.literal(""), z.string().email("Informe um e-mail válido.")]), responsavel: z.string(), notes: z.string() }).refine(value => !!value.responsavel || value.phone.trim().length > 0, { path: ["phone"], message: "Telefone necessário para cliente sem responsável." });
type Form = z.infer<typeof schema>;
const blank: Form = { name: "", phone: "", email: "", responsavel: "", notes: "" };

export function CustomersPage() {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Customer | null>(null);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [open, setOpen] = useState(false);
  const customers = useQuery({ queryKey: ["customers", search], queryFn: async () => rows((await api.get<Row<Customer>>("/customers/", { params: search ? { search } : {} })).data) });
  const personList = customers.data ?? [];
  const dependents = personList.filter(person => person.responsavel === selected?.id);
  const history = useQuery({ queryKey: ["customer-history", selected?.id], enabled: !!selected, queryFn: async () => rows((await api.get<Row<Appointment>>("/appointments/", { params: { customer: selected?.id } })).data) });
  const dependentHistory = useQuery({ queryKey: ["dependent-history", dependents.map(person => person.id)], enabled: dependents.length > 0, queryFn: async () => Promise.all(dependents.map(async person => ({ person, appointments: rows((await api.get<Row<Appointment>>("/appointments/", { params: { customer: person.id } })).data) }))) });
  const { register, handleSubmit, reset, formState: { errors } } = useForm<Form>({ resolver: zodResolver(schema), defaultValues: blank });
  const save = useMutation({ mutationFn: (data: Form) => { const payload = { ...data, responsavel: data.responsavel ? Number(data.responsavel) : null }; return editing ? api.patch(`/customers/${editing.id}/`, payload) : api.post("/customers/", payload); }, onSuccess: async () => { await client.invalidateQueries({ queryKey: ["customers"] }); setOpen(false); setEditing(null); reset(blank); } });
  const startCreate = () => { setEditing(null); reset(blank); setOpen(true); };
  const startEdit = (person: Customer) => { setEditing(person); reset({ name: person.name, phone: person.phone, email: person.email, responsavel: person.responsavel ? String(person.responsavel) : "", notes: person.notes }); setOpen(true); };
  const consent = useMutation({ mutationFn: ({ id, consented }: { id: number; consented: boolean }) => api.post(`/customers/${id}/lgpd-consent/`, { consented }), onSuccess: (_, variables) => { void client.invalidateQueries({ queryKey: ["customers"] }); toast(variables.consented ? "Consentimento LGPD registrado." : "Consentimento LGPD revogado.", "success"); } });
  const exportCustomer = useMutation({
    mutationFn: async (id: number) => (await api.get<Blob>(`/customers/${id}/export/`, { responseType: "blob" })).data,
    onSuccess: async (blob, id) => {
      const url = URL.createObjectURL(blob instanceof Blob ? blob : new Blob([JSON.stringify(blob)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `cliente-${id}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      toast("Exportação LGPD baixada.", "success");
    },
  });
  const anonymize = useMutation({
    mutationFn: (id: number) => api.post(`/customers/${id}/anonymize/`),
    onSuccess: (_, id) => {
      void client.invalidateQueries({ queryKey: ["customers"] });
      void client.invalidateQueries({ queryKey: ["customer-history"] });
      setSelected(current => (current?.id === id ? null : current));
      toast("Dados pessoais anonimizados.", "success");
    },
  });
  return <div className="app-shell"><DashboardHeader current="Clientes" />
    <main className="page-content"><div className="page-heading"><div><p className="eyebrow">RELACIONAMENTO</p><h1>Clientes</h1><p className="muted-copy">Cadastros e histórico de atendimento.</p></div><button className="button-primary" onClick={startCreate}>Adicionar cliente</button></div><div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,.85fr)]"><section className="panel p-4 sm:p-5"><label className="field-label">Buscar cliente<input className="field-input" value={search} onChange={event => setSearch(event.target.value)} placeholder="Nome, telefone ou e-mail" /></label>{customers.isLoading ? <p className="py-8 text-center">Carregando clientes…</p> : customers.isError ? <p role="alert" className="notice-error mt-4">{errorMessage(customers.error)}</p> : <div className="mt-4 grid gap-2">{personList.map(person => <button key={person.id} className={`customer-row ${selected?.id === person.id ? "is-selected" : ""}`} onClick={() => setSelected(person)}><span className="customer-initial">{person.name.slice(0, 1).toUpperCase()}</span><span className="min-w-0 flex-1 text-left"><strong>{person.name}</strong><small>{person.phone || "Sem telefone"} · {person.email || "Sem e-mail"}</small></span><span className="text-xs text-indigo-200">{person.responsavel ? "Dependente" : "›"}</span></button>)}</div>}{!customers.isLoading && personList.length === 0 && <p className="helper-copy mt-4">Nenhum cliente encontrado.</p>}</section>
    <section className="panel p-4 sm:p-5">{selected ? <><div className="flex items-start justify-between gap-3"><div><p className="eyebrow">CADASTRO</p><h2 className="mt-1 font-serif text-2xl">{selected.name}</h2></div><button className="button-quiet" onClick={() => startEdit(selected)}>Editar</button></div>{selected.responsavel ? <p className="notice-card mt-4">Dependente de {personList.find(person => person.id === selected.responsavel)?.name ?? "cliente"}</p> : dependents.length > 0 && <p className="notice-card mt-4">Responsável por {dependents.map(person => person.name).join(", ")}</p>}<div className="lgpd-block"><h3 className="mt-5 font-semibold">Privacidade (LGPD)</h3><p className="helper-copy mt-1">{selected.lgpd_consent ? `Consentimento registrado em ${selected.lgpd_consent_at ? new Date(selected.lgpd_consent_at).toLocaleDateString("pt-BR") : "—"}.` : "Este cliente ainda não registrou consentimento."}</p><div className="mt-3 flex flex-wrap gap-2"><button className="button-quiet" onClick={() => consent.mutate({ id: selected.id, consented: !selected.lgpd_consent })}>{selected.lgpd_consent ? "Revogar consentimento" : "Registrar consentimento"}</button><button className="button-quiet" onClick={() => exportCustomer.mutate(selected.id)}>Exportar dados</button><button className="button-danger" onClick={() => { if (window.confirm("Anonimizar irreversivelmente os dados deste cliente?")) anonymize.mutate(selected.id); }}>Anonimizar dados</button></div>{(consent.isError || exportCustomer.isError || anonymize.isError) && <p role="alert" className="notice-error mt-3">{errorMessage(consent.error ?? exportCustomer.error ?? anonymize.error)}</p>}</div>
    <h3 className="mt-5 font-semibold">Histórico deste cliente</h3>{history.isLoading ? <p className="helper-copy mt-2">Carregando atendimentos…</p> : <AppointmentHistory appointments={history.data ?? []} />}<h3 className="mt-5 font-semibold">Histórico de dependentes</h3>{dependents.length === 0 ? <p className="helper-copy mt-2">Este cliente não tem dependentes cadastrados.</p> : dependentHistory.data?.map(({ person, appointments }) => <div key={person.id} className="mt-3 border-t border-white/10 pt-3"><strong>{person.name}</strong><AppointmentHistory appointments={appointments} /></div>)}</> : <div className="empty-state"><span>✧</span><h2>Selecione um cliente</h2><p>O histórico e os vínculos aparecerão aqui.</p></div>}</section></div></main>
    {open && <div className="modal-backdrop"><section className="modal-card panel" aria-labelledby="customer-title"><div className="panel-heading"><div><p className="eyebrow">CLIENTE</p><h2 id="customer-title">{editing ? "Editar cliente" : "Novo cliente"}</h2></div><button className="icon-button" onClick={() => setOpen(false)} aria-label="Fechar">×</button></div><form className="service-form" onSubmit={handleSubmit(data => save.mutate(data))}><label className="field-label">Nome<input className="field-input" {...register("name")} />{errors.name && <small className="notice-error">{errors.name.message}</small>}</label><div className="form-columns"><label className="field-label">Telefone<input className="field-input" type="tel" {...register("phone")} />{errors.phone && <small className="notice-error">{errors.phone.message}</small>}</label><label className="field-label">E-mail<input className="field-input" type="email" {...register("email")} />{errors.email && <small className="notice-error">{errors.email.message}</small>}</label></div><label className="field-label">Responsável (opcional)<select className="field-input" {...register("responsavel")}><option value="">Sem responsável</option>{personList.filter(person => !person.responsavel && person.id !== editing?.id).map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select><small>Ao informar um responsável, as confirmações usam o contato dele.</small></label><label className="field-label">Observações<textarea className="field-input" rows={3} {...register("notes")} /></label>{save.isError && <p role="alert" className="notice-error">{errorMessage(save.error)}</p>}<button className="button-primary button-wide" disabled={save.isPending}>{save.isPending ? "Salvando…" : "Salvar cliente"}</button></form></section></div>}
  </div>;
}

function AppointmentHistory({ appointments }: { appointments: Appointment[] }) { return appointments.length ? <ul className="mt-2 grid gap-2">{appointments.map(appointment => <li key={appointment.id} className="text-sm"><span className="text-indigo-200">{appointment.items[0]?.start_at ? new Date(appointment.items[0].start_at).toLocaleDateString("pt-BR") : "—"}</span><span className="text-slate-400"> · {appointment.items.map(item => item.service_name).join(", ")} · {appointment.status}</span></li>)}</ul> : <p className="helper-copy mt-2">Nenhum atendimento registrado.</p>; }
