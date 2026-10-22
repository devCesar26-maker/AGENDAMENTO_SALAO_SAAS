import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, errorMessage } from "../lib/api";
import { Modal, Button, Card, FormField, SkeletonList, toast } from "../components/ui";

type Professional = { id: number; name: string; photo: string; is_active: boolean; service_links: Link[] };
type Link = { id: number; service: number; service_name: string; service_category: string; price_override: string | null; duration_override: number | null; commission_percentage: string };
type Service = { id: number; name: string; category_name: string; duration_minutes: number; price: string };
type WorkingHour = { id: number; weekday: number; start_time: string; end_time: string };
type TimeOff = { id: number; start_date: string; end_date: string; reason: string };
type Row<T> = T[] | { results: T[] };
const rows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const weekdays = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const profileSchema = z.object({ name: z.string().trim().min(2, "Informe um nome."), photo: z.union([z.literal(""), z.string().url("Informe um endereço de foto válido.")]) });
const linkSchema = z.object({ service: z.coerce.number().positive("Escolha um serviço."), price_override: z.string(), duration_override: z.string(), commission_percentage: z.coerce.number().min(0).max(100) });
const hoursSchema = z.object({ weekday: z.coerce.number().min(0).max(6), start_time: z.string().min(1), end_time: z.string().min(1) }).refine(value => value.start_time !== value.end_time, { path: ["end_time"], message: "Início e fim precisam ser diferentes." });
const timeoffSchema = z.object({ start_date: z.string().min(1), end_date: z.string().min(1), reason: z.string() }).refine(value => value.end_date >= value.start_date, { path: ["end_date"], message: "A data final deve ser igual ou posterior à inicial." });

