export type ExportVerification =
  | "VERIFIED"
  | "NEEDS_INFORMATION"
  | "NEEDS_REVIEW";

export interface ExportEvidence {
  label: string;
  url: string;
  document?: string | null;
  pageOrSection?: string | null;
  checkedAt: string;
}

export interface ExportSummary {
  generatedAt: string;
  projectTitle: string;
  grantTitle: string;
  provider: string;
  statusLabel: string;
  verification: ExportVerification;
  relevanceSummary: string;
  eligibilitySummary: string;
  financeSummary: readonly string[];
  nextSteps: readonly string[];
  evidence: readonly ExportEvidence[];
  disclaimer: string;
  fixtureNotice?: string | null;
}

export function validateExportSummary(summary: ExportSummary): ExportSummary {
  if (!summary.projectTitle.trim()) throw new Error("Export potřebuje název projektu.");
  if (!summary.grantTitle.trim()) throw new Error("Export potřebuje název výzvy.");
  if (!summary.provider.trim()) throw new Error("Export potřebuje poskytovatele.");
  if (summary.evidence.length === 0) {
    throw new Error("Export nesmí tvrdit ověřené údaje bez provenance.");
  }
  for (const evidence of summary.evidence) {
    const url = new URL(evidence.url);
    if (url.protocol !== "https:") {
      throw new Error("Provenance URL musí používat HTTPS.");
    }
    if (!evidence.checkedAt) {
      throw new Error("Provenance musí obsahovat datum kontroly.");
    }
  }
  if (!summary.disclaimer.trim()) throw new Error("Export musí obsahovat disclaimer.");
  return summary;
}

export const demoExportSummary: ExportSummary = validateExportSummary({
  generatedAt: "2026-09-23T20:00:00+02:00",
  projectTitle: "Rekonstrukce tenisových kurtů",
  grantTitle: "Regiony 2026 — investice pod 10 mil. Kč",
  provider: "Národní sportovní agentura",
  statusLabel: "Historický testovací záznam — podání skončilo",
  verification: "NEEDS_INFORMATION",
  relevanceSummary:
    "Tematicky odpovídá technickému zhodnocení sportovní infrastruktury.",
  eligibilitySummary:
    "Známé podmínky zatím nelze uzavřít; chybí ověření vztahu k místu realizace.",
  financeSummary: [
    "Přesný výpočet podpory zatím není kompletní.",
    "Neznámý údaj se v exportu nevydává za 0 Kč ani za splněnou podmínku.",
  ],
  nextSteps: [
    "Ověřit vlastnictví nebo dlouhodobý vztah k tenisovému areálu.",
    "Načíst ověřené funding scenario a způsobilé náklady.",
    "Před rozhodnutím otevřít aktuální oficiální podmínky poskytovatele.",
  ],
  evidence: [
    {
      label: "Národní sportovní agentura — investiční dotace",
      url: "https://nsa.gov.cz/dotace-investicni/",
      checkedAt: "2026-09-23",
    },
  ],
  disclaimer:
    "Dotační maják není poskytovatelem podpory. Rozhodující jsou vždy aktuální oficiální podmínky příslušného poskytovatele.",
  fixtureNotice:
    "Tento export používá historický testovací záznam pro vývoj UX. Není určen jako aktuální doporučení k podání žádosti.",
});
