import axios from "axios";

const TOKEN_KEY = "xagent_token";

export const api = axios.create({
  baseURL: "/api/v1",
  timeout: 30_000,
});

// 注入鉴权头
api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

// 401 清 token 跳登录
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
    }
    return Promise.reject(err);
  }
);

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export async function login(username: string, password: string): Promise<{
  access_token: string;
  user_id: string;
  tenant_id: string;
  roles: string[];
}> {
  const resp = await api.post("/auth/login", { username, password });
  setToken(resp.data.access_token);
  return resp.data;
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

// OIDC/SSO：后端配置了 oidc_client_id 时 enabled=true，登录页据此渲染 SSO 按钮
export async function getOidcProviders(): Promise<{ enabled: boolean }> {
  const resp = await api.get("/auth/oidc/providers");
  return resp.data;
}
