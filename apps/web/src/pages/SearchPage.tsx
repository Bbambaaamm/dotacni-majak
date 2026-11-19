import { useCallback, useEffect, useRef, useState } from "react";

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

const STATUS_OPTIONS = ["OPEN", "PLANNED", "ANNOUNCED"] as const;
type StatusFilter = "ALL" | typeof STATUS_OPTIONS[number];

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
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  const moreController = useRef<AbortController | null>(null);
  const filterPanel = useRef<HTMLDetailsElement | null>(null);
  const mobileFiltersOpen = useRef(false);
  const attachFilterPanel = useCallback((node: HTMLDetailsElement | null) => {
    filterPanel.current = node;
    if (node) node.open = window.matchMedia("(min-width: 801px)").matches || mobileFiltersOpen.current;
  }, []);
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 801px)");
    const update = () => {
      mobileFiltersOpen.current = false;
      if (filterPanel.current) filterPanel.current.open = desktop.matches;
    };
    desktop.addEventListener("change", update);
    return () => desktop.removeEventListener("change", update);
  }, []);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [providerFilter, setProviderFilter] = useState("");
  const [providerDraft, setProviderDraft] = useState("");
  const [deadlineFilter, setDeadlineFilter] = useState<"ALL" | "KNOWN" | "UNKNOWN">("ALL");
  const [closesBy, setClosesBy] = useState("");
  const [closesByDraft, setClosesByDraft] = useState("");
  const [closesFrom, setClosesFrom] = useState("");
  const [closesFromDraft, setClosesFromDraft] = useState("");
  const [sortOrder, setSortOrder] = useState<"RELEVANCE" | "DEADLINE" | "DEADLINE_LATEST">("RELEVANCE");

  const loadedResults = data?.results ?? [];
  const providerOptions = data?.facets?.providers ?? [];
  const filteredResults = loadedResults;
  function changeSort(next: "RELEVANCE" | "DEADLINE" | "DEADLINE_LATEST") {
    if (next === sortOrder) return;
    moreController.current?.abort();
    setData(null);
    setLoading(true);
    setSortOrder(next);
  }
  function changeStatus(next: StatusFilter) {
    moreController.current?.abort();
    setData(null);
    setLoading(true);
    setProviderFilter("");
    setProviderDraft("");
    setSortOrder("RELEVANCE");
    setStatusFilter(next);
  }
  function changeDeadline(next: "ALL" | "KNOWN" | "UNKNOWN") {
    moreController.current?.abort();
    setData(null);
    setLoading(true);
    setProviderFilter("");
    setProviderDraft("");
    setSortOrder("RELEVANCE");
    if (next === "UNKNOWN") {
      setClosesBy("");
      setClosesByDraft("");
      setClosesFrom("");
      setClosesFromDraft("");
    }
    setDeadlineFilter(next);
  }
  function changeClosesBy(next: string) {
    if (next === closesBy) return;
    moreController.current?.abort();
    setData(null);
    setLoading(true);
    setClosesBy(next);
    if (next && deadlineFilter === "UNKNOWN") setDeadlineFilter("ALL");
  }
  function changeClosesFrom(next: string) {
    if (next === closesFrom) return;
    moreController.current?.abort();
    setData(null);
    setLoading(true);
    setClosesFrom(next);
    if (next && deadlineFilter === "UNKNOWN") setDeadlineFilter("ALL");
  }
  function changeProvider(next: string) {
    if (next === providerFilter) return;
    moreController.current?.abort();
    setData(null);
    setLoading(true);
    setSortOrder("RELEVANCE");
    setProviderFilter(next);
  }
  function clearProvider() {
    setProviderDraft("");
    changeProvider("");
  }
  const activeFilters = [
    statusFilter !== "ALL" ? { key: "status", label: `Stav: ${statusLabel(statusFilter)}`, clear: () => changeStatus("ALL") } : null,
    providerFilter ? { key: "provider", label: `Poskytovatel: ${providerFilter}`, clear: clearProvider } : null,
    deadlineFilter !== "ALL" ? { key: "deadline", label: deadlineFilter === "KNOWN" ? "Termín: uveden" : "Termín: neuveden", clear: () => changeDeadline("ALL") } : null,
    closesBy ? { key: "closesBy", label: `Uzávěrka nejpozději: ${closesBy}`, clear: () => { setClosesByDraft(""); changeClosesBy(""); } } : null,
    closesFrom ? { key: "closesFrom", label: `Uzávěrka nejdříve: ${closesFrom}`, clear: () => { setClosesFromDraft(""); changeClosesFrom(""); } } : null,
  ].filter((item): item is { key: string; label: string; clear: () => void } => item !== null);

  useEffect(() => {
    if (!intent || demoState) return;

    const controller = new AbortController();
    moreController.current?.abort();
    setData(null);
    setLoading(true);
    setError(null);
    setLoadingMore(false);
    setMoreError(null);

    searchGrants(intent, controller.signal, undefined, statusFilter === "ALL" ? undefined : statusFilter,
      deadlineFilter === "ALL" ? undefined : deadlineFilter, providerFilter || undefined, closesBy || undefined, sortOrder, closesFrom || undefined)
      .then((result) => {
        if (controller.signal.aborted) return;
        setData(result);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(searchErrorMessage(reason));
        setLoading(false);
      });

    return () => { controller.abort(); moreController.current?.abort(); };
  }, [intent, demoState, statusFilter, deadlineFilter, providerFilter, closesBy, closesFrom, sortOrder]);

  async function loadMore() {
    if (!data?.nextCursor || loadingMore) return;
    const cursor = data.nextCursor;
    const controller = new AbortController();
    moreController.current = controller;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const page = await searchGrants(intent, controller.signal, cursor,
        statusFilter === "ALL" ? undefined : statusFilter,
        deadlineFilter === "ALL" ? undefined : deadlineFilter, providerFilter || undefined, closesBy || undefined, sortOrder, closesFrom || undefined);
      if (controller.signal.aborted) return;
      setData((current) => {
        if (!current || current.nextCursor !== cursor) return current;
        const seen = new Set(current.results.map((grant) => grant.grantCallVersionId));
        return { ...current, nextCursor: page.nextCursor,
          results: [...current.results, ...page.results.filter((grant) => !seen.has(grant.grantCallVersionId))] };
      });
    } catch (reason) {
      if (!controller.signal.aborted) setMoreError(searchErrorMessage(reason));
    } finally {
      if (!controller.signal.aborted) setLoadingMore(false);
    }
  }

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
      data.results.length === 0 && statusFilter === "ALL" && deadlineFilter === "ALL" && !providerFilter && !closesBy && !closesFrom ? (
        <ResultStatePanel
          state={{
            ...resultStateContent("NO_RESULTS"),
            primaryHref: `/projekty?intent=${encodeURIComponent(intent)}&watch=1`,
          }}
        />
      ) : null}

      {!loading && !error && data?.indexState === "READY" && (data.results.length > 0 || statusFilter !== "ALL" || deadlineFilter !== "ALL" || Boolean(providerFilter) || Boolean(closesBy) || Boolean(closesFrom)) ? (
        <section aria-labelledby="results-title">
          <div className="section-heading">
            <div>
              <h2 id="results-title">Nalezené možnosti</h2>
              <p>
                {filteredResults.length === data.results.length
                  ? `${data.results.length} výsledků.`
                  : `${filteredResults.length} z ${data.results.length} výsledků.`}{" "}
                Toto jsou pouze dosud načtené výsledky, nikoli počet všech odpovídajících výzev.
                Stav, dostupnost termínu, uzávěrka nejdříve, uzávěrka nejpozději a přesný název poskytovatele se filtrují napříč všemi odpovídajícími aktivními výzvami.
                Filtry data zahrnují zvolené kalendářní dny (UTC); neznámý termín v nich není zahrnut. Nezaručují, že výzva stále přijímá žádosti.
                Když jsou počty dostupné, nápověda poskytovatelů zahrnuje shody i mimo načtenou stránku. Můžete zadat i jiný přesný název.
                Řazení podle uvedeného termínu platí pro všechny odpovídající výzvy před stránkováním; neznámé termíny zůstávají na konci. Způsobilost a financování se
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

          <details className="filter-panel" ref={attachFilterPanel}
            onToggle={(event) => {
              if (!window.matchMedia("(min-width: 801px)").matches) {
                mobileFiltersOpen.current = event.currentTarget.open;
              }
            }}
            onKeyDown={(event) => {
              if (event.key !== "Escape" || !filterPanel.current?.open ||
                  window.matchMedia("(min-width: 801px)").matches) return;
              event.preventDefault();
              mobileFiltersOpen.current = false;
              filterPanel.current.open = false;
              filterPanel.current.querySelector("summary")?.focus();
            }}>
            <summary>Upravit filtry a řazení</summary>
            <div className="result-filters" aria-label="Filtrovat výsledky">
            {data.facets === null ? <p className="fine-print" role="status">Počty pro filtry nejsou dostupné, protože hledání má příliš mnoho shod. Filtry můžete dál používat.</p> : null}
            <label>
              Stav výzvy
              <select
                aria-label="Stav výzvy"
                value={statusFilter}
                onChange={(event) => changeStatus(event.target.value as StatusFilter)}
              >
                <option value="ALL">Všechny aktivní stavy</option>
                {STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>
                    {statusLabel(status)}{data.facets ? ` (${data.facets.status[status]})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <form onSubmit={(event) => { event.preventDefault(); changeProvider(providerDraft.trim()); }}>
              <label htmlFor="provider-filter">Přesný název poskytovatele</label>
              <input id="provider-filter" type="text" list="search-providers" maxLength={200}
                value={providerDraft} onChange={(event) => setProviderDraft(event.target.value)} />
              <datalist id="search-providers">
                {providerOptions.map((provider) => <option key={provider.name} value={provider.name} />)}
              </datalist>
              <button type="submit">Použít poskytovatele</button>
              <p className="fine-print provider-facet-note">{data.facets
                ? `Dostupní poskytovatelé pro ostatní filtry: ${providerOptions.map((item) => `${item.name} (${item.count})`).join(", ") || "žádní"}.`
                : "Nápověda poskytovatelů není dostupná. Zadejte přesný název ručně."}
                {data.facets?.providersTruncated ? " Zobrazeno prvních 20; další poskytovatelé mohou odpovídat. Zadejte jejich přesný název." : ""}</p>
            </form>
            <label>
              Termín podání
              <select aria-label="Termín podání" value={deadlineFilter}
                onChange={(event) => changeDeadline(event.target.value as "ALL" | "KNOWN" | "UNKNOWN")}>
                <option value="ALL">Všechny termíny</option>
                <option value="KNOWN">Termín uveden{data.facets ? ` (${data.facets.deadline.KNOWN})` : ""}</option>
                <option value="UNKNOWN">Termín neuveden (UNKNOWN){data.facets ? ` (${data.facets.deadline.UNKNOWN})` : ""}</option>
              </select>
            </label>
            <form onSubmit={(event) => { event.preventDefault(); changeClosesBy(closesByDraft); }}>
              <label htmlFor="closes-by-filter">Uzávěrka nejpozději (včetně dne, UTC)</label>
              <input id="closes-by-filter" type="date" value={closesByDraft}
                min={closesFrom || undefined}
                onChange={(event) => setClosesByDraft(event.target.value)} />
              <button type="submit">Použít datum uzávěrky</button>
            </form>
            <form onSubmit={(event) => { event.preventDefault(); changeClosesFrom(closesFromDraft); }}>
              <label htmlFor="closes-from-filter">Uzávěrka nejdříve (včetně dne, UTC)</label>
              <input id="closes-from-filter" type="date" value={closesFromDraft}
                max={closesBy || undefined}
                onChange={(event) => setClosesFromDraft(event.target.value)} />
              <button type="submit">Použít datum od</button>
            </form>
            <label>
              Řazení všech odpovídajících výsledků
              <select aria-label="Řazení všech odpovídajících výsledků" value={sortOrder}
                onChange={(event) => changeSort(event.target.value as "RELEVANCE" | "DEADLINE" | "DEADLINE_LATEST")}>
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
                moreController.current?.abort();
                setData(null);
                setLoading(true);
                setStatusFilter("ALL");
                setProviderFilter("");
                setProviderDraft("");
                setDeadlineFilter("ALL");
                setClosesBy("");
                setClosesByDraft("");
                setClosesFrom("");
                setClosesFromDraft("");
              }}>Zrušit všechny filtry</button>
            </div>
          ) : null}

          {filteredResults.length === 0 ? (
            <p className="filter-empty" role="status">
              Zvoleným filtrům neodpovídá žádná aktivní výzva pro váš záměr. Zkuste jiného poskytovatele nebo zrušte filtry.
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
          <div aria-live="polite" role="status">
            Načteno {data.results.length} výsledků{data.nextCursor ? "; další mohou být dostupné." : "."}
          </div>
          {moreError ? <p role="alert">Další výsledky se nepodařilo načíst. Dosud načtené výsledky zůstávají zobrazené. {moreError}</p> : null}
          {data.nextCursor ? (
            <button className="button button--secondary" type="button" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? "Načítáme další výsledky…" : moreError ? "Zkusit načíst další znovu" : "Načíst další výsledky"}
            </button>
          ) : null}
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
