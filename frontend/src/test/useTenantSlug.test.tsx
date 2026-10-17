import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { tenantSlugForHostname, useTenantSlug } from "../lib/useTenantSlug";

function Probe() { const slug = useTenantSlug(); return <span>{slug ?? "sem-tenant"}</span>; }

describe("useTenantSlug", () => {
  it("resolve slug from subdomain and leaves app/local hosts without tenant", () => {
    expect(tenantSlugForHostname("cesar-eclatstudio.eclatstudio.com.br")).toBe("cesar-eclatstudio");
    expect(tenantSlugForHostname("app.eclatstudio.com.br")).toBeNull();
    expect(tenantSlugForHostname("localhost:5173")).toBeNull();
  });

  it("uses /b/:slug as an explicit override", () => {
    vi.stubGlobal("location", { ...window.location, hostname: "app.eclatstudio.com.br" });
    render(<MemoryRouter initialEntries={["/b/meu-salao"]}><Routes><Route path="/b/:slug" element={<Probe />} /></Routes></MemoryRouter>);
    expect(screen.getByText("meu-salao")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
