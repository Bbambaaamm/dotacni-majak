import "./suggest-source.css";

const issueUrl =
  "https://github.com/Bbambaaamm/dotacni-majak/issues/new?template=source-suggestion.yml";

export function SuggestSourcePage() {
  return (
    <article className="suggest-source-page">
      <header className="suggest-source-head">
        <p className="eyebrow">Rozšiřujeme pokrytí transparentně</p>
        <h1>Chybí Majáku dotační zdroj?</h1>
        <p className="results-lead">
          Pošlete nám veřejný odkaz na oficiální dotační portál nebo program.
          Každý návrh nejdřív ručně ověříme. Do Majáku se nic nezařadí
          automaticky jen na základě uživatelského odkazu.
        </p>
      </header>

      <section className="suggest-source-card" aria-labelledby="suggest-how">
        <h2 id="suggest-how">Jak to funguje</h2>
        <ol>
          <li>
            <strong>Navrhnete veřejný zdroj.</strong>
            <span>Název a URL stačí pro první kontrolu.</span>
          </li>
          <li>
            <strong>Ověříme autoritu a bezpečný přístup.</strong>
            <span>
              Preferujeme oficiální API a otevřená data; neobcházíme přihlášení,
              CAPTCHA ani technické ochrany.
            </span>
          </li>
          <li>
            <strong>Teprve potom vznikne connector.</strong>
            <span>
              Nový zdroj musí mít fixtures, contract testy, healthcheck,
              provenance a bezpečné chování při výpadku.
            </span>
          </li>
        </ol>

        <a
          className="button button--primary button-link"
          href={issueUrl}
          rel="noreferrer"
        >
          Navrhnout zdroj na GitHubu
        </a>
        <p className="suggest-source-note">
          GitHub vyžaduje účet. Do formuláře nevkládejte osobní údaje,
          přihlašovací údaje ani neveřejné dokumenty.
        </p>
      </section>

      <section className="suggest-source-principle" aria-labelledby="source-safety">
        <h2 id="source-safety">Návrh není automatické schválení</h2>
        <p>
          Uživatelé mohou pomoci najít chybějící zdroje, ale status
          <strong> oficiální zdroj</strong> vznikne až po kontrole poskytovatele,
          veřejné dostupnosti a retrieval metody. Tím chráníme uživatele před
          podvrženými odkazy a neověřenými dotačními podmínkami.
        </p>
        <p>
          <a href="/pokryti">Zobrazit současné pokrytí Majáku</a>
        </p>
      </section>
    </article>
  );
}
