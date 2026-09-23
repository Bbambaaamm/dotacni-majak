import { useState } from "react";

import {
  createRelevanceFeedback,
  LocalRelevanceFeedbackStore,
  type RelevanceJudgment,
} from "../lib/relevanceFeedback";
import "./RelevanceFeedback.css";

interface RelevanceFeedbackProps {
  grantCallVersionId: string;
  projectId?: string | null;
  matcherVersion: string;
}

const choices: readonly {
  judgment: RelevanceJudgment;
  label: string;
}[] = [
  { judgment: "RELEVANT", label: "Ano" },
  { judgment: "NOT_RELEVANT", label: "Ne" },
  { judgment: "UNSURE", label: "Nevím" },
];

export function RelevanceFeedback({
  grantCallVersionId,
  projectId = null,
  matcherVersion,
}: RelevanceFeedbackProps) {
  const [saved, setSaved] = useState<RelevanceJudgment | null>(null);

  function submit(judgment: RelevanceJudgment) {
    const storage = new LocalRelevanceFeedbackStore(window.localStorage);
    storage.save(
      createRelevanceFeedback({
        id: crypto.randomUUID(),
        grantCallVersionId,
        projectId,
        judgment,
        matcherVersion,
        createdAt: new Date().toISOString(),
      }),
    );
    setSaved(judgment);
  }

  return (
    <section className="relevance-feedback" aria-labelledby="feedback-title">
      <div>
        <h4 id="feedback-title">Je tato možnost relevantní pro váš projekt?</h4>
        <p>
          Pomáháte nám měřit kvalitu vyhledávání. Odpověď nemění oficiální
          podmínky ani vaše vyhodnocení způsobilosti.
        </p>
      </div>
      <div className="relevance-feedback__choices">
        {choices.map((choice) => (
          <button
            aria-pressed={saved === choice.judgment}
            className="button button--secondary"
            key={choice.judgment}
            onClick={() => submit(choice.judgment)}
            type="button"
          >
            {choice.label}
          </button>
        ))}
      </div>
      {saved ? (
        <p className="relevance-feedback__saved" role="status">
          Zpětná vazba byla uložena v tomto prohlížeči.
        </p>
      ) : null}
      <p className="fine-print">
        V této fázi se feedback ukládá lokálně bez jména, e-mailu nebo volného
        textu. Serverová synchronizace bude samostatně opt-in.
      </p>
    </section>
  );
}
