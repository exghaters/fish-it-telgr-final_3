import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem("fishit_user");
    return raw ? JSON.parse(raw) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Auth token lives in an httpOnly cookie; verify the session via /auth/me.
    api
      .get("/auth/me")
      .then((r) => {
        setUser(r.data);
        localStorage.setItem("fishit_user", JSON.stringify(r.data));
      })
      .catch(() => {
        localStorage.removeItem("fishit_user");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("fishit_user", JSON.stringify(data.user));
    setUser(data.user);
    return data.user;
  }, []);

  const register = useCallback(async (email, password) => {
    const { data } = await api.post("/auth/register", { email, password });
    localStorage.setItem("fishit_user", JSON.stringify(data.user));
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      /* ignore network errors on logout */
    }
    localStorage.removeItem("fishit_user");
    localStorage.removeItem("fishit_account");
    setUser(null);
    window.location.href = "/login";
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
