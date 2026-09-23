import { StatusBadge } from "../components/StatusBadge";
import {
  toPublicSourceCoverage,
  type PublicSourceHealth,
} from "../lib/sourceCoverage";
import "./coverage.css";

const fixture = [
  toPublicSourceCoverage({
    code: "EU_FT",
    name: "EU Funding & Tenders",
    category: "EU",
    status: "HEALTHY",
    lastCheckedLabel: "vývojový fixture",
    lastSuccessLabel: "vývojový fixture",
  }),
  toPublicSourceCoverage({
    code: "DOTACE_EU",
    name: "DotaceEU",
    category: "ČR / EU fondy",
    status: "HEALTHY",
    lastCheckedLabel: "vývojový fixture",
    lastSuccessLabel: "vývojový fixture",
  }),
  toPublicSourceCoverage({
    code: "NSA",
    name: "Národní sportovní agentura",
    category: "ČR",
    status: "HEALTHY",
    lastCheckedLabel: "vývojový fixture",
    lastSuccessLabel: "vývojový fixture",
  }),
  toPublicSourceCoverage({
    code: "STC",
    name: "Středočeský kraj — Příručka středočeských fondů",
    category: "Kraj",
    status: "DEGRADED",
    lastCheckedLabel: "live smoke — GitHub runner timeout",
    lastSuccessLabel: "ověřeno z veřejného oficiálního dokumentu při research",
    limitation:
      "LIMITED — sledujeme programy výslovně uvedené v aktuální oficiální Příručce středočeských fondů. Oficiální web z GitHub runneru timeoutuje; chráněný EDP neobcházíme.",
  }),
  toPublicSourceCoverage({
    code: "JDP",
    name: "Jednotný dotační portál",
    category: "ČR",
    status: "DEGRADED",
    lastCheckedLabel: "retrieval research",
    lastSuccessLabel: null,
    limitation: "Veřejná stabilní retrieval cesta ještě není ověřena.",
  }),
] as const;

function badgeKind(
  status: PublicSourceHealth,
): "success" | "warning" | "error" {
  switch (status) {
    case "HEALTHY":
      return "success";
    case "DEGRADED":
      return "warning";
    case "UNAVAILABLE":
      return "error";
  }
}

export function CoveragePage() {
  return (
    <article className="coverage-page">
      <header className="coverage-head">
        <p className="eyebrow">Transparentní pokrytí</p>
        <h1>Co Maják skutečně sleduje?</h1>
        <p className="results-lead">
          Netvrdíme, že monitorujeme každou existující dotaci. U každého
          zdroje ukazujeme jeho stav, poslední úspěšnou kontrolu a známé
          omezení.
        </p>
        <StatusBadge
          kind="warning"
          label="Tato obrazovka zatím používá vývojový health fixture."
        />
      </header>

      <section aria-labelledby="coverage-list-title">
        <div className="section-heading">
          <div>
            <h2 id="coverage-list-title">Připojené a plánované zdroje</h2>
            <p>
              Produkční verze bude hodnoty číst ze Source Health backendu.
            </p>
          </div>
          <a
            className="button button--secondary button-link"
            href="/navrhnout-zdroj"
          >
            Navrhnout chybějící zdroj
          </a>
        </div>

        <div className="coverage-list">
          {fixture.map((source) => (
            <article className="coverage-card" key={source.code}>
              <div className="coverage-card__head">
                <div>
                  <span className="coverage-card__category">
                    {source.category}
                  </span>
                  <h3>{source.name}</h3>
                </div>
                <StatusBadge
                  kind={badgeKind(source.status)}
                  label={source.statusLabel}
                />
              </div>

              <dl>
                <div>
                  <dt>Poslední kontrola</dt>
                  <dd>{source.lastCheckedLabel}</dd>
                </div>
                <div>
                  <dt>Poslední úspěch</dt>
                  <dd>{source.lastSuccessLabel}</dd>
                </div>
                <div>
                  <dt>Poslední ověřená data</dt>
                  <dd>
                    {source.servesLastKnownGood
                      ? "Ano — dokud zdroj znovu neověříme"
                      : "Aktuální health stav je v pořádku"}
                  </dd>
                </div>
              </dl>

              {source.limitation ? (
                <p className="coverage-card__limitation">
                  <strong>Známé omezení:</strong> {source.limitation}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section className="coverage-principle">
        <h2>Výpadek zdroje není změna dotační výzvy.</h2>
        <p>
          Když se rozbije parser nebo oficiální web, poslední důvěryhodná data
          ponecháme viditelná a zdroj označíme jako omezený nebo nedostupný.
          Samotný výpadek nikdy automaticky nezmění výzvu na uzavřenou či
          zrušenou.
        </p>
      </section>
    </article>
  );
}
