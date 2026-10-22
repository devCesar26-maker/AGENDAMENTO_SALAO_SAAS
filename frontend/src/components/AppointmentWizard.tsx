import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, errorMessage } from "../lib/api";

type Row<T> = T[] | { results: T[] };
type Service = { id: number; name: string; category?: number; category_name?: string; duration_minutes: number; price: string; is_active?: boolean };
type Professional = { id: number; name: string; photo?: string; is_active?: boolean; services?: number[]; service_links?: { service: number }[] };
type Customer = { id: number; name: string; phone?: string; email?: string; responsavel?: number | null; responsavel_name?: string };
type Slot = { start_at: string; items: { service: number; professional: number; start_at: string; end_at: string; price?: string }[] };
export type BookingData = { name: string; phone: string; email: string; consent: boolean; start_at: string; items: { service: number; professional: number; order: number }[]; atendido?: { name: string; phone?: string; email?: string }; customer?: number; responsavel?: number; dependente?: { name: string; phone?: string; email?: string }; service?: number; professional?: number | null; desired_date?: string };

const rows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const attendeeSchema = z.object({ name: z.string().trim().min(2, "Informe o nome."), phone: z.string().trim().refine(value => value.replace(/\D/g, "").length >= 8, "Informe um telefone válido."), email: z.union([z.literal(""), z.string().email("Confira o e-mail.")]), attendeeName: z.string().trim(), attendeePhone: z.string().trim(), attendeeEmail: z.union([z.literal(""), z.string().email("Confira o e-mail do atendido.")]), consent: z.boolean().refine(value => value, "Marque esta opção para continuar.") });
type AttendeeValues = z.infer<typeof attendeeSchema>;

