import type { ReactNode } from "react";

export type BadgeTone = "ok" | "warn" | "danger" | "neutral" | "accent";

export type BadgeProps = {
  /** A cor reforça o texto; o texto sozinho precisa dizer o estado. */
  tone?: BadgeTone;
  children: ReactNode;
};

export function Badge({ tone = "neutral", children }: BadgeProps) {
  return <span className={`av-badge av-badge--${tone}`}>{children}</span>;
}
