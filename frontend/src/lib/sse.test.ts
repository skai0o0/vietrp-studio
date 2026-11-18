import { afterEach, describe, expect, it, vi } from "vitest";
import { SseParser, streamSse, type SseEvent } from "./sse";

describe("SseParser", () => {
  it("parses a single event with JSON data", () => {
    const parser = new SseParser();
    expect(parser.push('event: content\ndata: {"text":"xin chào"}\n\n')).toEqual([
      { event: "content", data: { text: "xin chào" } },
    ]);
  });

  it("joins multi-line data with newlines", () => {
    const parser = new SseParser();
    const events = parser.push("event: notice\ndata: dòng 1\ndata: dòng 2\n\n");
    expect(events).toEqual([{ event: "notice", data: "dòng 1\ndòng 2" }]);
  });

  it("handles chunks split mid-line and mid-CRLF", () => {
    const parser = new SseParser();
    const out: SseEvent[] = [];
    for (const chunk of ["eve", "nt: draft\r", '\ndata: {"a"', ":1}\r\n", "\r\n"]) {
      out.push(...parser.push(chunk));
    }
    expect(out).toEqual([{ event: "draft", data: { a: 1 } }]);
  });

  it("drops ping events and comments silently", () => {
    const parser = new SseParser();
    const events = parser.push(
      ": keep-alive\n\nevent: ping\ndata: {}\n\nevent: done\ndata: {}\n\n",
    );
    expect(events).toEqual([{ event: "done", data: {} }]);
  });

  it("defaults the event name to message", () => {
    const parser = new SseParser();
    expect(parser.push("data: hello\n\n")).toEqual([{ event: "message", data: "hello" }]);
  });
});

function streamOf(chunks: string[], signal?: AbortSignal): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      if (!signal) controller.close();
      else
        signal.addEventListener("abort", () =>
          controller.error(new DOMException("x", "AbortError")),
        );
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("streamSse", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("dispatches events and calls onDone", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(streamOf(["event: plan\ndata: {}\n\n", "event: done\ndata: {}\n\n"])),
    );
    const events: string[] = [];
    const onDone = vi.fn();
    await streamSse({
      url: "/api/x",
      body: { a: 1 },
      onEvent: (e) => events.push(e.event),
      onDone,
    });
    expect(events).toEqual(["plan", "done"]);
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("reports HTTP failures through onError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 500 })));
    const onError = vi.fn();
    await streamSse({ url: "/api/x", onEvent: vi.fn(), onError });
    expect(onError).toHaveBeenCalledOnce();
  });

  it("stops quietly when aborted", async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(async () => streamOf(["event: plan\ndata: {}\n\n"], controller.signal)),
    );
    const onError = vi.fn();
    const onDone = vi.fn();
    const promise = streamSse({
      url: "/api/x",
      signal: controller.signal,
      onEvent: vi.fn(),
      onError,
      onDone,
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    controller.abort();
    await promise;
    expect(onError).not.toHaveBeenCalled();
    expect(onDone).toHaveBeenCalledOnce();
  });
});
