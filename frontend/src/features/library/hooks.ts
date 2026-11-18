import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import type {
  ExportAs,
  ExportFormat,
  ListParams,
  Lorebook,
  LorebookExportFormat,
  Persona,
  VietrpCard,
  VietrpWorld,
  Visibility,
} from "@/types/library";
import { characterApi, importApi, libraryApi, lorebookApi, personaApi, worldApi } from "./api";

const DEFAULT_PAGE_SIZE = 30; // WP-I contract: limit default 30

export const libraryKeys = {
  characters: (params: ListParams = {}) => ["characters", params] as const,
  character: (itemId: string | undefined) => ["character", itemId] as const,
  worlds: (params: ListParams = {}) => ["worlds", params] as const,
  world: (itemId: string | undefined) => ["world", itemId] as const,
  personas: () => ["personas"] as const,
  persona: (itemId: string | undefined) => ["persona", itemId] as const,
  lorebooks: (params: ListParams = {}) => ["lorebooks", params] as const,
  lorebook: (itemId: string | undefined) => ["lorebook", itemId] as const,
};

/** Invalidate list queries of the given kinds, plus the gallery (it shows public items). */
function invalidateLists(client: QueryClient, ...keys: string[]): void {
  for (const key of keys) void client.invalidateQueries({ queryKey: [key] });
  void client.invalidateQueries({ queryKey: ["gallery"] });
}

interface SaveInput<T> {
  data: T;
  visibility: Visibility;
}

/* ---------- characters ---------- */

export function useCharacters(params: ListParams = {}) {
  return useInfiniteQuery({
    queryKey: ["characters", params],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      characterApi.list({ limit: DEFAULT_PAGE_SIZE, ...params, cursor: pageParam }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useCharacter(itemId: string | undefined) {
  return useQuery({
    queryKey: libraryKeys.character(itemId),
    enabled: Boolean(itemId),
    queryFn: async () => (await characterApi.get(itemId as string)).character,
  });
}

export function useCreateCharacter() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: SaveInput<VietrpCard>) => characterApi.create(v.data, v.visibility),
    onSuccess: ({ character }) => {
      client.setQueryData(["character", character.id], character);
      invalidateLists(client, "characters");
    },
  });
}

export function useUpdateCharacter(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: SaveInput<VietrpCard>) => characterApi.update(itemId, v.data, v.visibility),
    onSuccess: ({ character }) => {
      client.setQueryData(["character", itemId], character);
      invalidateLists(client, "characters");
    },
  });
}

export function useDeleteCharacter() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => characterApi.remove(itemId),
    onSuccess: (_r, itemId) => {
      client.removeQueries({ queryKey: ["character", itemId] });
      invalidateLists(client, "characters");
    },
  });
}

export function useDuplicateCharacter() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => characterApi.duplicate(itemId),
    onSuccess: () => invalidateLists(client, "characters"),
  });
}

/** Pass `null` to remove the avatar. */
export function useSetCharacterAvatar(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: Blob | null) =>
      file ? characterApi.setAvatar(itemId, file) : characterApi.removeAvatar(itemId),
    onSuccess: ({ character }) => {
      client.setQueryData(["character", itemId], character);
      invalidateLists(client, "characters");
    },
  });
}

export function useExportCharacter() {
  return useMutation({
    mutationFn: (v: { id: string; format: ExportFormat; as: ExportAs }) =>
      characterApi.exportFile(v.id, v.format, v.as),
  });
}

export function useJudgeCharacter(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => libraryApi.judgeCharacter(itemId),
    onSuccess: ({ character }) => {
      client.setQueryData(libraryKeys.character(itemId), character);
      invalidateLists(client, "characters");
    },
  });
}

/* ---------- worlds ---------- */

export function useWorlds(params: ListParams = {}) {
  return useInfiniteQuery({
    queryKey: libraryKeys.worlds(params),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      worldApi.list({ limit: DEFAULT_PAGE_SIZE, ...params, cursor: pageParam }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useWorld(itemId: string | undefined) {
  return useQuery({
    queryKey: libraryKeys.world(itemId),
    enabled: Boolean(itemId),
    queryFn: async () => (await worldApi.get(itemId as string)).world,
  });
}

export function useCreateWorld() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: SaveInput<VietrpWorld>) => worldApi.create(v.data, v.visibility),
    onSuccess: ({ world }) => {
      client.setQueryData(["world", world.id], world);
      invalidateLists(client, "worlds");
    },
  });
}

export function useUpdateWorld(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: SaveInput<VietrpWorld>) => worldApi.update(itemId, v.data, v.visibility),
    onSuccess: ({ world }) => {
      client.setQueryData(["world", itemId], world);
      invalidateLists(client, "worlds");
    },
  });
}

