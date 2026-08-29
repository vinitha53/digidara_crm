import { createContext, useContext, useEffect, useMemo, useState } from "react";
import api, {
  clearSession,
  refreshSession,
  sessionIsIdle,
  SESSION_IDLE_TIMEOUT_MS,
  SESSION_LAST_ACTIVITY_KEY,
  SESSION_LAST_RENEWAL_KEY,
  SESSION_RENEW_INTERVAL_MS,
} from "../api/client";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

function storedUser() {
  try {
    const token = localStorage.getItem("access_token");
    if (!token || sessionIsIdle()) {
      clearSession();
      return null;
    }
    return JSON.parse(localStorage.getItem("user") || "null");
  } catch {
    clearSession();
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

  useEffect(() => {
    if (!user) return undefined;

    let activityWriteAt = 0;
    let stopped = false;

    const expireSession = () => {
      if (stopped) return;
      clearSession();
      setUser(null);
      setLoading(false);
    };

    const recordActivity = () => {
      const now = Date.now();
      // Check the old timestamp before recording the new event. Returning to
      // an idle tab after 30 minutes must log in again, not revive the session.
      if (sessionIsIdle(now)) {
        expireSession();
        return;
      }
      if (now - activityWriteAt >= 10_000) {
        localStorage.setItem(SESSION_LAST_ACTIVITY_KEY, String(now));
        activityWriteAt = now;
      }
      const lastRenewal = Number(localStorage.getItem(SESSION_LAST_RENEWAL_KEY)) || 0;
      if (now - lastRenewal >= SESSION_RENEW_INTERVAL_MS) {
        refreshSession().catch(expireSession);
      }
    };

    const checkIdle = () => {
      if (sessionIsIdle()) expireSession();
    };

    const onStorage = (event) => {
      if (event.key === "access_token" && !event.newValue) expireSession();
    };

    const activityEvents = ["pointerdown", "pointermove", "keydown", "scroll", "touchstart"];
    activityEvents.forEach((event) => window.addEventListener(event, recordActivity, { passive: true }));
    window.addEventListener("focus", checkIdle);
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", checkIdle);
    const idleTimer = window.setInterval(checkIdle, Math.min(30_000, SESSION_IDLE_TIMEOUT_MS));

    return () => {
      stopped = true;
      activityEvents.forEach((event) => window.removeEventListener(event, recordActivity));
      window.removeEventListener("focus", checkIdle);
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", checkIdle);
      window.clearInterval(idleTimer);
    };
  }, [user]);

  function completeLogin(data) {
    const now = Date.now();
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    localStorage.setItem(SESSION_LAST_ACTIVITY_KEY, String(now));
    localStorage.setItem(SESSION_LAST_RENEWAL_KEY, String(now));
    setUser(data.user);
    return data;
  }

  async function login(email, password, loginType) {
    const { data } = await api.post("/auth/login", { email, password, login_type: loginType });
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
    // Notify the server with the token captured before local credentials are
    // removed. Local logout still completes immediately if the network fails.
    const accessToken = localStorage.getItem("access_token");
    if (accessToken) {
      api.post("/auth/logout", null, {
        headers: { Authorization: `Bearer ${accessToken}` },
      }).catch(() => {});
    }
    clearSession();
    setUser(null);
    setLoading(false);
  }

  const value = useMemo(() => ({ user, loading, login, verifyOtp, resendOtp, logout, isAdmin: user?.role === "admin" }), [user, loading]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
