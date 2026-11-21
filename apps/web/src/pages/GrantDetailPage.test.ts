import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { formatMinorMoney } from "../lib/sharedProject";
import { ChangeEventDate, ChangeStatusTransition, changeEventLabel, changeFieldLabel, changeSeverityLabel, DetailMetadataDate, formatMinor, fundingSummary, SourceDeadline, SourceObservation, statusLabel, vatRuleLabel } from "./GrantDetailPage";
import type { GrantChangeDetail, GrantFundingScenarioDetail } from "../lib/grantDetailApi";

describe("detail status labels", () => {
  it("renders accepted draft and archived statuses without implying an open application", () => {
    for (const status of ["DRAFT", "ARCHIVED"]) {
      expect(statusLabel(status)).not.toContain(status);
      expect(statusLabel(status)).toContain("příjem není potvrzen");
    }
  });
});

describe("detail grant amount bounds", () => {
  const scenario: GrantFundingScenarioDetail = {
    id: "scenario", name: "Synthetic", conditionGroupId: null, instrumentType: "GRANT",
    currencyCode: "CZK", supportRateMinBps: null, supportRateMaxBps: null,
    grantAmountMinMinor: null, grantAmountMaxMinor: null,
    projectCostMinMinor: null, projectCostMaxMinor: null, paymentMode: null,
    vatRule: null, advancePaymentAllowed: null, evidenceId: null,
  };

  it("does not turn a grant lower bound into a maximum", () => {
    expect(fundingSummary({ ...scenario, grantAmountMinMinor: 5000000 }))
      .toContain("min. 50 000");
    expect(fundingSummary({ ...scenario, grantAmountMinMinor: 5000000 }))
      .toContain("horní mez není uvedena");
  });

  it("shows both bounds when documented, and preserves unknown amounts", () => {
    expect(fundingSummary({ ...scenario, grantAmountMinMinor: 5000000, grantAmountMaxMinor: 10000000 }))
      .toMatch(/min\..*max\./);
    expect(fundingSummary(scenario)).toContain("není v normalizovaných datech uvedena");
  });
});

describe("detail VAT rule provenance", () => {
  it("quotes a documented scenario rule without treating it as personal tax advice", () => {
    expect(vatRuleLabel("DPH je nezpůsobilá pouze při možnosti odpočtu"))
      .toBe("Údaj ze scénáře: DPH je nezpůsobilá pouze při možnosti odpočtu. Ověřte u poskytovatele, zda platí pro váš projekt.");
  });

  it("keeps missing or blank rule unknown rather than inferring VAT recovery", () => {
    expect(vatRuleLabel(null)).toContain("Není doloženo");
    expect(vatRuleLabel("  ")).toBe(vatRuleLabel(null));
    expect(vatRuleLabel(null)).toContain("nevyvozujte");
  });
});

describe("detail currency minor units", () => {
  it.each([
    [1234, "JPY"],
    [1234, "KWD"],
    [1234, "CZK"],
  ])("displays %s minor units of %s using the currency exponent", (minor, currency) => {
    expect(formatMinor(minor, currency)).toBe(formatMinorMoney(minor, currency));
  });

  it("does not present unsafe amounts as verified major-unit money", () => {
    expect(formatMinor(Number.MAX_SAFE_INTEGER + 1, "CZK"))
      .toBe("Částku nelze bezpečně zobrazit; ověřte ji u poskytovatele.");
    expect(formatMinor(1234, "not-a-currency"))
      .toBe("Částku nelze bezpečně zobrazit; ověřte ji u poskytovatele.");
    expect(formatMinor(null, "CZK")).toBe("Není uvedeno");
  });
});

describe("detail source deadline", () => {
  it.each([
    [null, false],
    ["2027-06-01", false],
    ["2027-06-01T12:30:00z", false],
    ["datum-nejasne", true],
    ["2027-02-30T12:30:00Z", true],
    ["2027-06-01T12:30:00", true],
  ])("keeps %s and marks caution %s", (value, caution) => {
    const html = renderToStaticMarkup(createElement(SourceDeadline, { value }));
    expect(html).toContain(value ? value.slice(0, 10) : "Není uvedeno");
    expect(html.includes('role="note"')).toBe(caution);
    if (caution) expect(html).toContain("ověřte jej v oficiálním zdroji");
  });
});

describe("detail metadata dates", () => {
  it.each([
    ["2026-09-26T20:00:00Z", false],
    ["2026-09-26", false],
    ["2026-02-30T12:00:00Z", true],
    ["datum-nejasne", true],
  ])("preserves %s without implying invalid metadata is verified", (value, caution) => {
    const html = renderToStaticMarkup(createElement(DetailMetadataDate, {
      value, label: "stažení dokumentu",
    }));
    expect(html.includes('role="note"')).toBe(caution);
    if (caution) {
      expect(html).toContain(value);
      expect(html).toContain("nepovažujte jej za doloženou aktuálnost");
    }
  });
});

