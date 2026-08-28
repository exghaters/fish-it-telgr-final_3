import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("fishit_token");
  config.headers = config.headers || {};
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
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
      // Only wipe token if we are not on login/register pages
      const path = window.location.pathname;
      if (!path.startsWith("/login") && !path.startsWith("/register") && path !== "/") {
        localStorage.removeItem("fishit_token");
        localStorage.removeItem("fishit_user");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
