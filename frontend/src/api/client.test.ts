// SYS-03: the API client sends X-ShelfSync: 1 on every write, stays same-origin, never handles the cookie, and
// turns a 401 "signed_out" into the signed-out state. fetch is mocked; no request leaves the test.
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiUnreachableError, CSRF_HEADER, createApiClient, ERROR_CODES, type HttpMethod } from "./client";
import schemaSource from "./schema.d.ts?raw";

function respond(status: number, body?: unknown): Response {
  if (status === 204) return new Response(null, { status });
  return new Response(body === undefined ? "Not Found" : JSON.stringify(body), {
    status,
    headers: body === undefined ? { "Content-Type": "text/plain" } : { "Content-Type": "application/json" },
  });
}

function mockFetch(status = 200, body: unknown = {}) {
  return vi.fn<typeof fetch>(async () => respond(status, body));
}

function sentInit(fetchMock: ReturnType<typeof mockFetch>, call = 0): RequestInit {
  const init = fetchMock.mock.calls[call]?.[1];
  if (!init) throw new Error("fetch wasn't called");
  return init;
}

/** The error a promise fails with (the test fails if it doesn't). */
async function failure<E extends Error = ApiError>(promise: Promise<unknown>): Promise<E> {
  try {
    await promise;
  } catch (error) {
    return error as E;
  }
  throw new Error("expected the call to fail");
}

function headersOf(init: RequestInit): Record<string, string> {
  return init.headers as Record<string, string>;
}

describe("writes and reads", () => {
  it.each<HttpMethod>(["POST", "PUT", "PATCH", "DELETE"])("%s carries X-ShelfSync: 1", async (method) => {
    const fetchMock = mockFetch(204);
    await createApiClient({ fetch: fetchMock }).request(method, "/api/thing");
    expect(headersOf(sentInit(fetchMock))[CSRF_HEADER]).toBe("1");
    expect(sentInit(fetchMock).method).toBe(method);
  });

  it.each<HttpMethod>(["GET", "HEAD"])("%s carries no X-ShelfSync header", async (method) => {
    const fetchMock = mockFetch(200);
    await createApiClient({ fetch: fetchMock }).request(method, "/api/thing");
    expect(headersOf(sentInit(fetchMock))).not.toHaveProperty(CSRF_HEADER);
  });

  it("stays same-origin, never follows a redirect, sends no referrer and never caches", async () => {
    const fetchMock = mockFetch(200);
    await createApiClient({ fetch: fetchMock }).get("/api/health");
    const init = sentInit(fetchMock);
    expect(init).toMatchObject({
      credentials: "same-origin",
      mode: "same-origin",
      redirect: "error",
      referrerPolicy: "no-referrer",
      cache: "no-store",
    });
  });

  it("never sets a Cookie or Authorization header itself (the session cookie is HttpOnly)", async () => {
    const fetchMock = mockFetch(204);
    await createApiClient({ fetch: fetchMock }).send("POST", "/api/session", { ticket: "x".repeat(43) });
    const names = Object.keys(headersOf(sentInit(fetchMock))).map((name) => name.toLowerCase());
    expect(names).not.toContain("cookie");
    expect(names).not.toContain("authorization");
  });

  it("sends a JSON body as JSON", async () => {
    const fetchMock = mockFetch(204);
    await createApiClient({ fetch: fetchMock }).send("POST", "/api/session", { ticket: "abc" });
    const init = sentInit(fetchMock);
    expect(headersOf(init)["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"ticket":"abc"}');
  });

  it.each(["https://evil.example/api/x", "//evil.example/api/x", "/api/../x", "/other", "api/x", "/api/x?token=1"])(
    "refuses a path that isn't a plain same-origin /api path: %s",
    async (path) => {
      const fetchMock = mockFetch(200);
      await expect(createApiClient({ fetch: fetchMock }).request("GET", path)).rejects.toThrow("Not an API path");
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("returns undefined for 204 and the parsed body otherwise", async () => {
    expect(await createApiClient({ fetch: mockFetch(204) }).send("POST", "/api/x")).toBeUndefined();
    expect(await createApiClient({ fetch: mockFetch(200, { app: "shelfsync" }) }).get("/api/health")).toEqual({
      app: "shelfsync",
    });
  });
});

describe("errors", () => {
  it("a 401 signed_out calls onSignedOut once and throws an ApiError with the code", async () => {
    const onSignedOut = vi.fn();
    const api = createApiClient({ fetch: mockFetch(401, { error: "signed_out" }), onSignedOut });
    const error = await failure(api.get("/api/catalog"));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("signed_out");
    expect(onSignedOut).toHaveBeenCalledTimes(1);
  });

  it.each([
    [401, "bad_ticket"],
    [401, "bad_token"],
    [403, "forbidden"],
    [500, "internal"],
  ])("HTTP %i %s doesn't sign the tab out", async (status, code) => {
    const onSignedOut = vi.fn();
    const api = createApiClient({ fetch: mockFetch(status, { error: code }), onSignedOut });
    await expect(api.send("POST", "/api/x")).rejects.toBeInstanceOf(ApiError);
    expect(onSignedOut).not.toHaveBeenCalled();
  });

  it("an unknown or non-JSON error body gives no code and is never repeated", async () => {
    const odd = await failure(
      createApiClient({ fetch: mockFetch(400, { error: "<script>x</script>" }) }).get("/api/x"),
    );
    expect(odd.code).toBeNull();
    expect(odd.message).toBe("GET /api/x answered HTTP 400");
    const text = await failure(createApiClient({ fetch: mockFetch(404) }).get("/api/x"));
    expect(text.code).toBeNull();
  });

  it("the error text holds the method, path and status only, never the body that was sent", async () => {
    const ticket = "T1cket-Value_that-must-never-show-up-0123456789";
    const error = await failure(
      createApiClient({ fetch: mockFetch(422, { error: "invalid_request" }) }).send("POST", "/api/session", { ticket }),
    );
    expect(error.message).toBe("POST /api/session answered HTTP 422 (invalid_request)");
    expect(JSON.stringify(error)).not.toContain(ticket);
    expect(String(error.stack)).not.toContain(ticket);
  });

  it("no answer at all becomes ApiUnreachableError, without the browser's message", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => {
      throw new TypeError("Failed to fetch secret-looking-detail");
    });
    const error = await failure<ApiUnreachableError>(
      createApiClient({ fetch: fetchMock }).request("GET", "/api/health"),
    );
    expect(error).toBeInstanceOf(ApiUnreachableError);
    expect(error.message).toBe("GET /api/health got no answer");
  });
});

describe("error codes", () => {
  it("are exactly the ErrorResponse enum in the generated schema", () => {
    const block = /ErrorResponse: \{[\s\S]*?error: ([^;]+);/.exec(schemaSource)?.[1] ?? "";
    const fromSchema = [...block.matchAll(/"([a-z_]+)"/g)].map((match) => match[1]);
    expect(fromSchema.length).toBeGreaterThan(0);
    expect([...ERROR_CODES].sort()).toEqual([...fromSchema].sort());
  });

  it("a code the schema doesn't name is dropped, never echoed", async () => {
    const api = createApiClient({ fetch: vi.fn<typeof fetch>(async () => respond(400, { error: "<b>made up</b>" })) });
    const error = await api.get("/api/health").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBeNull();
    expect((error as ApiError).message).toBe("GET /api/health answered HTTP 400");
  });
});
