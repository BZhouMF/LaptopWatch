import axios from "axios";

const api_client = axios.create({
  timeout: 30000,
  withCredentials: true,
});

api_client.interceptors.response.use(
  (response) => response,
  (error) => {
    // 503 = service not active — let callers handle gracefully, don't trigger 401 redirect
    if (error.response?.status === 503) {
      return Promise.reject(error);
    }
    if (error.response?.status === 401) {
      const current_path = window.location.pathname;
      if (current_path !== "/login") {
        window.location.replace(`/login?redirect=${encodeURIComponent(current_path)}`);
      }
    }
    return Promise.reject(error);
  }
);

export default api_client;
