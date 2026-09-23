import { demoExportSummary } from "../lib/exportSummary";
import { StatusBadge } from "../components/StatusBadge";
import "./export-summary.css";

function verificationKind() {
  switch (demoExportSummary.verification) {
    case "VERIFIED":
      return "success" as const;
    case "NEEDS_INFORMATION":
      return "unknown" as const;
    case "NEEDS_REVIEW":
      return "warning" as const;
  }
}

export function ExportSummaryPage() {
  const summary = demoExportSummary;

  return (
    <article className="export-summary">
      <div className="export-actions no-print">
        <a href="/dotace/regiony-2026" className="back-link">
          ← Zpět na detail
        </a>
        <button
          type="button"
          className="button button--primary"
          onClick={() => window.print()}
        >
          Tisk / uložit jako PDF
        </button>
      </div>

      <header className="export-header">
        <p className="eyebrow">Dotační maják — export přehledu</p>
        <h1>{summary.projectTitle}</h1>
        <p className="export-meta">
          Vytvořeno: <time dateTime={summary.generatedAt}>23. 9. 2026</time>
        </p>
        {summary.fixtureNotice ? (
          <aside className="export-fixture">
            <StatusBadge kind="warning" label="Testovací export" />
            <p>{summary.fixtureNotice}</p>
          </aside>
        ) : null}
      </header>

      <section className="export-section">
        <h2>Vybraná výzva</h2>
        <dl className="export-facts">
          <div><dt>Název</dt><dd>{summary.grantTitle}</dd></div>
          <div><dt>Poskytovatel</dt><dd>{summary.provider}</dd></div>
          <div><dt>Stav</dt><dd>{summary.statusLabel}</dd></div>
        </dl>
      </section>

      <section className="export-section">
        <h2>Vyhodnocení</h2>
        <StatusBadge
          kind={verificationKind()}
          label={
            summary.verification === "VERIFIED"
              ? "Ověřené známé podmínky"
              : summary.verification === "NEEDS_INFORMATION"
                ? "Chybí informace"
                : "Vyžaduje kontrolu"
          }
        />
        <h3>Proč možnost odpovídá</h3>
        <p>{summary.relevanceSummary}</p>
        <h3>Způsobilost</h3>
        <p>{summary.eligibilitySummary}</p>
      </section>

      <section className="export-section">
        <h2>Finance</h2>
        <ul>
          {summary.financeSummary.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </section>

      <section className="export-section">
        <h2>Co udělat teď</h2>
        <ol>
          {summary.nextSteps.map((step) => <li key={step}>{step}</li>)}
        </ol>
      </section>

      <section className="export-section">
        <h2>Oficiální zdroje</h2>
        {summary.evidence.map((item) => (
          <article className="export-evidence" key={item.url}>
            <h3>{item.label}</h3>
            <p>Kontrolováno: {item.checkedAt}</p>
            {item.document ? <p>Dokument: {item.document}</p> : null}
            {item.pageOrSection ? <p>Část: {item.pageOrSection}</p> : null}
            <a href={item.url}>{item.url}</a>
          </article>
        ))}
      </section>

      <footer className="export-disclaimer">
        <strong>Důležité</strong>
        <p>{summary.disclaimer}</p>
      </footer>
    </article>
  );
}
