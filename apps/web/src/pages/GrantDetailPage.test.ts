import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { formatMinorMoney } from "../lib/sharedProject";
import { ChangeEventDate, DetailMetadataDate, formatMinor, fundingSummary, SourceDeadline, SourceObservation, statusLabel } from "./GrantDetailPage";
import type { GrantFundingScenarioDetail } from "../lib/grantDetailApi";

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
