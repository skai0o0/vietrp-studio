import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";
import type { CharacterOut, LorebookOut, WorldOut } from "@/types/library";

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export type Handler = (call: Call) => Response | undefined;

export function json(status: number, body?: unknown): Response {
  if (status === 204) return new Response(null, { status });
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Stubs `fetch`; unmatched calls answer 404. Returns the recorded calls. */
export function mockApi(handler: Handler): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const call: Call = {
        method: init?.method ?? "GET",
        path,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      };
      calls.push(call);
      return handler(call) ?? json(404, { error: { code: "not_found", message: "no route" } });
    }),
  );
  return calls;
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

/** Renders `element` at `route` inside a router and a fresh QueryClient. */
export function renderAt(element: ReactElement, pattern: string, route: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={pattern} element={element} />
          <Route path="*" element={<p>other page</p>} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const NOW = "2026-01-01T00:00:00Z";

export function characterOut(overrides: Partial<CharacterOut> = {}): CharacterOut {
  return {
    id: "c1",
    name: "Mai",
    tagline: "Cô bạn cùng lớp",
    tags: ["school"],
    visibility: "private",
    avatar_url: null,
    needs_age: false,
    updated_at: NOW,
    created_at: NOW,
    is_owner: true,
    author: "Mèo",
    warnings: [],
    data: { format: "vietrp-card", spec_version: "1.0", name: "Mai", age: 17, is_fictional: true },
    ...overrides,
  };
}

export function worldOut(overrides: Partial<WorldOut> = {}): WorldOut {
  return {
    id: "w1",
    name: "Sài Gòn 2077",
    tagline: "",
    tags: [],
    visibility: "private",
    cover_url: null,
    needs_age: false,
    updated_at: NOW,
    created_at: NOW,
    is_owner: true,
    author: "Mèo",
    warnings: [],
    data: {
      format: "vietrp-world",
      spec_version: "1.0",
      name: "Sài Gòn 2077",
      locations: [],
      openings: [],
    },
    ...overrides,
  };
}

export function lorebookOut(overrides: Partial<LorebookOut> = {}): LorebookOut {
  return {
    id: "l1",
    name: "Lore trường",
    entry_count: 1,
    visibility: "private",
    updated_at: NOW,
    is_owner: true,
    author: "Mèo",
    data: {
      format: "vietrp-lorebook",
      spec_version: "1.0",
      name: "Lore trường",
      entries: [
        {
          id: "entry_1",
          title: "Cổng trường",
          keys: ["cổng"],
          content: "Cổng chính màu xanh.",
        },
      ],
    },
    ...overrides,
  };
}
