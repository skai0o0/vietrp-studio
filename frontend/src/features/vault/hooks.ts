import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/apiClient";
import { VAULT_ME_KEY } from "@/lib/queryClient";
import { vaultApi, type VaultOut } from "./api";

/** `null` means the vault is locked. */
export type VaultMe = VaultOut | null;

export function useVaultMe() {
  return useQuery<VaultMe>({
    queryKey: VAULT_ME_KEY,
    retry: false,
    staleTime: Infinity,
    queryFn: async () => {
      try {
        return (await vaultApi.me()).vault;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
  });
}

/** Drops every cached query except the vault state, so no data leaks between vaults. */
function resetOwnedCache(client: QueryClient, vault: VaultMe): void {
  client.removeQueries({ predicate: (query) => query.queryKey[0] !== VAULT_ME_KEY[0] });
  client.setQueryData(VAULT_ME_KEY, vault);
}

export function useUnlock() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (passphrase: string) => vaultApi.unlock(passphrase),
    onSuccess: (result) => {
      if (result.exists) resetOwnedCache(client, result.vault);
    },
  });
}

export function useCreateVault() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { passphrase: string; displayName: string }) =>
      vaultApi.create(input.passphrase, input.displayName),
    onSuccess: (result) => resetOwnedCache(client, result.vault),
  });
}

export function useLock() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => vaultApi.lock(),
    onSettled: () => resetOwnedCache(client, null),
  });
}

export function useRenameVault() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (displayName: string) => vaultApi.rename(displayName),
    onSuccess: (result) => client.setQueryData(VAULT_ME_KEY, result.vault),
  });
}
