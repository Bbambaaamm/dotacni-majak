import { StatusBadge } from "./StatusBadge";
import type { ResultStateContent } from "../lib/resultState";
import "./ResultStatePanel.css";

function badgeKind(
  kind: ResultStateContent["kind"],
): "info" | "warning" | "error" | "unknown" {
  switch (kind) {
    case "NO_RESULTS":
      return "info";
    case "INELIGIBLE":
      return "error";
    case "UNKNOWN":
      return "unknown";
    case "SOURCE_UNAVAILABLE":
      return "warning";
  }
}

export function ResultStatePanel({
  state,
}: {
  state: ResultStateContent;
}) {
  return (
    <section
      className="result-state-panel"
      aria-labelledby={`result-state-${state.kind}`}
    >
      <StatusBadge kind={badgeKind(state.kind)} label={state.eyebrow} />
      <h1 id={`result-state-${state.kind}`}>{state.title}</h1>
      <p className="result-state-panel__lead">{state.description}</p>

      {state.sourceLastSuccess ? (
        <p className="result-state-panel__freshness">
          <strong>Poslední úspěšná kontrola:</strong>{" "}
          {state.sourceLastSuccess}
        </p>
      ) : null}

      <ul>
        {state.details.map((detail) => (
          <li key={detail}>{detail}</li>
        ))}
      </ul>

      <div className="result-state-panel__actions">
        <a className="button button--primary button-link" href={state.primaryHref}>
          {state.primaryLabel}
        </a>
        {state.secondaryLabel && state.secondaryHref ? (
          <a
            className="button button--secondary button-link"
            href={state.secondaryHref}
          >
            {state.secondaryLabel}
          </a>
        ) : null}
      </div>

      {state.kind === "SOURCE_UNAVAILABLE" ? (
        <p className="fine-print">
          Poslední ověřená data ponecháváme viditelná. Nedostupnost zdroje
          sama o sobě nemění stav výzvy na uzavřenou nebo zrušenou.
        </p>
      ) : null}
    </section>
  );
}
