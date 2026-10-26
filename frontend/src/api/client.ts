// The one API client (SYS-03, the page's side; contract in docs/runs/m1a.2-security.md section 3).
// - Same origin only: every path starts with /api/, and the browser sends the session cookie by itself
//   (credentials "same-origin"). The cookie is HttpOnly: this code never reads, stores or sends it by hand.
// - Every write (any method except GET and HEAD) carries X-ShelfSync: 1; the browser adds the page's Origin.
// - Error text holds the method, the path and the status only: never a request body, so never a ticket.
// - A 401 "signed_out" from any call tells the session store, which shows the signed-out state. No retry.

export const CSRF_HEADER = "X-ShelfSync";
export const CSRF_VALUE = "1";

/** The fixed error codes the backend sends (`{"error": "<code>"}`); anything else is ignored, never echoed. */
export const ERROR_CODES = [
  "forbidden",
  "signed_out",
  "bad_token",
  "bad_ticket",
  "invalid_request",
  "internal",
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

export type HttpMethod = "GET" | "HEAD" | "POST" | "PUT" | "PATCH" | "DELETE";

export class ApiError extends Error {
  readonly method: HttpMethod;
  readonly path: string;
  readonly status: number;
  readonly code: ErrorCode | null;

  constructor(method: HttpMethod, path: string, status: number, code: ErrorCode | null) {
    super(`${method} ${path} answered HTTP ${status}${code ? ` (${code})` : ""}`);
    this.name = "ApiError";
    this.method = method;
    this.path = path;
    this.status = status;
    this.code = code;
  }
}

/** The request never reached ShelfSync (the server is stopped, or the network layer refused it). */
export class ApiUnreachableError extends Error {
  readonly method: HttpMethod;
  readonly path: string;

  constructor(method: HttpMethod, path: string) {
    super(`${method} ${path} got no answer`);
    this.name = "ApiUnreachableError";
    this.method = method;
    this.path = path;
  }
}

export function isWrite(method: HttpMethod): boolean {
  return method !== "GET" && method !== "HEAD";
}

const API_PATH = /^\/api\/[A-Za-z0-9/_-]*$/;

export interface ApiClientOptions {
  fetch?: typeof fetch;
  onSignedOut?: () => void;
}

export interface ApiClient {
  request(method: HttpMethod, path: string, body?: unknown): Promise<Response>;
  get<T>(path: string): Promise<T>;
  send<T = void>(method: Exclude<HttpMethod, "GET" | "HEAD">, path: string, body?: unknown): Promise<T>;
}

async function errorCode(response: Response): Promise<ErrorCode | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "error" in body) {
      const code = (body as { error: unknown }).error;
      if (typeof code === "string" && (ERROR_CODES as readonly string[]).includes(code)) return code as ErrorCode;
    }
  } catch {
    // Not JSON (a 404 from the static files, a 405): no code.
  }
  return null;
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const doFetch = options.fetch ?? ((input, init) => globalThis.fetch(input, init));

  async function request(method: HttpMethod, path: string, body?: unknown): Promise<Response> {
    if (!API_PATH.test(path)) throw new Error(`Not an API path: ${path.slice(0, 80)}`);
    const headers: Record<string, string> = { Accept: "application/json" };
    if (isWrite(method)) headers[CSRF_HEADER] = CSRF_VALUE;
    const init: RequestInit = {
      method,
      headers,
      credentials: "same-origin",
      mode: "same-origin",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
    };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    try {
      return await doFetch(path, init);
    } catch {
      // The browser's own message is dropped: it can't hold the body, but nothing here repeats what it was sent.
      throw new ApiUnreachableError(method, path);
    }
  }

  async function checked(method: HttpMethod, path: string, body?: unknown): Promise<Response> {
    const response = await request(method, path, body);
    if (response.ok) return response;
    const code = await errorCode(response);
    if (response.status === 401 && code === "signed_out") options.onSignedOut?.();
    throw new ApiError(method, path, response.status, code);
  }

  return {
    request,
    async get<T>(path: string): Promise<T> {
      const response = await checked("GET", path);
      return (await response.json()) as T;
    },
    async send<T = void>(method: Exclude<HttpMethod, "GET" | "HEAD">, path: string, body?: unknown): Promise<T> {
      const response = await checked(method, path, body);
      if (response.status === 204) return undefined as T;
      return (await response.json()) as T;
    },
  };
}
