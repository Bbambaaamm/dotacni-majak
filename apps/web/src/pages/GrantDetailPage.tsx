import { useEffect, useMemo, useState } from "react";

import { RelevanceFeedback } from "../components/RelevanceFeedback";
import { StatusBadge } from "../components/StatusBadge";
import {
  fetchGrantDetail,
  type GrantDetailResponse,
  type GrantFundingScenarioDetail,
} from "../lib/grantDetailApi";
import { grantCallIdFromWebPath } from "../lib/routes";
import { allSourcesMissing, sourcePresenceLabel } from "../lib/sourcePresence";
import "./results.css";

function statusLabel(status: string): string {
  switch (status) {
    case "OPEN":
      return "Lze podat žádost";
    case "PLANNED":
      return "Plánovaná výzva";
    case "ANNOUNCED":
      return "Vyhlášená výzva";
    case "PAUSED":
      return "Příjem je pozastaven";
    case "CLOSED":
      return "Příjem žádostí skončil";
    case "CANCELLED":
      return "Výzva byla zrušena";
    default:
      return status;
  }
}

function verificationLabel(status: string): string {
  switch (status) {
    case "VERIFIED":
      return "Ověřeno";
    case "PARTIALLY_VERIFIED":
      return "Částečně ověřeno";
    case "AUTO_EXTRACTED":
      return "Automaticky zpracováno";
    case "NEEDS_REVIEW":
      return "Vyžaduje ověření";
    default:
      return status;
  }
}

function formatDate(value: string | null): string {
  if (!value) return "Není uvedeno";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("cs-CZ", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(parsed);
}

function deadlineLabel(type: string): string {
  switch (type) {
    case "APPLICATION_WINDOW": return "Příjem žádostí (souhrn výzvy)";
    case "APPLICATION_OPEN": return "Zahájení příjmu žádostí";
    case "APPLICATION_CLOSE": return "Ukončení příjmu žádostí";
    case "PROJECT_START": return "Zahájení projektu";
    case "PROJECT_FINISH": return "Dokončení projektu";
    case "DOCUMENT_COMPLETION": return "Doplnění dokumentů";
    case "SUSTAINABILITY_END": return "Konec udržitelnosti";
    default: return "Další termín";
  }
}

// Preserve the source's offset and precision; do not silently turn a
// date-only deadline into a midnight cutoff or reinterpret it locally.
function deadlineTime(value: string | null): string {
  if (!value) return "Není uvedeno";
  return value.replace("T", " ").replace(/Z$/, " UTC");
}

function formatRate(value: number | null): string {
  if (value === null) return "Není uvedeno";
  return new Intl.NumberFormat("cs-CZ", {
    maximumFractionDigits: 2,
  }).format(value / 100) + " %";
}

function formatMinor(value: number | null, currency: string): string {
  if (value === null) return "Není uvedeno";
  try {
    const formatter = new Intl.NumberFormat("cs-CZ", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    });
    const digits = formatter.resolvedOptions().maximumFractionDigits ?? 2;
    return formatter.format(value / (10 ** digits));
  } catch {
    return `${value} ${currency}`;
  }
}

function instrumentLabel(type: GrantFundingScenarioDetail["instrumentType"]): string {
  switch (type) {
    case "GRANT": return "Dotace / příspěvek";
    case "LOAN": return "Úvěr";
    case "GUARANTEE": return "Záruka";
    case "EQUITY": return "Kapitálový nástroj";
    case "MIXED": return "Kombinovaný nástroj";
    case "OTHER": return "Jiný nástroj podpory";
  }
}

function fundingSummary(scenario: GrantFundingScenarioDetail): string {
  const parts: string[] = [];
  if (scenario.supportRateMaxBps !== null) {
    parts.push(`max. ${formatRate(scenario.supportRateMaxBps)}`);
  }
  if (scenario.grantAmountMaxMinor !== null) {
    parts.push(
      `max. ${formatMinor(scenario.grantAmountMaxMinor, scenario.currencyCode)}`,
    );
  }
  return parts.join(" · ") || "Částka nebo míra podpory není v normalizovaných datech uvedena.";
}

