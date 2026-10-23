import type { ReactNode } from "react";

import { Logo, type LogoSources } from "./Logo";

export type AppHeaderProps = {
  /** Nome da área atual, ao lado do logo. */
  section?: string;
  /** Conteúdo à direita: estado de atualização, usuário, ações. */
  aside?: ReactNode;
  logoSources?: LogoSources;
};

export function AppHeader({ section, aside, logoSources }: AppHeaderProps) {
  return (
    <header className="av-app-header">
      <div className="av-app-header__brand">
        <Logo variant="horizontal" height={36} sources={logoSources} />
        {section && <span className="av-app-header__section text-heading">{section}</span>}
      </div>
      {aside && <div className="av-app-header__aside text-small">{aside}</div>}
    </header>
  );
}
