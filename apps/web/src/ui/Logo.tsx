export type LogoSources = { light: string; dark: string };

export type LogoProps = {
  /** horizontal: cabeçalhos. mark: espaços quadrados (ícone de app, avatar do sistema). */
  variant?: "horizontal" | "mark";
  /** Altura em px; a largura acompanha a proporção do arquivo. */
  height?: number;
  /** Arquivos para fundo claro e escuro. Padrão: /brand/ do painel. */
  sources?: LogoSources;
};

const DEFAULT_SOURCES: Record<"horizontal" | "mark", LogoSources> = {
  horizontal: {
    light: "/brand/alessio-vision-horizontal.png",
    dark: "/brand/alessio-vision-horizontal-on-dark.png",
  },
  mark: {
    light: "/brand/alessio-vision-mark.png",
    dark: "/brand/alessio-vision-mark-on-dark.png",
  },
};

export function Logo({ variant = "horizontal", height = 32, sources }: LogoProps) {
  const files = sources ?? DEFAULT_SOURCES[variant];
  // As duas versões são renderizadas e o CSS mostra a do tema ativo; só uma é anunciada.
  return (
    <span className={`av-logo av-logo--${variant}`} style={{ height }}>
      <img className="av-logo__light" src={files.light} alt="Alessio Vision" height={height} />
      <img className="av-logo__dark" src={files.dark} alt="" aria-hidden="true" height={height} />
    </span>
  );
}
