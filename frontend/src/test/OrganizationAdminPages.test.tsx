import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TeamPage } from "../pages/TeamPage";
import { OrganizationSettingsPage } from "../pages/OrganizationSettingsPage";
import { InvitationAcceptPage } from "../pages/InvitationAcceptPage";
import { api, setAccessToken } from "../lib/api";
import { useAuth } from "../lib/auth-context";

vi.mock("../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }, setAccessToken: vi.fn(), errorMessage: (error: Error) => error.message }));
vi.mock("../lib/auth-context", () => ({ useAuth: vi.fn() }));
vi.mock("../components/DashboardHeader", () => ({ DashboardHeader: () => <header /> }));

const organization = { id: 2, name: "Studio Éclat", slug: "studio-eclat", vertical: "SALAO" as const, phone: "11999999999", address: "Rua A", timezone: "America/Sao_Paulo", working_hours: { mon: [["09:00", "18:00"]] } };
function renderPage(element: React.ReactNode, route = "/") { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><Routes><Route path="/" element={element}/><Route path="/convite/:token" element={<InvitationAcceptPage/>}/></Routes></MemoryRouter></QueryClientProvider>); }

describe("administração da organização", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useAuth).mockReturnValue({ user: { id: 1, email: "owner@studio.test", first_name: "Ana", last_name: "Silva", organization: { id: 2, slug: "studio-eclat" }, role: "OWNER" }, loading: false, login: vi.fn().mockResolvedValue(undefined), logout: vi.fn(), acceptSession: vi.fn(), refreshUser: vi.fn().mockResolvedValue(undefined) });
    vi.mocked(api.get).mockImplementation(async (url) => ({ data: url.includes("members") ? [{ id: 4, role: "PROFESSIONAL", is_active: true, user: { id: 3, email: "bia@studio.test", first_name: "Bia", last_name: "Lima" } }] : url.includes("invitations") ? [] : organization } as never));
    vi.mocked(api.post).mockResolvedValue({ data: {} } as never);
    vi.mocked(api.patch).mockResolvedValue({ data: organization } as never);
    vi.mocked(api.delete).mockResolvedValue({ data: {} } as never);
    vi.stubGlobal("confirm", () => true);
    vi.stubGlobal("location", { assign: vi.fn(), origin: "http://localhost" });
  });

  it("envia convite para membro com papel selecionado", async () => {
    const user = userEvent.setup(); renderPage(<TeamPage/>);
    await user.type(await screen.findByLabelText("E-mail"), "nova@studio.test");
    await user.selectOptions(screen.getByLabelText("Papel"), "MANAGER");
    await user.click(screen.getByRole("button", { name: "Enviar convite" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/organizations/studio-eclat/invitations/", { email: "nova@studio.test", role: "MANAGER" }));
  });

  it("permite ao owner alterar role de outro membro", async () => {
    const user = userEvent.setup(); renderPage(<TeamPage/>);
    await user.selectOptions(await screen.findByLabelText("Papel de Bia Lima"), "MANAGER");
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/organizations/studio-eclat/members/4/", { role: "MANAGER" }));
  });

  it("salva configurações de organização e horário", async () => {
    const user = userEvent.setup(); renderPage(<OrganizationSettingsPage/>);
    await user.clear(await screen.findByLabelText("Nome do estabelecimento"));
    await user.type(screen.getByLabelText("Nome do estabelecimento"), "Studio Novo");
    await user.click(screen.getByRole("button", { name: "Salvar configurações" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/organizations/studio-eclat/", expect.objectContaining({ name: "Studio Novo", working_hours: expect.objectContaining({ mon: [["09:00", "18:00"]] }) })));
  });

  it("aceita convite completo de conta nova e instala os tokens", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { email: "nova@studio.test", role: "MANAGER", organization: { name: "Studio Éclat", slug: "studio-eclat" }, account_exists: false } } as never);
    vi.mocked(api.post).mockResolvedValue({ data: { access: "access-new", refresh: "refresh-new", role: "MANAGER", organization: { id: 2, slug: "studio-eclat" } } } as never);
    const user = userEvent.setup(); renderPage(<InvitationAcceptPage/>, "/convite/token-seguro");
    await user.type(await screen.findByLabelText("Nome"), "Joana");
    await user.type(screen.getByLabelText("Sobrenome (opcional)"), "Costa");
    await user.type(screen.getByLabelText(/Crie uma senha/), "SenhaSegura2026");
    await user.click(screen.getByRole("button", { name: "Aceitar convite" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/invitations/token-seguro/accept/", { first_name: "Joana", last_name: "Costa", password: "SenhaSegura2026" }));
    expect(setAccessToken).toHaveBeenCalledWith("access-new");
  });

  it("faz login e vincula conta já existente", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    const refreshUser = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({ user: null, loading: false, login, logout: vi.fn(), acceptSession: vi.fn(), refreshUser });
    vi.mocked(api.get).mockResolvedValue({ data: { email: "existente@studio.test", role: "PROFESSIONAL", organization: { name: "Studio Éclat", slug: "studio-eclat" }, account_exists: true } } as never);
    const user = userEvent.setup(); renderPage(<InvitationAcceptPage/>, "/convite/token-existente");
    await user.type(await screen.findByLabelText("Entre com sua senha"), "Senha#123");
    await user.click(screen.getByRole("button", { name: "Aceitar convite" }));
    await waitFor(() => expect(login).toHaveBeenCalledWith("existente@studio.test", "Senha#123"));
    expect(api.post).toHaveBeenCalledWith("/invitations/token-existente/accept/", { password: "Senha#123" });
    expect(refreshUser).toHaveBeenCalled();
  });
});
