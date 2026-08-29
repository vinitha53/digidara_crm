import axios from "axios";

const baseURL = import.meta.env.VITE_API_URL || "http://localhost:5002/api";
const api = axios.create({ baseURL });
let refreshPromise = null;

export const SESSION_IDLE_TIMEOUT_MS = 30 * 60 * 1000;
export const SESSION_RENEW_INTERVAL_MS = 15 * 60 * 1000;
export const SESSION_LAST_ACTIVITY_KEY = "session_last_activity";
export const SESSION_LAST_RENEWAL_KEY = "session_last_renewal";

export function clearSession() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user");
  localStorage.removeItem(SESSION_LAST_ACTIVITY_KEY);
  localStorage.removeItem(SESSION_LAST_RENEWAL_KEY);
}

export function sessionIsIdle(now = Date.now()) {
  const lastActivity = Number(localStorage.getItem(SESSION_LAST_ACTIVITY_KEY));
  return !Number.isFinite(lastActivity) || lastActivity <= 0 || now - lastActivity >= SESSION_IDLE_TIMEOUT_MS;
}

function isPublicAuthRequest(url = "") {
  return ["/auth/login", "/auth/verify-otp", "/auth/resend-otp", "/auth/refresh"]
    .some((path) => url.includes(path));
}

function expiresSoon(token, marginSeconds = 60) {
  try {
    const encodedPayload = token.split(".")[1];
    const base64 = encodedPayload.replace(/-/g, "+").replace(/_/g, "/");
    const normalized = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const payload = JSON.parse(atob(normalized));
    return Number(payload.exp || 0) * 1000 <= Date.now() + marginSeconds * 1000;
  } catch {
    return true;
  }
}

export function refreshSession() {
  if (refreshPromise) return refreshPromise;
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return Promise.reject(new Error("No refresh token"));
  if (sessionIsIdle()) return Promise.reject(new Error("Session is inactive"));

  refreshPromise = axios.post(`${baseURL}/auth/refresh`, null, {
    headers: { Authorization: `Bearer ${refreshToken}` },
  }).then(({ data }) => {
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    localStorage.setItem(SESSION_LAST_RENEWAL_KEY, String(Date.now()));
    return data.access_token;
  }).finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

function redirectToLogin() {
  clearSession();
  if (!location.pathname.includes("/login")) location.href = "/login";
}

api.interceptors.request.use(async (config) => {
  let token = localStorage.getItem("access_token");
  if (token && !isPublicAuthRequest(config.url) && expiresSoon(token) && localStorage.getItem("refresh_token")) {
    try {
      token = await refreshSession();
    } catch {
      redirectToLogin();
      throw new axios.CanceledError("Session renewal failed");
    }
  }
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const request = err.config;
    if (err.response?.status === 401 && request && !request._sessionRetry && !isPublicAuthRequest(request.url)) {
      request._sessionRetry = true;
      try {
        const token = await refreshSession();
        request.headers.Authorization = `Bearer ${token}`;
        return api(request);
      } catch {
        redirectToLogin();
      }
    } else if (err.response?.status === 401 && !isPublicAuthRequest(request?.url)) {
      redirectToLogin();
    }
    return Promise.reject(err);
  }
);

export default api;
