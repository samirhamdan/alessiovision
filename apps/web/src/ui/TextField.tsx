import type { InputHTMLAttributes } from "react";

import { cx } from "./cx";

export type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  /** Obrigatório: liga rótulo, dica e erro ao campo. */
  id: string;
  label: string;
  hint?: string;
  /** Mensagem que explica o problema e como corrigir. Marca o campo como inválido. */
  error?: string;
};

export function TextField({ id, label, hint, error, className, ...props }: TextFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={cx("av-field", className)}>
      <label className="av-field__label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="av-field__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
        {...props}
      />
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
