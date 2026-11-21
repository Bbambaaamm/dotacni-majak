import { sourceCalendarDate } from "../lib/sourceCalendarDate";
import { verificationLabel } from "../lib/verificationLabel";

export function SearchProvenance({ capturedAt, verificationStatus }: {
  capturedAt: string;
  verificationStatus: string;
}) {
  return <>
    <dl>
      <div><dt>Verze zachycena</dt><dd>{sourceCalendarDate(capturedAt)}</dd></div>
      <div><dt>Ověření zachycené verze</dt><dd>{verificationLabel(verificationStatus)}</dd></div>
    </dl>
    <p className="fine-print" role="note">Údaje pocházejí ze zachycené verze. Datum zachycení ani stav ověření nepotvrzují aktuální podmínky nebo příjem žádostí. Ověřte je v oficiálním zdroji.</p>
  </>;
}
