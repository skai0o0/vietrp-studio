/** A POST-capable SSE client over fetch + ReadableStream (EventSource cannot POST). */
import { ApiError } from "./apiClient";

export interface SseEvent {
  event: string;
  data: unknown;
}

const LINE_BREAK = /\r\n|\n|\r/;

/** Incremental parser for the text/event-stream wire format. `ping` events are dropped. */
export class SseParser {
  private buffer = "";
  private eventName = "";
  private dataLines: string[] = [];

  /** Feed a decoded chunk; returns the events it completed. */
  push(chunk: string): SseEvent[] {
    this.buffer += chunk;
    const events: SseEvent[] = [];
    for (;;) {
      const match = LINE_BREAK.exec(this.buffer);
      if (!match) break;
      // A trailing lone "\r" may be half of "\r\n": wait for the next chunk.
      if (match[0] === "\r" && match.index + 1 === this.buffer.length) break;
      const line = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const parsed = this.handleLine(line);
      if (parsed) events.push(parsed);
    }
    return events;
  }

  private handleLine(line: string): SseEvent | null {
    if (line === "") return this.dispatch();
    if (line.startsWith(":")) return null; // comment / keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.eventName = value;
    else if (field === "data") this.dataLines.push(value);
    return null;
  }

  private dispatch(): SseEvent | null {
    if (this.dataLines.length === 0 && this.eventName === "") return null;
    const name = this.eventName || "message";
    const raw = this.dataLines.join("\n");
    this.eventName = "";
    this.dataLines = [];
    if (name === "ping") return null;
    let data: unknown = raw;
    try {
      data = raw === "" ? null : JSON.parse(raw);
    } catch {
      /* keep the raw string for non-JSON payloads */
    }
    return { event: name, data };
  }
}

/** Reads the `{error:{code,message}}` envelope so callers can branch on e.g. `turn_running`. */
async function httpError(response: Response): Promise<ApiError> {
  let code = "unknown";
  let message = `SSE request failed with status ${response.status}`;
  try {
    const body = (await response.json()) as { error?: { code?: unknown; message?: unknown } };
    if (typeof body.error?.code === "string") code = body.error.code;
    if (typeof body.error?.message === "string") message = body.error.message;
  } catch {
    /* non-JSON body */
  }
  return new ApiError(response.status, code, message);
}

export interface SseRequest {
  url: string;
  method?: "POST" | "GET";
  body?: unknown;
  signal?: AbortSignal;
  onEvent: (event: SseEvent) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
}

/**
 * Opens a stream and dispatches events until the server closes it or `signal` aborts.
 * Never reconnects on its own: a POST turn must not be replayed silently.
 */
export async function streamSse(request: SseRequest): Promise<void> {
  const { url, method = "POST", body, signal, onEvent, onError, onDone } = request;
  try {
    const response = await fetch(url, {
      method,
      credentials: "include",
      headers: {
        Accept: "text/event-stream",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      ...(signal ? { signal } : {}),
    });
    if (!response.ok) throw await httpError(response);
    if (!response.body) throw new Error(`SSE request failed with status ${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const parser = new SseParser();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const event of parser.push(decoder.decode(value, { stream: true }))) onEvent(event);
    }
    for (const event of parser.push(decoder.decode() + "\n\n")) onEvent(event);
    onDone?.();
  } catch (error) {
    if (signal?.aborted) {
      onDone?.();
      return;
    }
    onError?.(error instanceof Error ? error : new Error(String(error)));
  }
}
