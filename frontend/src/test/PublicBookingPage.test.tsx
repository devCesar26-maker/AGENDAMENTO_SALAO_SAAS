import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PublicBookingPage } from "../pages/PublicBookingPage";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() }, errorMessage: (e: Error) => e.message }));
describe("PublicBookingPage", () => {
  beforeEach(() => {
    vi.mocked(api.get).mockImplementation(async (url) => ({ data: url === "/public/catalog/" ? {services:[{id:1,name:"Corte",duration_minutes:30,price:"50.00"}]} : url === "/public/professionals/" ? [{id:3,name:"Bia",services:[1]}] : {slots:[{start_at:"2030-01-02T10:00:00-03:00",items:[{service:1,professional:3,start_at:"2030-01-02T10:00:00-03:00",end_at:"2030-01-02T10:30:00-03:00"}]}]} } as never));
    vi.mocked(api.post).mockResolvedValue({ data: {id:8} } as never);
  });
  it("completes service, slot, customer, consent and reservation flow", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/b/salao"]}><Routes><Route path="/b/:slug" element={<PublicBookingPage/>}/></Routes></MemoryRouter></QueryClientProvider>);
    await user.click(await screen.findByLabelText(/Corte/));
    await user.selectOptions(screen.getByLabelText("Horário"), "2030-01-02T10:00:00-03:00");
    await user.type(screen.getByLabelText("Nome"), "Ana Cliente");
    await user.type(screen.getByLabelText("Telefone"), "11999999999");
    await user.click(screen.getByRole("checkbox", { name: /Autorizo o uso/ }));
    await user.click(screen.getByRole("button", { name: "Confirmar reserva" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/public/appointments/", expect.objectContaining({ name:"Ana Cliente", phone:"11999999999", consent:true }), expect.objectContaining({ headers: { "X-Tenant-Slug": "salao" } })));
    expect(vi.mocked(api.post).mock.calls[0][1]).not.toHaveProperty("origin");
    expect(await screen.findByText("Reserva solicitada")).toBeInTheDocument();
  });
});
