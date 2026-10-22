import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";

interface Insight {
  type: string;
  severity: "info" | "warning";
  message: string;
  reference: Record<string, unknown>;
}

interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

const TYPE_LABELS: Record<string, string> = {
  low_occupancy: "Ocupação baixa",
  inactive_customers: "Clientes inativos",
  declining_service: "Serviço em queda",
  professional_imbalance: "Distribuição da equipe",
};

const TYPE_HINTS: Record<string, string> = {
  low_occupancy: "Considere abrir promoções nesse período ou ajustar o expediente.",
  inactive_customers: "Envie uma mensagem de retorno para reativar esses clientes.",
  declining_service: "Revise preço, divulgação ou a experiência desse serviço.",
  professional_imbalance: "Redistribua a agenda para equilibrar a equipe.",
};

const PAGE_SIZE = 10;

export function InsightsPage() {
  const [page, setPage] = useState(1);

  const insightsQuery = useQuery({
    queryKey: ["insights", page],
    queryFn: async () => {
      const { data } = await api.get<Paginated<Insight>>("/insights/", {
        params: { page, page_size: PAGE_SIZE },
      });
      return data;
    },
  });

  const results = insightsQuery.data?.results ?? [];
  const total = insightsQuery.data?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="page-content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">OPORTUNIDADES</p>
          <h1>Insights</h1>
          <p className="muted-copy">
            Sugestões automáticas a partir dos seus dados. São pistas para você decidir, não ordens.
          </p>
        </div>
      </div>

      {insightsQuery.isError ? (
        <p role="alert" className="notice-error">
          Não foi possível carregar os insights. {errorMessage(insightsQuery.error)}
        </p>
      ) : insightsQuery.isLoading ? (
        <div className="panel loading-panel">Analisando seus dados…</div>
      ) : results.length === 0 ? (
        <section className="panel">
          <p className="helper-copy">
            Nada pendente por aqui. Conforme você registra atendimentos, os insights aparecem automaticamente.
          </p>
        </section>
      ) : (
        <>
          <ul className="grid gap-3">
            {results.map((insight, index) => (
              <li
                key={`${insight.type}-${index}`}
                className={`panel insight-card ${insight.severity === "warning" ? "is-warning" : ""}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="eyebrow">{TYPE_LABELS[insight.type] ?? insight.type}</p>
                    <p className="mt-1">{insight.message}</p>
                    <p className="muted-copy mt-1 text-sm">{TYPE_HINTS[insight.type]}</p>
                  </div>
                  <span
                    className={`ui-badge ${insight.severity === "warning" ? "ui-badge-warning" : "ui-badge-neutral"}`}
                  >
                    {insight.severity === "warning" ? "Atenção" : "Observação"}
                  </span>
                </div>
              </li>
            ))}
          </ul>

          {totalPages > 1 && (
            <nav className="pagination" aria-label="Paginação de insights">
              <button
                type="button"
                className="button-quiet"
                disabled={!insightsQuery.data?.previous || insightsQuery.isFetching}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                Anterior
              </button>
              <span className="muted-copy">
                Página {page} de {totalPages} · {total} sugestões
              </span>
              <button
                type="button"
                className="button-quiet"
                disabled={!insightsQuery.data?.next || insightsQuery.isFetching}
                onClick={() => setPage((current) => current + 1)}
              >
                Próxima
              </button>
            </nav>
          )}
        </>
      )}
    </main>
  );
}