export function ProfessionalsPage() {
  const client = useQueryClient();
  const [selected, setSelected] = useState<Professional | null>(null);
  const [editing, setEditing] = useState<Professional | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const profiles = useQuery({ queryKey: ["professionals"], queryFn: async () => rows((await api.get<Row<Professional>>("/professionals/")).data) });
  const services = useQuery({ queryKey: ["services"], queryFn: async () => rows((await api.get<Row<Service>>("/services/")).data) });
  const profileForm = useForm({ resolver: zodResolver(profileSchema), defaultValues: { name: "", photo: "" } });
  const linkForm = useForm({ resolver: zodResolver(linkSchema), defaultValues: { service: 0, price_override: "", duration_override: "", commission_percentage: 0 } });
  const hoursForm = useForm({ resolver: zodResolver(hoursSchema), defaultValues: { weekday: 0, start_time: "09:00", end_time: "18:00" } });
  const timeoffForm = useForm({ resolver: zodResolver(timeoffSchema), defaultValues: { start_date: "", end_date: "", reason: "" } });
  const reload = async () => { await client.invalidateQueries({ queryKey: ["professionals"] }); if (selected) { await client.invalidateQueries({ queryKey: ["professional-detail", selected.id] }); const cached = client.getQueryData<Row<Professional>>(["professionals"]); const updated = cached ? rows(cached).find(person => person.id === selected.id) : undefined; if (updated) setSelected(updated); } };
  const selectProfessional = (person: Professional) => {
    setSelected(person);
    if (window.matchMedia("(max-width: 979px)").matches) {
      window.setTimeout(() => document.getElementById("professional-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
    }
  };
  const saveProfile = useMutation({ mutationFn: async (data: { name: string; photo: string }) => { if (editing) await api.patch(`/professionals/${editing.id}/`, data); else await api.post("/professionals/", { ...data, is_active: true }); }, onSuccess: async () => { await reload(); setProfileOpen(false); setEditing(null); toast(editing ? "Perfil atualizado com sucesso" : "Profissional adicionado com sucesso", "success"); } });
  const toggleProfile = useMutation({ mutationFn: (person: Professional) => api.patch(`/professionals/${person.id}/`, { is_active: !person.is_active }), onSuccess: (_, variables) => { reload(); toast(`Profissional ${variables.is_active ? "desativado" : "ativado"} com sucesso`, "success"); } });
  const detail = useQuery({ queryKey: ["professional-detail", selected?.id], enabled: !!selected, queryFn: async () => {
    const id = selected!.id;
    const [linkRows, hoursRows, offRows] = await Promise.all([
      api.get<Row<Link>>(`/professionals/${id}/services/`), api.get<Row<WorkingHour>>(`/professionals/${id}/working-hours/`), api.get<Row<TimeOff>>(`/professionals/${id}/time-offs/`),
    ]);
    return { links: rows(linkRows.data), hours: rows(hoursRows.data), timeoffs: rows(offRows.data) };
  } });
  const addLink = useMutation({ mutationFn: (data: { service: number; price_override: string | null; duration_override: number | null; commission_percentage: number }) => api.post(`/professionals/${selected!.id}/services/`, data), onSuccess: async () => { await reload(); linkForm.reset({ service: 0, price_override: "", duration_override: "", commission_percentage: 0 }); toast("Serviço vinculado com sucesso", "success"); } });
  const removeLink = useMutation({ mutationFn: (id: number) => api.delete(`/professional-services/${id}/`), onSuccess: () => { reload(); toast("Serviço desvinculado", "success"); } });
  const addHours = useMutation({ mutationFn: (data: z.infer<typeof hoursSchema>) => api.post(`/professionals/${selected!.id}/working-hours/`, data), onSuccess: async () => { await reload(); hoursForm.reset({ weekday: 0, start_time: "09:00", end_time: "18:00" }); toast("Horário adicionado com sucesso", "success"); } });
  const removeHours = useMutation({ mutationFn: (id: number) => api.delete(`/working-hours/${id}/`), onSuccess: () => { reload(); toast("Horário removido", "success"); } });
  const addTimeoff = useMutation({ mutationFn: (data: z.infer<typeof timeoffSchema>) => api.post(`/professionals/${selected!.id}/time-offs/`, data), onSuccess: async () => { await reload(); timeoffForm.reset({ start_date: "", end_date: "", reason: "" }); toast("Bloqueio adicionado com sucesso", "success"); } });
  const removeTimeoff = useMutation({ mutationFn: (id: number) => api.delete(`/time-offs/${id}/`), onSuccess: () => { reload(); toast("Bloqueio removido", "success"); } });
  const startEdit = (person: Professional) => { setEditing(person); profileForm.reset({ name: person.name, photo: person.photo }); setProfileOpen(true); };

  return (
    <>
      <main className="page-content">
        <div className="page-heading">
          <div>
            <p className="eyebrow">EQUIPE</p>
            <h1>Profissionais</h1>
            <p className="muted-copy">Cadastre a equipe, os serviços e os horários de cada pessoa.</p>
          </div>
          <Button onClick={() => { setEditing(null); profileForm.reset({ name: "", photo: "" }); setProfileOpen(true); }}>
            Adicionar profissional
          </Button>
        </div>
        {profiles.isError && <p role="alert" className="notice-error">{errorMessage(profiles.error)}</p>}
        {profiles.isLoading ? (
          <div className="p-8">
            <SkeletonList count={3} />
          </div>
        ) : (
          <div className="professional-layout">
            <section className="professional-grid" aria-label="Equipe cadastrada">
              {profiles.data?.map(person => (
                <Card className={`professional-card card-hover ${selected?.id === person.id ? "is-selected" : ""}`} key={person.id}>
                  <button className="professional-card-main" onClick={() => selectProfessional(person)} aria-pressed={selected?.id === person.id}>
                    {person.photo ? (
                      <img src={person.photo} alt="" className="professional-photo" />
                    ) : (
                      <span className="professional-photo">{person.name.split(/\s+/).map(name => name[0]).slice(0, 2).join("").toUpperCase()}</span>
                    )}
                    <span>
                      <strong>{person.name}</strong>
                      <small>{person.service_links?.length ?? 0} serviço(s) cadastrado(s)</small>
                    </span>
                    <i className={`status-pill ${person.is_active ? "status-active" : "status-inactive"}`}>
                      {person.is_active ? "Ativo" : "Inativo"}
                    </i>
                  </button>
                  <div className="professional-card-actions">
                    <Button className={`professional-configure ${selected?.id === person.id ? "is-current" : ""}`} onClick={() => selectProfessional(person)}>
                      {selected?.id === person.id ? "Configurações abertas" : "Configurar serviços e horários"} <span aria-hidden="true">→</span>
                    </Button>
                    <Button variant="secondary" onClick={() => startEdit(person)}>Editar perfil</Button>
                    <Button variant="secondary" onClick={() => toggleProfile.mutate(person)}>{person.is_active ? "Desativar" : "Ativar"}</Button>
                  </div>
                </Card>
              ))}
              {profiles.data?.length === 0 && (
                <Card className="empty-state">
                  <span>✧</span>
                  <h2>Sua equipe começa aqui</h2>
                  <p>Adicione o primeiro profissional para começar.</p>
                </Card>
              )}
            </section>
            {selected && (
              <section id="professional-detail" className="panel professional-detail" aria-label={`Configurações de ${selected.name}`}>
                <div className="professional-detail-heading">
                  <div>
                    <p className="eyebrow">CONFIGURAÇÕES DO PROFISSIONAL</p>
                    <h2 className="font-serif text-2xl">{selected.name}</h2>
                    <p className="muted-copy">Vincule serviços e ajuste disponibilidade, horários e folgas.</p>
                  </div>
                  <Button variant="secondary" className="professional-detail-close" onClick={() => setSelected(null)}>Fechar</Button>
                </div>
                {detail.isLoading ? (
                  <p role="status">Carregando configurações…</p>
                ) : detail.isError ? (
                  <p role="alert" className="notice-error">{errorMessage(detail.error)}</p>
                ) : (
                  <>
                    <section className="detail-section">
                      <div className="detail-section-heading">
                        <div>
                          <h3>Serviços vinculados</h3>
                          <p className="helper-copy">Os serviços selecionados ficam disponíveis para agendamento com {selected.name}.</p>
                        </div>
                        <span className="detail-count">{detail.data?.links.length ?? 0}</span>
                      </div>
                      {detail.data?.links.length === 0 && (
                        <div className="professional-link-empty">
                          <strong>Nenhum serviço vinculado</strong>
                          <span>Escolha um serviço abaixo para liberar horários na agenda.</span>
                        </div>
                      )}
                      {detail.data?.links.map(link => (
                        <div className="detail-row" key={link.id}>
                          <span>
                            <strong>{link.service_name}</strong>
                            <small>{link.service_category} · {link.duration_override ?? services.data?.find(service => service.id === link.service)?.duration_minutes} min · R$ {link.price_override ?? services.data?.find(service => service.id === link.service)?.price} · comissão {link.commission_percentage}%</small>
                          </span>
                          <Button variant="secondary" aria-label={`Desvincular ${link.service_name}`} onClick={() => removeLink.mutate(link.id)}>Remover</Button>
                        </div>
                      ))}
                      {services.isLoading ? (
                        <p role="status" className="helper-copy">Carregando serviços…</p>
                      ) : services.isError ? (
                        <p role="alert" className="notice-error">Não foi possível carregar os serviços. {errorMessage(services.error)}</p>
                      ) : (
                        <form className="compact-form form-columns" onSubmit={linkForm.handleSubmit(data => addLink.mutate({
                        service: data.service,
                        price_override: data.price_override || null,
                        duration_override: data.duration_override ? Number(data.duration_override) : null,
                        commission_percentage: data.commission_percentage,
                      }))}>
                          <FormField label="Serviço">
                            <select className="field-input" {...linkForm.register("service", { valueAsNumber: true })}>
                              <option value="">Selecione</option>
                              {services.data?.map(service => <option key={service.id} value={service.id}>{service.name}</option>)}
                            </select>
                          </FormField>
                          <FormField label="Preço (R$)">
                            <input className="field-input" {...linkForm.register("price_override")} placeholder="Opcional" />
                          </FormField>
                          <FormField label="Duração (min)">
                            <input className="field-input" type="number" {...linkForm.register("duration_override")} placeholder="Opcional" />
                          </FormField>
                          <FormField label="Comissão (%)">
                            <input className="field-input" type="number" {...linkForm.register("commission_percentage", { valueAsNumber: true })} />
                          </FormField>
                          <Button variant="secondary" type="submit" className="self-end">Vincular serviço</Button>
                        </form>
                      )}
                    </section>
                    <section className="detail-section">
                      <h3>Horário semanal</h3>
                      <div className="weekly-hours-grid">
                        {weekdays.map((day, weekday) => (
                          <div key={day} className="weekly-day">
                            <strong>{day}</strong>
                            <div>
                              {detail.data?.hours.filter(hour => hour.weekday === weekday).map(hour => (
                                <span className="weekly-hour" key={hour.id}>
                                  {hour.start_time.slice(0, 5)}–{hour.end_time.slice(0, 5)} <Button variant="secondary" aria-label={`Remover horário ${day}`} onClick={() => removeHours.mutate(hour.id)}>×</Button>
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                      <form className="compact-form form-columns" onSubmit={hoursForm.handleSubmit(data => addHours.mutate(data))}>
                        <FormField label="Dia">
                          <select className="field-input" {...hoursForm.register("weekday", { valueAsNumber: true })}>
                            {weekdays.map((day, index) => <option value={index} key={day}>{day}</option>)}
                          </select>
                        </FormField>
                        <FormField label="Início">
                          <input className="field-input" type="time" {...hoursForm.register("start_time")} />
                        </FormField>
                        <FormField label="Fim">
                          <input className="field-input" type="time" {...hoursForm.register("end_time")} />
                        </FormField>
                        <Button variant="secondary" type="submit" className="self-end">Adicionar horário</Button>
                      </form>
                    </section>
                    <section className="detail-section">
                      <h3>Folgas e bloqueios</h3>
                      {detail.data?.timeoffs.map(off => (
                        <div key={off.id} className="detail-row">
                          <span>
                            <strong>{off.start_date} — {off.end_date}</strong>
                            <small>{off.reason || "Bloqueio de agenda"}</small>
                          </span>
                          <Button variant="secondary" aria-label="Remover folga" onClick={() => removeTimeoff.mutate(off.id)}>Remover</Button>
                        </div>
                      ))}
                      <form className="compact-form form-columns" onSubmit={timeoffForm.handleSubmit(data => addTimeoff.mutate(data))}>
                        <FormField label="Início">
                          <input className="field-input" type="date" {...timeoffForm.register("start_date")} />
                        </FormField>
                        <FormField label="Fim">
                          <input className="field-input" type="date" {...timeoffForm.register("end_date")} />
                        </FormField>
                        <FormField label="Motivo">
                          <input className="field-input" {...timeoffForm.register("reason")} />
                        </FormField>
                        <Button variant="secondary" type="submit" className="self-end">Adicionar bloqueio</Button>
                      </form>
                    </section>
                  </>
                )}
              </section>
            )}
          </div>
        )}
      </main>
      <Modal
        isOpen={profileOpen}
        onClose={() => setProfileOpen(false)}
        title={editing ? "Editar profissional" : "Novo profissional"}
      >
        <form className="service-form" onSubmit={profileForm.handleSubmit(data => {
          saveProfile.mutate(data);
        })}>
          <FormField label="Nome" error={profileForm.formState.errors.name?.message}>
            <input className="field-input" placeholder="Nome do profissional" {...profileForm.register("name")} />
          </FormField>
          <FormField label="Foto (URL opcional)" error={profileForm.formState.errors.photo?.message}>
            <input className="field-input" type="url" placeholder="https://..." {...profileForm.register("photo")} />
          </FormField>
          {saveProfile.isError && <p role="alert" className="notice-error">{errorMessage(saveProfile.error)}</p>}
          <Button type="submit" className="button-wide" disabled={saveProfile.isPending}>
            {saveProfile.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </form>
      </Modal>
    </>
  );
}
