import type { ButtonHTMLAttributes } from "react";

import { cx } from "./cx";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** primary: a ação principal da tela (uma por área). danger: ações destrutivas. */
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "md" | "sm";
};

export function Button({ variant = "primary", size = "md", type = "button", className, ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={cx("av-button", `av-button--${variant}`, size === "sm" && "av-button--sm", className)}
      {...props}
    />
  );
}
