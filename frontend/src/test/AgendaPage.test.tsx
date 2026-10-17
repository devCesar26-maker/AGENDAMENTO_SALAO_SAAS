import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgendaPage } from "../pages/AgendaPage";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

vi.mock("../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, errorMessage: (e: Error) => e.message }));
vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }));
vi.mock("@fullcalendar/react", () => ({ default: ({ events, select }: { events: {title:string}[]; select: (a: {start:Date})=>void }) => <div><button onClick={() => select({start:new Date("2030-01-02T10:00:00")})}>Slot vago</button>{events.map(e => <span key={e.title}>{e.title}</span>)}</div> }));

describe("AgendaPage", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({ user: { id: 1, email: "a@b.com", first_name: "A", last_name: "B", organization: null, role: "OWNER" }, loading: false, login: vi.fn(), logout: vi.fn() });
    vi.mocked(api.get).mockImplementation(async (url) => ({ data: url === "/customers/" ? [{id:1,name:"Ana"}] : url === "/services/" ? [{id:2,name:"Corte"}] : url === "/professionals/" ? [{id:3,name:"Bia"}] : url === "/availability/" ? { slots:[{start_at:"2030-01-02T10:00:00-03:00",items:[{service:2,professional:3,start_at:"2030-01-02T10:00:00-03:00",end_at:"2030-01-02T11:00:00-03:00"}]}] } : [] } as never));
    vi.mocked(api.post).mockResolvedValue({ data: {} } as never);
  });
  it("creates an appointment from an available slot", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><AgendaPage /></QueryClientProvider>);
    await user.click(await screen.findByRole("button", { name: "Slot vago" }));
    await user.selectOptions(screen.getByLabelText("Cliente"), "1");
    await user.selectOptions(screen.getByLabelText("Serviço"), "2");
    await user.selectOptions(screen.getByLabelText("Profissional"), "3");
    await waitFor(() => expect(screen.getByRole("option", { name: "10:00" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Horários livres"), "2030-01-02T10:00:00-03:00");
    await user.click(screen.getByRole("button", { name: "Confirmar agendamento" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/appointments/", expect.objectContaining({ customer: 1, items: [{service:2,professional:3,order:0}] })));
  });
});
