import { useState } from "react";
import { AppointmentWizard, type BookingData } from "../components/AppointmentWizard";
import { api, errorMessage } from "../lib/api";
import { useTenantSlug } from "../lib/useTenantSlug";

export function PublicBookingPage() {
  const slug = useTenantSlug();
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState(false);
  const [completionTitle, setCompletionTitle] = useState("Reserva solicitada");
  const [completionMessage, setCompletionMessage] = useState("");
  const tenantConfig = { headers: { "X-Tenant-Slug": slug ?? "" } };
  const complete = (title: string, message: string) => { setCompletionTitle(title); setCompletionMessage(message); setCompleted(true); setError(""); };
  const submit = async (data: BookingData) => {
    setError("");
    try {
      await api.post("/public/appointments/", data, tenantConfig);
      complete("Reserva solicitada", `Seu pedido de horário foi enviado para ${slug}. O salão poderá confirmar os detalhes.`);
    } catch (cause) { setError(errorMessage(cause)); }
  };
  const joinWaitlist = async (data: BookingData) => {
    setError("");
    try {
      await api.post("/public/waitlist/", { name: data.name, phone: data.phone, email: data.email, consent: data.consent, service: data.service, professional: data.professional, desired_date: data.desired_date }, tenantConfig);
      complete("Inscrição registrada", "Você entrou na lista de espera. Avisaremos por e-mail se surgir um horário; a vaga não fica reservada.");
    } catch (cause) { setError(errorMessage(cause)); }
  };
  if (!slug) return <main className="grid min-h-screen place-items-center p-5"><p role="alert" className="panel max-w-lg p-6 text-center">Não foi possível identificar o salão. Acesse o link de reserva enviado pelo estabelecimento.</p></main>;
  if (completed) return <main className="grid min-h-screen place-items-center p-5"><section className="panel w-full max-w-md p-7 text-center"><div className="mx-auto grid size-12 place-items-center rounded-full border border-amber-200/30 bg-amber-200/10 text-2xl text-amber-200">✓</div><p className="eyebrow mt-4">ÉCLAT · {slug}</p><h1 className="mt-2 font-serif text-3xl">{completionTitle}</h1><p className="muted-copy mt-3">{completionMessage}</p></section></main>;
  return <main className="app-shell min-h-screen px-3 py-5 sm:px-5 sm:py-10"><section className="panel mx-auto max-w-3xl p-4 sm:p-7"><header className="mb-5 border-b border-white/10 pb-5"><a className="brand-lockup" href="#"><span className="brand-mark">É</span><span><strong>Éclat</strong><small>RESERVA · {slug.toUpperCase()}</small></span></a><h1 className="mt-5 font-serif text-3xl font-normal sm:text-4xl">Agende seu horário</h1><p className="muted-copy mt-2">Escolha o serviço e um horário. É simples e rápido.</p></header>{error && <p role="alert" className="notice-error mb-4 rounded-lg bg-red-950/50 p-3">{error}</p>}<AppointmentWizard mode="public" slug={slug} onConfirm={data => void submit(data)} onWaitlist={data => void joinWaitlist(data)} /></section></main>;
}
