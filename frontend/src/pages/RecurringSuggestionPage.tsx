import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";

interface SuggestionItem {
  service: string;
  professional: string;
  start_at: string;
  end_at: string;
}

interface SuggestionPayload {
  organization_name: string;
  customer_name: string;
  status: string;
  expires_at: string | null;
  items: SuggestionItem[];
}

const ENDPOINT = (token: string, decision?: "confirm" | "decline") =>
  decision ? `/public/suggestions/${token}/${decision}/` : `/public/suggestions/${token}/`;

function friendlyDetail(error: unknown): string {
  const axiosError = (error ?? {}) as {
    response?: { data?: { detail?: string } };
    detail?: string;
  };
  return axiosError.response?.data?.detail ?? axiosError.detail ?? errorMessage(error);
}

function when(item: SuggestionItem): string {
  return new Date(item.start_at).toLocaleString("pt-BR", { dateStyle: "full", timeStyle: "short" });
}

export function RecurringSuggestionPage() {
  const { token = "" } = useParams();
  const [decided, setDecided] = useState<"confirm" | "decline" | null>(null);

  const payloadQuery = useQuery({
    queryKey: ["suggestion", token],
    queryFn: async () => {
      try {
        const { data } = await api.get<SuggestionPayload>(ENDPOINT(token));
        return data;
      } catch (error) {
        throw new Error(friendlyDetail(error));
      }
    },
    retry: false,
    staleTime: 0,
  });

  const decisionMutation = useMutation({
    mutationFn: async (decision: "confirm" | "decline") => {
      try {
        const { data } = await api.post<SuggestionPayload>(ENDPOINT(token, decision));
        return { decision, data };
      } catch (error) {
        throw new Error(friendlyDetail(error));
      }
    },
    onSuccess: ({ decision }) => setDecided(decision),
  });

  if (payloadQuery.isError) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="eyebrow">SUGESTÃO</p>
          <h1 className="login-title mt-2">Esta sugestão não está mais disponível</h1>
          <p role="alert" className="muted-copy mt-3">{payloadQuery.error.message}</p>
        </section>
      </main>
    );
  }

  if (payloadQuery.isLoading || !payloadQuery.data) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="muted-copy">Carregando…</p>
        </section>
      </main>
    );
  }

  if (decided) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="eyebrow">{payloadQuery.data.organization_name.toUpperCase()}</p>
          <h1 className="mt-2 font-serif text-3xl">
            {decided === "confirm" ? "Horário confirmado!" : "Sugestão recusada"}
          </h1>
          <p className="muted-copy mt-3">
            {decided === "confirm"
              ? "Enviamos a confirmação do seu agendamento. Até lá!"
              : "Sem problemas — nenhum horário foi reservado. Você pode agendar quando quiser."}
          </p>
        </section>
      </main>
    );
  }

  const payload = payloadQuery.data;
  const first = payload.items[0];

  return (
    <main className="grid min-h-screen place-items-center p-5">
      <section className="panel w-full max-w-md p-7">
        <p className="eyebrow">LEMBRETE · {payload.organization_name}</p>
        <h1 className="mt-2 font-serif text-3xl">Que tal agendar de novo?</h1>
        <p className="muted-copy mt-1">
          {payload.customer_name}, já faz um tempinho desde seu último{" "}
          {payload.items.length === 1 ? "atendimento" : "atendimentos"}. Guardamos um horário parecido com o seu
          costume:
        </p>

        <ul className="mt-5 grid gap-3">
          {payload.items.map((item, index) => (
            <li key={index} className="rounded-lg border border-white/10 bg-white/3 p-3 text-sm">
              <p className="font-medium">{item.service}</p>
              <p className="muted-copy">Com {item.professional}</p>
              <p className="mt-1 text-indigo-200">{when(item)}</p>
            </li>
          ))}
        </ul>

        {first && (
          <p className="muted-copy mt-4">
            Se não puder, sem problema — basta recusar e o horário volta a ficar livre.
          </p>
        )}

        {decisionMutation.isError && (
          <p role="alert" className="notice-error mt-4">{decisionMutation.error.message}</p>
        )}

        <div className="mt-6 flex flex-col gap-2">
          <button
            className="button-primary button-wide"
            disabled={decisionMutation.isPending}
            onClick={() => decisionMutation.mutate("confirm")}
          >
            {decisionMutation.isPending && decisionMutation.variables === "confirm"
              ? "Confirmando…"
              : "Confirmar este horário"}
          </button>
          <button
            className="button-quiet button-wide"
            disabled={decisionMutation.isPending}
            onClick={() => decisionMutation.mutate("decline")}
          >
            Não, obrigado
          </button>
        </div>
      </section>
    </main>
  );
}
