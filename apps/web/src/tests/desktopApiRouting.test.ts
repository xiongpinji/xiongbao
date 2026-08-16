import { buildApiUrl, normalizeDesktopApiBaseUrl } from "../api/baseUrl";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

describe("desktop API routing", () => {
  it("keeps browser requests on the relative reverse-proxy path", () => {
    assert(
      buildApiUrl("/api/v1/auth/login", "") === "/api/v1/auth/login",
      "browser requests must remain relative",
    );
  });

  it("routes packaged desktop requests to the configured loopback backend", () => {
    const baseUrl = normalizeDesktopApiBaseUrl("http://127.0.0.1:8123/");
    assert(baseUrl === "http://127.0.0.1:8123", "desktop base URL must be normalized");
    assert(
      buildApiUrl("/api/v1/auth/login", baseUrl) ===
        "http://127.0.0.1:8123/api/v1/auth/login",
      "desktop requests must use the configured loopback backend",
    );
  });

  it("rejects remote, credentialed, and path-bearing desktop backends", () => {
    for (const value of [
      "https://127.0.0.1:8000",
      "http://example.com:8000",
      "http://user@127.0.0.1:8000",
      "http://127.0.0.1:8000/api",
    ]) {
      let rejected = false;
      try {
        normalizeDesktopApiBaseUrl(value);
      } catch {
        rejected = true;
      }
      assert(rejected, `desktop backend must reject ${value}`);
    }
  });
});
