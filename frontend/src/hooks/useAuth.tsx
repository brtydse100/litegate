import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { User } from "../types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const generation = useRef(0);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true);
    await queryClient.cancelQueries();
    queryClient.clear();
    try {
      const nextUser = await api.me();
      if (current === generation.current) setUser(nextUser);
    } catch {
      if (current === generation.current) {
        localStorage.removeItem("token");
        setUser(null);
      }
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [queryClient]);

  useEffect(() => {
    void loadUser();
  }, [loadUser]);

  const login = useCallback(async () => {
    localStorage.removeItem("token");
    await loadUser();
  }, [loadUser]);

  const logout = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true);
    await queryClient.cancelQueries();
    queryClient.clear();
    try {
      await api.logout();
    } finally {
      if (current === generation.current) {
        localStorage.removeItem("token");
        setUser(null);
        setLoading(false);
      }
    }
  }, [queryClient]);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