function lastSeenLabel(detail: GrantDetailResponse): string {
  const latest = detail.sources
    .map((source) => source.lastSeenAt)
    .filter(Boolean)
    .sort()
    .at(-1);
  return latest ? formatDate(latest) : "Není doložena";
}

export function GrantDetailPage() {
  const grantCallId = useMemo(
    () => grantCallIdFromWebPath(window.location.pathname),
    [],
  );
  const [detail, setDetail] = useState<GrantDetailResponse | null>(null);
  const [loading, setLoading] = useState(Boolean(grantCallId));
  const [error, setError] = useState<string | null>(
    grantCallId ? null : "Neplatná adresa dotační výzvy.",
  );
  const [retry, setRetry] = useState(0);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!grantCallId) return;
    const controller = new AbortController();
    setLoading(true);
    setDetail(null);
    setError(null);
    setNotFound(false);

    fetchGrantDetail(grantCallId, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setDetail(value);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        const status = (
          reason
          && typeof reason === "object"
          && "status" in reason
          && typeof reason.status === "number"
        )
          ? reason.status
          : 0;
        setNotFound(status === 404);
        setError(
          status === 404
            ? "Tuto dotační výzvu jsme v aktuálním indexu nenašli."
            : "Detail výzvy se teď nepodařilo bezpečně načíst.",
        );
        setLoading(false);
      });

    return () => controller.abort();
  }, [grantCallId, retry]);

  if (loading) {
    return (
      <article className="detail-page" aria-live="polite">
        <a href="/hledat" className="back-link">← Zpět na výsledky</a>
        <section className="next-action">
          <div>
            <p className="eyebrow">Načítáme detail</p>
            <h1>Ověřujeme aktuální verzi výzvy a její zdroje.</h1>
          </div>
        </section>
      </article>
    );
  }

  if (error || !detail) {
    return (
      <article className="detail-page">
        <a href="/hledat" className="back-link">← Zpět na výsledky</a>
        <section className="next-action" role="alert">
          <div>
            <p className="eyebrow">Detail není dostupný</p>
            <h1>{error ?? "Tuto výzvu teď neumíme zobrazit."}</h1>
            <p>Neznámý nebo nedostupný údaj nevydáváme za ověřenou skutečnost.</p>
          </div>
          {!notFound && grantCallId ? (
            <button className="button button--primary" type="button" onClick={() => setRetry((count) => count + 1)}>
              Zkusit načíst detail znovu
            </button>
          ) : null}
          <a className="button button--secondary button-link" href="/hledat">
            Zpět na vyhledávání
          </a>
        </section>
      </article>
    );
  }

  const projectHref = `/projekty?intent=${encodeURIComponent(detail.title)}&grantCallId=${encodeURIComponent(detail.grantCallId)}`;
  const nonGrant = detail.fundingInstrumentType !== "GRANT"
    || detail.fundingScenarios.some((scenario) => scenario.instrumentType !== "GRANT");
  const primarySource = detail.officialDetailUrl
    ?? detail.sources[0]?.canonicalUrl
    ?? detail.provider.officialUrl;
  const showSourceCaution = allSourcesMissing(detail.sources);

  return (
    <article className="detail-page">
      <a href="/hledat" className="back-link">← Zpět na výsledky</a>

      <header className="detail-hero">
        <div className="action-row">
          <StatusBadge kind="info" label={statusLabel(detail.status)} />
          <StatusBadge
            kind={detail.verificationStatus === "VERIFIED" ? "success" : "unknown"}
            label={verificationLabel(detail.verificationStatus)}
          />
        </div>
        {showSourceCaution ? (
          <p className="source-presence-caution" role="status">
            <strong>Ověřte dostupnost u poskytovatele.</strong>{" "}
            V žádném zobrazeném zdrojovém záznamu není stav „viděn“.
            {detail.sources.some((source) => source.presenceState === "MISSING_CANDIDATE")
              ? " Některé chybění je zatím předběžné."
              : null}
            {detail.sources.some((source) => source.presenceState === "CONFIRMED_MISSING")
              ? " Potvrzené chybění znamená jen to, že záznam nebyl u zdroje nalezen."
              : null}
            {" "}Chybění u zdroje samo o sobě neznamená zrušení výzvy.
          </p>
        ) : null}
        <p className="eyebrow">{detail.provider.name}</p>
        <h1>{detail.title}</h1>
        {detail.summary ? <p className="results-lead">{detail.summary}</p> : null}
      </header>

      <section className="next-action" aria-labelledby="detail-next">
        <div>
          <p className="eyebrow">Co udělat teď</p>
          <h2 id="detail-next">
            {detail.availability.requirements === "UNKNOWN"
              ? "Uložte výzvu k projektu a ověřte kompletní podmínky v oficiálním zdroji."
              : "Porovnejte známé požadavky s vaším projektem."}
          </h2>
          <p>
            {detail.availability.requirements === "UNKNOWN"
              ? "Maják zatím nemá všechny podmínky této výzvy normalizované. Proto způsobilost neoznačujeme jako splněnou ani nesplněnou."
              : `Máme ${detail.requirements.length} strukturovaných požadavků. Konkrétní způsobilost se vyhodnotí proti profilu žadatele a projektu.`}
          </p>
        </div>
        <a className="button button--primary button-link" href={projectHref}>
          Přidat k projektu
        </a>
      </section>

      <div className="detail-layout">
        <div>
          <section className="detail-section">
            <h2>Rychlý přehled</h2>
            <dl className="facts">
              <div>
                <dt>Program</dt>
                <dd>{detail.programme.name}</dd>
              </div>
              <div>
                <dt>Stav</dt>
                <dd>{statusLabel(detail.status)}</dd>
              </div>
              <div>
                <dt>Zahájení příjmu</dt>
                <dd>{formatDate(detail.submissionOpenAt)}</dd>
              </div>
              <div>
                <dt>Ukončení příjmu</dt>
                <dd>{formatDate(detail.submissionCloseAt)}</dd>
              </div>
              <div>
                <dt>Verze výzvy zachycena</dt>
                <dd>{formatDate(detail.capturedAt)}</dd>
              </div>
              <div>
                <dt>Poslední pozorování záznamu u zdroje</dt>
                <dd>{lastSeenLabel(detail)}</dd>
              </div>
            </dl>
            <p className="fine-print">Pozorování záznamu nepotvrzuje, že podmínky této verze byly znovu ověřeny. Před podáním zkontrolujte oficiální zdroj.</p>
          </section>

          <section className="detail-section" aria-labelledby="deadline-title">
            <h2 id="deadline-title">Termíny podle zdroje</h2>
            <p className="fine-print">
              Jde o údaje k zachycené verzi výzvy, nikoli potvrzení, že lze právě podat žádost. Před podáním ověřte změny a přesný čas v oficiálním zdroji.
            </p>
            {detail.deadlines.length ? (
              <ul className="reason-list">
                {detail.deadlines.map((deadline) => {
                  const evidence = detail.evidence.find((item) => item.id === deadline.evidenceId);
                  return (
                    <li key={deadline.id}>
                      <strong>{deadlineLabel(deadline.type)}</strong>
                      <dl className="facts">
                        {deadline.startsAt ? <div><dt>Od</dt><dd>{deadlineTime(deadline.startsAt)}</dd></div> : null}
                        <div><dt>Do</dt><dd>{deadlineTime(deadline.endsAt)}</dd></div>
                        {deadline.timezone && deadline.timezone !== "UTC"
                          ? <div><dt>Zóna uvedená zdrojem</dt><dd>{deadline.timezone}</dd></div> : null}
                      </dl>
                      {deadline.description ? <p>{deadline.description}</p> : null}
                      {evidence ? (
                        <p><a href={evidence.sourceUrl} rel="noreferrer" target="_blank">
                          Doklad termínu: {evidence.documentTitle ?? "oficiální dokument"}
                          {evidence.pageFrom ? `, str. ${evidence.pageFrom}` : ""} ↗
                        </a></p>
                      ) : (
                        <p className="fine-print">Samostatný doklad termínu není připojen; ověřte jej v oficiálním zdroji.</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p>Termíny nejsou v této verzi normalizované. Neznámý čas neznamená neomezený příjem žádostí.</p>
            )}
          </section>

          <section className="detail-section" aria-labelledby="finance-title">
            <h2 id="finance-title">Finance</h2>
            <p>Typ podpory podle verze výzvy: {instrumentLabel(detail.fundingInstrumentType)}</p>
            {detail.fundingScenarios.length ? (
              <div className="results-list">
                {detail.fundingScenarios.map((scenario) => {
                  const evidence = detail.evidence.find((item) => item.id === scenario.evidenceId);
                  return (
                    <article className="grant-card" key={scenario.id}>
                      <h3>{scenario.name}</h3>
                      <p><strong>Typ podpory: {instrumentLabel(scenario.instrumentType)}</strong></p>
                      {scenario.instrumentType !== "GRANT" || detail.fundingInstrumentType !== "GRANT" ? (
                        <p className="fine-print">Tento scénář nemá potvrzený čistě grantový typ. Grantové částky a procenta nepoužíváme jako výpočet úvěru, záruky ani vlastních zdrojů; podmínky a cash-flow ověřte u poskytovatele.</p>
                      ) : (
                        <>
                          <p>{fundingSummary(scenario)}</p>
                          <dl className="facts">
                            <div>
                              <dt>Míra podpory</dt>
                              <dd>
                                {scenario.supportRateMinBps !== null
                                  ? `${formatRate(scenario.supportRateMinBps)} – `
                                  : ""}
                                {formatRate(scenario.supportRateMaxBps)}
                              </dd>
                            </div>
                            <div>
                              <dt>Maximální dotace</dt>
                              <dd>{formatMinor(scenario.grantAmountMaxMinor, scenario.currencyCode)}</dd>
                            </div>
                            <div>
                              <dt>Režim platby</dt>
                              <dd>{scenario.paymentMode ?? "Není uvedeno"}</dd>
                            </div>
                          </dl>
                        </>
                      )}
                      {evidence ? (
                        <p><a href={evidence.sourceUrl} rel="noreferrer" target="_blank">
                          Doklad financování: {evidence.documentTitle ?? "oficiální dokument"}
                          {evidence.pageFrom ? `, str. ${evidence.pageFrom}` : ""} ↗
                        </a> · {verificationLabel(evidence.verificationStatus)}</p>
                      ) : (
                        <p className="fine-print">Samostatný doklad financování není připojen; ověřte typ nástroje a podmínky v oficiálním zdroji.</p>
                      )}
                    </article>
                  );
                })}
              </div>
            ) : (
              <>
                <StatusBadge kind="unknown" label="Finance zatím nejsou kompletně normalizované" />
                <p>
                  Nezobrazujeme odhad míry podpory ani vlastní spoluúčasti, pokud je nemáme bezpečně doložené.
                </p>
              </>
            )}
          </section>

          <section className="detail-section" aria-labelledby="requirements-title">
            <h2 id="requirements-title">Požadavky a přílohy</h2>
            {detail.requirements.length ? (
              <ul className="reason-list">
                {detail.requirements.map((requirement) => {
                  const evidence = detail.evidence.find((item) => item.id === requirement.evidenceId);
                  return (
                    <li key={requirement.id}>
                      <StatusBadge
                        kind={requirement.necessity === "REQUIRED" ? "info" : "unknown"}
                        label={`${requirement.necessity === "REQUIRED" ? "Povinné" : requirement.necessity === "CONDITIONAL" ? "Podmíněné" : "Doporučené"}: ${requirement.title}`}
                      />
                      {requirement.description ? <p>{requirement.description}</p> : null}
                      {evidence ? (
                        <p><a href={evidence.sourceUrl} rel="noreferrer" target="_blank">
                          Doklad požadavku: {evidence.documentTitle ?? "oficiální dokument"}
                          {evidence.pageFrom ? `, str. ${evidence.pageFrom}` : ""} ↗
                        </a> · {verificationLabel(evidence.verificationStatus)}</p>
                      ) : (
                        <p className="fine-print">Samostatný doklad požadavku není připojen; ověřte jej v oficiálním zdroji.</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <>
                <StatusBadge kind="unknown" label="Strukturované požadavky zatím nejsou dostupné" />
                <p>
                  Kompletní seznam příloh a podmínek je proto nutné zatím ověřit v oficiálním zdroji.
                </p>
              </>
            )}
          </section>

          {detail.changes.length ? (
            <section className="detail-section">
              <h2>Poslední změny</h2>
              <ul className="reason-list">
                {detail.changes.map((change) => (
                  <li key={change.id}>
                    <strong>{change.changeType}</strong>
                    {" · "}
                    {formatDate(change.createdAt)}
                    {change.fieldPath ? ` · ${change.fieldPath}` : ""}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {detail.versions.length > 1 ? (
            <details className="detail-section">
              <summary>Historie verzí ({detail.versions.length})</summary>
              <ul>
                {detail.versions.map((version) => (
                  <li key={version.id}>
                    Verze {version.versionNumber}
                    {" · "}
                    {formatDate(version.capturedAt)}
                    {" · "}
                    {statusLabel(version.status)}
                    {version.isCurrent ? " · aktuální" : ""}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>

        <aside className="evidence-card" aria-labelledby="source-title">
          <h2 id="source-title">Oficiální zdroje</h2>
          <p><strong>{detail.provider.name}</strong></p>
          <p>{detail.programme.name}</p>

          {detail.sources.length ? (
            <ul>
              {detail.sources.map((source) => (
                <li key={`${source.sourceCode}:${source.canonicalUrl}`}>
                  <a href={source.canonicalUrl} rel="noreferrer" target="_blank">
                    {source.sourceName} ↗
                  </a>
                  <br />
                  <strong>{sourcePresenceLabel(source.presenceState)}</strong>
                  <br />
                  <small>Pozorováno {formatDate(source.lastSeenAt)}</small>
                </li>
              ))}
            </ul>
          ) : (
            <>
              <p>Výskyt u zdroje není známý: k výzvě nemáme zdrojový záznam.</p>
              {primarySource ? (
                <a href={primarySource} rel="noreferrer" target="_blank">Otevřít oficiální zdroj ↗</a>
              ) : (
                <StatusBadge kind="unknown" label="Zdrojový odkaz zatím není v indexu dostupný" />
              )}
            </>
          )}

          {detail.evidence.length ? (
            <details>
              <summary>Konkrétní evidence ({detail.evidence.length})</summary>
              <ul>
                {detail.evidence.slice(0, 20).map((evidence) => (
                  <li key={evidence.id}>
                    <a href={evidence.sourceUrl} rel="noreferrer" target="_blank">
                      {evidence.documentTitle ?? evidence.fieldPath} ↗
                    </a>
                    {evidence.pageFrom ? ` · str. ${evidence.pageFrom}` : ""}
                  </li>
                ))}
              </ul>
            </details>
          ) : (
            <p className="fine-print">
              Máme zdrojový záznam, ale ne všechna pole ještě mají samostatnou stránkovou evidence.
            </p>
          )}

          <p className="fine-print">
            Dotační maják není poskytovatelem podpory. Rozhodující jsou oficiální podmínky poskytovatele.
          </p>
        </aside>
      </div>

      <RelevanceFeedback
        grantCallVersionId={detail.versionId}
        matcherVersion="fts-ontology-v1"
      />

      <div className="sticky-action">
        <a className="button button--primary button-link" href={projectHref}>
          {nonGrant ? "Prověřit tuto podporu" : "Chci tuto dotaci"}
        </a>
        {primarySource ? (
          <a
            className="button button--secondary button-link"
            href={primarySource}
            rel="noreferrer"
            target="_blank"
          >
            Oficiální zdroj ↗
          </a>
        ) : null}
      </div>
    </article>
  );
}
