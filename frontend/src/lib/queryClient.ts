import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "./apiClient";

export const VAULT_ME_KEY = ["vault", "me"] as const;

// Defaults: short staleness for owned data, and never retry client errors.
const STALE_TIME_MS = 30_000;
const MAX_RETRIES = 2;

function handleError(error: unknown, client: QueryClient): void {
  if (error instanceof ApiError && error.status === 401 && error.code === "vault_locked") {
    void client.invalidateQueries({ queryKey: VAULT_ME_KEY });
  }
}

export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (error) => handleError(error, client) }),
    mutationCache: new MutationCache({ onError: (error) => handleError(error, client) }),
    defaultOptions: {
      queries: {
        staleTime: STALE_TIME_MS,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
          return failureCount < MAX_RETRIES;
        },
      },
    },
  });
  return client;
}

export const queryClient = createQueryClient();
