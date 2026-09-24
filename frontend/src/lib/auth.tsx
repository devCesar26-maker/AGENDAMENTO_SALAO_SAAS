/**
 * Contexto de autenticação: usuário/role em memória + sessão restaurada via
 * cookie de refresh ao montar. Rotas protegidas por role vivem em App.tsx.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setAccessToken } from "./api";

export type Role = "OWNER" | "MANAGER" | "PROFESSIONAL";

export interface AuthUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  organization: { id: number; slug: string } | null;
  role: Role | null;
}

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Restaura a sessão com o cookie de refresh (a página pode ter sido recarregada).
  useEffect(() => {
    api
      .post<{ access: string; user: AuthUser }>("/auth/refresh/")
      .then(({ data }) => {
        setAccessToken(data.access);
        setUser(data.user);
      })
      .catch(() => setAccessToken(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post<{ access: string; user: AuthUser }>("/auth/login/", {
      email,
      password,
    });
    setAccessToken(data.access);
    setUser(data.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout/");
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth deve ser usado dentro de AuthProvider");
  return ctx;
}