export function AppointmentWizard({ mode, slug, initialDate, onConfirm, onWaitlist, isSubmitting = false }: { mode: "dashboard" | "public"; slug?: string; initialDate?: string; onConfirm: (data: BookingData) => void; onWaitlist?: (data: BookingData) => void; isSubmitting?: boolean }) {
  const [step, setStep] = useState(0);
  const [serviceIds, setServiceIds] = useState<number[]>([]);
  const [professional, setProfessional] = useState("any");
  const [date, setDate] = useState(initialDate ?? localDate(new Date()));
  const [slot, setSlot] = useState("");
  const [anotherPerson, setAnotherPerson] = useState(false);
  const [waitlistOnly, setWaitlistOnly] = useState(false);
  const [stepError, setStepError] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [createDependent, setCreateDependent] = useState(false);
  const { register, handleSubmit, getValues, setValue, setError, trigger, formState: { errors } } = useForm<AttendeeValues>({ resolver: zodResolver(attendeeSchema), defaultValues: { name: "", phone: "", email: "", attendeeName: "", attendeePhone: "", attendeeEmail: "", consent: false } });
  const tenantConfig = mode === "public" ? { headers: { "X-Tenant-Slug": slug ?? "" } } : undefined;
  const serviceQuery = useQuery({ queryKey: [mode, "wizard-services", slug], enabled: mode === "dashboard" || !!slug, queryFn: async () => {
    if (mode === "public") return (await api.get<{ services: Service[] }>("/public/catalog/", tenantConfig)).data.services;
    return rows((await api.get<Row<Service>>("/services/")).data).filter(service => service.is_active !== false);
  } });
  const professionalQuery = useQuery({ queryKey: [mode, "wizard-professionals", slug], enabled: mode === "dashboard" || !!slug, queryFn: async () => {
    if (mode === "public") {
      const data = (await api.get<Row<Professional>>("/public/professionals/", tenantConfig)).data;
      return rows(data);
    }
    return rows((await api.get<Row<Professional>>("/professionals/")).data).filter(person => person.is_active !== false);
  } });
  const customersQuery = useQuery({ queryKey: ["customers"], enabled: mode === "dashboard", queryFn: async () => rows((await api.get<Row<Customer>>("/customers/")).data) });
  const serviceKey = serviceIds.join(",");
  const slotsQuery = useQuery({ queryKey: [mode, "wizard-availability", slug, serviceKey, professional, date], enabled: serviceIds.length > 0 && !!date && (mode === "dashboard" || !!slug), queryFn: async () => {
    const path = mode === "public" ? "/public/availability/" : "/availability/";
    return (await api.get<{ slots: Slot[] }>(path, { ...tenantConfig, params: { services: serviceKey, professional, date } })).data.slots;
  } });
  const services = serviceQuery.data ?? [];
  const chosenServices = serviceIds.map(id => services.find(service => service.id === id)).filter((service): service is Service => !!service);
  const pros = professionalQuery.data ?? [];
  const availablePros = pros.filter(person => serviceIds.every(id => (person.services ?? person.service_links?.map(link => link.service) ?? []).includes(id)));
  const selectedSlot = slotsQuery.data?.find(candidate => candidate.start_at === slot);
  const groupedServices = (() => {
    const groups = new Map<string, Service[]>();
    services.forEach(service => { const category = service.category_name || "Outros serviços"; groups.set(category, [...(groups.get(category) ?? []), service]); });
    return [...groups.entries()];
  })();
  const selectedPrice = selectedSlot?.items.reduce((sum, item) => sum + Number(item.price ?? chosenServices.find(service => service.id === item.service)?.price ?? 0), 0) ?? chosenServices.reduce((sum, service) => sum + Number(service.price), 0);
  const selectedDuration = chosenServices.reduce((sum, service) => sum + (service.duration_minutes ?? 0), 0);
  const weekStart = new Date(`${date}T12:00:00`);
  weekStart.setDate(weekStart.getDate() - ((weekStart.getDay() + 6) % 7));
  const publicDates = Array.from({ length: 7 }, (_, index) => { const day = new Date(weekStart); day.setDate(day.getDate() + index); return day; });
  const canGoPreviousWeek = localDate(weekStart) > localDate(new Date());
  const validStep = async () => {
    setStepError("");
    if (step === 0 && (serviceIds.length < 1 || serviceIds.length > 5)) { setStepError("Escolha pelo menos um serviço para continuar."); return false; }
    if (step === 1 && professional !== "any" && !availablePros.some(person => String(person.id) === professional)) { setStepError("Escolha um profissional disponível para esses serviços."); return false; }
    if (step === 2 && !waitlistOnly && (!slot || !selectedSlot)) { setStepError("Escolha um horário livre ou tente outra data."); return false; }
    if (step === 3) {
      if (mode === "public") {
        if (!(await trigger(["name", "phone", "email", "consent"]))) return false;
        if (anotherPerson && !getValues("attendeeName").trim()) { setError("attendeeName", { message: "Informe o nome de quem será atendido." }); return false; }
        return true;
      }
      if (createDependent) {
        if (!customerId) { setStepError("Escolha o cliente responsável."); return false; }
        if (!(await trigger(["attendeeName", "attendeePhone", "attendeeEmail"]))) return false;
        if (!getValues("attendeeName").trim()) { setError("attendeeName", { message: "Informe o nome de quem será atendido." }); return false; }
        return true;
      }
      if (!customerId) { setStepError("Escolha um cliente."); return false; }
      return true;
    }
    return true;
  };
  const next = async () => { if (await validStep()) setStep(current => Math.min(4, current + 1)); };
  const submit = (values: AttendeeValues) => {
    if (waitlistOnly && mode === "public") {
      onWaitlist?.({ name: values.name, phone: values.phone, email: values.email, consent: values.consent, start_at: date, items: [], service: serviceIds[0], professional: professional === "any" ? null : Number(professional), desired_date: date });
      return;
    }
    if (!selectedSlot) return;
    const items = selectedSlot.items.map((item, order) => ({ service: item.service, professional: item.professional, order }));
    const responsible = mode === "public" ? { name: values.name, phone: values.phone, email: values.email, consent: values.consent } : {};
    const data: BookingData = { ...responsible, start_at: selectedSlot.start_at, items } as BookingData;
    if (mode === "public" && anotherPerson && values.attendeeName.trim().toLocaleLowerCase() !== values.name.trim().toLocaleLowerCase()) data.atendido = { name: values.attendeeName.trim(), phone: values.attendeePhone, email: values.attendeeEmail };
    if (mode === "dashboard" && createDependent) { data.responsavel = Number(customerId); data.dependente = { name: values.attendeeName.trim(), phone: values.attendeePhone, email: values.attendeeEmail }; }
    if (mode === "dashboard" && !createDependent) data.customer = Number(customerId);
    onConfirm(data);
  };
  const handleNextClick = () => { void next(); };
  const changeWeek = (amount: number) => { const nextDate = new Date(`${date}T12:00:00`); nextDate.setDate(nextDate.getDate() + amount * 7); setDate(localDate(nextDate)); setSlot(""); };
  const timeBuckets = (slotsQuery.data ?? []).reduce<Record<string, Slot[]>>((buckets, item) => { const hour = Number(new Date(item.start_at).toLocaleTimeString("en-GB", { hour: "2-digit", hour12: false })); const period = hour < 12 ? "Manhã" : hour < 18 ? "Tarde" : "Noite"; buckets[period] = [...(buckets[period] ?? []), item]; return buckets; }, {});
  const hasNoSlots = !slotsQuery.isFetching && slotsQuery.data?.length === 0;

  return <section className="wizard-shell" aria-label="Agendamento">
    <div className="wizard-progress"><div className="flex justify-between gap-2">{["Serviços", "Profissional", "Horário", "Pessoas", "Revisão"].map((label, index) => <div key={label} className={`wizard-progress-step ${index === step ? "is-current" : index < step ? "is-done" : ""}`}><span>{index + 1}</span><small>{label}</small></div>)}</div><div className="wizard-progress-track"><span style={{ width: `${step * 25}%` }} /></div></div>
    {serviceQuery.isError || professionalQuery.isError ? <p role="alert" className="notice-error">Não foi possível carregar as opções. {errorMessage(serviceQuery.error ?? professionalQuery.error)}</p> : null}
    {step === 0 && <div className="wizard-step"><div><p className="eyebrow">ETAPA 1 DE 5</p><h3>O que você quer agendar?</h3><p className="muted-copy">Escolha até cinco serviços. A ordem da escolha será a ordem do atendimento.</p></div>{groupedServices.map(([category, entries]) => <section key={category} className="wizard-category"><h4>{category}</h4><div className="wizard-card-grid">{entries.map(service => <button type="button" key={service.id} aria-pressed={serviceIds.includes(service.id)} className={`wizard-choice-card ${serviceIds.includes(service.id) ? "is-selected" : ""}`} onClick={() => { setStepError(""); const nextIds = serviceIds.includes(service.id) ? serviceIds.filter(id => id !== service.id) : serviceIds.length < 5 ? [...serviceIds, service.id] : serviceIds; setServiceIds(nextIds); setSlot(""); if (professional !== "any") { const selectedPro = pros.find(person => String(person.id) === professional); const proServices = selectedPro?.services ?? selectedPro?.service_links?.map(link => link.service) ?? []; if (!nextIds.every(id => proServices.includes(id))) setProfessional("any"); } }}><span className="wizard-choice-mark">{serviceIds.includes(service.id) ? "✓" : "＋"}</span><strong>{service.name}</strong><small>{service.duration_minutes} min · R$ {service.price}</small></button>)}</div></section>)}</div>}
    {step === 1 && <div className="wizard-step"><div><p className="eyebrow">ETAPA 2 DE 5</p><h3>Com quem você quer agendar?</h3></div><div className="wizard-card-grid"><button type="button" aria-pressed={professional === "any"} className={`wizard-person-card wizard-any-card ${professional === "any" ? "is-selected" : ""}`} onClick={() => { setProfessional("any"); setSlot(""); }}><span className="wizard-avatar">✦</span><span><strong>Qualquer disponível</strong><small>Mostra horários de toda a equipe</small></span></button>{availablePros.map(person => <button type="button" key={person.id} aria-pressed={professional === String(person.id)} className={`wizard-person-card ${professional === String(person.id) ? "is-selected" : ""}`} onClick={() => { setProfessional(String(person.id)); setSlot(""); }}>{person.photo ? <img className="wizard-avatar" src={person.photo} alt="" /> : <span className="wizard-avatar">{person.name.split(/\s+/).map(part => part[0]).slice(0, 2).join("").toUpperCase()}</span>}<span><strong>{person.name}</strong><small>Profissional</small></span></button>)}</div>{availablePros.length === 0 && <div className="notice-card"><p>Não há profissionais vinculados a todos os serviços escolhidos.</p>{mode === "dashboard" && <p>Vincule os serviços a um profissional ativo para liberar a agenda.</p>}</div>}</div>}
    {step === 2 && <div className="wizard-step"><div><p className="eyebrow">ETAPA 3 DE 5</p><h3>{waitlistOnly ? "Entre na lista de espera" : "Escolha o dia e o horário"}</h3><p className="muted-copy">Os horários são atualizados quando você muda o dia ou o profissional.</p></div><div className="flex items-center justify-between"><button type="button" className="button-quiet" disabled={!canGoPreviousWeek} onClick={() => changeWeek(-1)} aria-label="Semana anterior">‹ Semana anterior</button><button type="button" className="button-quiet" onClick={() => changeWeek(1)} aria-label="Próxima semana">Próxima semana ›</button></div><div className="wizard-date-strip">{publicDates.map(day => { const key = localDate(day); return <button type="button" key={key} disabled={key < localDate(new Date())} aria-pressed={key === date} className={`wizard-date-card ${key === date ? "is-selected" : ""}`} onClick={() => { setDate(key); setSlot(""); setWaitlistOnly(false); }}><small>{day.toLocaleDateString("pt-BR", { weekday: "short" })}</small><strong>{day.getDate()}</strong><small>{day.toLocaleDateString("pt-BR", { month: "short" })}</small></button>; })}</div><label className="field-label wizard-exact-date">Ou escolha uma data<input className="field-input" type="date" min={localDate(new Date())} value={date} onChange={event => { setDate(event.target.value); setSlot(""); setWaitlistOnly(false); }} /></label>{slotsQuery.isFetching && <p role="status" className="helper-copy">Buscando horários livres…</p>}{slotsQuery.isError && <p role="alert" className="notice-error">{errorMessage(slotsQuery.error)}</p>}{Object.entries(timeBuckets).map(([period, options]) => <section key={period} className="wizard-time-group"><h4>{period}</h4><div className="wizard-time-grid">{options.map(option => <button type="button" key={option.start_at} aria-pressed={slot === option.start_at} className={`wizard-time-button ${slot === option.start_at ? "is-selected" : ""}`} onClick={() => { setSlot(option.start_at); setWaitlistOnly(false); }}>{new Date(option.start_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</button>)}</div></section>)}{hasNoSlots && <div className="notice-card"><strong>Não encontramos horários livres nesta data.</strong><p>Os horários dependem do expediente do estabelecimento e do profissional, além do vínculo do serviço com alguém da equipe. Confira essas configurações ou tente outro dia.</p>{mode === "dashboard" && <div className="wizard-setup-links"><a href="/app/configuracoes">Horário do estabelecimento</a><a href="/app/profissionais">Expediente e serviços da equipe</a></div>}{onWaitlist && <button type="button" className="button-quiet ml-2" onClick={() => { setWaitlistOnly(true); setStep(3); }}>Quero entrar na lista de espera</button>}</div>}{waitlistOnly && <p className="helper-copy">Se surgir uma vaga, avisaremos você. A vaga não fica reservada.</p>}</div>}
    {step === 3 && <div className="wizard-step"><div><p className="eyebrow">ETAPA 4 DE 5</p><h3>{mode === "public" ? "Quem está fazendo a reserva?" : "Quem vai ser atendido?"}</h3></div>{mode === "public" ? <><label className="field-label">Seu nome<input className="field-input" autoComplete="name" {...register("name")} />{errors.name && <small className="notice-error">{errors.name.message}</small>}</label><div className="form-columns"><label className="field-label">Telefone<input className="field-input" type="tel" autoComplete="tel" {...register("phone")} />{errors.phone && <small className="notice-error">{errors.phone.message}</small>}</label><label className="field-label">E-mail para aviso (opcional)<input className="field-input" type="email" autoComplete="email" {...register("email")} />{errors.email && <small className="notice-error">{errors.email.message}</small>}</label></div><label className="wizard-toggle"><input type="checkbox" checked={anotherPerson} onChange={event => setAnotherPerson(event.target.checked)} />É para outra pessoa?</label>{anotherPerson && <div className="wizard-dependent-fields"><p className="helper-copy">Usaremos seu contato para confirmar e lembrar do horário.</p><label className="field-label">Nome de quem será atendido<input className="field-input" {...register("attendeeName")} />{errors.attendeeName && <small className="notice-error">{errors.attendeeName.message}</small>}</label><div className="form-columns"><label className="field-label">Telefone (opcional)<input className="field-input" type="tel" {...register("attendeePhone")} /></label><label className="field-label">E-mail (opcional)<input className="field-input" type="email" {...register("attendeeEmail")} /></label></div></div>}<label className="wizard-toggle"><input type="checkbox" {...register("consent")} />Concordo com o uso dos meus dados para gerenciar a reserva.</label>{errors.consent && <small className="notice-error">Marque esta opção para continuar.</small>}</> : <><label className="field-label">Cliente responsável<select className="field-input" value={customerId} onChange={event => { setStepError(""); setCustomerId(event.target.value); }}><option value="">Escolha um cliente</option>{customersQuery.data?.filter(person => !createDependent || !person.responsavel).map(person => <option value={person.id} key={person.id}>{person.name}</option>)}</select></label><label className="wizard-toggle"><input type="checkbox" checked={createDependent} onChange={event => { const creating = event.target.checked; setCreateDependent(creating); if (creating && customersQuery.data?.find(person => String(person.id) === customerId)?.responsavel) setCustomerId(""); setValue("attendeeName", ""); }} />Agendar para outra pessoa</label>{createDependent && <div className="wizard-dependent-fields"><p className="helper-copy">O cadastro da pessoa ficará vinculado ao responsável selecionado.</p><label className="field-label">Nome de quem será atendido<input className="field-input" {...register("attendeeName")} />{errors.attendeeName && <small className="notice-error">{errors.attendeeName.message}</small>}</label><div className="form-columns"><label className="field-label">Telefone (opcional)<input className="field-input" type="tel" {...register("attendeePhone")} /></label><label className="field-label">E-mail (opcional)<input className="field-input" type="email" {...register("attendeeEmail")} /></label></div></div>}</>}{mode === "dashboard" && customersQuery.isError && <p role="alert" className="notice-error">Não foi possível carregar clientes. {errorMessage(customersQuery.error)}</p>}</div>}
    {step === 4 && <div className="wizard-step"><div><p className="eyebrow">ETAPA 5 DE 5</p><h3>{waitlistOnly ? "Confira sua inscrição" : "Revise seu agendamento"}</h3><p className="muted-copy">{waitlistOnly ? "Se surgir uma vaga, o salão poderá entrar em contato. A vaga não fica reservada." : "Confira os detalhes antes de confirmar."}</p></div><div className="wizard-review"><div><small>{waitlistOnly ? "Serviço" : "Serviços"}</small><strong>{waitlistOnly ? chosenServices[0]?.name : chosenServices.map((service, index) => `${index + 1}. ${service.name}`).join(" · ")}</strong></div>{waitlistOnly ? <><div><small>Profissional</small><strong>{professional === "any" ? "Qualquer disponível" : availablePros.find(person => String(person.id) === professional)?.name}</strong></div><div><small>Data desejada</small><strong>{new Date(`${date}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })}</strong></div></> : <><div><small>Profissional</small><strong>{professional === "any" ? "Qualquer disponível" : availablePros.find(person => String(person.id) === professional)?.name}</strong></div><div><small>Data e horário</small><strong>{selectedSlot && new Date(selectedSlot.start_at).toLocaleString("pt-BR", { weekday: "long", day: "2-digit", month: "long", hour: "2-digit", minute: "2-digit" })}</strong></div></>}<div><small>Atendido</small><strong>{mode === "public" ? (anotherPerson && getValues("attendeeName") ? getValues("attendeeName") : getValues("name")) : (createDependent ? getValues("attendeeName") : customersQuery.data?.find(person => String(person.id) === customerId)?.name)}</strong></div>{!waitlistOnly && <div className="wizard-review-total"><span>{selectedDuration} min</span><strong>R$ {selectedPrice.toFixed(2).replace(".", ",")}</strong></div>}</div>{mode === "public" && <p className="helper-copy">{waitlistOnly ? (getValues("email") ? `Entraremos em contato pelo e-mail ${getValues("email")} ou pelo telefone informado.` : "Entraremos em contato pelo telefone informado.") : `O salão enviará a confirmação para ${getValues("email") || getValues("phone")}.`}</p>}</div>}
    {stepError && <p role="alert" className="notice-error">{stepError}</p>}<div className="wizard-footer"><div className="wizard-total"><span>{waitlistOnly ? "Lista de espera" : `${chosenServices.length} serviço(s) · ${selectedDuration} min`}</span><strong>{waitlistOnly ? "" : `R$ ${selectedPrice.toFixed(2).replace(".", ",")}`}</strong></div><div className="flex gap-2">{step > 0 && <button type="button" className="button-quiet" onClick={() => setStep(current => Math.max(0, current - 1))}>Voltar</button>}{step < 4 ? <button type="button" className="button-primary" onClick={handleNextClick} disabled={serviceQuery.isLoading || professionalQuery.isLoading || (step === 2 && slotsQuery.isFetching && !waitlistOnly)}>Continuar</button> : <button type="button" className="button-primary" onClick={mode === "public" ? handleSubmit(submit) : () => submit(getValues())} disabled={isSubmitting}>{isSubmitting ? "Enviando…" : waitlistOnly ? "Entrar na lista de espera" : mode === "public" ? "Confirmar reserva" : "Criar agendamento"}</button>}</div></div>
  </section>;
}
