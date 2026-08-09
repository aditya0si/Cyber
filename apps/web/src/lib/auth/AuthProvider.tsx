/** Auth provider (docs/13 §2.1): token lifecycle + /me. */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { api, tokenStore } from "@/lib/api/client";
import type { MeResponse } from "@/lib/api/types";

interface AuthContextValue {
  me: MeResponse | null;
  loading: boolean;
  loggedIn: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    if (!tokenStore.access) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      setMe(await api.me());
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await api.login(email, password);
      tokenStore.set(tokens.access_token, tokens.refresh_token);
      await refreshMe();
    },
    [refreshMe],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      const tokens = await api.register(email, password);
      tokenStore.set(tokens.access_token, tokens.refresh_token);
      await refreshMe();
    },
    [refreshMe],
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    setMe(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ me, loading, loggedIn: Boolean(me), login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
