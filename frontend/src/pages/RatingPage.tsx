import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";

interface RatingItem {
  service: string;
  professional: string;
  start_at: string;
}

interface RatingPayload {
  organization_name: string;
  customer_name: string;
  expires_at: string;
  items: RatingItem[];
}

interface RatingResult {
  id: number;
  score: number;
  detail: string;
}

const ENDPOINT = (token: string) => `/public/ratings/${token}/`;

// Estes endpoints devolvem {"detail": "..."} direto (fora do padrão {"error": ...}).
function friendlyDetail(error: unknown): string {
  const axiosError = (error ?? {}) as {
    response?: { data?: { detail?: string } };
    detail?: string;
  };
  return axiosError.response?.data?.detail ?? axiosError.detail ?? errorMessage(error);
}

function when(item: RatingItem): string {
  return new Date(item.start_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function RatingPage() {
  const { token = "" } = useParams();
  const queryClient = useQueryClient();
  const [score, setScore] = useState(0);
  const [comment, setComment] = useState("");
  const [hovered, setHovered] = useState(0);

  const payloadQuery = useQuery({
    queryKey: ["rating", token],
    queryFn: async () => {
      try {
        const { data } = await api.get<RatingPayload>(ENDPOINT(token));
        return data;
      } catch (error) {
        throw new Error(friendlyDetail(error));
      }
    },
    retry: false,
    staleTime: 30_000,
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      try {
        const { data } = await api.post<RatingResult>(ENDPOINT(token), { score, comment });
        return data;
      } catch (error) {
        throw new Error(friendlyDetail(error));
      }
    },
    onSuccess: () => {
      queryClient.setQueryData<RatingPayload>(["rating", token], undefined);
    },
  });

  if (payloadQuery.isError) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="eyebrow">AVALIAÇÃO</p>
          <h1 className="login-title mt-2">Não foi possível abrir sua avaliação</h1>
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

  if (submitMutation.isSuccess) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="panel w-full max-w-md p-7 text-center">
          <p className="eyebrow">OBRIGADO!</p>
          <h1 className="mt-2 font-serif text-3xl">Avaliação registrada</h1>
          <p className="muted-copy mt-3">Sua opinião ajuda o salão a melhorar cada atendimento.</p>
        </section>
      </main>
    );
  }

  const payload = payloadQuery.data;
  const visible = hovered || score;

  return (
    <main className="grid min-h-screen place-items-center p-5">
      <section className="panel w-full max-w-md p-7">
        <p className="eyebrow">AVALIAÇÃO · {payload.organization_name}</p>
        <h1 className="mt-2 font-serif text-3xl">Como foi seu atendimento?</h1>
        <p className="muted-copy mt-1">Olá, {payload.customer_name}.</p>

        <ul className="mt-5 grid gap-3">
          {payload.items.map((item, index) => (
            <li key={index} className="rounded-lg border border-white/10 bg-white/3 p-3 text-sm">
              <p className="font-medium">{item.service}</p>
              <p className="muted-copy">Com {item.professional}</p>
              <p className="mt-1 text-indigo-200">{when(item)}</p>
            </li>
          ))}
        </ul>

        <fieldset className="mt-6">
          <legend className="field-label">Sua nota</legend>
          <div className="flex gap-1" role="radiogroup" aria-label="Nota de 1 a 5">
            {[1, 2, 3, 4, 5].map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={score === value}
                aria-label={`${value} de 5`}
                className={`icon-button text-2xl ${visible >= value ? "text-amber-300" : "text-white/30"}`}
                onMouseEnter={() => setHovered(value)}
                onMouseLeave={() => setHovered(0)}
                onClick={() => setScore(value)}
              >
                ★
              </button>
            ))}
          </div>
        </fieldset>

        <label className="field-label mt-4">
          Comentário (opcional)
          <textarea
            className="field-input"
            rows={3}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
        </label>

        {submitMutation.isError && (
          <p role="alert" className="notice-error mt-4">{submitMutation.error.message}</p>
        )}

        <button
          className="button-primary button-wide mt-6"
          disabled={score === 0 || submitMutation.isPending}
          onClick={() => submitMutation.mutate()}
        >
          {submitMutation.isPending ? "Enviando…" : "Enviar avaliação"}
        </button>
      </section>
    </main>
  );
}
