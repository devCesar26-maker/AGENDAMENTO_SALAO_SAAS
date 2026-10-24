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

  it("aplica as preferências somente ao salvar e mantém o piso de legibilidade", async () => {
    const user = userEvent.setup();
    render(<AppearanceSettings organizationSlug="studio" />);

    await waitFor(() => expect(document.documentElement.style.getPropertyValue("--workspace-panel-opacity")).toBe("75%"));
    expect(document.documentElement.style.getPropertyValue("--workspace-shade")).toBe("38%");
    await user.click(screen.getByRole("button", { name: "Aparência" }));

    const dialog = screen.getByRole("dialog", { name: "Personalizar aparência do espaço" });
    expect(dialog).toBeInTheDocument();

    const opacity = screen.getByRole("slider", { name: /Opacidade dos cartões/ });
    expect(opacity).toHaveAttribute("min", "65");

    fireEvent.change(opacity, { target: { value: "10" } });
    // O valor é elevado ao piso e a prévia aparece, mas o documento segue intacto até salvar.
    await waitFor(() => expect((opacity as HTMLInputElement).value).toBe("65"));
    expect(document.documentElement.style.getPropertyValue("--workspace-panel-opacity")).toBe("75%");
    expect(dialog.querySelector(".appearance-preview-card")).not.toBeNull();

    fireEvent.change(opacity, { target: { value: "90" } });
    fireEvent.change(screen.getByRole("slider", { name: /Escurecimento/ }), { target: { value: "50" } });
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => expect(document.documentElement.style.getPropertyValue("--workspace-panel-opacity")).toBe("90%"));
    expect(document.documentElement.style.getPropertyValue("--workspace-shade")).toBe("50%");

    const stored = JSON.parse(localStorage.getItem("eclat:appearance:studio") ?? "{}");
    expect(stored.version).toBe(3);
    expect(stored.panelOpacity).toBe(90);
  });

  it("aplica a imagem só depois de salvar e descarta a remoção ao cancelar", async () => {
    const user = userEvent.setup();
    render(<AppearanceSettings organizationSlug="studio" />);

    await user.click(screen.getByRole("button", { name: "Aparência" }));
    const file = new File(["fake-image"], "fundo.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Imagem de fundo"), file);
    await waitFor(() => expect(document.querySelector(".appearance-preview-photo")).not.toBeNull());
    expect(document.documentElement.dataset.workspaceBackdrop).toBe("false");

    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => expect(document.documentElement.dataset.workspaceBackdrop).toBe("true"));

    await user.click(screen.getByRole("button", { name: "Aparência" }));
    await user.click(screen.getByRole("button", { name: "Remover imagem" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(document.documentElement.dataset.workspaceBackdrop).toBe("true");
  });

  it("migra as preferências antigas para o padrão em que a imagem aparece", async () => {
    localStorage.setItem(
      "eclat:appearance:studio",
      JSON.stringify({ image: "data:image/png;base64,abc", shade: 88, blur: 10, position: "center top", panelOpacity: 92 }),
    );

    render(<AppearanceSettings organizationSlug="studio" />);

    // A imagem e o enquadramento escolhidos continuam; os ajustes voltam ao padrão legível.
    await waitFor(() => expect(document.documentElement.dataset.workspaceBackdrop).toBe("true"));
    expect(document.documentElement.style.getPropertyValue("--workspace-shade")).toBe("38%");
    expect(document.documentElement.style.getPropertyValue("--workspace-blur")).toBe("0px");
    expect(document.documentElement.style.getPropertyValue("--workspace-panel-opacity")).toBe("75%");
    expect(document.documentElement.style.getPropertyValue("--workspace-position")).toBe("center top");
    expect(document.documentElement.style.getPropertyValue("--workspace-backdrop")).toBe('url("data:image/png;base64,abc")');

    const stored = JSON.parse(localStorage.getItem("eclat:appearance:studio") ?? "{}");
    expect(stored.version).toBe(3);
    expect(stored.image).toBe("data:image/png;base64,abc");
  });

  it("eleva ao piso os valores abaixo do mínimo já salvos", async () => {
    localStorage.setItem("eclat:appearance:studio", JSON.stringify({ image: "", shade: 40, blur: 4, position: "center", panelOpacity: 20, version: 2 }));

    render(<AppearanceSettings organizationSlug="studio" />);

    await waitFor(() => expect(document.documentElement.style.getPropertyValue("--workspace-panel-opacity")).toBe("65%"));
    // Preferências conscientes da versão anterior são preservadas quando são legíveis.
    expect(document.documentElement.style.getPropertyValue("--workspace-shade")).toBe("40%");
    expect(document.documentElement.style.getPropertyValue("--workspace-blur")).toBe("4px");
  });
});
