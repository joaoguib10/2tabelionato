"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { useRouter } from "next/navigation";

import { apiFetch } from "../lib/api";

type User = {
  id: string;
  nome: string;
  username: string;
  role: "ADMIN" | "USUARIO";
  ativo: boolean;
};

type AuthContextType = {
  user: User | null;
  loading: boolean;
  refreshUser: () => Promise<boolean>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    async function loadUser() {
      try {
        const response = await apiFetch("/api/auth/me");

        if (!response || !response.ok) {
          setUser(null);
          return;
        }

        const data = await response.json();

        setUser(data);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    loadUser();
  }, []);

  useEffect(() => {
    function expirarSessao() {
      setUser(null);
      router.replace("/login");
    }

    window.addEventListener("auth:expired", expirarSessao);
    return () => window.removeEventListener("auth:expired", expirarSessao);
  }, [router]);

  async function refreshUser(): Promise<boolean> {
    try {
      const response = await apiFetch("/api/auth/me");

      if (!response?.ok) {
        setUser(null);
        return false;
      }

      const data = (await response.json()) as User;
      setUser(data);
      return true;
    } catch {
      setUser(null);
      return false;
    }
  }

  function logout() {
    void apiFetch("/api/auth/logout", { method: "POST" }).catch(
      () => undefined,
    );
    setUser(null);
    router.replace("/login");
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        refreshUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth deve ser utilizado dentro de AuthProvider");
  }

  return context;
}
