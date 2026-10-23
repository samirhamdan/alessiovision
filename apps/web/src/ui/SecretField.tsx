import { useState } from "react";

export type SecretFieldProps = {
  label: string;
  /** Código, link ou comando exibido uma única vez. */
  value: string;
  /** O que fazer com o valor e quando ele expira. */
  hint?: string;
};

export function SecretField({ label, value, hint }: SecretFieldProps) {
  const [copied, setCopied] = useState<"idle" | "ok" | "fail">("idle");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied("ok");
    } catch {
      setCopied("fail");
    }
  };

  return (
    <div className="av-secret">
      <p className="av-field__label">{label}</p>
      <div className="av-secret__row">
        <code className="av-secret__value text-data">{value}</code>
        <button type="button" className="av-button av-button--secondary av-button--sm" onClick={copy}>
          {copied === "ok" ? "Copiado" : "Copiar"}
        </button>
      </div>
      <p className="av-field__hint" aria-live="polite">
        {copied === "fail" ? "Não foi possível copiar. Selecione o texto e copie manualmente." : hint}
      </p>
    </div>
  );
}
