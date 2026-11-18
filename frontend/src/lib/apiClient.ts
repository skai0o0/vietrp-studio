export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  /** Seconds from the `Retry-After` header (429 responses), when present and numeric. */
  readonly retryAfter: number | undefined;

  constructor(status: number, code: string, message: string, retryAfter?: number) {
    super(message);
    this.retryAfter = retryAfter;
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export interface ApiRequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

const NETWORK_ERROR_CODE = "network_error";
const UNKNOWN_ERROR_CODE = "unknown";

interface ErrorBody {
  error?: { code?: unknown; message?: unknown };
}

async function parseError(response: Response): Promise<ApiError> {
  let code = UNKNOWN_ERROR_CODE;
  let message = response.statusText || "Request failed";
  try {
    const body = (await response.json()) as ErrorBody;
    if (typeof body.error?.code === "string") code = body.error.code;
    if (typeof body.error?.message === "string") message = body.error.message;
  } catch {
    /* non-JSON error body: keep the defaults */
  }
  const header = Number(response.headers.get("Retry-After"));
  const retryAfter = Number.isFinite(header) && header > 0 ? header : undefined;
  return new ApiError(response.status, code, message, retryAfter);
}

/** JSON-in/JSON-out fetch wrapper. Network failures become `ApiError` with code `network_error`. */
export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, headers } = options;
  const init: RequestInit = {
    method,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    ...(signal ? { signal } : {}),
  };

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, NETWORK_ERROR_CODE, "Network request failed");
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const apiClient = {
  get: <T>(path: string, signal?: AbortSignal) => apiRequest<T>(path, signal ? { signal } : {}),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    apiRequest<T>(path, { method: "POST", body, ...(signal ? { signal } : {}) }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
};
