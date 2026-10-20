import { createContext, useContext } from "react";

export type Role = "OWNER" | "MANAGER" | "PROFESSIONAL";

export interface AuthUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  organization: { id: number; slug: string } | null;
  role: Role | null;
}

export interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  acceptSession?: (access: string, user: AuthUser) => void;
  refreshUser?: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth deve ser usado dentro de AuthProvider");
  return ctx;
}
