let configuredBackendBaseUrl = "";

export function normalizeDesktopApiBaseUrl(value: string): string {
  const url = new URL(value);
  const host = url.hostname.toLowerCase();
  if (
    url.protocol !== "http:" ||
    !["127.0.0.1", "localhost", "[::1]"].includes(host) ||
    url.username ||
    url.password ||
    (url.pathname !== "" && url.pathname !== "/") ||
    url.search ||
    url.hash
  ) {
    throw new Error("desktop API URL must be an HTTP loopback origin");
  }
  return url.origin;
}

export function buildApiUrl(path: string, backendBaseUrl = configuredBackendBaseUrl): string {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error("API path must be absolute and non-escaping");
  }
  return `${backendBaseUrl}${path}`;
}

export async function initializeApiBaseUrl(): Promise<void> {
  if (!("__TAURI_INTERNALS__" in globalThis)) return;
  const { invoke } = await import("@tauri-apps/api/core");
  const value = await invoke<string>("desktop_api_base_url");
  configuredBackendBaseUrl = normalizeDesktopApiBaseUrl(value);
}
