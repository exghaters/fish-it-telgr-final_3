import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

// withCredentials: send/receive the httpOnly auth cookie on every request.
const api = axios.create({ baseURL: API_BASE, withCredentials: true });

api.interceptors.request.use((config) => {
  config.headers = config.headers || {};
  const acct = localStorage.getItem("fishit_account");
  if (acct) {
    config.headers["X-Account-Id"] = acct;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      // Only redirect if we are not already on public pages
      const path = window.location.pathname;
      if (!path.startsWith("/login") && !path.startsWith("/register") && path !== "/") {
        localStorage.removeItem("fishit_user");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
