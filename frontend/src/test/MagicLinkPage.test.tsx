import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MagicLinkPage } from "../pages/MagicLinkPage";
import { api } from "../lib/api";

vi.mock(
  "../lib/api",
  () => ({ api: { get: vi.fn(), post: vi.fn() }, errorMessage: (e: Error) => e.message })
);

const payload = {
  status: "SCHEDULED",
  organization_name: "Studio Índigo",
  customer_name: "Carla Souza",
  can_cancel: true,
  expires_at: "2026-10-21T09:00:00-03:00",
  items: [
    {
      service: "Corte feminino",
      professional: "Ana Lima",
      start_at: "2026-10-22T09:00:00-03:00",
      end_at: "2026-10-22T10:00:00-03:00",
    },
  ],
};

const canceled = { ...payload, status: "CANCELED", can_cancel: false };

function renderAtToken() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/a/tok-123"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/a/:token" element={<MagicLinkPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function apiError(status: number, detail: string) {
  // Shape de AxiosError o suficiente para friendlyDetail/errorMessage.
  return Object.assign(new Error(detail), {
    response: { status, data: { detail } },
    isAxiosError: true,
  });
}

beforeEach(() => {
  vi.mocked(api.post).mockResolvedValue({ data: canceled } as never);
});

describe("MagicLinkPage", () => {
  it("mostra serviço, profissional, data/hora e estado atual", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: payload } as never);
    renderAtToken();

    expect(await screen.findByText("Corte feminino")).toBeInTheDocument();
    expect(screen.getByText(/Com Ana Lima/)).toBeInTheDocument();
    expect(screen.getByText(/22\/10\/2026/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Agendado");
  });

  it("cancela pelo token após confirmação e atualiza a tela", async () => {
    const user = userEvent.setup();
    vi.mocked(api.get).mockResolvedValue({ data: payload } as never);
    renderAtToken();

    await user.click(await screen.findByRole("button", { name: "Cancelar agendamento" }));
    await user.click(await screen.findByRole("button", { name: "Sim, cancelar" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/public/appointments/tokens/tok-123/cancel/")
    );
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Cancelado"));
    expect(
      screen.queryByRole("button", { name: "Cancelar agendamento" })
    ).not.toBeInTheDocument();
  });

  it("token inválido mostra mensagem clara, sem jargão", async () => {
    vi.mocked(api.get).mockRejectedValue(apiError(404, "Este link é inválido."));
    renderAtToken();

    expect(await screen.findByText(/Este link é inválido/)).toBeInTheDocument();
  });

  it("token expirado mostra orientação para pedir um novo link", async () => {
    vi.mocked(api.get).mockRejectedValue(
      apiError(410, "Este link expirou. Peça um novo ao salão.")
    );
    renderAtToken();

    expect(await screen.findByText(/Este link expirou/)).toBeInTheDocument();
  });

  it("token já utilizado mostra mensagem de uso único", async () => {
    vi.mocked(api.get).mockRejectedValue(apiError(410, "Este link já foi utilizado."));
    renderAtToken();

    expect(await screen.findByText(/já foi utilizado/)).toBeInTheDocument();
  });

  it("falha no cancelamento mostra a mensagem e mantém o botão", async () => {
    const user = userEvent.setup();
    vi.mocked(api.get).mockResolvedValue({ data: payload } as never);
    vi.mocked(api.post).mockRejectedValue(
      apiError(409, "Este agendamento não pode mais ser cancelado online.")
    );
    renderAtToken();

    await user.click(await screen.findByRole("button", { name: "Cancelar agendamento" }));
    await user.click(await screen.findByRole("button", { name: "Sim, cancelar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /não pode mais ser cancelado online/
    );
    expect(
      screen.getByRole("button", { name: "Cancelar agendamento" })
    ).toBeEnabled();
  });
});
