import { FormEvent, useState } from "react";

import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import { CZ_REGIONS, type LegalType, looksLikeCzechICO } from "../lib/profileQuestions";

const LEGAL_TYPES: { value: LegalType; label: string }[] = [
  { value: "obec",  label: "Obec" },
  { value: "spolek", label: "Spolek" },
  { value: "firma",  label: "Firma" },
  { value: "obcan",  label: "Občan" },
];

const PAGE_ANNOUNCEMENTS = {
  legalTypeChanged: "Zvolen typ podnikatele",
  icoChanged: "Změněno IČO",
  regionChanged: "Změněn kraj",
  saved: "Profil byl uložen",
  saveError: "Profil se nepodařilo uložit",
  loadError: "Profil nelze načíst z místního úložiště",
};

export function ProfileWizardPage() {
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [legalType, setLegalType] = useState<LegalType | undefined>(undefined);
  const [ico, setIco] = useState("");
  const [regionId, setRegionId] = useState("");
  const [icoError, setIcoError] = useState<string | null>(null);

  function announce(text: keyof typeof PAGE_ANNOUNCEMENTS) {
    const live = document.getElementById("profile-live");
    if (live) live.textContent = PAGE_ANNOUNCEMENTS[text];
  }

  function validateIcoInput(raw: string): void {
    const trimmed = raw.trim();
    if (trimmed.length > 0 && !looksLikeCzechICO(trimmed)) {
      setIcoError("IČO nevyhovuje kontrolnímu součtu — zkontrolujte zadání");
    } else {
      setIcoError(null);
    }
  }

  function handleIcoChange(value: string) {
    setIco(value);
    validateIcoInput(value);
    announce("icoChanged");
  }

  function noteIcoAutofill(msg: string) {
    setMessage(msg);
  }

  function handleLegalTypeChange(value: LegalType) {
    setLegalType(value);
    announce("legalTypeChanged");
    // If IČO present and legal type just selected, show autofill note (not automatic — user confirmed)
    if (ico && looksLikeCzechICO(ico)) {
      noteIcoAutofill("Děkujeme za zadání IČO. Typ podnikatele byl zvolen manuálně — příkaz na automatické vyplnění z IČO není v tomto pohodlí dostupný.");
    }
  }

  function handleRegionChange(value: string) {
    setRegionId(value);
    announce("regionChanged");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);

    if (!legalType) {
      setMessage("Zvolte typ podnikatele — dékujeme za zadání základních údajů.");
      return;
    }

    setBusy(true);
    try {
      const profile = {
        legalType,
        ico: ico.trim() || undefined,
        regionId,
        updatedAt: new Date().toISOString(),
        isProfile: true,
      };
      localStorage.setItem("dotacni-majak:profile", JSON.stringify(profile));
      announce("saved");
      setStep(2); // success view
    } catch {
      setMessage("Profil se teď nepodařilo uložit — zkuste to znovu.");
      setStep(0);
    } finally {
      setBusy(false);
    }
  }

  function renderStep0(): React.ReactNode {
    const missingType = legalType === undefined;
    return (
      <fieldset className="profile-form__step">
        <legend>Krok 1: Typ podnikatele</legend>
        <p className="profile-form__intro">
          Vyberte, jaký typ podnikatele jste. Pomůže nám to vybrat správné dotace
          pro vás a zobrazit jen ty programy, které vám mohou vyhovovat.
        </p>

        <fieldset className="profile-form__radios">
          <legend>Jaký typ podnikatele jste?</legend>
          <div className="profile-form__radio-list">
            {LEGAL_TYPES.map((t) => (
              <label key={t.value} className="radio-label">
                <input
                  type="radio"
                  name="legalType"
                  value={t.value}
                  checked={legalType === t.value}
                  onChange={() => handleLegalTypeChange(t.value)}
                />
                <span>{t.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* IČO field — optional, shown for any type (per issue scope: IČO optional/autofill) */}
        <div className="profile-form__ico-field">
          <label>
            IČO (volitelné)
            <input
              type="text"
              value={ico}
              onChange={(e) => handleIcoChange(e.target.value)}
              maxLength={8}
              placeholder="např. 01234567"
              disabled={icoError !== null}
              aria-describedby={icoError ? "ico-error" : undefined}
              aria-label="IČO (volitelné)"
            />
          </label>
          {icoError && (
            <p id="ico-error" className="field-error" role="alert">
              {icoError}
            </p>
          )}
          <p className="field-help">
            Pokud máte veřejně číslo IČO, zadejte ho zde — pomůže nám to
            přesnější doporučení. Nemusíte ho však zadat.
          </p>
        </div>

        <div className="profile-form__actions">
          <Button type="button" onClick={() => setStep(1)} disabled={missingType}>
            Zvolil jsem typ podnikatele — přejděte na lokality
          </Button>
        </div>

        {message && <p className="form-message" role="status">{message}</p>}
      </fieldset>
    );
  }

  function renderStep1(): React.ReactNode {
    return (
      <fieldset className="profile-form__step">
        <legend>Krok 2: Lokalita</legend>
        <p className="profile-form__intro">
          Zvolte svůj kraj nebo hlavní město — některé dotace jsou určeny pouze pro
          určité lokality.
        </p>

        <label className="profile-form__field">
          Kraj / město
          <select
            value={regionId}
            onChange={(e) => handleRegionChange(e.target.value)}
            aria-label="Kraj / město"
          >
            <option value="">Vyberte kraj nebo město…</option>
            {CZ_REGIONS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <p className="field-help">
          Některé dotace jsou určeny pouze pro určité kraje nebo pomocí nich reálně
          fungují, takže na základě vašeho kraje můžeme omezit doporučení na
          programy, které jsou skutečně dostupné pro vás.
        </p>

        <div className="profile-form__actions">
          <Button
            type="submit"
            disabled={!regionId || busy}
          >
            {busy ? "Ukládám…"
              : "Uložit profil a zobrazit doporučení"}
          </Button>
        </div>
      </fieldset>
    );
  }

  function renderStep2(): React.ReactNode {
    return (
      <div className="profile-page__success">
        <StatusBadge kind="success" label="Profil byl uložen" />
        <h1>Profil byl uložen</h1>
        <p className="profile-page__success-lead">
          Na základě vašeho typu podnikatele a lokality máte přístup k těmto
          programům, které nám zavedly.
        </p>
        <p>
          Nyní můžete zobrazit doporučení podle vašeho profilu. Pokud chcete
          upravit svůj profil, můžete se vrátit zpět.
        </p>
        <div className="profile-form__actions">
          <Button type="button" variant="secondary" onClick={() => setStep(0)}>
            Upravit profil
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={() => {
              window.location.href = "/hledat";
            }}
          >
            Přejít na hledání dotací
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="profile-page">
      <div className="profile-page__header">
        <p className="eyebrow">Nastavte svůj profil</p>
        <h1>Najděte správné dotace pro sebe</h1>
        <p className="profile-page__lead">
          Tato stránka vás provede dvěma kroky: typ podnikatele a lokality.
          Každý krok je volitelný — můžete přeskočit krok a přidat informace
          později.
        </p>
      </div>

      <form className="profile-form" onSubmit={handleSubmit}>
        <div className="profile-form__step-indicator" aria-hidden="true">
          <span className={`profile-form__dot ${step >= 0 ? "profile-form__dot--active" : ""}`}>1</span>
          <span className="profile-form__dot-separator" aria-hidden="true">→</span>
          <span className={`profile-form__dot ${step >= 1 ? "profile-form__dot--active" : ""}`}>2</span>
          <span className="profile-form__dot-separator" aria-hidden="true">→</span>
          <span className={`profile-form__dot ${step >= 2 ? "profile-form__dot--active" : ""}`}>3</span>
        </div>

        <div className="profile-page__live-status">
          <span id="profile-live" className="profile-page__live-status-text" aria-live="polite">
            {step === 0 ? "Zvolte typ podnikatele" : step === 1 ? "Vyberte lokality" : "Profil byl uložen"}
          </span>
        </div>

        {step === 0 ? renderStep0() : step === 1 ? renderStep1() : renderStep2()}
      </form>

      <div className="profile-page__footer">
        <p className="profile-page__footer-note">
          Při zadávání IČO použijte pouze veřejně dostupné údaje. Nemusíte zadávat
          IČO — můžete ho přidat později.
        </p>
      </div>
    </div>
  );
}
