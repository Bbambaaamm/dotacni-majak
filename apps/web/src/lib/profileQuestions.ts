/**
 * Progressive profile question definitions for applicant onboarding.
 *
 * Set of questions depends on applicant type: obec / spolek / firma / občan.
 * Each question carries metadata for "why we ask" explanation and importance.
 *
 * IČO is optional: if provided and validates as Czech IC (8 digits, modulo-11 = 10),
 * it autofills legal type and ČR entity name. Set to null/empty/noValidation to hide
 * or skip validation.
 */

export type LegalType =
  | "obec"        // obec (municipality) — IČO-type entity
  | "spolek"      // občanský svaz / sdružení občanů
  | "firma"       // podnikající subjekt (OSVČ, s.r.o., a.s., …)
  | "obcan"       // občan (fyzická osoba)
  | null;         // not yet known / hidden

/** Lookup key — always a string, never null (null → common questions fallback). */
type LegalTypeKey = NonNullable<LegalType> | "unknown";

/** Applicant legal type is unknown or not yet selected. */
export const LEGAL_TYPE_UNKNOWN: LegalType = null;

/** Real Czech regions (kraje + hlavní město Praha) for geographic selection. */
export const CZ_REGIONS = [
  { id: "praha",   name: "Hlavní město Praha", short: "Praha" },
  { id: "jc",      name: "Jihočeský kraj",      short: "Jihočeský" },
  { id: "kc",      name: "Karlovarský kraj",     short: "Karlovarský" },
  { id: "li",      name: "Liberecký kraj",       short: "Liberecký" },
  { id: "us",      name: "Ústecký kraj",         short: "Ústecký" },
  { id: "st",      name: "Středočeský kraj",     short: "Středočeský" },
  { id: "pl",      name: "Plzeňský kraj",        short: "Plzeňský" },
  { id: "jl",      name: "Jihomoravský kraj",    short: "Jihomoravský" },
  { id: "ol",      name: "Olomoucký kraj",       short: "Olomoucký" },
  { id: "zr",      name: "Zlinský kraj",         short: "Zlinský" },
  { id: "vm",      name: "Moravskoslezský kraj", short: "Moravskoslezský" },
  { id: "ms",      name: "Mitteleuropa (historické Moravy a Slezska)", short: "M.S. (M</em>)" },
  { id: "zs",      name: "Západočeský kraj",    short: "Západočeský" },
  { id: "ji",      name: "Jihomoravský kraj – regionální potvrzení", short: "JMK" },
] as const;

export const JUDICIAL_REGIONS = [
  {
    id: "praha",
    name: "Městský soud Praha",
    short: "MS Praha",
    regionId: "praha",
  },
  {
    id: "brno",
    name: "Městský soud Brno",
    short: "MS Brno",
    regionId: "jc",
  },
  {
    id: "jl",
    name: "Městský soud Jihlava",
    short: "MS Jihlava",
    regionId: "jc",
  },
  {
    id: "pl",
    name: "Městský soud Plzeň",
    short: "MS Plzeň",
    regionId: "pl",
  },
  {
    id: "us",
    name: "Městský soud Ústí n.L.",
    short: "MS Ústí n.L.",
    regionId: "us",
  },
  {
    id: "li",
    name: "Městský soud Liberec",
    short: "MS Liberec",
    regionId: "li",
  },
  {
    id: "mr",
    name: "Městský soud Mladá Boleslav",
    short: "MS Mladá Boleslav",
    regionId: "st",
  },
  {
    id: "cz",
    name: "Městský soud České Budějovice",
    short: "MS Č.Budějovice",
    regionId: "jc",
  },
  {
    id: "ol",
    name: "Městský soud Olomouc",
    short: "MS Olomouc",
    regionId: "ol",
  },
  {
    id: "zl",
    name: "Městský soud Zlín",
    short: "MS Zlín",
    regionId: "zr",
  },
  {
    id: "om",
    name: "Městský soud Ostrava",
    short: "MS Ostrava",
    regionId: "ms",
  },
  {
    id: "zp",
    name: "Městský soud Znojmo",
    short: "MS Znojmo",
    regionId: "jc",
  },
  {
    id: "sk",
    name: "Městský soud Šumperk",
    short: "MS Šumperk",
    regionId: "ol",
  },
] as const;

/** Whether a string looks like a Czech IČO: 8 digits, last digit valid (modulo 11 = 10). */
export function looksLikeCzechICO(value: string): boolean {
  const trimmed = value.replace(/\s+/g, "");
  if (!/^\d{8}$/.test(trimmed)) return false;
  let sum = 0;
  for (let i = 0; i < 7; i += 1) {
    sum += Number(trimmed[i]) * (8 - i);
  }
  const checkDigit = sum % 11;
  // modulo 11 checksum: if remainder < 10, last digit must equal remainder + 10
  // if remainder >= 10, last digit must be 0
  return Number(trimmed[7]) === (checkDigit < 10 ? checkDigit + 10 : 0);
}

