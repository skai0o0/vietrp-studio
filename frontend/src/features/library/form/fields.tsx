import { AlertCircle, Lightbulb } from "lucide-react";
import { useId, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { t } from "@/i18n";
import { cn } from "@/lib/cn";
import { useFieldMeta } from "./FormContext";

export const textareaClass =
  "flex w-full rounded-md border border-border bg-surface px-3 py-2 font-content text-sm text-fg placeholder:text-muted read-only:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-2 aria-[invalid=true]:border-danger";
const selectClass =
  "h-10 w-full rounded-md border border-border bg-surface px-3 text-sm text-fg disabled:cursor-not-allowed disabled:opacity-60";

interface FieldBase {
  label: string;
  /** Path inside `data`; used to look up server errors and warnings. */
  path?: string;
  /** A second path to also match (e.g. warnings keyed by id instead of index). */
  altPath?: string;
  hint?: string;
  className?: string;
}

interface FrameProps {
  id: string;
  label: string;
  hint: string | undefined;
  error: string | undefined;
  warnings: string[];
  counter?: string | undefined;
  className: string | undefined;
  children: ReactNode;
}

function FieldFrame({
  id,
  label,
  hint,
  error,
  warnings,
  counter,
  className,
  children,
}: FrameProps) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {counter ? <span className="text-xs text-muted">{counter}</span> : null}
      </div>
      {children}
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="flex items-start gap-1.5 text-xs text-danger">
          <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}
      {warnings.map((text) => (
        <p
          key={text}
          data-testid="field-warning"
          className="flex items-start gap-1.5 border-l-2 border-accent-2 pl-2 text-xs text-muted"
        >
          <Lightbulb className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{text}</span>
        </p>
      ))}
    </div>
  );
}

function describedBy(
  id: string,
  hint: string | undefined,
  error: string | undefined,
): string | undefined {
  const ids = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

interface TextFieldProps extends FieldBase {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Shown as a `n/max` counter; not enforced here (the server owns the limits). */
  counterMax?: number;
}

export function TextField(props: TextFieldProps) {
  const { label, path, altPath, hint, className, value, onChange, placeholder, counterMax } = props;
  const id = useId();
  const meta = useFieldMeta(path, altPath);
  return (
    <FieldFrame
      id={id}
      label={label}
      hint={hint}
      error={meta.error}
      warnings={meta.warnings}
      counter={counterMax ? `${value.length}/${counterMax}` : undefined}
      className={className}
    >
      <Input
        id={id}
        value={value}
        readOnly={meta.readOnly}
        placeholder={meta.readOnly ? undefined : placeholder}
        aria-invalid={meta.error ? true : undefined}
        aria-describedby={describedBy(id, hint, meta.error)}
        className={cn(meta.error && "border-2 border-danger")}
        onChange={(event) => onChange(event.target.value)}
      />
    </FieldFrame>
  );
}

interface TextAreaFieldProps extends FieldBase {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
}

export function TextAreaField(props: TextAreaFieldProps) {
  const { label, path, altPath, hint, className, value, onChange, placeholder, rows = 4 } = props;
  const id = useId();
  const meta = useFieldMeta(path, altPath);
  return (
    <FieldFrame
      id={id}
      label={label}
      hint={hint}
      error={meta.error}
      warnings={meta.warnings}
      counter={t("library.fields.charCount", { count: value.length })}
      className={className}
    >
      <textarea
        id={id}
        value={value}
        rows={rows}
        readOnly={meta.readOnly}
        placeholder={meta.readOnly ? undefined : placeholder}
        aria-invalid={meta.error ? true : undefined}
        aria-describedby={describedBy(id, hint, meta.error)}
        className={cn(textareaClass, "min-h-20 resize-y")}
        onChange={(event) => onChange(event.target.value)}
      />
    </FieldFrame>
  );
}

interface NumberFieldProps extends FieldBase {
  value: number | null;
  onChange: (value: number | null) => void;
  placeholder?: string;
}

export function NumberField(props: NumberFieldProps) {
  const { label, path, altPath, hint, className, value, onChange, placeholder } = props;
  const id = useId();
  const meta = useFieldMeta(path, altPath);
  return (
    <FieldFrame
      id={id}
      label={label}
      hint={hint}
      error={meta.error}
      warnings={meta.warnings}
      className={className}
    >
      <Input
        id={id}
        type="number"
        inputMode="numeric"
        value={value === null ? "" : String(value)}
        readOnly={meta.readOnly}
        placeholder={placeholder}
        aria-invalid={meta.error ? true : undefined}
        aria-describedby={describedBy(id, hint, meta.error)}
        className={cn(meta.error && "border-2 border-danger")}
        onChange={(event) => {
          const raw = event.target.value.trim();
          const parsed = Number(raw);
          onChange(raw === "" || !Number.isFinite(parsed) ? null : Math.trunc(parsed));
        }}
      />
    </FieldFrame>
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectFieldProps extends FieldBase {
  value: string;
  options: readonly SelectOption[];
  onChange: (value: string) => void;
  /** Adds an empty first option with this label. */
  emptyLabel?: string;
}

export function SelectField(props: SelectFieldProps) {
  const { label, path, altPath, hint, className, value, options, onChange, emptyLabel } = props;
  const id = useId();
  const meta = useFieldMeta(path, altPath);
  return (
    <FieldFrame
      id={id}
      label={label}
      hint={hint}
      error={meta.error}
      warnings={meta.warnings}
      className={className}
    >
      <select
        id={id}
        value={value}
        disabled={meta.readOnly}
        aria-invalid={meta.error ? true : undefined}
        aria-describedby={describedBy(id, hint, meta.error)}
        className={cn(selectClass, meta.error && "border-2 border-danger")}
        onChange={(event) => onChange(event.target.value)}
      >
        {emptyLabel !== undefined ? <option value="">{emptyLabel}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldFrame>
  );
}

interface ToggleFieldProps extends FieldBase {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function ToggleField(props: ToggleFieldProps) {
  const { label, path, altPath, hint, className, checked, onChange } = props;
  const id = useId();
  const meta = useFieldMeta(path, altPath);
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id}>{label}</Label>
        <Switch
          id={id}
          checked={checked}
          disabled={meta.readOnly}
          aria-describedby={describedBy(id, hint, meta.error)}
          onCheckedChange={onChange}
        />
      </div>
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {meta.error ? (
        <p id={`${id}-error`} role="alert" className="flex items-start gap-1.5 text-xs text-danger">
          <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{meta.error}</span>
        </p>
      ) : null}
    </div>
  );
}
