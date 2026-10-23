import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppearanceSettings } from "../components/AppearanceSettings";

describe("AppearanceSettings", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    document.documentElement.removeAttribute("data-workspace-backdrop");
  });

  it("abre em um diálogo central e aplica as preferências no documento", async () => {
    const user = userEvent.setup();
    render(<AppearanceSettings organizationSlug="studio" />);

    await waitFor(() => expect(document.documentElement.style.getPropertyValue("--workspace-shade")).toBe("65%"));
    await user.click(screen.getByRole("button", { name: "Aparência" }));

    expect(screen.getByRole("dialog", { name: "Personalizar aparência do espaço" })).toBeInTheDocument();

    fireEvent.change(screen.getByRole("slider", { name: /Escurecimento/ }), { target: { value: "40" } });
    await waitFor(() => expect(document.documentElement.style.getPropertyValue("--workspace-shade")).toBe("40%"));

    const file = new File(["fake-image"], "fundo.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Imagem de fundo"), file);
    await waitFor(() => expect(document.documentElement.dataset.workspaceBackdrop).toBe("true"));
  });
});
