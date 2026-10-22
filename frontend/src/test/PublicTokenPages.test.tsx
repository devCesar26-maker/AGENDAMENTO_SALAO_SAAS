import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RatingPage } from "../pages/RatingPage";
import { RecurringSuggestionPage } from "../pages/RecurringSuggestionPage";
import { WaitlistPriorityPage } from "../pages/WaitlistPriorityPage";
import { api } from "../lib/api";

vi.mock(
  "../lib/api",
  () => ({ api: { get: vi.fn(), post: vi.fn() }, errorMessage: (e: Error) => e.message })
);

function renderAt(path: string, pattern: string, element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path={pattern} element={element} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function apiError(status: number, detail: string) {
  return Object.assign(new Error(detail), {
    response: { status, data: { detail } },
    isAxiosError: true,
  });
}

const item = {
  service: "Corte feminino",
  professional: "Ana Lima",
  start_at: "2026-10-22T09:00:00-03:00",
  end_at: "2026-10-22T10:00:00-03:00",
};

describe("RatingPage", () => {
  const payload = {
    organization_name: "Studio Índigo",
    customer_name: "Carla Souza",
    expires_at: "2026-11-05T09:00:00-03:00",
    items: [item],
  };

  it("só habilita o envio depois de escolher uma nota", async () => {
    const user = userEvent.setup();
    vi.mocked(api.get).mockResolvedValue({ data: payload } as never);
    renderAt("/avaliar/tok-1", "/avaliar/:token", <RatingPage />);

    expect(await screen.findByText("Corte feminino")).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Enviar avaliação" });
    expect(submit).toBeDisabled();

    await user.click(screen.getByRole("radio", { name: "5 de 5" }));
    expect(submit).toBeEnabled();
  });

  it("envia a nota e mostra confirmação", async () => {
    const user = userEvent.setup();
    vi.mocked(api.get).mockResolvedValue({ data: payload } as never);
    vi.mocked(api.post).mockResolvedValue({
      data: { id: 1, score: 5, detail: "Avaliação registrada." },
    } as never);
    renderAt("/avaliar/tok-1", "/avaliar/:token", <RatingPage />);

    await user.click(await screen.findByRole("radio", { name: "4 de 5" }));
    await user.click(screen.getByRole("button", { name: "Enviar avaliação" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/public/ratings/tok-1/", { score: 4, comment: "" })
    );
    expect(await screen.findByText(/Avaliação registrada/)).toBeInTheDocument();
  });

  it("link expirado mostra mensagem clara", async () => {
    vi.mocked(api.get).mockRejectedValue(apiError(410, "Este link expirou. Peça um novo ao salão."));
    renderAt("/avaliar/tok-1", "/avaliar/:token", <RatingPage />);

    expect(await screen.findByText(/Este link expirou/)).toBeInTheDocument();
  });
});

describe("RecurringSuggestionPage", () => {
  const payload = {
    organization_name: "Studio Índigo",
    customer_name: "Carla Souza",
    status: "SUGGESTED",
    expires_at: "2026-11-05T09:00:00-03:00",
    items: [item],
  };

  it("confirma a sugestão e mostra o resultado", async () => {
    const user = userEvent.setup();
    vi.mocked(api.get).mockResolvedValue({ data: payload } as never);
    vi.mocked(api.post).mockResolvedValue({ data: { ...payload, status: "CONFIRMED" } } as never);
    renderAt("/sugestao/tok-2", "/sugestao/:token", <RecurringSuggestionPage />);

    await user.click(await screen.findByRole("button", { name: "Confirmar este horário" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/public/suggestions/tok-2/confirm/")
    );
    expect(await screen.findByText(/Horário confirmado/)).toBeInTheDocument();
  });

  it("recusa a sugestão sem reservar", async () => {
    const user = userEvent.setup();
    vi.mocked(api.get).mockResolvedValue({ data: payload } as never);
    vi.mocked(api.post).mockResolvedValue({ data: { ...payload, status: "CANCELED" } } as never);
    renderAt("/sugestao/tok-2", "/sugestao/:token", <RecurringSuggestionPage />);

    await user.click(await screen.findByRole("button", { name: "Não, obrigado" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/public/suggestions/tok-2/decline/"));
    expect(await screen.findByText(/Sugestão recusada/)).toBeInTheDocument();
  });
});

describe("WaitlistPriorityPage", () => {
  const payload = {
    organization_name: "Studio Índigo",
    customer_name: "Carla Souza",
    service: "Corte feminino",
    professional: "Ana Lima",
    start_at: item.start_at,
    end_at: item.end_at,
    price: "90.00",
    expires_at: "2026-10-22T12:00:00-03:00",
  };

  it("mostra a oferta e reserva ao confirmar", async () => {
    const user = userEvent.setup();
    vi.mocked(api.get).mockResolvedValue({ data: payload } as never);
    vi.mocked(api.post).mockResolvedValue({
      data: { id: 7, status: "SCHEDULED", start_at: item.start_at },
    } as never);
    renderAt("/prioridade/tok-3", "/prioridade/:token", <WaitlistPriorityPage />);

    expect(await screen.findByText(/Com Ana Lima/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reservar este horário" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/public/waitlist/offers/tok-3/", { consent: true })
    );
    expect(await screen.findByText(/Horário reservado/)).toBeInTheDocument();
  });

  it("oferta expirada mostra que não está mais disponível", async () => {
    vi.mocked(api.get).mockRejectedValue(
      apiError(410, "Esta oferta expirou ou já foi utilizada.")
    );
    renderAt("/prioridade/tok-3", "/prioridade/:token", <WaitlistPriorityPage />);

    expect(await screen.findByText(/expirou ou já foi utilizada/)).toBeInTheDocument();
  });
});