export function isICOValid(ico: string): ico is string {
  return looksLikeCzechICO(ico);
}

export function validateICO(ico: string): string | null {
  if (!ico) return null;
  const trimmed = ico.replace(/\s+/g, "");
  if (!/^\d{8}$/.test(trimmed)) {
    return "IČO musí mít osmi číslic";
  }
  if (!isICOValid(trimmed)) {
    return "IČO nevyhovuje kontrolnímu součtu — zkontrolujte zadání";
  }
  return null; // valid
}

// ─── Profile question definitions ──────────────────────────────────────────────

export interface ProfileQuestionDef {
  /** Internal key — unique per applicant type; used for storage and tracking. */
  key: string;
  /** Human-readable label shown next to the input. */
  label: string;
  /** Plain-language explanation of WHY the question is being asked (visible to user). */
  why: string;
  /** Whether this question is currently required at the UI level. */
  required: boolean;
  /** Help text shown below the input (e.g. validation hints). */
  help?: string;
  /** Hint shown in input placeholder. */
  placeholder?: string;
  /** Optional min/max length for text inputs. */
  minLength?: number;
  maxLength?: number;
  /** Whether this question should disappear when key is empty (progressive). */
  progressive?: boolean;
}

// Questions common to all applicant types
const COMMON_QUESTIONS: ProfileQuestionDef[] = [
  {
    key: "fullName",
    label: "Jak se jmenujete?",
    why: "Pro vyplňování formulářů budeme přiřazovat vaše jméno k vašim odpovědím, aby byly vázané na vás.",
    required: true,
    minLength: 2,
    maxLength: 120,
    progressive: true,
  },
  {
    key: "email",
    label: "E-mail",
    why: "Na tento e-mail nám pošleme potvrzení o registraci.",
    required: true,
    progressive: true,
    placeholder: "jmeno.prijmeni@priklad.cz",
    maxLength: 320,
  },
  {
    key: "ico",
    label: "IČO (volitelné)",
    why: "Pokud máte veřejně číslo IČO, můžeme naše doporučení omezit na programy, které odpovídají vašemu statusu. IČO je veřejný údaj, který umožňuje přesnější ověření.",
    required: false,
    progressive: true,
    placeholder: "např. 01234567",
    maxLength: 8,
  },
  {
    key: "legalType",
    label: "Typ podnikatele",
    why:
      "Různé typy subjektů (občan, firma, obec, spolek) mají různé možnosti dotací a specifické požadavky. Zvolený typ nám pomůže zobrazit jen ty programy, které vám mohou vyhovovat.",
    required: true,
    progressive: true,
  },
  {
    key: "region",
    label: "Kraj / město",
    why: "Některé dotace jsou určeny pouze pro určité kraje nebo prostřednictvím nich reálně fungují, takže na základě vašeho kraje můžeme omezit doporučení na programy, které jsou skutečně dostupné pro vás.",
    required: true,
    progressive: true,
  },
  {
    key: "districtId",
    label: "Okres / správní obvod",
    why: "Některé dotace fungují na úrovni okresu nebo správního obvodu, takže znalost vašeho okresu nám umožní zobrazit programy, které jsou podle rozpočtu a scope dostupné pro váš okres.",
    required: false,
    progressive: true,
    placeholder: "např. Praha 1 / Praha 2 / …",
  },
];

// Questions specific to "obec" (municipality)
const MUNICIPALITY_QUESTIONS: ProfileQuestionDef[] = [
  ...COMMON_QUESTIONS,
  {
    key: "mayorName",
    label: "Jméno starosty",
    why:
      "Pro verejně podnikající obce potřebujeme jméno představitele pro účely podpisu a zasílání doporučení.",
    required: false,
    progressive: true,
    maxLength: 120,
  },
  {
    key: "municipalityName",
    label: "Název obce",
    why:
      "Název obce je potřebný pro účely podpisu, pro zobrazení aktuální podpisové přijímací hodnoty a pro účely generování doporučení a tvorby podkladů.",
    required: true,
    minLength: 2,
    maxLength: 120,
  },
  {
    key: "population",
    label: "Počet obyvatel",
    why:
      "Počet obyvatel nám pomáhá vybrat programy podle velikosti obce a také určí přijímací hodnoty.",
    required: false,
    progressive: true,
    minLength: 1,
    maxLength: 9,
    placeholder: "např. 5750",
  },
  {
    key: "district",
    label: "Okres",
    why:
      "Některé dotace fungují na úrovni okresu nebo správního obvodu, takže znalost vašeho okresu nám umožní zobrazit programy, které jsou podle rozpočtu a scope dostupné pro váš okres.",
    required: true,
    progressive: true,
    placeholder: "např. Praha / Brno / Jihlava",
  },
];

