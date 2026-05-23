"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { generateJWT, decodeJWT } from "@/utils/jwt";

interface AuthContextType {
  token: string | null;
  user: {
    sub: string;
    role: string;
    exp: number;
    iat: number;
  } | null;
  loading: boolean;
  loginAs: (role: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Helper to set a cookie
  const setCookie = (name: string, value: string, days = 7) => {
    const expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = `${name}=${value}; expires=${expires}; path=/; SameSite=Lax`;
  };

  // Helper to read a cookie
  const getCookie = (name: string) => {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
    return null;
  };

  const loginAs = async (role: string) => {
    setLoading(true);
    try {
      const username = `${role}-user`;
      const newToken = await generateJWT(username, role);
      setToken(newToken);
      setUser(decodeJWT(newToken));
      setCookie("token", newToken);
      localStorage.setItem("aeos_token", newToken);
    } catch (e) {
      console.error("Login failed:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const initializeAuth = async () => {
      if (typeof window !== "undefined") {
        const storedToken = getCookie("token") || localStorage.getItem("aeos_token");
        if (storedToken) {
          const decoded = decodeJWT(storedToken);
          if (decoded && decoded.exp > Math.floor(Date.now() / 1000)) {
            setToken(storedToken);
            setUser(decoded);
            setLoading(false);
            return;
          }
        }
        // If no token, default to operator role for frictionless testing
        await loginAs("operator");
      }
    };
    initializeAuth();
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, loginAs }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
