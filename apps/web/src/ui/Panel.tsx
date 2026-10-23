import { type ReactNode, useId } from "react";

export type PanelProps = {
  title?: string;
  /** Texto curto ao lado do título, por exemplo uma contagem. */
  meta?: ReactNode;
  /** Botões alinhados à direita do título. */
  actions?: ReactNode;
  children: ReactNode;
};

export function Panel({ title, meta, actions, children }: PanelProps) {
  const titleId = useId();
  return (
    <section className="av-panel" aria-labelledby={title ? titleId : undefined}>
      {(title || actions) && (
        <header className="av-panel__header">
          {title && (
            <h2 id={titleId} className="av-panel__title text-heading">
              {title}
              {meta && <span className="av-panel__meta text-small">{meta}</span>}
            </h2>
          )}
          {actions && <div className="av-panel__actions">{actions}</div>}
        </header>
      )}
      <div className="av-panel__body">{children}</div>
    </section>
  );
}
