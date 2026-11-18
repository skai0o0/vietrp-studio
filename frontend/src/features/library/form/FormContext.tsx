import { createContext, useContext } from "react";

export interface FormState {
  readOnly: boolean;
  /** Field errors from the server, keyed by path inside `data`. */
  errors: Record<string, string>;
  /** Soft warnings from the server, keyed by path inside `data`. */
  warnings: Record<string, string[]>;
}

const FormStateContext = createContext<FormState>({ readOnly: false, errors: {}, warnings: {} });

export const FormStateProvider = FormStateContext.Provider;

export function useFormState(): FormState {
  return useContext(FormStateContext);
}

export function useFieldMeta(
  path?: string,
  altPath?: string,
): {
  readOnly: boolean;
  error: string | undefined;
  warnings: string[];
} {
  const { readOnly, errors, warnings } = useFormState();
  const error = (path ? errors[path] : undefined) ?? (altPath ? errors[altPath] : undefined);
  const list = [
    ...(path ? (warnings[path] ?? []) : []),
    ...(altPath ? (warnings[altPath] ?? []) : []),
  ];
  return { readOnly, error, warnings: list };
}
