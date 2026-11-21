import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { RelevanceFeedback } from "../components/RelevanceFeedback";
import { OfficialSourceLink } from "../components/OfficialSourceLink";
import { StatusBadge } from "../components/StatusBadge";
import { OPEN_STATUS_LABEL, OPEN_STATUS_NOTE } from "../lib/capturedStatus";
import { deadlineTime, sourceDeadlineNeedsReview } from "../lib/deadlineTime";
import { grantDetailAction } from "../lib/grantDetailAction";
import { fundingScenarioNotice } from "../lib/fundingScenarioNotice";
import {
  fetchGrantDetail,
  type GrantDetailResponse,
  type GrantFundingScenarioDetail,
} from "../lib/grantDetailApi";
import { buildReturnSearchUrl } from "../lib/intent";
import { grantCallIdFromWebPath } from "../lib/routes";
import { safeOfficialUrl } from "../lib/safeOfficialUrl";
import { sourceCalendarDate } from "../lib/sourceCalendarDate";
import { verificationLabel } from "../lib/verificationLabel";
import { allSourcesMissing, sourcePresenceLabel } from "../lib/sourcePresence";
import "./results.css";

function statusLabel(status: string): string {
  switch (status) {
    case "OPEN":
      return OPEN_STATUS_LABEL;
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

function formatRate(value: number): string {
  return new Intl.NumberFormat("cs-CZ", {
    maximumFractionDigits: 2,
  }).format(value / 100) + " %";
}

function supportRateLabel(min: number | null, max: number | null): string {
  if (min !== null && max !== null) return `${formatRate(min)} – ${formatRate(max)}`;
  if (min !== null) return `min. ${formatRate(min)}; horní mez není uvedena`;
  if (max !== null) return `max. ${formatRate(max)}; dolní mez není uvedena`;
  return "Není uvedeno";
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

function paymentModeLabel(mode: string | null): string {
  switch (mode) {
    case "ADVANCE": return "Zálohová platba";
    case "REIMBURSEMENT": return "Proplacení po úhradě nákladů";
    case "MIXED": return "Kombinovaný režim";
    case "UNKNOWN":
    case null: return "Není doložen";
    default: return mode.trim()
      ? `Jiný režim uvedený u scénáře: ${mode}. Ověřte způsob platby u poskytovatele.`
      : "Režim platby je uveden bez hodnoty; ověřte jej u poskytovatele.";
  }
}

function advanceLabel(value: boolean | null): string {
  if (value === true) return "Ano, podle scénáře";
  if (value === false) return "Ne, podle scénáře";
  return "Není doloženo";
}

function fundingSummary(scenario: GrantFundingScenarioDetail): string {
  const parts: string[] = [];
  if (scenario.supportRateMaxBps !== null) {
    parts.push(`max. ${formatRate(scenario.supportRateMaxBps)}`);
  } else if (scenario.supportRateMinBps !== null) {
    parts.push(`min. ${formatRate(scenario.supportRateMinBps)}; horní mez není uvedena`);
  }
  if (scenario.grantAmountMaxMinor !== null) {
    parts.push(
      `max. ${formatMinor(scenario.grantAmountMaxMinor, scenario.currencyCode)}`,
    );
  }
  return parts.join(" · ") || "Částka nebo míra podpory není v normalizovaných datech uvedena.";
}

export function SourceObservation({ sources }: { sources: GrantDetailResponse["sources"] }) {
  const observations = sources.map((source) => ({
    value: source.lastSeenAt,
    instant: Date.parse(source.lastSeenAt),
    needsReview: sourceDeadlineNeedsReview(source.lastSeenAt),
  }));
  const latest = observations
    .filter((observation) => !observation.needsReview && Number.isFinite(observation.instant))
    .sort((a, b) => b.instant - a.instant)[0];
  return <>
    {latest ? sourceCalendarDate(latest.value) : "Není doložena"}
    {observations.some((observation) => observation.needsReview) ? (
      <span role="note"> — U některých zdrojových záznamů nelze ověřit formát data pozorování;
        zobrazené datum nemusí být nejnovější. Ověřte stav u poskytovatele.</span>
    ) : null}
  </>;
}

export function SourceDeadline({ value }: { value: string | null }) {
  return <>
    {deadlineTime(value)}
    {sourceDeadlineNeedsReview(value) ? (
      <span role="note"> — Formát termínu není ověřen; ověřte jej v oficiálním zdroji.</span>
    ) : null}
  </>;
}

export function DetailMetadataDate({ value, label }: { value: string; label: string }) {
  return <>
    {sourceCalendarDate(value)}
    {sourceDeadlineNeedsReview(value) ? (
      <span role="note"> — Formát data ({label}) není ověřen; nepovažujte jej za doloženou aktuálnost.</span>
    ) : null}
  </>;
}

export function ChangeEventDate({ value }: { value: string }) {
  return <>
    {sourceCalendarDate(value)}
    {sourceDeadlineNeedsReview(value) ? (
      <span role="note"> — Formát data změny není ověřen. Pořadí změn ani datum události nejsou ověřené; ověřte je v oficiálním zdroji.</span>
    ) : null}
  </>;
}

export function GrantDetailPage() {
  const backToSearchHref = buildReturnSearchUrl(window.location.search);
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
  const pendingRetryFocus = useRef(false);
  const detailHeading = useRef<HTMLHeadingElement | null>(null);
  const errorHeading = useRef<HTMLHeadingElement | null>(null);

  useLayoutEffect(() => {
    if (!pendingRetryFocus.current || loading) return;
    pendingRetryFocus.current = false;
    const active = document.activeElement;
    if (active && active !== document.body && active !== document.documentElement && active.isConnected) return;
    (error ? errorHeading : detailHeading).current?.focus();
  }, [detail, error, loading]);

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
        <a href={backToSearchHref} className="back-link">← Zpět na výsledky</a>
        <section className="next-action" aria-busy="true">
          <div>
            <p className="eyebrow">Načítáme detail</p>
            <h1>Ověřujeme aktuální verzi výzvy a její zdroje.</h1>
          </div>
          {retry > 0 ? (
            <button className="button button--primary" type="button" aria-disabled="true" aria-busy="true">
              Načítáme detail znovu…
            </button>
          ) : null}
        </section>
      </article>
    );
  }

  if (error || !detail) {
    return (
      <article className="detail-page">
        <a href={backToSearchHref} className="back-link">← Zpět na výsledky</a>
        <section className="next-action" role="alert">
          <div>
            <p className="eyebrow">Detail není dostupný</p>
            <h1 ref={errorHeading} tabIndex={-1}>{error ?? "Tuto výzvu teď neumíme zobrazit."}</h1>
            <p>Neznámý nebo nedostupný údaj nevydáváme za ověřenou skutečnost.</p>
          </div>
          {!notFound && grantCallId ? (
            <button className="button button--primary" type="button" onClick={(event) => {
              pendingRetryFocus.current = document.activeElement === event.currentTarget;
              setRetry((count) => count + 1);
            }}>
              Zkusit načíst detail znovu
            </button>
          ) : null}
          <a className="button button--secondary button-link" href={backToSearchHref}>
            Zpět na vyhledávání
          </a>
        </section>
      </article>
    );
  }

  const projectHref = `/projekty?intent=${encodeURIComponent(detail.title)}&grantCallId=${encodeURIComponent(detail.grantCallId)}`;
  const versionSource = safeOfficialUrl(detail.officialDetailUrl);
  const recordSource = detail.sources.map((source) => safeOfficialUrl(source.canonicalUrl)).find(Boolean);
  const providerSource = safeOfficialUrl(detail.provider.officialUrl);
  const primarySource = versionSource ?? recordSource ?? providerSource;
  const providerHomepageOnly = Boolean(primarySource && providerSource && !versionSource && !recordSource);
  const sourceActionLabel = providerHomepageOnly
    ? "Web poskytovatele (odkaz na tuto výzvu není doložen) ↗"
    : "Ověřit stav u poskytovatele ↗";
  const showSourceCaution = allSourcesMissing(detail.sources);
  const action = grantDetailAction(
    detail.status,
    detail.availability.requirements !== "UNKNOWN",
    detail.requirements.length,
  );

  return (
    <article className="detail-page">
      <a href={backToSearchHref} className="back-link">← Zpět na výsledky</a>

      <header className="detail-hero">
        <div className="action-row">
          <StatusBadge kind="info" label={statusLabel(detail.status)} />
          <StatusBadge
            kind={detail.verificationStatus === "VERIFIED" ? "success" : "unknown"}
            label={verificationLabel(detail.verificationStatus)}
          />
        </div>
        {detail.status === "OPEN" ? <p className="fine-print">{OPEN_STATUS_NOTE}</p> : null}
        {detail.sources.length === 0 ? (
          <p className="source-presence-caution" role="status">
            <strong>Výskyt výzvy u zdroje není doložen.</strong>{" "}
            K této verzi nemáme zdrojový záznam ani datum jeho posledního pozorování.
            Stav výzvy proto před podáním ověřte přímo u poskytovatele; chybějící záznam sám o sobě neznamená zrušení.
          </p>
        ) : null}
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
            {detail.sources.length === 20 ? " Další zdrojové záznamy mohou být mimo zobrazený seznam." : null}
            {" "}Chybění u zdroje samo o sobě neznamená zrušení výzvy.
          </p>
        ) : null}
        <p className="eyebrow">{detail.provider.name}</p>
        <h1 ref={detailHeading} tabIndex={-1}>{detail.title}</h1>
        {detail.summary ? <p className="results-lead">{detail.summary}</p> : null}
      </header>

      <section className="next-action" aria-labelledby="detail-next">
        <div>
          <p className="eyebrow">Co udělat teď</p>
          <h2 id="detail-next">{action.heading}</h2>
          <p>{action.explanation}</p>
        </div>
        <a className="button button--primary button-link"
          href={action.applicationCandidate ? projectHref : primarySource ?? "/hledat"}
          rel={!action.applicationCandidate && primarySource ? "noreferrer" : undefined}
          target={!action.applicationCandidate && primarySource ? "_blank" : undefined}>
          {action.applicationCandidate ? action.projectLabel : primarySource ? sourceActionLabel : "Hledat další výzvy"}
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
                <dd><SourceDeadline value={detail.submissionOpenAt} /></dd>
              </div>
              <div>
                <dt>Ukončení příjmu</dt>
                <dd><SourceDeadline value={detail.submissionCloseAt} /></dd>
              </div>
              <div>
                <dt>Verze výzvy zachycena</dt>
                <dd><DetailMetadataDate value={detail.capturedAt} label="zachycení verze" /></dd>
              </div>
              <div>
                <dt>Poslední pozorování záznamu u zdroje</dt>
                <dd><SourceObservation sources={detail.sources} /></dd>
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
                        {deadline.startsAt ? <div><dt>Od</dt><dd><SourceDeadline value={deadline.startsAt} /></dd></div> : null}
                        <div><dt>Do</dt><dd><SourceDeadline value={deadline.endsAt} /></dd></div>
                        {deadline.timezone && deadline.timezone !== "UTC"
                          ? <div><dt>Zóna uvedená zdrojem</dt><dd>{deadline.timezone}</dd></div> : null}
                      </dl>
                      {deadline.description ? <p>{deadline.description}</p> : null}
                      {evidence ? (
                        <p><OfficialSourceLink url={evidence.sourceUrl}>
                          Doklad termínu: {evidence.documentTitle ?? "oficiální dokument"}
                          {evidence.pageFrom ? `, str. ${evidence.pageFrom}` : ""} ↗
                        </OfficialSourceLink></p>
                      ) : deadline.evidenceId !== null ? (
                        <p className="fine-print">Doklad termínu je uveden, ale není dostupný v omezeném seznamu dokladů; ověřte jej v oficiálním zdroji.</p>
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
                      <p className="fine-print">{fundingScenarioNotice(scenario)}</p>
                      <p><strong>Typ podpory: {instrumentLabel(scenario.instrumentType)}</strong></p>
                      {scenario.instrumentType !== "GRANT" || detail.fundingInstrumentType !== "GRANT" ? (
                        <p className="fine-print">Tento scénář nemá potvrzený čistě grantový typ. Grantové částky a procenta nepoužíváme jako výpočet úvěru, záruky ani vlastních zdrojů; podmínky a cash-flow ověřte u poskytovatele.</p>
                      ) : (
                        <>
                          <p>{fundingSummary(scenario)}</p>
                          <dl className="facts">
                            <div>
                              <dt>Míra podpory</dt>
                              <dd>{supportRateLabel(scenario.supportRateMinBps, scenario.supportRateMaxBps)}</dd>
                            </div>
                            <div>
                              <dt>Maximální dotace</dt>
                              <dd>{formatMinor(scenario.grantAmountMaxMinor, scenario.currencyCode)}</dd>
                            </div>
                            <div>
                              <dt>Minimální náklady projektu podle scénáře</dt>
                              <dd>{formatMinor(scenario.projectCostMinMinor, scenario.currencyCode)}</dd>
                            </div>
                            <div>
                              <dt>Maximální náklady projektu podle scénáře</dt>
                              <dd>{formatMinor(scenario.projectCostMaxMinor, scenario.currencyCode)}</dd>
                            </div>
                            <div>
                              <dt>Režim platby</dt>
                              <dd>{paymentModeLabel(scenario.paymentMode)}</dd>
                            </div>
                            <div>
                              <dt>Záloha povolena</dt>
                              <dd>{advanceLabel(scenario.advancePaymentAllowed)}</dd>
                            </div>
                          </dl>
                          <p className="fine-print">Individuální potřebu vlastních peněz a předfinancování z těchto mezí ani z míry podpory nelze určit. Závisí na způsobilých a nezpůsobilých nákladech, DPH, podmínkách platby a vašem projektu. Ověřte rozpočet a cash-flow v projektu a u poskytovatele.</p>
                        </>
                      )}
                      {evidence ? (
                        <p><OfficialSourceLink url={evidence.sourceUrl}>
                          Doklad financování: {evidence.documentTitle ?? "oficiální dokument"}
                          {evidence.pageFrom ? `, str. ${evidence.pageFrom}` : ""} ↗
                        </OfficialSourceLink> · {verificationLabel(evidence.verificationStatus)}</p>
                      ) : scenario.evidenceId !== null ? (
                        <p className="fine-print">Doklad financování je uveden, ale není dostupný v omezeném seznamu dokladů; ověřte typ nástroje a podmínky v oficiálním zdroji.</p>
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

          <section className="detail-section" aria-labelledby="detail-eligibility-title">
            <h2 id="detail-eligibility-title">Způsobilost pro váš projekt</h2>
            <StatusBadge kind="unknown" label="Osobní způsobilost zde není posouzena" />
            <p>
              Tematická shoda ani zveřejněné požadavky nedokládají, že váš projekt splňuje podmínky.
              K posouzení je potřeba projekt, údaje žadatele a pravidla aktuální verze výzvy.
              Chybějící údaj znamená neznámý výsledek (UNKNOWN), nikoli nesplnění podmínky.
            </p>
            {action.applicationCandidate ? (
              <p>
                <a href={projectHref}>Přejít k projektu a ověřit známé podmínky</a>.
                Pokud pravidla nebo údaje chybí, posouzení to výslovně uvede; ani kladný výsledek není příslibem dotace.
              </p>
            ) : (
              <p>Než budete připravovat žádost, ověřte aktuální stav a podmínky u poskytovatele.</p>
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
                        <p><OfficialSourceLink url={evidence.sourceUrl}>
                          Doklad požadavku: {evidence.documentTitle ?? "oficiální dokument"}
                          {evidence.pageFrom ? `, str. ${evidence.pageFrom}` : ""} ↗
                        </OfficialSourceLink> · {verificationLabel(evidence.verificationStatus)}</p>
                      ) : requirement.evidenceId !== null ? (
                        <p className="fine-print">Doklad požadavku je uveden, ale není dostupný v omezeném seznamu dokladů; ověřte jej v oficiálním zdroji.</p>
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
              <h2>Poslední změny ({detail.changes.length}{detail.changes.length === 20 ? " zobrazených" : ""})</h2>
              {detail.changes.length === 20 ? (
                <p className="fine-print" role="status">
                  Detail API vrací nejvýše 20 změn. Mohou existovat další změny; tento seznam není zaručeně úplný. Aktuální podmínky ověřte v oficiálním zdroji.
                </p>
              ) : null}
              <ul className="reason-list">
                {detail.changes.map((change) => (
                  <li key={change.id}>
                    <strong>{change.changeType}</strong>
                    {" · "}
                    <ChangeEventDate value={change.createdAt} />
                    {change.fieldPath ? ` · ${change.fieldPath}` : ""}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {detail.versions.length > 1 ? (
            <details className="detail-section">
              <summary>Historie verzí ({detail.versions.length}{detail.versions.length === 20 ? " zobrazených" : ""})</summary>
              {detail.versions.length === 20 ? (
                <p className="fine-print" role="status">
                  Detail API vrací nejvýše 20 verzí: aktuální verzi a nejnovější další verze. Další verze mohou existovat; tento seznam není zaručeně úplný. Aktuální podmínky ověřte v oficiálním zdroji.
                </p>
              ) : null}
              <ul>
                {detail.versions.map((version) => (
                  <li key={version.id}>
                    Verze {version.versionNumber}
                    {" · "}
                    <DetailMetadataDate value={version.capturedAt} label="zachycení verze" />
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
            <>
              {detail.sources.length === 20 ? (
                <p className="fine-print" role="status">
                  Detail API vrací nejvýše 20 zdrojových záznamů. Mohou existovat další, včetně záznamů se stavem „viděn“; tento seznam není zaručeně úplný. Výskyt a stav výzvy ověřte v oficiálním zdroji.
                </p>
              ) : null}
              <ul>
                {detail.sources.map((source) => (
                  <li key={`${source.sourceCode}:${source.canonicalUrl}`}>
                    <OfficialSourceLink url={source.canonicalUrl}>
                      {source.sourceName} ↗
                    </OfficialSourceLink>
                    <br />
                    <strong>{sourcePresenceLabel(source.presenceState)}</strong>
                    <br />
                    <small>Pozorováno {sourceCalendarDate(source.lastSeenAt)}
                      {sourceDeadlineNeedsReview(source.lastSeenAt) ? (
                        <span role="note"> — Formát data pozorování není ověřen; ověřte stav u poskytovatele.</span>
                      ) : null}
                    </small>
                  </li>
                ))}
              </ul>
              {!recordSource && !versionSource ? (
                <>
                  <p className="fine-print">Odkaz na konkrétní výzvu není bezpečně dostupný; {providerSource
                    ? "toto je pouze obecný web poskytovatele."
                    : "aktuální podmínky ověřte přímo u poskytovatele."}</p>
                  {providerSource ? (
                    <p><a href={providerSource} rel="noreferrer" target="_blank">{sourceActionLabel}</a></p>
                  ) : null}
                </>
              ) : null}
            </>
          ) : (
            <>
              <p>Výskyt u zdroje není známý: k výzvě nemáme zdrojový záznam.</p>
              {providerHomepageOnly ? (
                <p className="fine-print">Odkaz na konkrétní výzvu nemáme; toto je obecný web poskytovatele.</p>
              ) : null}
              {primarySource ? (
                <a href={primarySource} rel="noreferrer" target="_blank">
                  {providerHomepageOnly ? sourceActionLabel : "Otevřít oficiální zdroj ↗"}
                </a>
              ) : (
                <StatusBadge kind="unknown" label="Zdrojový odkaz zatím není v indexu dostupný" />
              )}
            </>
          )}

          {detail.evidence.length ? (
            <details>
              <summary>Konkrétní evidence ({detail.evidence.length}{detail.evidence.length === 100 ? " zobrazených" : ""})</summary>
              {detail.evidence.length === 100 ? (
                <p className="fine-print" role="status">
                  Detail API vrací nejvýše 100 dokladů. Mohou existovat další; tento seznam není zaručeně úplný. Ověřte podmínky v oficiálním zdroji.
                </p>
              ) : null}
              <p className="fine-print">Datum stažení dokumentu není datum opětovného ověření podmínek výzvy.</p>
              <ul>
                {detail.evidence.map((evidence) => (
                  <li key={evidence.id}>
                    <OfficialSourceLink url={evidence.sourceUrl}>
                      {evidence.documentTitle ?? evidence.fieldPath} ↗
                    </OfficialSourceLink>
                    {evidence.pageFrom ? ` · str. ${evidence.pageFrom}` : ""}
                    <br />
                    <small>Dokument stažen: <DetailMetadataDate value={evidence.retrievedAt} label="stažení dokumentu" /> · Ověření doloženého údaje: {verificationLabel(evidence.verificationStatus)}</small>
                  </li>
                ))}
              </ul>
            </details>
          ) : (
            <p className="fine-print">
              {detail.sources.length
                ? "Ke zdrojovému záznamu nejsou připojeny samostatné doklady pro všechna pole. Ověřte podmínky v oficiálním zdroji."
                : "Ke výzvě nemáme zdrojový záznam ani samostatné doklady. Ověřte podmínky v oficiálním zdroji."}
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
        {action.applicationCandidate ? (
          <a className="button button--primary button-link" href={projectHref}>
            {action.projectLabel}
          </a>
        ) : (
          <a className="button button--primary button-link" href={primarySource ?? "/hledat"}
            rel={primarySource ? "noreferrer" : undefined} target={primarySource ? "_blank" : undefined}>
            {primarySource ? sourceActionLabel : "Hledat další výzvy"}
          </a>
        )}
        {primarySource && action.applicationCandidate ? (
          <a className="button button--secondary button-link"
            href={primarySource}
            rel="noreferrer"
            target="_blank"
          >
            {providerHomepageOnly ? sourceActionLabel : "Oficiální zdroj ↗"}
          </a>
        ) : null}
      </div>
    </article>
  );
}
