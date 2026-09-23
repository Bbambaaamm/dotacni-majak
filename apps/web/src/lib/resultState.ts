export type ResultStateKind =
  | "NO_RESULTS"
  | "INELIGIBLE"
  | "UNKNOWN"
  | "SOURCE_UNAVAILABLE";

export interface ResultStateContent {
  kind: ResultStateKind;
  eyebrow: string;
  title: string;
  description: string;
  details: readonly string[];
  primaryLabel: string;
  primaryHref: string;
  secondaryLabel?: string;
  secondaryHref?: string;
  sourceLastSuccess?: string;
}

export function resultStateContent(
  kind: ResultStateKind,
): ResultStateContent {
  switch (kind) {
    case "NO_RESULTS":
      return {
        kind,
        eyebrow: "Teď není vhodná otevřená výzva",
        title: "Maják může hledat dál.",
        description:
          "Nemusíte se vracet každý týden. Uložte záměr a nové výzvy se s ním znovu porovnají.",
        details: [
          "Nezaměňujeme nulový výsledek za nemožnost financování.",
          "Plánované a budoucí výzvy mohou situaci změnit.",
        ],
        primaryLabel: "Pohlídat tento záměr",
        primaryHref: "/projekty",
        secondaryLabel: "Upravit záměr",
        secondaryHref: "/hledat",
      };
    case "INELIGIBLE":
      return {
        kind,
        eyebrow: "Tematicky odpovídá, ale podmínka nesedí",
        title: "Tato výzva pro vás podle známých pravidel není způsobilá.",
        description:
          "Ukazujeme konkrétní blocking podmínku, ne jen červený stav.",
        details: [
          "Výzva je určena pouze obcím.",
          "Váš testovací profil je sportovní spolek.",
        ],
        primaryLabel: "Zobrazit podobné možnosti",
        primaryHref: "/hledat",
        secondaryLabel: "Otevřít detail podmínky",
        secondaryHref: "/dotace/regiony-2026",
      };
    case "UNKNOWN":
      return {
        kind,
        eyebrow: "Chybí rozhodující údaj",
        title: "Potřebujeme ještě jednu informaci.",
        description:
          "Neznámý údaj nepovažujeme automaticky za splněný ani nesplněný.",
        details: [
          "Potřebujeme ověřit vztah k nemovitosti.",
          "Odpověď může změnit způsobilost u několika výzev.",
        ],
        primaryLabel: "Doplnit údaj",
        primaryHref: "/projekty",
        secondaryLabel: "Proč se ptáme?",
        secondaryHref: "/jak-to-funguje",
      };
    case "SOURCE_UNAVAILABLE":
      return {
        kind,
        eyebrow: "Zdroj je dočasně nedostupný",
        title: "Zobrazujeme poslední ověřená data.",
        description:
          "Výpadek zdroje nesmí způsobit zmizení nebo hromadné uzavření výzev.",
        details: [
          "Aktuálnost novějších změn teď neumíme potvrdit.",
          "Před rozhodnutím otevřete také oficiální zdroj.",
        ],
        primaryLabel: "Zobrazit stav zdrojů",
        primaryHref: "/pokryti",
        secondaryLabel: "Pokračovat s posledními daty",
        secondaryHref: "/hledat",
        sourceLastSuccess: "22. 9. 2026 03:18",
      };
  }
}

export function parseDemoResultState(
  value: string | null,
): ResultStateKind | null {
  switch (value) {
    case "no-results":
      return "NO_RESULTS";
    case "ineligible":
      return "INELIGIBLE";
    case "unknown":
      return "UNKNOWN";
    case "source-unavailable":
      return "SOURCE_UNAVAILABLE";
    default:
      return null;
  }
}
