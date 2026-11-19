import { type FormEvent, useState } from "react";

import { Button } from "../components/Button";
import {
  APPLICANT_PROFILE_STORAGE_KEY,
  createApplicantProfile,
  LocalApplicantProfileStore,
  type ApplicantProfile,
  type ApplicantProfileType,
  type FieldSource,
} from "../lib/applicantProfile";
import "./profile.css";

const applicantTypes: readonly [ApplicantProfileType, string][] = [
  ["UNKNOWN", "Zatím nevím"],
  ["NATURAL_PERSON", "Fyzická osoba"],
  ["SELF_EMPLOYED", "OSVČ"],
  ["BUSINESS", "Firma"],
  ["MUNICIPALITY", "Obec"],
  ["REGION", "Kraj"],
  ["ASSOCIATION", "Spolek"],
  ["SPORTS_CLUB", "Sportovní klub"],
  ["NONPROFIT", "Nezisková organizace"],
  ["SCHOOL", "Škola"],
  ["CONTRIBUTORY_ORGANISATION", "Příspěvková organizace"],
  ["HOA", "SVJ"],
  ["COOPERATIVE", "Družstvo"],
  ["AGRICULTURAL_ENTITY", "Zemědělský subjekt"],
  ["RESEARCH_ORGANISATION", "Výzkumná organizace"],
  ["OTHER", "Jiný typ"],
];

function loadLocalProfile(): { profile: ApplicantProfile | null; blocked: boolean; error: boolean } {
  try {
    const storage = window.localStorage;
    const raw = storage.getItem(APPLICANT_PROFILE_STORAGE_KEY);
    const profile = new LocalApplicantProfileStore(storage).get();
    return { profile, blocked: raw !== null && profile === null, error: false };
  } catch {
    return { profile: null, blocked: true, error: true };
  }
}

