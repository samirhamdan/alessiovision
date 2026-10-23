import type { SelectHTMLAttributes } from "react";

import { cx } from "./cx";

export type SelectOption = { value: string; label: string };

export type SelectFieldProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> & {
  /** Obrigatório: liga rótulo, dica e erro ao campo. */
  id: string;
  label: string;
  options: SelectOption[];
  hint?: string;
  error?: string;
};

export function SelectField({ id, label, options, hint, error, className, ...props }: SelectFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={cx("av-field", className)}>
      <label className="av-field__label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="av-field__input av-field__select"
        aria-invalid={error ? true : undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint && (
        <p id={hintId} className="av-field__hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="av-field__error">
          {error}
        </p>
      )}
    </div>
  );
}
