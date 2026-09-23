import type { PropsWithChildren } from "react";

import { routes } from "../lib/routes";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Přeskočit na hlavní obsah
      </a>

      <header className="site-header">
        <div className="shell site-header__inner">
          <a className="brand" href="/" aria-label="Dotační maják — domů">
            <span className="brand__mark" aria-hidden="true">◭</span>
            <span>
              <strong>Dotační maják</strong>
              <small>Najde. Pohlídá. Dotáhne.</small>
            </span>
          </a>

          <nav aria-label="Hlavní navigace">
            <ul className="site-nav">
              {routes.map((route) => (
                <li key={route.id}>
                  <a href={route.path}>{route.label}</a>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>

      <main id="main-content" className="shell main-content">
        {children}
      </main>
    </>
  );
}