export function useDeleteWorld() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => worldApi.remove(itemId),
    onSuccess: (_r, itemId) => {
      client.removeQueries({ queryKey: ["world", itemId] });
      invalidateLists(client, "worlds");
    },
  });
}

export function useDuplicateWorld() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => worldApi.duplicate(itemId),
    onSuccess: () => invalidateLists(client, "worlds"),
  });
}

/** Pass `null` to remove the cover. */
export function useSetWorldCover(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: Blob | null) =>
      file ? worldApi.setCover(itemId, file) : worldApi.removeCover(itemId),
    onSuccess: ({ world }) => {
      client.setQueryData(["world", itemId], world);
      invalidateLists(client, "worlds");
    },
  });
}

export function useExportWorld() {
  return useMutation({ mutationFn: (itemId: string) => worldApi.exportFile(itemId) });
}

export function useJudgeWorld(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => libraryApi.judgeWorld(itemId),
    onSuccess: ({ world }) => {
      client.setQueryData(libraryKeys.world(itemId), world);
      invalidateLists(client, "worlds");
    },
  });
}

/* ---------- personas ---------- */

export function usePersonas() {
  return useQuery({
    queryKey: ["personas"],
    queryFn: async () => (await personaApi.list()).items,
  });
}

export function usePersona(itemId: string | undefined) {
  return useQuery({
    queryKey: ["persona", itemId],
    enabled: Boolean(itemId),
    queryFn: async () => (await personaApi.get(itemId as string)).persona,
  });
}

export function useCreatePersona() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: Persona) => personaApi.create(data),
    onSuccess: ({ persona }) => {
      client.setQueryData(["persona", persona.id], persona);
      void client.invalidateQueries({ queryKey: ["personas"] });
    },
  });
}

export function useUpdatePersona(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: Persona) => personaApi.update(itemId, data),
    onSuccess: ({ persona }) => {
      client.setQueryData(["persona", itemId], persona);
      void client.invalidateQueries({ queryKey: ["personas"] });
    },
  });
}

export function useDeletePersona() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => personaApi.remove(itemId),
    onSuccess: (_r, itemId) => {
      client.removeQueries({ queryKey: ["persona", itemId] });
      void client.invalidateQueries({ queryKey: ["personas"] });
    },
  });
}

/** Pass `null` to remove the avatar. */
export function useSetPersonaAvatar(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: Blob | null) =>
      file ? personaApi.setAvatar(itemId, file) : personaApi.removeAvatar(itemId),
    onSuccess: ({ persona }) => {
      client.setQueryData(["persona", itemId], persona);
      void client.invalidateQueries({ queryKey: ["personas"] });
    },
  });
}

/* ---------- lorebooks ---------- */

export function useLorebooks(params: ListParams = {}) {
  return useInfiniteQuery({
    queryKey: ["lorebooks", params],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      lorebookApi.list({ limit: DEFAULT_PAGE_SIZE, ...params, cursor: pageParam }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useLorebook(itemId: string | undefined) {
  return useQuery({
    queryKey: ["lorebook", itemId],
    enabled: Boolean(itemId),
    queryFn: async () => (await lorebookApi.get(itemId as string)).lorebook,
  });
}

export function useCreateLorebook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: SaveInput<Lorebook>) => lorebookApi.create(v.data, v.visibility),
    onSuccess: ({ lorebook }) => {
      client.setQueryData(["lorebook", lorebook.id], lorebook);
      invalidateLists(client, "lorebooks");
    },
  });
}

export function useUpdateLorebook(itemId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: SaveInput<Lorebook>) => lorebookApi.update(itemId, v.data, v.visibility),
    onSuccess: ({ lorebook }) => {
      client.setQueryData(["lorebook", itemId], lorebook);
      invalidateLists(client, "lorebooks");
    },
  });
}

export function useDeleteLorebook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => lorebookApi.remove(itemId),
    onSuccess: (_r, itemId) => {
      client.removeQueries({ queryKey: ["lorebook", itemId] });
      invalidateLists(client, "lorebooks");
    },
  });
}

export function useDuplicateLorebook() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => lorebookApi.duplicate(itemId),
    onSuccess: () => invalidateLists(client, "lorebooks"),
  });
}

export function useExportLorebook() {
  return useMutation({
    mutationFn: (v: { id: string; format: LorebookExportFormat }) =>
      lorebookApi.exportFile(v.id, v.format),
  });
}

/* ---------- import ---------- */

export function useImportFile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: Blob) => importApi.importFile(file),
    onSuccess: () => invalidateLists(client, "characters", "worlds", "lorebooks"),
  });
}
