import { StatusBadge } from "../components/StatusBadge";
import "./results.css";

const reasons = [
  ["success", "Podporuje technické zhodnocení sportovní infrastruktury"],
  ["success", "Sportovní spolek patří mezi podporované žadatele"],
  ["success", "Rozpočet 4 mil. Kč odpovídá známým limitům"],
  ["unknown", "Potřebujeme ověřit vztah k nemovitosti"],
] as const;

export function SearchPage() {
  return (
    <div className="results-page">
      <header className="results-head">
        <p className="eyebrow">Výsledky pro váš záměr</p>
        <h1>Rekonstrukce tenisových kurtů</h1>
        <p className="results-lead">
          Hledáme podle významu projektu, ne pouze podle slov „tenisový kurt“.
          Relevance, způsobilost a financování hodnotíme odděleně.
        </p>
      </header>

      <section aria-labelledby="next-question" className="next-action">
        <div>
          <p className="eyebrow">Co udělat teď</p>
          <h2 id="next-question">Doplňte vztah k tenisovému areálu.</h2>
          <p>Tato odpověď může změnit způsobilost u několika nalezených možností.</p>
        </div>
        <button className="button button--primary" type="button">Doplnit údaj</button>
      </section>

      <section aria-labelledby="results-title">
        <div className="section-heading">
          <div>
            <h2 id="results-title">Nalezené možnosti</h2>
            <p>Ukázková karta používá strukturu připravenou pro živá canonical data.</p>
          </div>
          <button className="button button--secondary" type="button">Pohlídat tento záměr</button>
        </div>

        <article className="grant-card">
          <div className="grant-card__top">
            <div>
              <StatusBadge kind="info" label="Podání skončilo — historický testovací záznam" />
              <h3>Regiony 2026 — investice pod 10 mil. Kč</h3>
              <p>Národní sportovní agentura</p>
            </div>
            <span className="match-label">Velmi dobrá tematická shoda</span>
          </div>

          <div className="grant-grid">
            <section>
              <h4>Proč ji vidíte</h4>
              <ul className="reason-list">
                {reasons.map(([kind, text]) => (
                  <li key={text}>
                    <StatusBadge kind={kind} label={text} />
                  </li>
                ))}
              </ul>
            </section>

            <section className="facts">
              <h4>Rychlý přehled</h4>
              <dl>
                <div><dt>Způsobilost</dt><dd>Potřebujeme 1 údaj</dd></div>
                <div><dt>Rozpočet projektu</dt><dd>4 000 000 Kč</dd></div>
                <div><dt>Termín</dt><dd>ověří detail výzvy</dd></div>
                <div><dt>Zdroj</dt><dd>oficiální NSA</dd></div>
              </dl>
            </section>
          </div>

          <div className="grant-card__actions">
            <a className="button button--primary button-link" href="/dotace/regiony-2026">Zobrazit detail</a>
            <button className="button button--secondary" type="button">Sledovat</button>
            <button className="button button--tertiary" type="button">Porovnat</button>
          </div>
        </article>
      </section>
    </div>
  );
}
