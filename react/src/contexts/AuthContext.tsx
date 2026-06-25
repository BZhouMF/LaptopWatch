import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import api_client from "../api/client";

interface AuthState {
  is_loading: boolean;
  error: string | null;
  login: (account: string, password: string) => Promise<void>;
  logout: () => void;
  clear_error: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [is_loading, set_is_loading] = useState(false);
  const [error, set_error] = useState<string | null>(null);
  const navigate = useNavigate();

  const login = useCallback(async (account: string, password: string) => {
    set_is_loading(true);
    set_error(null);
    try {
      const form_data = new URLSearchParams();
      form_data.append("account", account);
      form_data.append("password", password);
      const resp = await api_client.post("/login", form_data, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      if (resp.data?.code !== 0) {
        set_error(resp.data?.msg || "登录失败");
        return;
      }
      const params = new URLSearchParams(window.location.search);
      const redirect = params.get("redirect") || "/";
      navigate(redirect, { replace: true });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { msg?: string } } })?.response?.data?.msg;
      set_error(msg || "登录失败，请检查账号密码");
    } finally {
      set_is_loading(false);
    }
  }, [navigate]);

  const logout = useCallback(() => {
    window.location.href = "/logout";
  }, []);

  const clear_error = useCallback(() => set_error(null), []);

  return (
    <AuthContext.Provider value={{ is_loading, error, login, logout, clear_error }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
