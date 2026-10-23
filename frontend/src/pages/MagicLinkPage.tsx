import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";
import { Dialog } from "../components/ui";

interface MagicItem {
  service: string;
  professional: string;
  start_at: string;
  end_at: string;
}

interface MagicPayload {
  status: string;
  organization_name: string;
  customer_name: string;
  can_cancel: boolean;
  cancel_token?: string;
  expires_at: string;
  items: MagicItem[];
}

const STATUS_LABELS: Record<string, string> = {
  SCHEDULED: "Agendado",
  CONFIRMED: "Confirmado",
  COMPLETED: "Concluído",
  CANCELED: "Cancelado",
  NO_SHOW: "Não compareceu",
};

const ENDPOINT = (token: string) => `/public/appointments/tokens/${token}`;
const CANCEL_ENDPOINT = (token: string) => `/public/appointments/tokens/${token}/cancel/`;

// O link mágico devolve {"detail": "..."} direto (fora do padrão {"error": ...}),
// então tentamos esse campo primeiro para as mensagens amigáveis do backend.
function friendlyDetail(error: unknown): string {
  const axiosError = (error ?? {}) as {
    response?: { data?: { detail?: string } };
    detail?: string;
  };
  const fromBackend = axiosError.response?.data?.detail ?? axiosError.detail;
  return fromBackend ?? errorMessage(error);
}

function when(item: MagicItem): string {
  return new Date(item.start_at).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export function MagicLinkPage() {
  const { token = "" } = useParams();
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const appointmentQuery = useQuery({
    queryKey: ["magic-link", token],
    queryFn: async () => {
      try {
        const { data } = await api.get<MagicPayload>(ENDPOINT(token));
        return data;
      } catch (error) {
        throw new Error(friendlyDetail(error));
      }
    },
    retry: false,
    staleTime: 30_000,
  });

  const cancelMutation = useMutation({
    mutationFn: async () => {
      try {
        // O backend entrega um token CANCEL específico no GET. Se o e-mail for
        // antigo (sem esse campo), o token VIEW da URL continua funcionando.
        const target = appointmentQuery.data?.cancel_token ?? token;
        const { data } = await api.post<MagicPayload>(CANCEL_ENDPOINT(target));
        return data;
      } catch (error) {
        throw new Error(friendlyDetail(error));
      }
    },
    onSuccess: (data) => {
      setConfirmOpen(false);
      queryClient.setQueryData(["magic-link", token], data);
    },
  });

  const appointment = appointmentQuery.data;
  // Só bloqueia enquanto a requisição está em andamento: após um erro o botão
  // precisa voltar a funcionar para o cliente tentar novamente.
  const canceling = cancelMutation.isPending;

  if (appointmentQuery.isError) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="eyebrow">AGENDAMENTO</p>
          <h1 className="login-title mt-2">Não foi possível mostrar seu agendamento</h1>
          <p role="alert" className="muted-copy mt-3">
            {appointmentQuery.error.message}
          </p>
        </section>
      </main>
    );
  }

  if (appointmentQuery.isLoading || !appointment) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel max-w-md w-full p-7 text-center">
          <p className="muted-copy">Carregando seu agendamento…</p>
        </section>
      </main>
    );
  }

  return (
    <main className="grid min-h-screen place-items-center p-5">
      <section className="panel w-full max-w-md p-7">
        <p className="eyebrow">AGENDAMENTO · {appointment.organization_name}</p>
        <h1 className="mt-2 font-serif text-3xl">Seu horário</h1>
        <p className="muted-copy mt-1">
          Reserva de <strong>{appointment.customer_name}</strong> ·{" "}
          <span role="status">{STATUS_LABELS[appointment.status] ?? appointment.status}</span>
        </p>

        <ul className="mt-5 grid gap-3">
          {appointment.items.map((item, index) => (
            <li key={index} className="rounded-lg border border-white/10 bg-white/3 p-3 text-sm">
              <p className="font-medium">{item.service}</p>
              <p className="muted-copy">Com {item.professional}</p>
              <p className="mt-1 text-indigo-200">{when(item)}</p>
            </li>
          ))}
        </ul>

        {cancelMutation.isError && (
          <p role="alert" className="notice-error mt-4">
            {cancelMutation.error.message}
          </p>
        )}

        {appointment.can_cancel ? (
          <div className="mt-6">
            <button
              className="button-primary button-wide"
              onClick={() => setConfirmOpen(true)}
              disabled={canceling}
            >
              Cancelar agendamento
            </button>
          </div>
        ) : (
          <p className="muted-copy mt-6">
            {appointment.status === "CANCELED"
              ? "Este agendamento está cancelado. Fale com o salão para reagendar."
              : "Este agendamento não pode mais ser cancelado online."}
          </p>
        )}

        <Dialog
          isOpen={confirmOpen}
          onClose={() => setConfirmOpen(false)}
          onConfirm={() => cancelMutation.mutate()}
          title="Cancelar este agendamento?"
          description="Essa ação não pode ser desfeita — seu horário será liberado. Se quiser voltar, será preciso agendar de novo."
          confirmText="Sim, cancelar"
          cancelText="Manter agendamento"
          variant="danger"
          isLoading={canceling}
        />
      </section>
    </main>
  );
}
