import { ApiError, apiClient } from "@/lib/apiClient";
import type {
  CharacterOut,
  CharacterSummary,
  ExportAs,
  ExportFormat,
  ImportResult,
  ListParams,
  Lorebook,
  LorebookExportFormat,
  LorebookOut,
  LorebookSummary,
  Page,
  Persona,
  PersonaOut,
  VietrpCard,
  VietrpWorld,
  Visibility,
  WorldOut,
  WorldSummary,
} from "@/types/library";

/** Builds `?a=1&b=2`, skipping undefined/empty values. */
export function buildQuery(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function errorFrom(response: Response): Promise<ApiError> {
  let code = "unknown";
  let message = response.statusText || "Request failed";
  try {
    const body = (await response.json()) as { error?: { code?: unknown; message?: unknown } };
    if (typeof body.error?.code === "string") code = body.error.code;
    if (typeof body.error?.message === "string") message = body.error.message;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(response.status, code, message);
}

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "include", ...init });
  } catch {
    throw new ApiError(0, "network_error", "Network request failed");
  }
  if (!response.ok) throw await errorFrom(response);
  return response;
}

/** Multipart upload (field name `file`). The browser sets the boundary header. */
export async function uploadFile<T>(path: string, method: "PUT" | "POST", file: Blob): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const response = await rawFetch(path, {
    method,
    body: form,
    headers: { Accept: "application/json" },
  });
  return (await response.json()) as T;
}

function filenameFrom(disposition: string | null, fallback: string): string {
  const match = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  if (!match?.[1]) return fallback;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

/** Fetches a file and triggers a browser download via a temporary `a[download]`. */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const response = await rawFetch(path, { method: "GET" });
  const blob = await response.blob();
  const name = filenameFrom(response.headers.get("Content-Disposition"), fallbackName);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export interface CursorParams extends ListParams {
  cursor?: string | undefined;
}

const id = encodeURIComponent;

export const characterApi = {
  list: (p: CursorParams = {}) =>
    apiClient.get<Page<CharacterSummary>>(`/api/characters${buildQuery(p)}`),
  get: (cid: string) => apiClient.get<{ character: CharacterOut }>(`/api/characters/${id(cid)}`),
  create: (data: VietrpCard, visibility: Visibility) =>
    apiClient.post<{ character: CharacterOut }>("/api/characters", { data, visibility }),
  update: (cid: string, data: VietrpCard, visibility: Visibility) =>
    apiClient.put<{ character: CharacterOut }>(`/api/characters/${id(cid)}`, { data, visibility }),
  remove: (cid: string) => apiClient.delete<void>(`/api/characters/${id(cid)}`),
  duplicate: (cid: string) =>
    apiClient.post<{ character: CharacterOut }>(`/api/characters/${id(cid)}/duplicate`),
  judge: (cid: string) =>
    apiClient.post<{ character: CharacterOut }>(`/api/characters/${id(cid)}/judge`),
  setAvatar: (cid: string, file: Blob) =>
    uploadFile<{ character: CharacterOut }>(`/api/characters/${id(cid)}/avatar`, "PUT", file),
  removeAvatar: (cid: string) =>
    apiClient.delete<{ character: CharacterOut }>(`/api/characters/${id(cid)}/avatar`),
  exportFile: (cid: string, format: ExportFormat, as: ExportAs) =>
    downloadFile(
      `/api/characters/${id(cid)}/export${buildQuery({ format, as })}`,
      `character.${as}`,
    ),
};

export const worldApi = {
  list: (p: CursorParams = {}) => apiClient.get<Page<WorldSummary>>(`/api/worlds${buildQuery(p)}`),
  get: (wid: string) => apiClient.get<{ world: WorldOut }>(`/api/worlds/${id(wid)}`),
  create: (data: VietrpWorld, visibility: Visibility) =>
    apiClient.post<{ world: WorldOut }>("/api/worlds", { data, visibility }),
  update: (wid: string, data: VietrpWorld, visibility: Visibility) =>
    apiClient.put<{ world: WorldOut }>(`/api/worlds/${id(wid)}`, { data, visibility }),
  remove: (wid: string) => apiClient.delete<void>(`/api/worlds/${id(wid)}`),
  duplicate: (wid: string) =>
    apiClient.post<{ world: WorldOut }>(`/api/worlds/${id(wid)}/duplicate`),
  judge: (wid: string) => apiClient.post<{ world: WorldOut }>(`/api/worlds/${id(wid)}/judge`),
  setCover: (wid: string, file: Blob) =>
    uploadFile<{ world: WorldOut }>(`/api/worlds/${id(wid)}/cover`, "PUT", file),
  removeCover: (wid: string) =>
    apiClient.delete<{ world: WorldOut }>(`/api/worlds/${id(wid)}/cover`),
  exportFile: (wid: string) =>
    downloadFile(
      `/api/worlds/${id(wid)}/export${buildQuery({ format: "vietrp", as: "json" })}`,
      "world.json",
    ),
};

export const personaApi = {
  list: () => apiClient.get<{ items: PersonaOut[] }>("/api/personas"),
  get: (pid: string) => apiClient.get<{ persona: PersonaOut }>(`/api/personas/${id(pid)}`),
  create: (data: Persona) => apiClient.post<{ persona: PersonaOut }>("/api/personas", { data }),
  update: (pid: string, data: Persona) =>
    apiClient.put<{ persona: PersonaOut }>(`/api/personas/${id(pid)}`, { data }),
  remove: (pid: string) => apiClient.delete<void>(`/api/personas/${id(pid)}`),
  setAvatar: (pid: string, file: Blob) =>
    uploadFile<{ persona: PersonaOut }>(`/api/personas/${id(pid)}/avatar`, "PUT", file),
  removeAvatar: (pid: string) =>
    apiClient.delete<{ persona: PersonaOut }>(`/api/personas/${id(pid)}/avatar`),
};

export const lorebookApi = {
  list: (p: CursorParams = {}) =>
    apiClient.get<Page<LorebookSummary>>(`/api/lorebooks${buildQuery(p)}`),
  get: (lid: string) => apiClient.get<{ lorebook: LorebookOut }>(`/api/lorebooks/${id(lid)}`),
  create: (data: Lorebook, visibility: Visibility) =>
    apiClient.post<{ lorebook: LorebookOut }>("/api/lorebooks", { data, visibility }),
  update: (lid: string, data: Lorebook, visibility: Visibility) =>
    apiClient.put<{ lorebook: LorebookOut }>(`/api/lorebooks/${id(lid)}`, { data, visibility }),
  remove: (lid: string) => apiClient.delete<void>(`/api/lorebooks/${id(lid)}`),
  duplicate: (lid: string) =>
    apiClient.post<{ lorebook: LorebookOut }>(`/api/lorebooks/${id(lid)}/duplicate`),
  exportFile: (lid: string, format: LorebookExportFormat) =>
    downloadFile(`/api/lorebooks/${id(lid)}/export${buildQuery({ format })}`, "lorebook.json"),
};

export const importApi = {
  importFile: (file: Blob) => uploadFile<ImportResult>("/api/import", "POST", file),
};

export const libraryApi = {
  judgeCharacter: (cid: string) => characterApi.judge(cid),
  judgeWorld: (wid: string) => worldApi.judge(wid),
};
