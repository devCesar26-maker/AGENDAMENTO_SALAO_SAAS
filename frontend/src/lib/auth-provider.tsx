import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, setAccessToken } from "./api";
import { AuthContext, type AuthUser } from "./auth-context";

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

  const acceptSession = useCallback((access: string, acceptedUser: AuthUser) => {
    setAccessToken(access);
    setUser(acceptedUser);
  }, []);

  const refreshUser = useCallback(async () => {
    const { data } = await api.get<{ id: number; email: string; first_name: string; last_name: string; memberships: { id: number; organization: { id: number; slug: string }; role: AuthUser["role"] }[] }>("/me/");
    const membership = data.memberships[0];
    setUser({ id: data.id, email: data.email, first_name: data.first_name, last_name: data.last_name, organization: membership?.organization ?? null, role: membership?.role ?? null });
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, acceptSession, refreshUser }}>{children}</AuthContext.Provider>
  );
}