// Questions specific to "spolek"
const ASSOCIATION_QUESTIONS: ProfileQuestionDef[] = [
  ...COMMON_QUESTIONS,
  {
    key: "associationName",
    label: "Název sdružení",
    why: "Název sdružení je potřebný pro účely podpisu a pro účely zobrazení doporučení.",
    required: true,
    minLength: 2,
    maxLength: 120,
  },
  {
    key: "seatRegion",
    label: "Sídlo",
    why:
      "Některé dotace jsou určeny pouze pro určité kraje nebo prostřednictvím nich reálně fungují, takže na základě vámi vybraného sídla můžeme omezit doporučení na programy dostupné pro váš kraj.",
    required: true,
    progressive: true,
    placeholder: "např. Praha",
  },
  {
    key: "foundationYear",
    label: "Rok založení",
    why:
      "Rok založení sdružení je podstatný pro určení, zda sdružení splňuje podmínku minimalního trvání podnikání (např. 3 roky) nebo ostatní speciální podmínky.",
    required: false,
    progressive: true,
    minLength: 4,
    maxLength: 4,
    placeholder: "např. 2018",
  },
  {
    key: "boardPresident",
    label: "Jméno předsedy",
    why:
      "Pro sdružení potřebujeme jméno předsedy pro účely podpisu a zasílání doporučení.",
    required: false,
    progressive: true,
    maxLength: 120,
  },
];

// Questions specific to "firma"
const FIRM_QUESTIONS: ProfileQuestionDef[] = [
  ...COMMON_QUESTIONS,
  {
    key: "firmName",
    label: "Název firmy",
    why:
      "Název firmy nám umožňuje zobrazit doporučení, která se vztahují na vaši firmu, a také částečně vyplnit formuláře, které budete potřebovat.",
    required: true,
    minLength: 2,
    maxLength: 160,
    progressive: true,
  },
  {
    key: "seatRegion",
    label: "Sídlo firmy",
    why:
      "Některé dotace jsou určeny pouze pro určité kraje nebo prostřednictvím nich reálně fungují, takže na základě vašeho sídla můžeme omezit doporučení na programy dostupné pro váš kraj.",
    required: true,
    progressive: true,
    placeholder: "např. Praha",
  },
  {
    key: "firmSize",
    label: "Počet zaměstnanců",
    why:
      "Počet zaměstnanců je často jedním z omezení pro některé dotace (malé a střední podniky), takže na základě vašeho počtu zaměstnanců můžeme filtrovat doporučení na programy, které jsou pro vás dostupné.",
    required: false,
    progressive: true,
    minLength: 1,
    maxLength: 9,
    placeholder: "např. 42",
  },
];

// Questions specific to "občan"
const CITIZEN_QUESTIONS: ProfileQuestionDef[] = [
  ...COMMON_QUESTIONS,
  {
    key: "ownerAddress",
    label: "Zkratka (adresa / město)",
    why:
      "Některé dotace jsou určeny pouze pro určité kraje nebo prostřednictvím nich reálně fungují, takže na základě vámi vybraného města můžeme omezit doporučení na programy dostupné pro váš kraj.",
    required: true,
    progressive: true,
    maxLength: 120,
  },
  {
    key: "ownerCity",
    label: "Město rezidence",
    why:
      "Město bydliště občana je podstatné pro určení, zda občan splňuje podmínku rezidence pro daný program.",
    required: false,
    progressive: true,
    maxLength: 120,
  },
  {
    key: "professionalInterest",
    label: "Profesní zájem",
    why:
      "Profesní zájem občana nám pomáhá filtrovat doporučení na programy, které jsou pro figurátora a osoby podnikající samostatně dostupné.",
    required: false,
    progressive: true,
    maxLength: 120,
  },
];

/** Map of applicant type → all questions for that type (including common).
 *  Key is always a string; null (unknown type) maps to "unknown". */
export const applicantQuestionDefs: {
  [K in LegalTypeKey]: readonly ProfileQuestionDef[];
} = {
  obec: MUNICIPALITY_QUESTIONS,
  spolek: ASSOCIATION_QUESTIONS,
  firma: FIRM_QUESTIONS,
  obcan: CITIZEN_QUESTIONS,
  unknown: COMMON_QUESTIONS,
};

/** All questions for ALL types — used for schema/ID enumeration. */
export const allQuestionKeys: readonly string[] = [
  ...new Set([
    ...Object.values(applicantQuestionDefs).flat(),
  ].map((q) => q.key)),
];

/** Internal key lookup — converts LegalType to a key for the map.
 *  null/unknown → "unknown" key. */
function legalTypeKey(type: LegalType): LegalTypeKey {
  return type === null ? "unknown" : type;
}

/** Returns questions for a given legal type; falls back to common for unknown/null. */
export function questionsForType(type: LegalType): readonly ProfileQuestionDef[] {
  return applicantQuestionDefs[legalTypeKey(type)];
}
