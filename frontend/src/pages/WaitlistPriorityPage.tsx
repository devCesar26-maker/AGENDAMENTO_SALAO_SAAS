import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";

interface PriorityOfferPayload {
  organization_name: string;
  customer_name: string;
  service: string;
  professional: string;
  start_at: string;
  end_at: string;
  price: string;
  expires_at: string;
}

interface BookingResult {
  id: number;
  status: string;
  start_at: string | null;
}

const ENDPOINT = (token: string) => `/public/waitlist/offers/${token}/`;

function friendlyDetail(error: unknown): string {
  const axiosError = (error ?? {}) as {
    response?: { data?: { detail?: string } };
    detail?: string;
  };
  return axiosError.response?.data?.detail ?? axiosError.detail ?? errorMessage(error);
}

function when(value: string): string {
  return new Date(value).toLocaleString("pt-BR", { dateStyle: "full", timeStyle: "short" });
}

export function WaitlistPriorityPage() {
  const { token = "" } = useParams();

  const offerQuery = useQuery({
    queryKey: ["priority-offer", token],
    queryFn: async () => {
      try {
        const { data } = await api.get<PriorityOfferPayload>(ENDPOINT(token));
        return data;
      } catch (error) {
        throw new Error(friendlyDetail(error));
      }
    },
    retry: false,
    staleTime: 0,
  });

  const bookMutation = useMutation({
    mutationFn: async () => {
      try {
        const { data } = await api.post<BookingResult>(ENDPOINT(token), { consent: true });
        return data;
      } catch (error) {
        throw new Error(friendlyDetail(error));
      }
    },
  });

  if (offerQuery.isError) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="eyebrow">RESERVA PRIORITÁRIA</p>
          <h1 className="login-title mt-2">Esta oferta não está mais disponível</h1>
          <p role="alert" className="muted-copy mt-3">{offerQuery.error.message}</p>
        </section>
      </main>
    );
  }

  if (offerQuery.isLoading || !offerQuery.data) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="muted-copy">Carregando…</p>
        </section>
      </main>
    );
  }

  if (bookMutation.isSuccess) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="eyebrow">TUDO CERTO!</p>
          <h1 className="mt-2 font-serif text-3xl">Horário reservado</h1>
          <p className="muted-copy mt-3">
            Seu agendamento em {offerQuery.data.organization_name} foi confirmado. Enviaremos os detalhes por e-mail.
          </p>
        </section>
      </main>
    );
  }

  const offer = offerQuery.data;

  return (
    <main className="grid min-h-screen place-items-center p-5">
      <section className="panel w-full max-w-md p-7">
        <p className="eyebrow">RESERVA PRIORITÁRIA · {offer.organization_name}</p>
        <h1 className="mt-2 font-serif text-3xl">Um horário abriu para você</h1>
        <p className="muted-copy mt-1">
          {offer.customer_name}, você é o primeiro da lista de espera para{" "}
          <strong>{offer.service}</strong>. Garanta este horário antes que ele seja liberado para os outros.
        </p>

        <ul className="mt-5 grid gap-3">
          <li className="rounded-lg border border-white/10 bg-white/3 p-3 text-sm">
            <p className="font-medium">{offer.service}</p>
            <p className="muted-copy">Com {offer.professional}</p>
            <p className="mt-1 text-indigo-200">{when(offer.start_at)}</p>
          </li>
        </ul>

        <p className="muted-copy mt-3">
          Oferta válida até {when(offer.expires_at)}. Depois disso, o horário é oferecido à próxima pessoa da fila.
        </p>

        {bookMutation.isError && (
          <p role="alert" className="notice-error mt-4">{bookMutation.error.message}</p>
        )}

        <button
          className="button-primary button-wide mt-6"
          disabled={bookMutation.isPending}
          onClick={() => bookMutation.mutate()}
        >
          {bookMutation.isPending ? "Reservando…" : "Reservar este horário"}
        </button>
      </section>
    </main>
  );
}
