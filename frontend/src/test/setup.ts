import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";

// The public booking flow shows salon-local appointment times.
process.env.TZ = "America/Sao_Paulo";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
});
