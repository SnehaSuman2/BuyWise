"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, tokenStore } from "./api";
import type { TokenResponse, User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (data: { email: string; username: string; password: string; display_name?: string }) => Promise<User>;
  loginWithGoogle: (idToken: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<User | null>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const apply = useCallback((t: TokenResponse) => { tokenStore.set(t); setUser(t.user); return t.user; }, []);

  const refreshUser = useCallback(async () => {
    if (!tokenStore.access && !tokenStore.refresh) { setUser(null); return null; }
    try {
      const me = await api.me();
      tokenStore.setUser(me);
      setUser(me);
      return me;
    } catch {
      tokenStore.clear();
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      const cached = tokenStore.user;
      if (cached && active) setUser(cached);
      await refreshUser();
      if (active) setLoading(false);
    })();
    return () => { active = false; };
  }, [refreshUser]);

  const value: AuthState = {
    user,
    loading,
    login: async (email, password) => apply(await api.login({ email, password })),
    register: async (data) => apply(await api.register(data)),
    loginWithGoogle: async (idToken) => apply(await api.googleLogin(idToken)),
    logout: async () => {
      const refresh = tokenStore.refresh;
      try { if (refresh) await api.logout(refresh); } catch { /* ignore */ }
      tokenStore.clear();
      setUser(null);
    },
    refreshUser,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
