import { type FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import { type ApplicantProfileType } from "../lib/applicantProfile";
import {
  answerApplicantType, loadProjectEligibility, type EligibilitySnapshot,
} from "../lib/projectEligibility";

type Answer = Exclude<ApplicantProfileType, "UNKNOWN">;
const answers: Array<[Answer, string]> = [
  ["NATURAL_PERSON", "Fyzická osoba"], ["SELF_EMPLOYED", "OSVČ"],
  ["BUSINESS", "Firma"], ["MUNICIPALITY", "Obec"], ["REGION", "Kraj"],
  ["ASSOCIATION", "Spolek"], ["SPORTS_CLUB", "Sportovní klub"],
  ["NONPROFIT", "Nezisková organizace"], ["SCHOOL", "Škola"],
  ["CONTRIBUTORY_ORGANISATION", "Příspěvková organizace"], ["HOA", "SVJ"],
  ["COOPERATIVE", "Družstvo"], ["AGRICULTURAL_ENTITY", "Zemědělský subjekt"],
  ["RESEARCH_ORGANISATION", "Výzkumná organizace"], ["OTHER", "Jiný typ"],
];

function label(snapshot: EligibilitySnapshot): string {
  switch (snapshot.status) {
    case "ELIGIBLE": return "Podle ověřených pravidel a vstupů způsobilé";
    case "LIKELY_ELIGIBLE": return "Známé podmínky vycházejí, ale vstup není ověřený";
    case "INELIGIBLE": return "Ověřená blokující podmínka není splněna";
    case "NEEDS_INFORMATION": return "Chybí údaj pro posouzení (UNKNOWN)";
    case "NEEDS_REVIEW": return "Výsledek vyžaduje ověření, nejde o zamítnutí";
  }
}

export function ProjectEligibility({ grantCallId, ownerCapability, onWritePendingChange }: {
  grantCallId: string; ownerCapability: string; onWritePendingChange: (pending: boolean) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [snapshot, setSnapshot] = useState<EligibilitySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [answer, setAnswer] = useState<Answer | "">("");
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    const next = new AbortController();
    controller.current = next;
    setSnapshot(null);
    setError(false);
    setLoading(true);
    loadProjectEligibility(grantCallId, ownerCapability, next.signal)
      .then((value) => { if (!next.signal.aborted) setSnapshot(value); })
      .catch(() => { if (!next.signal.aborted) setError(true); })
      .finally(() => { if (!next.signal.aborted) setLoading(false); });
    return () => next.abort();
  }, [grantCallId, ownerCapability, revision]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || loading || !answer || !snapshot?.missingAttributes.includes("applicant.type")) return;
    controller.current?.abort();
    onWritePendingChange(true);
    setSaving(true);
    setLoading(true);
    setSnapshot(null);
    setError(false);
    try {
      await answerApplicantType(answer, ownerCapability);
      setRevision((value) => value + 1);
    } catch {
      setError(true);
      setLoading(false);
    } finally {
      onWritePendingChange(false);
      setSaving(false);
    }
  }

  return (
    <section className="share-card" aria-labelledby="eligibility-title">
      <h2 id="eligibility-title">Způsobilost pro vybranou výzvu</h2>
      <p>Samostatné posouzení aktuální verze výzvy proti serverovému profilu projektu. Tematická shoda ani stav přípravy nejsou způsobilost. Místní profil z prohlížeče se neposílá automaticky.</p>
      <div role="status" aria-live="polite" aria-atomic="true">
        {loading ? <p>Načítáme aktuální posouzení…</p> : error ? (
          <p role="alert">Posouzení nebo uložení odpovědi se nepodařilo. Starý výsledek nepoužíváme; údaje ověřte v oficiálním zdroji.</p>
        ) : snapshot ? (
          <StatusBadge kind={snapshot.status === "ELIGIBLE" ? "success" : "unknown"} label={label(snapshot)} />
        ) : null}
      </div>
      {!loading && !error && snapshot ? (
        <>
          <p>Posuzovaná verze: <code>{snapshot.versionId}</code>. {snapshot.ruleSetId === null
            ? "Pro tuto verzi chybí pravidla; žádný výsledek nevyvozujeme."
            : "Podmínky je nutné před žádostí ověřit u poskytovatele."}</p>
          {snapshot.conditions.some((condition) => condition.evidenceId) && (
            <details>
              <summary>Podklad pravidla</summary>
              {snapshot.conditions.filter((condition) => condition.evidenceId).map((condition) => (
                <p key={condition.conditionId}>Referenční ID dokladu: <code>{condition.evidenceId}</code>. Samotné ID není ověření; dokument poskytovatele najdete v detailu výzvy.</p>
              ))}
            </details>
          )}
          {snapshot.missingAttributes.includes("applicant.type") && snapshot.status === "NEEDS_INFORMATION" ? (
            <form className="project-form" onSubmit={(event) => void submit(event)}>
              <h3>Jaký typ žadatele bude žádost podávat?</h3>
              <p>Ptáme se, protože pravidlo vyžaduje typ žadatele. Odpověď uložíme k tomuto anonymnímu vlastníkovi projektu; jde o váš neověřený údaj, nikoli o potvrzení poskytovatele.</p>
              <label>Typ žadatele
                <select required value={answer} onChange={(event) => setAnswer(event.target.value as Answer | "")}>
                  <option value="">Vyberte typ žadatele</option>
                  {answers.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                </select>
              </label>
              <Button type="submit" disabled={saving}>Uložit odpověď a přepočítat</Button>
            </form>
          ) : snapshot.missingAttributes.length ? (
            <p>Chybí další údaje pro pravidla. Neodvozujeme jejich hodnoty; ověřte je v oficiálním zdroji.</p>
          ) : null}
          {snapshot.status === "LIKELY_ELIGIBLE" && <p>Shoda není ověřená způsobilost ani příslib dotace. Váš údaj je pouze vlastní deklarace.</p>}
          {snapshot.blockers.length > 0 && <p>Blokující pravidlo vyžaduje kontrolu; bez ověřených vstupů nejde o definitivní nezpůsobilost.</p>}
        </>
      ) : null}
      <Button variant="secondary" disabled={saving || loading} onClick={() => setRevision((value) => value + 1)}>
        Obnovit posouzení z aktuální verze
      </Button>
      <a href={`/dotace/${encodeURIComponent(grantCallId)}`}>Otevřít detail a oficiální zdroj</a>
    </section>
  );
}