export function ProfilePage() {
  const [initial] = useState(loadLocalProfile);
  const [profile, setProfile] = useState(initial.profile);
  const [blocked, setBlocked] = useState(initial.blocked);
  const [message, setMessage] = useState(initial.error ? "Úložiště prohlížeče není dostupné. Profil nelze bezpečně načíst." : "");
  const [exported, setExported] = useState("");
  const [importText, setImportText] = useState("");

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    const fields = new FormData(event.currentTarget);
    const applicantType = String(fields.get("applicantType")) as ApplicantProfileType;
    const populationInput = String(fields.get("population") ?? "").trim();
    const municipalityCode = String(fields.get("municipalityCode") ?? "").trim();
    const population = populationInput ? Number(populationInput) : null;
    if (population !== null && (!Number.isSafeInteger(population) || population < 0)) {
      setMessage("Počet obyvatel musí být nezáporné celé číslo.");
      return;
    }
    if (municipalityCode && !/^[0-9]{6}$/.test(municipalityCode)) {
      setMessage("Kód obce musí obsahovat šest číslic.");
      return;
    }
    const previousPopulation = profile?.municipalityPopulation ?? null;
    const typeChanged = profile?.applicantType !== applicantType;
    const codeChanged = (municipalityCode || null) !== (profile?.municipalityCode ?? null);
    const populationChanged = population !== previousPopulation;
    if (codeChanged && previousPopulation !== null && !populationChanged) {
      setMessage("Při změně obce vymažte starý počet obyvatel nebo zadejte nový. Nepřenášíme starý údaj na jinou obec.");
      return;
    }
    const now = new Date().toISOString();
    const source: FieldSource = {
      sourceKind: "USER", sourceReference: null, observedAt: now,
      verifiedAt: null, verificationStatus: "USER_DECLARED", evidenceId: null,
    };
    const fieldSources = { ...profile?.fieldSources };
    if (typeChanged) {
      fieldSources.applicantType = source;
      delete fieldSources.applicantTypeId;
    }
    if (codeChanged) {
      for (const key of ["municipalityName", "regionCode", "seatGeographyId"] as const) {
        delete fieldSources[key];
      }
    }
    if (populationChanged || codeChanged) delete fieldSources.municipalityPopulationAsOf;
    if (populationChanged) {
      if (population === null) delete fieldSources.municipalityPopulation;
      else fieldSources.municipalityPopulation = source;
    }
    if ((municipalityCode || null) !== profile?.municipalityCode) {
      if (!municipalityCode) delete fieldSources.municipalityCode;
      else fieldSources.municipalityCode = source;
    }
    const next = createApplicantProfile({
      ...profile,
      id: profile?.id ?? crypto.randomUUID(), applicantType,
      applicantTypeId: typeChanged ? null : profile?.applicantTypeId,
      municipalityCode: municipalityCode || null,
      municipalityName: codeChanged ? null : profile?.municipalityName,
      regionCode: codeChanged ? null : profile?.regionCode,
      seatGeographyId: codeChanged ? null : profile?.seatGeographyId,
      municipalityPopulation: population,
      municipalityPopulationAsOf: populationChanged || codeChanged
        ? null : profile?.municipalityPopulationAsOf,
      fieldSources,
      createdAt: profile?.createdAt ?? now,
    });
    try {
      const saved = new LocalApplicantProfileStore(window.localStorage).save(next);
      setProfile(saved);
      setExported("");
      setMessage("Profil je uložen pouze v tomto prohlížeči. Způsobilost tím zatím nebyla vyhodnocena.");
    } catch {
      setMessage("Profil se nepodařilo uložit. Původní data zůstávají v úložišti.");
    }
  }

  function importProfile() {
    if (blocked) return;
    try {
      const restored = new LocalApplicantProfileStore(window.localStorage).import(importText);
      if (!restored) {
        setMessage("Soubor profilu není platný nebo má nepodporovanou verzi. Nic se nezměnilo.");
        return;
      }
      setProfile(restored);
      setImportText("");
      setExported("");
      setMessage("Profil byl obnoven pouze v tomto prohlížeči.");
    } catch {
      setMessage("Obnovení selhalo: úložiště není dostupné. Původní data nebyla smazána.");
    }
  }

  function clear() {
    if (!window.confirm("Opravdu smazat místní profil na tomto zařízení? Tuto akci nelze vrátit.")) return;
    try {
      new LocalApplicantProfileStore(window.localStorage).clear();
      setProfile(null);
      setBlocked(false);
      setExported("");
      setMessage("Místní profil byl smazán. Serverová data ani projekty se tím nemění.");
    } catch {
      setMessage("Profil se nepodařilo smazat. Zkontrolujte nastavení úložiště.");
    }
  }

  return (
    <div className="profile-page">
      <header>
        <p className="eyebrow">Profil žadatele</p>
        <h1>Údaje pro posouzení výzev</h1>
        <p>Profil je na tomto zařízení. Neposílá se automaticky na server a sám o sobě nepotvrzuje způsobilost. Uvádějte jen údaje, které znáte.</p>
      </header>
      {blocked && <p role="alert" className="form-message">Uložená data nelze bezpečně přečíst. Nejsou automaticky smazána ani přepsána. Můžete je nejdřív zálohovat přes nástroje prohlížeče a pak výslovně smazat místní profil.</p>}
      <form className="profile-form" onSubmit={save} key={profile?.updatedAt ?? "empty"}>
        <h2>Co o žadateli víte?</h2>
        <label>Typ žadatele
          <select name="applicantType" defaultValue={profile?.applicantType ?? "UNKNOWN"}>
            {applicantTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>Kód obce (volitelné)
          <input name="municipalityCode" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} defaultValue={profile?.municipalityCode ?? ""} />
        </label>
        <label>Počet obyvatel obce (volitelné)
          <input name="population" type="number" min="0" step="1" defaultValue={profile?.municipalityPopulation ?? ""} />
        </label>
        <p>Tyto údaje jsou vámi uvedené, nikoli ověřené z ARES nebo ČSÚ. Pokud počet obyvatel neznáte, nechte pole prázdné (UNKNOWN).</p>
        <Button type="submit" disabled={blocked}>Uložit místně</Button>
      </form>
      <section className="profile-form" aria-labelledby="profile-data-title">
        <h2 id="profile-data-title">Moje místní data</h2>
        <div className="action-row">
          <Button variant="secondary" disabled={!profile || blocked} onClick={() => {
            try { setExported(new LocalApplicantProfileStore(window.localStorage).export()); }
            catch { setMessage("Export není dostupný. Ověřte úložiště prohlížeče."); }
          }}>Zobrazit export JSON</Button>
          <Button variant="tertiary" onClick={clear} disabled={!profile && !blocked}>Smazat místní profil</Button>
        </div>
        {exported && <label>Export profilu (obsahuje vámi uvedené údaje)
          <textarea readOnly rows={8} value={exported} onFocus={(event) => event.currentTarget.select()} />
        </label>}
        <label>Obnovit profil z JSON
          <textarea rows={5} value={importText} onChange={(event) => setImportText(event.target.value)} />
        </label>
        <Button variant="secondary" disabled={blocked || !importText.trim()} onClick={importProfile}>Obnovit místně</Button>
      </section>
      {message && <p className="form-message" role="status">{message}</p>}
      <p><a href="/projekty">Pokračovat k projektům</a> — další krok pro sledování výzvy.</p>
    </div>
  );
}
