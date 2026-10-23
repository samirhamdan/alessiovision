import type { MouseEvent } from "react";

export type NavItem = { href: string; label: string };

export type NavTabsProps = {
  items: NavItem[];
  /** href do item atual. */
  current: string;
  /** Navegação sem recarregar a página; sem ela, os links funcionam normalmente. */
  onNavigate?: (href: string) => void;
};

export function NavTabs({ items, current, onNavigate }: NavTabsProps) {
  const handle = (event: MouseEvent<HTMLAnchorElement>, href: string) => {
    if (!onNavigate || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onNavigate(href);
  };
  return (
    <nav className="av-nav" aria-label="Seções">
      {items.map((item) => (
        <a
          key={item.href}
          href={item.href}
          className="av-nav__item"
          aria-current={item.href === current ? "page" : undefined}
          onClick={(event) => handle(event, item.href)}
        >
          {item.label}
        </a>
      ))}
    </nav>
  );
}
