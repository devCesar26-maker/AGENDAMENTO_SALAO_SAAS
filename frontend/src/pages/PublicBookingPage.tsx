import { useState } from "react";
import { MapPin, Phone } from "lucide-react";
import { AppointmentWizard, type BookingData } from "../components/AppointmentWizard";
import { BrandMark } from "../components/BrandMark";
import { api, errorMessage } from "../lib/api";
import { usePublicTenantBranding } from "../hooks/usePublicTenantBranding";
import { useTenantSlug } from "../lib/useTenantSlug";

export function PublicBookingPage() {
  const slug = useTenantSlug();
  const { profile, catalogLoading, catalogError } = usePublicTenantBranding(slug);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [completionTitle, setCompletionTitle] = useState("Reserva solicitada");
  const [completionMessage, setCompletionMessage] = useState("");
  const tenantConfig = { headers: { "X-Tenant-Slug": slug ?? "" } };
  const displayName = profile?.name ?? slug ?? "Estabelecimento";

  const complete = (title: string, message: string) => {
    setCompletionTitle(title);
    setCompletionMessage(message);
    setCompleted(true);
    setError("");
  };

  const submit = async (data: BookingData) => {
    setError("");
    setSubmitting(true);
    try {
      await api.post("/public/appointments/", data, tenantConfig);
      complete(
        "Reserva solicitada",
        `Seu pedido de horário foi enviado para ${displayName}. O salão poderá confirmar os detalhes.`,
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  };

  const joinWaitlist = async (data: BookingData) => {
    setError("");
    setSubmitting(true);
    try {
      await api.post(
        "/public/waitlist/",
        {
          name: data.name,
          phone: data.phone,
          email: data.email,
          consent: data.consent,
          service: data.service,
          professional: data.professional,
          desired_date: data.desired_date,
        },
        tenantConfig,
      );
      complete(
        "Inscrição registrada",
        "Você entrou na lista de espera. O salão entrará em contato se surgir uma vaga. Ela não fica reservada.",
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  };

  if (!slug) {
    return (
      <main className="public-booking-shell grid place-items-center">
        <p role="alert" className="panel public-booking-card text-center">
          Não foi possível identificar o salão. Acesse o link de reserva enviado pelo estabelecimento.
        </p>
      </main>
    );
  }

  if (completed) {
    return (
      <main className="public-booking-shell grid place-items-center">
        <section className="panel public-booking-card text-center">
          <div className="mx-auto grid size-12 place-items-center rounded-full border border-indigo-200/30 bg-indigo-200/10 text-2xl text-indigo-200">
            ✓
          </div>
          <p className="eyebrow mt-4">RESERVA · {displayName.toUpperCase()}</p>
          <h1 className="mt-2 font-serif text-3xl">{completionTitle}</h1>
          <p className="muted-copy mt-3">{completionMessage}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="public-booking-shell">
      <section className="panel public-booking-card">
        <header className="mb-5 border-b border-white/10 pb-5">
          <div className="brand-lockup">
            <BrandMark label={displayName} />
            <span>
              <strong>{displayName}</strong>
              <small>RESERVA ONLINE</small>
            </span>
          </div>
          <h1 className="mt-5 font-serif text-3xl font-normal sm:text-4xl">Agende seu horário</h1>
          <p className="muted-copy mt-2">Escolha o serviço e um horário. É simples e rápido.</p>
          {(profile?.phone || profile?.address) && (
            <div className="public-booking-meta">
              {profile.phone && (
                <span>
                  <Phone size={15} aria-hidden /> {profile.phone}
                </span>
              )}
              {profile.address && (
                <span>
                  <MapPin size={15} aria-hidden /> {profile.address}
                </span>
              )}
            </div>
          )}
        </header>
        {catalogLoading && <p className="helper-copy mb-4">Carregando disponibilidade…</p>}
        {catalogError && (
          <p role="alert" className="notice-error mb-4 rounded-lg bg-red-950/50 p-3">
            Não foi possível carregar os serviços deste estabelecimento.
          </p>
        )}
        {error && <p role="alert" className="notice-error mb-4 rounded-lg bg-red-950/50 p-3">{error}</p>}
        <AppointmentWizard mode="public" slug={slug} isSubmitting={submitting} onConfirm={data => void submit(data)} onWaitlist={data => void joinWaitlist(data)} />
      </section>
    </main>
  );
}
