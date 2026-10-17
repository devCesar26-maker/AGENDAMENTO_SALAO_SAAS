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

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
  );
}
