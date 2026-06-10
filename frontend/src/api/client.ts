/**
 * Base API client — all network calls go through here.
 *
 * During development the Vite proxy forwards /api → http://localhost:8000.
 * In production the same origin serves the SPA, so /api always works.
 */

const BASE = '/api';

// ─────────────────────────────────────────────────────────────────────────────
// Generic helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Generic HTTP request helper with automatic JSON parsing and error handling.
 *
 * Sends requests with Content-Type: application/json. On non-2xx responses,
 * attempts to extract a 'detail' or 'message' field from the JSON body and
 * throws an Error with that text. Returns undefined for 204 No Content.
 *
 * @template T - Expected response type.
 * @param path - URL path relative to BASE (e.g. '/sessions').
 * @param init - Optional fetch RequestInit (method, body, headers, etc.).
 * @returns Parsed JSON response typed as T.
 * @throws Error with the backend error detail on non-2xx responses.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch {
      // ignore JSON parse failure
    }
    throw new Error(detail);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json();
}

/**
 * Typed API client with convenience methods for each HTTP verb.
 *
 * All methods accept a relative path (e.g. '/sessions') and automatically
 * JSON-stringify request bodies and parse JSON responses.
 *
 * @property get    - Send a GET request. Returns parsed JSON.
 * @property post   - Send a POST request with a JSON body. Returns parsed JSON.
 * @property put    - Send a PUT request with a JSON body. Returns parsed JSON.
 * @property patch  - Send a PATCH request with a JSON body. Returns parsed JSON.
 * @property delete - Send a DELETE request. Returns parsed JSON or undefined.
 */
export const api = {
  get:    <T>(path: string)                    => request<T>(path, { method: 'GET' }),
  post:   <T>(path: string, body: unknown)     => request<T>(path, { method: 'POST',  body: JSON.stringify(body) }),
  put:    <T>(path: string, body: unknown)     => request<T>(path, { method: 'PUT',   body: JSON.stringify(body) }),
  patch:  <T>(path: string, body: unknown)     => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string)                    => request<T>(path, { method: 'DELETE' }),
};

// ─────────────────────────────────────────────────────────────────────────────
// SSE client — returns an EventSource-like async iterable
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Open an SSE stream via POST fetch (supports body, unlike native EventSource).
 *
 * Reads the response body as a stream of text chunks, splits on newlines,
 * and parses each 'data: {...}' line as JSON. Malformed lines are silently
 * skipped to tolerate partial writes.
 *
 * @param path   - URL path relative to BASE (e.g. '/chat').
 * @param body   - JSON-serialisable payload to send as the POST body.
 * @param signal - Optional AbortSignal to cancel the stream mid-flight.
 * @yields Parsed JSON event objects as they arrive from the backend.
 * @throws Error with the backend error detail on non-2xx responses.
 */
export async function* openSSEStream(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<Record<string, unknown>> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`;
    try {
      const b = await res.json();
      detail = b.detail ?? b.message ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const json = line.slice(6).trim();
        if (json) {
          try {
            yield JSON.parse(json);
          } catch {
            // skip malformed lines
          }
        }
      }
    }
  }
}
