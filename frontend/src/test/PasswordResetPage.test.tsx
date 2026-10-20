import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PasswordResetConfirmPage, PasswordResetRequestPage } from "../pages/PasswordResetPage";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({ api: { post: vi.fn() }, errorMessage: () => "Link inválido ou expirado. Solicite um novo." }));
const mockedPost = vi.mocked(api.post);

describe("recuperação de senha", () => {
  it("solicita o reset e informa a resposta genérica do servidor", async () => {
    mockedPost.mockResolvedValueOnce({ data: { detail: "Se este e-mail estiver cadastrado, você receberá um link de redefinição em instantes." } } as never);
    const user = userEvent.setup();
    render(<MemoryRouter><PasswordResetRequestPage /></MemoryRouter>);
    await user.type(screen.getByLabelText("E-mail"), "pessoa@example.com");
    await user.click(screen.getByRole("button", { name: "Enviar instruções" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Se este e-mail estiver cadastrado");
    expect(mockedPost).toHaveBeenCalledWith("/auth/password/reset/", { email: "pessoa@example.com" });
  });

  it("envia uid/token da URL e define a nova senha", async () => {
    mockedPost.mockResolvedValueOnce({ data: { detail: "Senha redefinida com sucesso. Você já pode entrar." } } as never);
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/resetar-senha/abc/token123"]}><Routes><Route path="/resetar-senha/:uidb64/:token" element={<PasswordResetConfirmPage />} /></Routes></MemoryRouter>);
    await user.type(screen.getByLabelText("Nova senha"), "UmaSenhaSegura!2026");
    await user.click(screen.getByRole("button", { name: "Redefinir senha" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Senha redefinida com sucesso");
    expect(mockedPost).toHaveBeenCalledWith("/auth/password/reset/confirm/", { uidb64: "abc", token: "token123", password: "UmaSenhaSegura!2026" });
  });
});
