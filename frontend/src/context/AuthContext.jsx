import { createContext, useContext, useEffect, useMemo, useState } from "react";
import api from "../api/client";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

function storedUser() {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) {
      localStorage.removeItem("user");
      return null;
    }
    return JSON.parse(localStorage.getItem("user") || "null");
  } catch {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(storedUser);
  const [loading, setLoading] = useState(Boolean(localStorage.getItem("access_token")));

  useEffect(() => {
    if (!localStorage.getItem("access_token")) return setLoading(false);
    api.get("/auth/me").then(({ data }) => {
      setUser(data);
      localStorage.setItem("user", JSON.stringify(data));
    }).catch(() => logout()).finally(() => setLoading(false));
  }, []);

  function completeLogin(data) {
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    setUser(data.user);
    return data;
  }

  async function login(email, password) {
    const { data } = await api.post("/auth/login", { email, password });
    return data.otp_required ? data : completeLogin(data);
  }

  async function verifyOtp(challengeId, otp) {
    const { data } = await api.post("/auth/verify-otp", { challenge_id: challengeId, otp });
    return completeLogin(data);
  }

  async function resendOtp(challengeId) {
    const { data } = await api.post("/auth/resend-otp", { challenge_id: challengeId });
    return data;
  }

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    setUser(null);
    setLoading(false);
  }

  const value = useMemo(() => ({ user, loading, login, verifyOtp, resendOtp, logout, isAdmin: user?.role === "admin" }), [user, loading]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
