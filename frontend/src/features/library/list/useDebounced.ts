import { useEffect, useState } from "react";

const SEARCH_DEBOUNCE_MS = 250; // typing pause before a list query is sent

export function useDebounced<T>(value: T, delay: number = SEARCH_DEBOUNCE_MS): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
