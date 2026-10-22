const THEME_KEY = "eclat:color-scheme";

export type ColorScheme = "light" | "dark" | "system";

export function getStoredScheme(): ColorScheme {
  try {
    const value = localStorage.getItem(THEME_KEY);
    if (value === "light" || value === "dark" || value === "system") return value;
  } catch {
    /* ignore */
  }
  return "dark";
}

export function setStoredScheme(scheme: ColorScheme) {
  try {
    localStorage.setItem(THEME_KEY, scheme);
  } catch {
    /* ignore */
  }
  applyColorScheme(scheme);
}

function resolvedScheme(scheme: ColorScheme): "light" | "dark" {
  if (scheme === "light" || scheme === "dark") return scheme;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function applyColorScheme(scheme: ColorScheme = getStoredScheme()) {
  const resolved = resolvedScheme(scheme);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
}

export function applyAccentColor(hex: string | undefined) {
  if (!hex || !/^#[0-9A-Fa-f]{6}$/.test(hex)) return;
  const root = document.documentElement;
  root.style.setProperty("--accent", hex);
  root.style.setProperty("--accent-strong", hex);
  root.style.setProperty("--accent-hover", hex);
}

export function initTheme() {
  applyColorScheme();
  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
    if (getStoredScheme() === "system") applyColorScheme("system");
  });
}
