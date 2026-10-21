import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ServicesPage } from "../pages/ServicesPage";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, errorMessage: (e: Error) => e.message }));
vi.mock("../components/DashboardHeader", () => ({ DashboardHeader: () => <header /> }));

const categoria = { id: 5, name: "Corte Feminino", is_active: true };
const servico = { id: 9, category: 5, category_name: "Corte Feminino", name: "Corte", description: "Corte clássico", duration_minutes: 60, price: "80.00", buffer_minutes: 0, is_active: true };

describe("ServicesPage", () => {
  beforeEach(() => {
    vi.mocked(api.get).mockImplementation(async (url) => (url === "/services/" ? { data: [servico] } : url === "/service-categories/" ? { data: [categoria] } : []) as never);
    vi.mocked(api.post).mockResolvedValue({ data: {} } as never);
    vi.mocked(api.patch).mockResolvedValue({ data: {} } as never);
  });

  it("salva novo serviço pelo clique no botão de submit do formulário", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<MemoryRouter><QueryClientProvider client={client}><ServicesPage /></QueryClientProvider></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: "Editar" }));
    await user.click(screen.getByRole("button", { name: "Salvar serviço" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/services/9/", expect.objectContaining({ name: "Corte", category: 5 })));
  });

  it("cria categoria pelo botão do modal", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<MemoryRouter><QueryClientProvider client={client}><ServicesPage /></QueryClientProvider></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: "Gerenciar categorias" }));
    await user.type(screen.getByLabelText("Nova categoria"), "Depilação");
    await user.click(screen.getByRole("button", { name: "Adicionar categoria" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/service-categories/", expect.objectContaining({ name: "Depilação" })));
  });
});
