import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/apiClient";
import { galleryApi } from "@/features/gallery/api";
import { useGallery } from "@/features/gallery/hooks";
import { buildQuery, characterApi, personaApi } from "./api";
import { useCharacters, useDeleteCharacter, useSetCharacterAvatar } from "./hooks";

const fetchMock = vi.fn();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function wrapperFor(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function newClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("buildQuery", () => {
  it("skips empty values and encodes", () => {
    expect(buildQuery({ q: "a b", tag: "", limit: 30, cursor: undefined })).toBe("?q=a+b&limit=30");
    expect(buildQuery({})).toBe("");
  });
});

describe("library api", () => {
  it("lists characters with query params and credentials", async () => {
    fetchMock.mockResolvedValue(json({ items: [], next_cursor: null }));
    await characterApi.list({ q: "mai", limit: 10 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/characters?q=mai&limit=10",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
  });

  it("maps error bodies to ApiError", async () => {
    fetchMock.mockResolvedValue(json({ error: { code: "nsfw_minor_public", message: "x" } }, 422));
    await expect(characterApi.get("abc")).rejects.toMatchObject({
      status: 422,
      code: "nsfw_minor_public",
    });
  });

  it("uploads avatar as multipart with the file field", async () => {
    fetchMock.mockResolvedValue(json({ character: { id: "c1" } }));
    await characterApi.setAvatar("c1", new Blob(["x"], { type: "image/png" }));
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/characters/c1/avatar");
    expect(init.method).toBe("PUT");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(Blob);
    expect(init.headers).not.toHaveProperty("Content-Type");
  });

  it("surfaces upload errors as ApiError", async () => {
    fetchMock.mockResolvedValue(json({ error: { code: "file_too_large", message: "big" } }, 413));
    await expect(personaApi.setAvatar("p1", new Blob(["x"]))).rejects.toBeInstanceOf(ApiError);
  });

  it("downloads via blob and a[download] using Content-Disposition", async () => {
    fetchMock.mockResolvedValue(
      new Response("{}", { headers: { "Content-Disposition": 'attachment; filename="mai.json"' } }),
    );
    const createUrl = vi.fn(() => "blob:x");
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    await characterApi.exportFile("c1", "ccv3", "json");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/characters/c1/export?format=ccv3&as=json");
    const clicked = click.mock.contexts[0] as HTMLAnchorElement | undefined;
    expect(clicked?.download).toBe("mai.json");
    expect(revoke).toHaveBeenCalledWith("blob:x");
    click.mockRestore();
  });
});

describe("gallery api", () => {
  it("builds gallery query and favorite routes", async () => {
    fetchMock.mockResolvedValue(json({ items: [], next_cursor: null }));
    await galleryApi.list({ type: "world", sort: "favorites" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/gallery?type=world&sort=favorites");
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await galleryApi.addFavorite("character", "c1");
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/favorites/character/c1",
      expect.objectContaining({ method: "PUT" }),
    ]);
  });
});

describe("hooks", () => {
  it("paginates characters with the cursor", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ items: [{ id: "a" }], next_cursor: "cur1" }))
      .mockResolvedValueOnce(json({ items: [{ id: "b" }], next_cursor: null }));
    const { result } = renderHook(() => useCharacters({ q: "x" }), {
      wrapper: wrapperFor(newClient()),
    });
    await waitFor(() => expect(result.current.hasNextPage).toBe(true));
    await act(async () => {
      await result.current.fetchNextPage();
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/characters?limit=30&q=x");
    expect(fetchMock.mock.calls[1]?.[0]).toContain("cursor=cur1");
    await waitFor(() => expect(result.current.hasNextPage).toBe(false));
  });

  it("invalidates lists and gallery after delete", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const client = newClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useDeleteCharacter(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.mutateAsync("c1");
    });
    const keys = spy.mock.calls.map((c) => (c[0] as { queryKey: string[] }).queryKey[0]);
    expect(keys).toEqual(expect.arrayContaining(["characters", "gallery"]));
  });

  it("removes the avatar when given null and updates the detail cache", async () => {
    fetchMock.mockResolvedValue(json({ character: { id: "c1", avatar_url: null } }));
    const client = newClient();
    const { result } = renderHook(() => useSetCharacterAvatar("c1"), {
      wrapper: wrapperFor(client),
    });
    await act(async () => {
      await result.current.mutateAsync(null);
    });
    expect(fetchMock.mock.calls[0]).toEqual([
      "/api/characters/c1/avatar",
      expect.objectContaining({ method: "DELETE" }),
    ]);
    expect(client.getQueryData(["character", "c1"])).toMatchObject({ id: "c1" });
  });

  it("gallery hook passes params", async () => {
    fetchMock.mockResolvedValue(json({ items: [], next_cursor: null }));
    const { result } = renderHook(() => useGallery({ sort: "recent" }), {
      wrapper: wrapperFor(newClient()),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/gallery?limit=30&sort=recent");
  });
});
