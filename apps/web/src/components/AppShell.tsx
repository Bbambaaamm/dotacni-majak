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

      <main id="main-content" className="shell main-content" tabIndex={-1}>
        {children}
      </main>

      <footer className="site-footer">
        <div className="shell site-footer__grid">
          <div>
            <strong>Dotační maják</strong>
            <p>Najde. Pohlídá. Dotáhne.</p>
          </div>
          <nav aria-label="Informace o projektu">
            <a href="/jak-to-funguje">Jak to funguje</a>
            <a href="/pokryti">Pokrytí Majáku</a>
            <a href="https://github.com/Bbambaaamm/dotacni-majak">GitHub</a>
          </nav>
          <p className="site-footer__legal">
            Dotační maják není poskytovatelem dotací. Rozhodující jsou vždy
            oficiální podmínky příslušného poskytovatele.
          </p>
        </div>
      </footer>
    </>
  );
}
