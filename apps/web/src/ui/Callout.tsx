import type { ReactNode } from "react";

export type CalloutProps = {
  /** danger: erro que impede seguir. ok: confirmação. neutral: informação. */
  tone?: "danger" | "ok" | "neutral";
  title?: string;
  children: ReactNode;
};

export function Callout({ tone = "neutral", title, children }: CalloutProps) {
  return (
    <div className={`av-callout av-callout--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {title && <p className="av-callout__title">{title}</p>}
      <div className="av-callout__body">{children}</div>
    </div>
  );
}
