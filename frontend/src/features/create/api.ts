import { apiClient } from "@/lib/apiClient";
import type { Visibility } from "@/types/library";
import type {
  CreatorPoolsOut,
  CreatorSaveOut,
  CreatorSessionCreate,
  CreatorSessionOut,
  CreatorSessionUpdate,
} from "./types";

const id = encodeURIComponent;

export interface CreatorSaveInput {
  visibility?: Visibility;
  data?: Record<string, unknown>;
}

export const creatorApi = {
  getPools: () => apiClient.get<CreatorPoolsOut>("/api/creator/pools"),
  createSession: (body: CreatorSessionCreate) =>
    apiClient.post<CreatorSessionOut>("/api/creator/sessions", body),
  getSession: (sessionId: string) =>
    apiClient.get<CreatorSessionOut>(`/api/creator/sessions/${id(sessionId)}`),
  updateSession: (sessionId: string, body: CreatorSessionUpdate) =>
    apiClient.patch<CreatorSessionOut>(`/api/creator/sessions/${id(sessionId)}`, body),
  saveSession: (sessionId: string, body: CreatorSaveInput) =>
    apiClient.post<CreatorSaveOut>(`/api/creator/sessions/${id(sessionId)}/save`, body),
  messageUrl: (sessionId: string) => `/api/creator/sessions/${id(sessionId)}/message`,
  generateUrl: (sessionId: string) => `/api/creator/sessions/${id(sessionId)}/generate`,
};
