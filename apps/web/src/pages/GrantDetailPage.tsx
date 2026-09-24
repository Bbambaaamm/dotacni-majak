import { useEffect, useMemo, useState } from "react";

import { RelevanceFeedback } from "../components/RelevanceFeedback";
import { StatusBadge } from "../components/StatusBadge";
import {
  fetchGrantDetail,
  type GrantDetailResponse,
  type GrantFundingScenarioDetail,
} from "../lib/grantDetailApi";
import { grantCallIdFromWebPath } from "../lib/routes";
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
  return latest ? formatDate(latest) : formatDate(detail.capturedAt);
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

  useEffect(() => {
    if (!grantCallId) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchGrantDetail(grantCallId, controller.signal)
      .then((value) => {
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
        setError(
          status === 404
            ? "Tuto dotační výzvu jsme v aktuálním indexu nenašli."
            : "Detail výzvy se teď nepodařilo bezpečně načíst.",
        );
        setLoading(false);
      });

    return () => controller.abort();
  }, [grantCallId]);

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
          <a className="button button--secondary button-link" href="/hledat">
            Zpět na vyhledávání
          </a>
        </section>
      </article>
    );
  }

  const projectHref = `/projekty?intent=${encodeURIComponent(detail.title)}&grantCallId=${encodeURIComponent(detail.grantCallId)}`;
  const primarySource = detail.officialDetailUrl
    ?? detail.sources[0]?.canonicalUrl
    ?? detail.provider.officialUrl;

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
                <dt>Poslední kontrola zdroje</dt>
                <dd>{lastSeenLabel(detail)}</dd>
              </div>
            </dl>
          </section>

          <section className="detail-section">
            <h2>Finance</h2>
            {detail.fundingScenarios.length ? (
              <div className="results-list">
                {detail.fundingScenarios.map((scenario) => (
                  <article className="grant-card" key={scenario.id}>
                    <h3>{scenario.name}</h3>
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
                  </article>
                ))}
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

          <section className="detail-section">
            <h2>Požadavky a přílohy</h2>
            {detail.requirements.length ? (
              <ul className="reason-list">
                {detail.requirements.map((requirement) => (
                  <li key={requirement.id}>
                    <StatusBadge
                      kind={requirement.necessity === "REQUIRED" ? "info" : "unknown"}
                      label={`${requirement.necessity === "REQUIRED" ? "Povinné" : requirement.necessity === "CONDITIONAL" ? "Podmíněné" : "Doporučené"}: ${requirement.title}`}
                    />
                    {requirement.description ? <p>{requirement.description}</p> : null}
                  </li>
                ))}
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
                  <small>Kontrolováno {formatDate(source.lastSeenAt)}</small>
                </li>
              ))}
            </ul>
          ) : primarySource ? (
            <a href={primarySource} rel="noreferrer" target="_blank">
              Otevřít oficiální zdroj ↗
            </a>
          ) : (
            <StatusBadge kind="unknown" label="Zdrojový odkaz zatím není v indexu dostupný" />
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
          Chci tuto dotaci
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
