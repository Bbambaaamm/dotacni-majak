import {
  buildGrantComparison,
  type ComparisonGrant,
  type EligibilityState,
} from "../lib/comparison";
import { StatusBadge } from "../components/StatusBadge";
import "./comparison.css";

const demoGrants: readonly ComparisonGrant[] = [
  {
    id: "regiony-2026",
    title: "Regiony 2026 — investice pod 10 mil. Kč",
    provider: "Národní sportovní agentura",
    statusLabel: "Historický testovací záznam",
    eligibility: "NEEDS_INFORMATION",
    eligibilityLabel: "Potřebujeme ověřit vztah k nemovitosti",
    deadlineLabel: "Podání skončilo",
    supportLabel: "Načte ověřený funding scenario",
    ownFundsLabel: "Výpočet zatím není kompletní",
    requiredItemsCount: null,
    unknownItemsCount: 1,
    sourceLabel: "Oficiální NSA",
    sourceVerifiedAtLabel: "testovací fixture",
    detailHref: "/dotace/regiony-2026",
  },
  {
    id: "demo-sport-a",
    title: "Ukázková sportovní výzva A",
    provider: "Syntetický UX fixture",
    statusLabel: "Ukázková data",
    eligibility: "ELIGIBLE",
    eligibilityLabel: "Známé testovací podmínky splněny",
    deadlineLabel: "Ukázkový termín",
    supportLabel: "Ukázková hodnota",
    ownFundsLabel: "Ukázková hodnota",
    requiredItemsCount: 6,
    unknownItemsCount: 0,
    sourceLabel: "Syntetický fixture",
    sourceVerifiedAtLabel: "není skutečná výzva",
    detailHref: "/hledat",
  },
];

const model = buildGrantComparison(demoGrants);

function eligibilityKind(
  state: EligibilityState,
): "success" | "error" | "unknown" | "warning" {
  switch (state) {
    case "ELIGIBLE":
    case "LIKELY_ELIGIBLE":
      return "success";
    case "INELIGIBLE":
      return "error";
    case "NEEDS_REVIEW":
      return "warning";
    case "NEEDS_INFORMATION":
      return "unknown";
  }
}

export function ComparePage() {
  return (
    <div className="compare-page">
      <header className="compare-head">
        <p className="eyebrow">Porovnání možností</p>
        <h1>Porovnejte fakta. Rozhodnutí zůstává na vás.</h1>
        <p className="results-lead">
          Maják nevybírá automatického vítěze. Vedle sebe ukazuje způsobilost,
          finance, termíny, neznámé údaje a stáří zdroje.
        </p>
        <StatusBadge
          kind="warning"
          label="Tato obrazovka zatím používá testovací UX fixture, ne živé rozhodnutí."
        />
      </header>

      <div className="comparison-desktop">
        <table className="comparison-table">
          <caption>
            Faktické porovnání {model.grants.length} dotačních možností
          </caption>
          <thead>
            <tr>
              <th scope="col">Parametr</th>
              {model.grants.map((grant) => (
                <th scope="col" key={grant.id}>
                  <span className="comparison-provider">{grant.provider}</span>
                  <strong>{grant.title}</strong>
                  <StatusBadge
                    kind={eligibilityKind(grant.eligibility)}
                    label={grant.eligibilityLabel}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {model.rows.map((row) => (
              <tr key={row.key}>
                <th scope="row">{row.label}</th>
                {row.values.map((value, index) => (
                  <td key={model.grants[index]?.id}>{value}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="comparison-mobile" aria-label="Porovnání po položkách">
        {model.rows.map((row) => (
          <section className="comparison-mobile__row" key={row.key}>
            <h2>{row.label}</h2>
            <dl>
              {model.grants.map((grant, index) => (
                <div key={grant.id}>
                  <dt>{grant.title}</dt>
                  <dd>{row.values[index]}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>

      <section className="next-action" aria-labelledby="comparison-next">
        <div>
          <p className="eyebrow">Co udělat teď</p>
          <h2 id="comparison-next">
            Otevřete detail výzvy, která stojí za další ověření.
          </h2>
          <p>
            Než se rozhodnete, zkontrolujte chybějící informace a původní
            oficiální zdroj. Vyšší podpora sama o sobě neznamená lepší volbu.
          </p>
        </div>
        <a
          className="button button--primary button-link"
          href={model.grants[0]?.detailHref}
        >
          Otevřít detail
        </a>
      </section>
    </div>
  );
}
