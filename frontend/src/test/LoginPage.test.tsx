import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { LoginPage } from "../pages/LoginPage";
import { useAuth } from "../lib/auth";

vi.mock("../lib/auth", () => ({
  useAuth: vi.fn(),
}));

const mockedUseAuth = vi.mocked(useAuth);

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue({
      user: null,
      loading: false,
      login: vi.fn().mockResolvedValue(undefined),
      logout: vi.fn().mockResolvedValue(undefined),
    });
  });

  it("exibe erro de validação para e-mail inválido", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText("E-mail"), "email-invalido");
    await user.type(screen.getByLabelText("Senha"), "senha123");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("Informe um e-mail válido")).toBeInTheDocument();
  });

  it("chama login com credenciais válidas", async () => {
    const user = userEvent.setup();
    const login = vi.fn().mockResolvedValue(undefined);
    mockedUseAuth.mockReturnValue({
      user: null,
      loading: false,
      login,
      logout: vi.fn().mockResolvedValue(undefined),
    });

    renderLogin();
    await user.type(screen.getByLabelText("E-mail"), "dona@salao.com");
    await user.type(screen.getByLabelText("Senha"), "senha123");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(login).toHaveBeenCalledWith("dona@salao.com", "senha123");
  });

  it("mostra mensagem de erro quando o login falha", async () => {
    const user = userEvent.setup();
    mockedUseAuth.mockReturnValue({
      user: null,
      loading: false,
      login: vi.fn().mockRejectedValue({
        response: { data: { error: { code: "authentication_failed", detail: "E-mail ou senha incorretos." } } },
      }),
      logout: vi.fn().mockResolvedValue(undefined),
    });

    renderLogin();
    await user.type(screen.getByLabelText("E-mail"), "dona@salao.com");
    await user.type(screen.getByLabelText("Senha"), "errada");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha incorretos.");
  });
});
