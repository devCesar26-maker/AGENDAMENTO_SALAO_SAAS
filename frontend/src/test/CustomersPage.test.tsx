import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { CustomersPage } from "../pages/CustomersPage";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth-context";

vi.mock("../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, errorMessage: (e: Error) => e.message }));
vi.mock("../lib/auth-context", () => ({ useAuth: vi.fn() }));

const cliente = { id: 7, name: "Carla", phone: "11999990000", email: "carla@x.com", responsavel: null, notes: "", lgpd_consent: false, lgpd_consent_at: null };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={client}><CustomersPage /></QueryClientProvider></MemoryRouter>);
}

describe("CustomersPage LGPD", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({ user: { id: 1, email: "a@b.com", first_name: "A", last_name: "B", organization: { id: 1, slug: "x" }, role: "OWNER" }, loading: false, login: vi.fn(), logout: vi.fn() });
    vi.mocked(api.post).mockResolvedValue({ data: {} } as never);
    vi.mocked(api.get).mockImplementation(async (url) => (url === "/customers/" ? { data: { results: [cliente] } } : { data: [] }) as never);
  });

  it("registra consentimento LGPD pelo endpoint dedicado", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByText("Carla"));
    await user.click(await screen.findByRole("button", { name: "Registrar consentimento" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/customers/7/lgpd-consent/", { consented: true }));
  });

  it("anonimiza dados do cliente após confirmação", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await user.click(await screen.findByText("Carla"));
    await user.click(await screen.findByRole("button", { name: "Anonimizar dados" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/customers/7/anonymize/"));
  });
});
