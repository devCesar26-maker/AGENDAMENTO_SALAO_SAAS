import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "../lib/auth";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({
  api: { post: vi.fn() },
  setAccessToken: vi.fn(),
}));

const user = {
  id: 7,
  email: "dona@salao.com",
  first_name: "Dona",
  last_name: "Studio",
  organization: { id: 3, slug: "studio" },
  role: "OWNER" as const,
};

function SessionProbe() {
  const auth = useAuth();
  return (
    <div>
      <p>{auth.loading ? "Carregando" : auth.user?.email ?? "Sem sessão"}</p>
      <button onClick={() => void auth.login("dona@salao.com", "Senha#123")}>Entrar</button>
    </div>
  );
}

function renderProvider() {
  return render(
    <AuthProvider>
      <SessionProbe />
    </AuthProvider>,
  );
}

describe("AuthProvider", () => {
  beforeEach(() => vi.resetAllMocks());

  it("restaura a sessão após login e remontagem do provider", async () => {
    vi.mocked(api.post)
      .mockRejectedValueOnce(new Error("sem cookie antes do login"))
      .mockResolvedValueOnce({ data: { access: "access-login", user } } as never)
      .mockResolvedValueOnce({ data: { access: "access-refresh", user } } as never);

    const firstPage = renderProvider();
    await screen.findByText("Sem sessão");
    await userEvent.setup().click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("dona@salao.com")).toBeInTheDocument();

    firstPage.unmount();
    renderProvider();

    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith("/auth/refresh/"));
    expect(await screen.findByText("dona@salao.com")).toBeInTheDocument();
  });
});
