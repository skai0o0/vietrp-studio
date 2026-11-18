import { apiClient } from "@/lib/apiClient";

export interface VaultOut {
  id: string;
  display_name: string;
  created_at: string;
}

export type UnlockResponse = { exists: true; vault: VaultOut } | { exists: false };

export interface SecretOut {
  name: string;
  is_set: boolean;
  hint: string | null;
  updated_at: string | null;
}

export const vaultApi = {
  me: () => apiClient.get<{ vault: VaultOut }>("/api/vault/me"),
  unlock: (passphrase: string) =>
    apiClient.post<UnlockResponse>("/api/vault/unlock", { passphrase }),
  create: (passphrase: string, displayName: string) =>
    apiClient.post<{ vault: VaultOut }>("/api/vault/create", {
      passphrase,
      display_name: displayName,
    }),
  lock: () => apiClient.post<void>("/api/vault/lock"),
  rename: (displayName: string) =>
    apiClient.patch<{ vault: VaultOut }>("/api/vault/me", { display_name: displayName }),
  listSecrets: () => apiClient.get<{ secrets: SecretOut[] }>("/api/secrets"),
  putSecret: (name: string, value: string) =>
    apiClient.put<{ secret: SecretOut }>(`/api/secrets/${encodeURIComponent(name)}`, { value }),
  deleteSecret: (name: string) =>
    apiClient.delete<void>(`/api/secrets/${encodeURIComponent(name)}`),
};
