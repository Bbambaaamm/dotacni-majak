import { RelevanceFeedback } from "../components/RelevanceFeedback";
import { StatusBadge } from "../components/StatusBadge";
import "./results.css";

export function GrantDetailPage() {
  return (
    <article className="detail-page">
      <a href="/hledat" className="back-link">← Zpět na výsledky</a>
      <header className="detail-hero">
        <StatusBadge kind="info" label="Testovací historický záznam" />
        <p className="eyebrow">Národní sportovní agentura</p>
        <h1>Regiony 2026 — investice pod 10 mil. Kč</h1>
        <p className="results-lead">
          Výzva je tematicky relevantní k rekonstrukci tenisových kurtů.
          To samo o sobě neznamená, že splňujete všechny podmínky.
        </p>
      </header>

      <section className="next-action" aria-labelledby="detail-next">
        <div>
          <p className="eyebrow">Co udělat teď</p>
          <h2 id="detail-next">Ověřte vlastnictví nebo dlouhodobý vztah k areálu.</h2>
          <p>Bez tohoto údaje zatím nemůžeme bezpečně dokončit vyhodnocení způsobilosti.</p>
        </div>
        <button className="button button--primary" type="button">Doplnit údaj</button>
      </section>

      <div className="detail-layout">
        <div>
          <section className="detail-section">
            <h2>Proč tato možnost odpovídá</h2>
            <ul className="reason-list">
              <li><StatusBadge kind="success" label="Technické zhodnocení sportovní infrastruktury" /></li>
              <li><StatusBadge kind="success" label="Projekt je investičního charakteru" /></li>
              <li><StatusBadge kind="unknown" label="Vztah k místu realizace ještě neznáme" /></li>
            </ul>
          </section>

          <section className="detail-section">
            <h2>Finance</h2>
            <p>
              Přesný výpočet vlastních prostředků zobrazíme až po načtení
              ověřeného funding scenario a způsobilých nákladů.
            </p>
            <StatusBadge kind="unknown" label="Výpočet zatím není kompletní" />
          </section>

          <section className="detail-section">
            <h2>Podmínky</h2>
            <p>Známé podmínky jsou zobrazené jednotlivě. UNKNOWN nikdy nepovažujeme za splněno ani nesplněno.</p>
          </section>
        </div>

        <aside className="evidence-card" aria-labelledby="source-title">
          <h2 id="source-title">Oficiální zdroj</h2>
          <p><strong>Národní sportovní agentura</strong></p>
          <p>Zdrojový detail a dokumenty budou propojeny s konkrétní verzí a evidence záznamem.</p>
          <a href="https://nsa.gov.cz/dotace-investicni/" rel="noreferrer" target="_blank">
            Otevřít oficiální zdroj ↗
          </a>
          <p className="fine-print">
            Dotační maják není poskytovatelem podpory. Rozhodující jsou oficiální podmínky poskytovatele.
          </p>
        </aside>
      </div>

      <RelevanceFeedback
        grantCallVersionId="fixture:nsa-regiony-2026:v1"
        matcherVersion="hybrid-v1"
      />

      <div className="sticky-action">
        <button className="button button--primary" type="button">Chci tuto dotaci</button>
        <button className="button button--secondary" type="button">Sledovat</button>
      </div>
    </article>
  );
}
