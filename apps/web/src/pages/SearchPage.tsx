import { useEffect, useState } from "react";

import { RelevanceFeedback } from "../components/RelevanceFeedback";
import { ResultStatePanel } from "../components/ResultStatePanel";
import { StatusBadge } from "../components/StatusBadge";
import { parseDemoResultState, resultStateContent } from "../lib/resultState";
import { readIntentFromSearch } from "../lib/intent";
import {
  searchErrorMessage,
  searchGrants,
  type GrantSearchResponse,
} from "../lib/searchApi";
import "./results.css";

function statusLabel(status: string): string {
  switch (status) {
    case "OPEN":
      return "Lze podat žádost";
    case "PLANNED":
      return "Plánovaná výzva";
    case "ANNOUNCED":
      return "Vyhlášená výzva";
    default:
      return status;
  }
}

function dateLabel(value: string | null): string {
  if (!value) return "Není uvedeno";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("cs-CZ", {
    day: "numeric",
    month: "numeric",
    year: "numeric",
  }).format(parsed);
}

export function SearchPage() {
  const params = new URLSearchParams(window.location.search);
  const intent = readIntentFromSearch(window.location.search);
  const demoState = parseDemoResultState(params.get("demoState"));
  const [data, setData] = useState<GrantSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(intent && !demoState));
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [providerFilter, setProviderFilter] = useState("ALL");
  const [deadlineFilter, setDeadlineFilter] = useState("ALL");
  const [sortOrder, setSortOrder] = useState("RELEVANCE");

  const loadedResults = data?.results ?? [];
  const statusOptions = [...new Set(loadedResults.map((grant) => grant.status))].sort();
  const providerOptions = [
    ...new Set(loadedResults.map((grant) => grant.providerName)),
  ].sort((a, b) => a.localeCompare(b, "cs-CZ"));
  const filteredResults = loadedResults.filter(
    (grant) =>
      (statusFilter === "ALL" || grant.status === statusFilter) &&
      (providerFilter === "ALL" || grant.providerName === providerFilter) &&
      (deadlineFilter === "ALL" ||
        (deadlineFilter === "KNOWN" ? grant.submissionCloseAt !== null : grant.submissionCloseAt === null)),
  ).sort((a, b) => {
    if (sortOrder === "RELEVANCE") return 0;
    if (!a.submissionCloseAt) return b.submissionCloseAt ? 1 : 0;
    if (!b.submissionCloseAt) return -1;
    const difference = Date.parse(a.submissionCloseAt) - Date.parse(b.submissionCloseAt);
    return sortOrder === "DEADLINE_LATEST" ? -difference : difference;
  });
  const activeFilters = [
    statusFilter !== "ALL" ? { key: "status", label: `Stav: ${statusLabel(statusFilter)}`, clear: () => setStatusFilter("ALL") } : null,
    providerFilter !== "ALL" ? { key: "provider", label: `Poskytovatel: ${providerFilter}`, clear: () => setProviderFilter("ALL") } : null,
    deadlineFilter !== "ALL" ? { key: "deadline", label: deadlineFilter === "KNOWN" ? "Termín: uveden" : "Termín: neuveden", clear: () => setDeadlineFilter("ALL") } : null,
  ].filter((item): item is { key: string; label: string; clear: () => void } => item !== null);

  useEffect(() => {
    if (!intent || demoState) return;

    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setStatusFilter("ALL");
    setProviderFilter("ALL");
    setDeadlineFilter("ALL");
    setSortOrder("RELEVANCE");

    searchGrants(intent, controller.signal)
      .then((result) => {
        setData(result);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(searchErrorMessage(reason));
        setLoading(false);
      });

    return () => controller.abort();
  }, [intent, demoState]);

  if (demoState) {
    return (
      <div className="results-page">
        <header className="results-head">
          <p className="eyebrow">QA režim výsledků</p>
          <h1>{intent || "Testovací scénář výsledků"}</h1>
          <p className="results-lead">
            QA stav je zobrazen pouze kvůli explicitnímu parametru
            <code> demoState</code>. Nejde o běžný výsledek vyhledávání.
          </p>
        </header>
        <ResultStatePanel state={resultStateContent(demoState)} />
      </div>
    );
  }

  if (!intent) {
    return (
      <div className="results-page">
        <header className="results-head">
          <p className="eyebrow">Najít dotaci</p>
          <h1>Co chcete uskutečnit?</h1>
          <p className="results-lead">
            Začněte popisem záměru. Nemusíte znát název programu ani dotační
            terminologii.
          </p>
        </header>
        <a className="button button--primary button-link" href="/">
          Zadat záměr
        </a>
      </div>
    );
  }

  return (
    <div className="results-page">
      <header className="results-head">
        <p className="eyebrow">Výsledky pro váš záměr</p>
        <h1>{intent}</h1>
        <p className="results-lead">
          Hledáme v indexovaných dotačních výzvách a používáme také širší pojmy
          z dotační ontologie. Relevance není totéž co způsobilost.
        </p>
      </header>

      {loading ? (
        <section className="next-action" aria-live="polite">
          <div>
            <p className="eyebrow">Vyhledáváme</p>
            <h2>Porovnáváme váš záměr s dostupnými výzvami.</h2>
            <p>Výsledek nebude doplněn žádnými modelovými nebo vymyšlenými daty.</p>
          </div>
        </section>
      ) : null}

      {error ? (
        <section className="next-action" role="alert">
          <div>
            <p className="eyebrow">Vyhledávání není dostupné</p>
            <h2>Výsledky teď neumíme bezpečně zobrazit.</h2>
            <p>{error}</p>
          </div>
          <a className="button button--secondary button-link" href="/">
            Upravit záměr
          </a>
        </section>
      ) : null}

      {!loading && !error && data?.indexState === "EMPTY" ? (
        <section className="next-action" role="status">
          <div>
            <p className="eyebrow">Lokální index je prázdný</p>
            <h2>Vyhledávání je zapojené, ale databáze zatím nemá dotační data.</h2>
            <p>
              To není skutečný výsledek „žádná dotace“. Nejdřív musí proběhnout
              ingestion oficiálních zdrojů do lokálního D1 indexu.
            </p>
          </div>
          <a className="button button--secondary button-link" href="/pokryti">
            Zobrazit pokrytí zdrojů
          </a>
        </section>
      ) : null}

      {!loading &&
      !error &&
      data?.indexState === "READY" &&
      data.results.length === 0 ? (
        <ResultStatePanel
          state={{
            ...resultStateContent("NO_RESULTS"),
            primaryHref: `/projekty?intent=${encodeURIComponent(intent)}&watch=1`,
          }}
        />
      ) : null}

      {!loading && !error && data?.indexState === "READY" && data.results.length > 0 ? (
        <section aria-labelledby="results-title">
          <div className="section-heading">
            <div>
              <h2 id="results-title">Nalezené možnosti</h2>
              <p>
                {filteredResults.length === data.results.length
                  ? `${data.results.length} výsledků.`
                  : `${filteredResults.length} z ${data.results.length} výsledků.`}{" "}
                Toto jsou pouze právě načtené výsledky (nejvýše 20), nikoli počet všech odpovídajících výzev.
                Filtry a řazení se vztahují pouze na tuto sadu. Způsobilost a financování se
                vyhodnocují odděleně a nejsou zde doplňovány odhadem.
              </p>
            </div>
            <a
              className="button button--secondary button-link"
              href={`/projekty?intent=${encodeURIComponent(intent)}&watch=1`}
            >
              Pohlídat tento záměr
            </a>
          </div>

          <details className="filter-panel" open>
            <summary>Upravit filtry a řazení</summary>
            <div className="result-filters" aria-label="Filtrovat načtené výsledky">
            <label>
              Stav výzvy
              <select
                aria-label="Stav výzvy"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="ALL">Všechny stavy ({data.results.length})</option>
                {statusOptions.map((status) => (
                  <option key={status} value={status}>
                    {statusLabel(status)} ({data.results.filter((grant) => grant.status === status).length})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Poskytovatel
              <select
                aria-label="Poskytovatel"
                value={providerFilter}
                onChange={(event) => setProviderFilter(event.target.value)}
              >
                <option value="ALL">Všichni poskytovatelé ({data.results.length})</option>
                {providerOptions.map((provider) => (
                  <option key={provider} value={provider}>
                    {provider} ({data.results.filter((grant) => grant.providerName === provider).length})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Termín podání
              <select aria-label="Termín podání" value={deadlineFilter}
                onChange={(event) => setDeadlineFilter(event.target.value)}>
                <option value="ALL">Všechny termíny</option>
                <option value="KNOWN">Termín uveden</option>
                <option value="UNKNOWN">Termín neuveden (UNKNOWN)</option>
              </select>
            </label>
            <label>
              Řazení načtených výsledků
              <select aria-label="Řazení načtených výsledků" value={sortOrder}
                onChange={(event) => setSortOrder(event.target.value)}>
                <option value="RELEVANCE">Původní pořadí relevance</option>
                <option value="DEADLINE">Nejbližší uvedený termín</option>
                <option value="DEADLINE_LATEST">Nejpozdější uvedený termín</option>
              </select>
            </label>
            <p className="fine-print">Termín bez uvedeného data není považován za prošlý ani za otevřený.</p>
            </div>
          </details>
          {activeFilters.length > 0 ? (
            <div className="active-filters" aria-label="Aktivní filtry">
              {activeFilters.map((filter) => (
                <button key={filter.key} type="button" className="filter-chip"
                  onClick={filter.clear} aria-label={`Zrušit filtr ${filter.label}`}>
                  {filter.label} ×
                </button>
              ))}
              <button type="button" className="filter-reset" onClick={() => {
                setStatusFilter("ALL");
                setProviderFilter("ALL");
                setDeadlineFilter("ALL");
              }}>Zrušit všechny filtry</button>
            </div>
          ) : null}

          {filteredResults.length === 0 ? (
            <p className="filter-empty" role="status">
              Tomuto filtru neodpovídá žádný z načtených výsledků.
            </p>
          ) : null}

          <div className="results-list">
            {filteredResults.map((grant) => (
              <article className="grant-card" key={grant.grantCallVersionId}>
                <div className="grant-card__top">
                  <div>
                    <StatusBadge kind="info" label={statusLabel(grant.status)} />
                    <h3>{grant.title}</h3>
                    <p>{grant.providerName}</p>
                  </div>
                  <span className="match-label">
                    {grant.matchKind === "DIRECT"
                      ? "Přímá tematická shoda"
                      : "Nalezeno přes širší význam"}
                  </span>
                </div>

                {grant.summary ? (
                  <p className="results-lead">{grant.summary}</p>
                ) : null}

                <div className="grant-grid">
                  <section>
                    <h4>Proč ji vidíte</h4>
                    <ul className="reason-list">
                      <li>
                        <StatusBadge
                          kind="success"
                          label={
                            grant.matchKind === "DIRECT"
                              ? "Text výzvy odpovídá slovům vašeho záměru"
                              : "Výzva odpovídá širším pojmům odvozeným z vašeho záměru"
                          }
                        />
                      </li>
                      <li>
                        <StatusBadge
                          kind="unknown"
                          label="Způsobilost konkrétního žadatele zatím není v tomto výsledku vyhodnocena"
                        />
                      </li>
                    </ul>
                  </section>

                  <section className="facts">
                    <h4>Rychlý přehled</h4>
                    <dl>
                      <div>
                        <dt>Stav</dt>
                        <dd>{statusLabel(grant.status)}</dd>
                      </div>
                      <div>
                        <dt>Termín podání</dt>
                        <dd>{dateLabel(grant.submissionCloseAt)}</dd>
                      </div>
                      <div>
                        <dt>Poskytovatel</dt>
                        <dd>{grant.providerName}</dd>
                      </div>
                    </dl>
                  </section>
                </div>

                <div className="grant-card__actions">
                  <a
                    className="button button--primary button-link"
                    href={`/dotace/${encodeURIComponent(grant.grantCallId)}`}
                  >
                    Zobrazit detail
                  </a>
                  {grant.officialDetailUrl ? (
                    <a
                      className="button button--secondary button-link"
                      href={grant.officialDetailUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Oficiální zdroj ↗
                    </a>
                  ) : null}
                </div>

                <RelevanceFeedback
                  grantCallVersionId={grant.grantCallVersionId}
                  matcherVersion="fts-ontology-v1"
                />
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {data?.expandedTerms.length ? (
        <details className="detail-section">
          <summary>Jaké širší pojmy Maják použil?</summary>
          <p>{data.expandedTerms.join(" · ")}</p>
        </details>
      ) : null}
    </div>
  );
}
