import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

function stubHealthFetch() {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ status: "ok", mode: "mock" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("API bearer token", () => {
  it("sends Authorization only when VITE_API_TOKEN is configured", async () => {
    vi.stubEnv("VITE_API_TOKEN", "local-dev-token-123");
    const fetchMock = stubHealthFetch();

    await api.health();

    const [url, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer local-dev-token-123",
    );
    // The token must not leak into the request URL.
    expect(String(url)).not.toContain("local-dev-token-123");
  });

  it("sends no Authorization header when VITE_API_TOKEN is unset", async () => {
    vi.stubEnv("VITE_API_TOKEN", "");
    const fetchMock = stubHealthFetch();

    await api.health();

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });
});
