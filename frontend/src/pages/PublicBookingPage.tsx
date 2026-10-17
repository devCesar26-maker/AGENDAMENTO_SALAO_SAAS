import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { api, errorMessage } from "../lib/api";
import { useTenantSlug } from "../lib/useTenantSlug";

type Row<T> = T[] | { results: T[] };
type Service = { id: number; name: string; duration_minutes: number; price: string };
type Professional = { id: number; name: string; service_links: { service: number }[] };
type Slot = { start_at: string; items: { service: number; professional: number; start_at: string; end_at: string }[] };
const rows = <T,>(data: Row<T>) => Array.isArray(data) ? data : data.results;
const schema = z.object({ name: z.string().trim().min(2, "Informe seu nome"), phone: z.string().trim().min(8, "Informe um telefone válido"), email: z.union([z.literal(""), z.string().email("E-mail inválido")]), consent: z.literal(true, { error: "É necessário aceitar o uso dos dados para confirmar" }) });
type CustomerInput = z.infer<typeof schema>;
const dateString = (d: Date) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;

export function PublicBookingPage() {
  const slug = useTenantSlug();
  const [serviceIds, setServiceIds] = useState<number[]>([]);
  const [professional, setProfessional] = useState("any");
  const [date, setDate] = useState(dateString(new Date()));
  const [slot, setSlot] = useState("");
  const [message, setMessage] = useState("");
  const [completed, setCompleted] = useState(false);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<CustomerInput>({ resolver: zodResolver(schema) });
  const serviceQuery = useQuery({ queryKey: ["public-services", slug], enabled: !!slug, queryFn: async () => rows((await api.get<Row<Service>>("/services/")).data) });
  const professionalsQuery = useQuery({ queryKey: ["public-professionals", slug], enabled: !!slug, queryFn: async () => rows((await api.get<Row<Professional>>("/professionals/")).data) });
  const chosenProfessionals = professionalsQuery.data?.filter(p => serviceIds.every(id => p.service_links?.some(link => link.service === id))) ?? [];
  const slotsQuery = useQuery({ queryKey: ["public-availability", serviceIds.join(","), professional, date], enabled: serviceIds.length > 0 && !!date, queryFn: async () => (await api.get<{ slots: Slot[] }>("/availability/", { params: { services: serviceIds.join(","), professional, date } })).data.slots });
  const onSubmit = async (data: CustomerInput) => {
    setMessage("");
    try {
      if (!slot) throw new Error("Escolha um horário disponível.");
      const customerResponse = await api.post<{id:number}>("/customers/", { name: data.name, phone: data.phone, email: data.email });
      await api.post(`/customers/${customerResponse.data.id}/lgpd-consent/`, { consented: true });
      const matchingSlot = slotsQuery.data?.find(candidate => candidate.start_at === slot);
      if (!matchingSlot) throw new Error("Esse horário acabou de ficar indisponível. Escolha outro.");
      await api.post("/appointments/", { customer: customerResponse.data.id, start_at: slot, origin: "PUBLIC_PAGE", items: matchingSlot.items.map((item, order) => ({ service: item.service, professional: item.professional, order })) });
      setCompleted(true);
    } catch (error) { setMessage(errorMessage(error)); }
  };
  const toggleService = (id: number) => { setServiceIds(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]); setSlot(""); };
  if (!slug) return <main className="grid min-h-screen place-items-center bg-slate-50 p-5"><p role="alert" className="rounded-xl bg-white p-6 text-center">Não foi possível identificar o salão. Acesse o link de reserva enviado pelo estabelecimento.</p></main>;
  if (completed) return <main className="grid min-h-screen place-items-center bg-violet-50 p-5"><section className="w-full max-w-md rounded-2xl bg-white p-7 text-center shadow-sm"><div className="mx-auto grid size-12 place-items-center rounded-full bg-green-100 text-2xl text-green-700">✓</div><h1 className="mt-4 text-2xl font-semibold">Reserva solicitada</h1><p className="mt-2 text-slate-600">Seu horário foi enviado para {slug}. O salão poderá confirmar os detalhes.</p></section></main>;
  const loadError = serviceQuery.isError || professionalsQuery.isError;
  return <main className="min-h-screen bg-gradient-to-b from-violet-50 to-slate-50 px-4 py-6 sm:py-12"><section className="mx-auto max-w-2xl rounded-2xl bg-white p-5 shadow-sm sm:p-8"><header className="border-b border-slate-100 pb-5"><p className="text-sm font-medium uppercase tracking-wide text-violet-700">{slug}</p><h1 className="mt-1 text-2xl font-semibold text-slate-900 sm:text-3xl">Agende seu horário</h1><p className="mt-2 text-sm text-slate-600">Escolha os serviços, o profissional e um horário livre.</p></header>
    {(serviceQuery.isLoading || professionalsQuery.isLoading) && <p role="status" className="py-8 text-center text-slate-600">Carregando opções…</p>}
    {loadError && <p role="alert" className="mt-5 rounded-lg bg-red-50 p-3 text-sm text-red-700">Não foi possível carregar os serviços. {errorMessage(serviceQuery.error ?? professionalsQuery.error)}</p>}
    {!serviceQuery.isLoading && !serviceQuery.isError && <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 pt-5">
      <fieldset><legend className="font-semibold">1. Serviços</legend><div className="mt-3 grid gap-2 sm:grid-cols-2">{serviceQuery.data?.map(service => <label key={service.id} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 ${serviceIds.includes(service.id) ? "border-violet-500 bg-violet-50" : "border-slate-200"}`}><input type="checkbox" checked={serviceIds.includes(service.id)} onChange={() => toggleService(service.id)} className="mt-1 accent-violet-700"/><span className="min-w-0 flex-1"><span className="block font-medium">{service.name}</span><span className="text-sm text-slate-500">{service.duration_minutes} min · R$ {service.price}</span></span></label>)}</div>{serviceQuery.data?.length === 0 && <p className="text-sm text-slate-500">Nenhum serviço disponível no momento.</p>}</fieldset>
      {serviceIds.length > 0 && <><label className="block font-semibold">2. Profissional<select value={professional} onChange={e => {setProfessional(e.target.value);setSlot("");}} className="mt-2 w-full rounded-lg border border-slate-300 bg-white p-3 font-normal"><option value="any">Qualquer disponível</option>{chosenProfessionals.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label><div className="grid gap-3 sm:grid-cols-2"><label className="block font-semibold">3. Data<input type="date" value={date} min={dateString(new Date())} onChange={e => {setDate(e.target.value);setSlot("");}} className="mt-2 w-full rounded-lg border border-slate-300 p-3 font-normal"/></label><label className="block font-semibold">Horário<select value={slot} onChange={e => setSlot(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 bg-white p-3 font-normal"><option value="">{slotsQuery.isFetching ? "Buscando…" : "Escolha um horário"}</option>{slotsQuery.data?.map(s => <option key={s.start_at} value={s.start_at}>{new Date(s.start_at).toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})}</option>)}</select></label></div>{slotsQuery.isError && <p role="alert" className="text-sm text-red-700">{errorMessage(slotsQuery.error)}</p>}{slotsQuery.data?.length === 0 && !slotsQuery.isFetching && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">Não há horários livres nesta data. Tente outro dia.</p>}
        <fieldset className="space-y-3"><legend className="font-semibold">4. Seus dados</legend><label className="block text-sm">Nome<input {...register("name")} autoComplete="name" className="mt-1 w-full rounded-lg border p-3"/>{errors.name && <small className="text-red-600">{errors.name.message}</small>}</label><div className="grid gap-3 sm:grid-cols-2"><label className="block text-sm">Telefone<input {...register("phone")} autoComplete="tel" type="tel" className="mt-1 w-full rounded-lg border p-3"/>{errors.phone && <small className="text-red-600">{errors.phone.message}</small>}</label><label className="block text-sm">E-mail (opcional)<input {...register("email")} autoComplete="email" type="email" className="mt-1 w-full rounded-lg border p-3"/>{errors.email && <small className="text-red-600">{errors.email.message}</small>}</label></div><label className="flex items-start gap-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700"><input type="checkbox" {...register("consent")} className="mt-1 accent-violet-700"/><span>Autorizo o uso dos meus dados para criar e gerenciar esta reserva, conforme a política de privacidade do salão.</span></label>{errors.consent && <small className="text-red-600">{errors.consent.message}</small>}</fieldset>
        {message && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{message}</p>}<button disabled={isSubmitting || slotsQuery.isFetching} className="w-full rounded-xl bg-violet-700 px-4 py-3 font-semibold text-white disabled:opacity-50">{isSubmitting ? "Enviando reserva…" : "Confirmar reserva"}</button>
      </>}
    </form>}
  </section></main>;
}
