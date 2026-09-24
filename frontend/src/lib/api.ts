/**
 * Cliente HTTP da API.
 *
 * Decisão de segurança: o access token vive apenas em memória (nunca em
 * localStorage — vulnerável a XSS). O refresh token é cookie httpOnly setado
 * pelo backend; ao expirar o access, este cliente faz refresh único e refaz a
 * requisição original.
 */
import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

export const api = axios.create({
  baseURL: "/api/v1",
  withCredentials: true, // envia cookie de refresh em /auth/refresh e /auth/logout
});

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  try {
    const { data } = await axios.post("/api/v1/auth/refresh/", {}, { withCredentials: true });
    accessToken = data.access;
    return data.access;
  } catch {
    accessToken = null;
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean };
    const url = original?.url ?? "";
    const isRefreshCall = url.includes("/auth/refresh/") || url.includes("/auth/login/");

    if (error.response?.status === 401 && original && !original._retried && !isRefreshCall) {
      original._retried = true;
      refreshing = refreshing ?? refreshAccessToken();
      const token = await refreshing;
      refreshing = null;
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      }
    }
    return Promise.reject(error);
  },
);

type ApiErrorBody = { error?: { detail?: string; fields?: Record<string, string[]> } };

function extractDetail(data: unknown): string | null {
  const body = data as ApiErrorBody;
  if (body?.error?.fields) {
    const first = Object.values(body.error.fields)[0];
    if (Array.isArray(first)) return String(first[0]);
    return body.error.detail ?? "Verifique os dados informados.";
  }
  return body?.error?.detail ?? null;
}

/** Extrai a mensagem padronizada {"error": {"detail": ...}} para exibir ao usuário. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const fromBody = extractDetail(error.response?.data);
    if (fromBody) return fromBody;
    if (error.response?.status === 401) return "Sessão expirada. Entre novamente.";
    if ((error.response?.status ?? 0) >= 500) return "Erro no servidor. Tente novamente.";
    return "Erro inesperado. Tente novamente.";
  }
  // Erros encapsulados por bibliotecas terceiras preservam o corpo da resposta.
  const duck = extractDetail((error as { response?: { data?: unknown } } | null)?.response?.data);
  return duck ?? "Erro inesperado. Tente novamente.";
}
