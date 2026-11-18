import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { vaultApi } from "@/features/vault/api";

export const SECRETS_KEY = ["secrets"] as const;

export function useSecrets() {
  return useQuery({
    queryKey: SECRETS_KEY,
    queryFn: async () => (await vaultApi.listSecrets()).secrets,
  });
}

export function usePutSecret() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; value: string }) =>
      vaultApi.putSecret(input.name, input.value),
    onSuccess: () => client.invalidateQueries({ queryKey: SECRETS_KEY }),
  });
}

export function useDeleteSecret() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => vaultApi.deleteSecret(name),
    onSuccess: () => client.invalidateQueries({ queryKey: SECRETS_KEY }),
  });
}