describe("detail change-event label", () => {
  it.each([
    ["DEADLINE_CHANGED", "Změna termínu výzvy"],
    ["STATUS_CHANGED", "Změna stavu výzvy"],
    ["APPLICANT_RULE_CHANGED", "Změna podmínek pro žadatele"],
    ["FUNDING_CHANGED", "Změna podmínek financování"],
    ["BUDGET_CHANGED", "Změna finančních limitů projektu"],
    ["SUPPORTED_ACTIVITY_CHANGED", "Změna podporovaných aktivit"],
    ["REQUIREMENT_CHANGED", "Změna požadavků výzvy"],
    ["DOCUMENT_CHANGED", "Změna dokumentu výzvy"],
    ["OTHER", "Jiná zaznamenaná změna"],
  ])("explains canonical %s without exposing an internal enum", (type, label) => {
    expect(changeEventLabel(type)).toBe(label);
  });

  it("does not guess a meaning for an unknown type", () => {
    expect(changeEventLabel("NEW_TYPE")).toContain("Neznámý typ změny");
    expect(changeEventLabel("NEW_TYPE")).toContain("ověřte jej v oficiálním zdroji");
    expect(changeEventLabel("NEW_TYPE")).not.toContain("NEW_TYPE");
  });
});

describe("detail change field presentation", () => {
  it("labels only recognized canonical fields without exposing their storage path", () => {
    expect(changeFieldLabel("status")).toBe("Stav výzvy");
    expect(changeFieldLabel("/status")).toBe("Stav výzvy");
    expect(changeFieldLabel("/submission_close_at")).toBe("Ukončení příjmu žádostí");
    expect(changeFieldLabel("submission_close_at")).toBe("Ukončení příjmu žádostí");
  });

  it("does not publish arbitrary internal paths or infer a meaning for them", () => {
    expect(changeFieldLabel("/internal/unknown/field"))
      .toBe("Jiný údaj (přesné pole zde není ověřeno)");
    expect(changeFieldLabel("/e2e/unverified-date")).not.toContain("/e2e/");
    expect(changeFieldLabel(null)).toBeNull();
  });
});

describe("detail change severity", () => {
  it.each([
    ["CRITICAL", "Kritická"],
    ["IMPORTANT", "Důležitá"],
    ["INFORMATIONAL", "Informativní"],
    ["EDITORIAL", "Redakční"],
  ])("explains canonical severity %s without exposing an internal enum", (severity, label) => {
    expect(changeSeverityLabel(severity)).toBe(label);
  });

  it("does not interpret an unknown severity", () => {
    expect(changeSeverityLabel("NEW_SEVERITY")).toBe("Závažnost není známa; ověřte změnu u poskytovatele");
  });
});

describe("recorded status transitions", () => {
  const change: GrantChangeDetail = {
    id: "change", changeType: "STATUS_CHANGED", severity: "IMPORTANT", fieldPath: "status",
    oldValue: "CLOSED", newValue: "OPEN", createdAt: "2026-09-26T20:00:00Z",
  };
  const render = (value: GrantChangeDetail) => renderToStaticMarkup(createElement(ChangeStatusTransition, { change: value }));

  it("explains a canonical transition as historical, not current eligibility", () => {
    const html = render(change);
    expect(html).toContain("Dříve zaznamenáno: Příjem žádostí skončil");
    expect(html).toContain("nově zaznamenáno: Otevřeno v zachycené verzi");
    expect(html).toContain("nikoli potvrzení současného stavu");
  });

  it.each([
    { oldValue: null }, { newValue: { status: "OPEN" } },
    { oldValue: "UNRECOGNIZED" }, { newValue: "UNRECOGNIZED" },
  ])("fails closed on missing or unrecognized values (%o)", (override) => {
    const html = render({ ...change, ...override });
    expect(html).toContain("nelze z tohoto záznamu bezpečně vyložit");
    expect(html).not.toContain("nově zaznamenáno");
    expect(html).not.toContain("UNRECOGNIZED");
  });

  it("does not interpret unrelated event types or fields", () => {
    expect(render({ ...change, changeType: "OTHER" })).toBe("");
    expect(render({ ...change, fieldPath: "status.note" })).toBe("");
  });
});

describe("detail change-event date", () => {
  it.each([
    ["2026-09-26T20:00:00Z", false],
    ["2026-09-26", false],
    ["2026-02-30T12:00:00Z", true],
    ["datum-nejasne", true],
  ])("does not present %s as a verified event date (caution %s)", (value, caution) => {
    const html = renderToStaticMarkup(createElement(ChangeEventDate, { value }));
    expect(html.includes('role="note"')).toBe(caution);
    if (caution) {
      expect(html).toContain(value);
      expect(html).toContain("Pořadí změn ani datum události nejsou ověřené");
    }
  });
});

describe("detail source observation", () => {
  const source = {
    sourceCode: "official", sourceName: "Zdroj", canonicalUrl: "https://example.org",
    lastSeenAt: "2026-10-01T23:30:00-10:00", presenceState: "SEEN",
  };

  it("selects the latest instant but does not silently ignore an unverified source date", () => {
    const html = renderToStaticMarkup(createElement(SourceObservation, { sources: [
      source,
      { ...source, sourceCode: "other", lastSeenAt: "2026-10-02T00:30:00+14:00" },
      { ...source, sourceCode: "malformed", lastSeenAt: "2026-02-30T12:00:00Z" },
    ] }));
    expect(html).toContain("1. října 2026");
    expect(html).toContain('role="note"');
    expect(html).toContain("nemusí být nejnovější");
  });

  it("does not promote an unparseable observation to a confirmed recency", () => {
    const html = renderToStaticMarkup(createElement(SourceObservation, { sources: [
      { ...source, lastSeenAt: "datum-nejasne" },
    ] }));
    expect(html).toContain("Není doložena");
    expect(html).toContain('role="note"');
    expect(renderToStaticMarkup(createElement(SourceObservation, { sources: [] }))).toBe("Není doložena");
    expect(renderToStaticMarkup(createElement(SourceObservation, { sources: [source] })))
      .not.toContain('role="note"');
  });
});
