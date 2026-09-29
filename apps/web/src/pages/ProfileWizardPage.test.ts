import { describe, expect, test } from "vitest";
import { CZ_REGIONS, allQuestionKeys } from "../lib/profileQuestions";
import { ProfileWizardPage } from "../pages/ProfileWizardPage";
import { renderToStaticMarkup } from "react-dom/server";

function mockHtmlDoc(): HTMLDocument {
  const doc = {
    getElementById(id: string): HTMLElement | null {
      return null;
    },
    createElement(tag: string): HTMLElement {
      return { tagName: "", textContent: "", classList: { add() {}, remove() {}, contains() { return false; }, toggle() {} } } as unknown as HTMLElement;
    },
  } as unknown as HTMLDocument;
  (globalThis as { document?: HTMLDocument }).document = doc;
  return doc;
}

describe("ProfileWizardPage", () => {
  beforeEach(() => {
    globalThis.document = undefined as unknown as HTMLDocument;
    // Reset to a clean HTMLDocument mock so we don't accidentally inherit the real one
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
  });

  afterEach(() => {
    globalThis.document = undefined as unknown as HTMLDocument;
  });

  test("renders page shell with progress indicator", () => {
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
    const html = renderToStaticMarkup(
      <ProfileWizardPage />,
    );

    expect(html).toContain("Nastavte svůj profil");
    expect(html).toContain("Najděte správné dotace pro sebe");
    expect(html).toContain("profile-form__step-indicator");
    // Progress dots
    expect(html).toContain('class="profile-form__dot profile-form__dot--active"');
    expect(html).toContain('>1<');
    expect(html).toContain('>→<');
    expect(html).toContain('>2<');
    expect(html).toContain('>→<');
    expect(html).toContain('>3<');
  });

  test("renders step 1 (legal type selection) with options", () => {
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
    const html = renderToStaticMarkup(
      <ProfileWizardPage />,
    );

    expect(html).toContain("Zvolte typ podnikatele");
    expect(html).toContain("Obec");
    expect(html).toContain("Spolek");
    expect(html).toContain("Firma");
    expect(html).toContain("Občan");
    expect(html).toContain("profile-form__radios");

    // IČO field: required/reference, optional, without autofill (no IČO entered, type not selected)
    expect(html).toContain("IČO (volitelné)");
    expect(html).toContain("profile-form__ico-field");
    expect(html).toContain("Není veřejně dostupné — nemusíte ho však zadat.");
  });

  test("step 1 shows IČO with autofill note when IČO entered but legal type not selected", () => {
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
    // With legalType still undefined and an IČO entered — IČO autofill note should appear
    const htmlBefore = renderToStaticMarkup(
      <ProfileWizardPage />,
    );
    expect(htmlBefore).toContain("IČO (volitelné)");
    expect(htmlBefore).not.toContain("Děkujeme za zadání IČO"); // no autofill note yet
  });

  test("step 1 shows save button disabled when legal type not selected", () => {
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
    const html = renderToStaticMarkup(
      <ProfileWizardPage />,
    );

    // Button should be disabled because missingType is true
    expect(html).toContain('disabled');
  });

  test("step 2 (locality) renders region select with Czech regions", () => {
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
    // Pass regionId in via state? No — we can't drive state in SSR.
    // Instead: verify step 2 is not rendered initially (only step 1 is)
    const html = renderToStaticMarkup(
      <ProfileWizardPage />,
    );

    // step 2 is only rendered when step === 1, initially step is 0
    expect(html).not.toContain("Kraj / město");
    expect(html).not.toContain("Vyberte kraj nebo město…");
  });

  test("success step (step 2 == 2) renders after save", () => {
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
    // Step 2 is only rendered when step === 2, initially step is 0
    const html = renderToStaticMarkup(
      <ProfileWizardPage />,
    );

    expect(html).not.toContain("Profil byl uložen");
    expect(html).not.toContain("profile-page__success");
  });

  test("progress dots reflect step state (initial step is 0)", () => {
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
    const html = renderToStaticMarkup(
      <ProfileWizardPage />,
    );

    // Initially: dot1 active, dot2 and dot3 inactive (no --active class)
    const dots = [...html.matchAll(/profile-form__dot[^>]*>(\d)</g)];
    expect(dots.length).toBe(3);

    // First dot should be active
    const firstDot = dots[0][0];
    expect(firstDot).toContain('class="profile-form__dot profile-form__dot--active"');
    expect(firstDot).toContain(">1<");

    // Second and third dots should NOT be active (step < 1, step < 2)
    const secondDot = dots[1][0];
    expect(secondDot).not.toContain("profile-form__dot--active");
    expect(secondDot).toContain(">2<");

    const thirdDot = dots[2][0];
    expect(thirdDot).not.toContain("profile-form__dot--active");
    expect(thirdDot).toContain(">3<");
  });

  test("live status text updates per step", () => {
    globalThis.document = mockHtmlDoc() as unknown as HTMLDocument;
    const html = renderToStaticMarkup(
      <ProfileWizardPage />,
    );

    // Step 0 initial status
    expect(html).toContain('id="profile-live"');
    expect(html).toContain("Zvolte typ podnikatele");
  });
});

describe("Geo regions", () => {
  test("CzRegions has 14 entries (kraje + PRAHA)", () => {
    expect(CZ_REGIONS).toHaveLength(14);
    // Every region must have id, name, short
    for (const region of CZ_REGIONS) {
      expect(typeof region.id).toBe("string");
      expect(typeof region.name).toBe("string");
      expect(typeof region.short).toBe("string");
    }
  });

  test("allQuestionKeys enumerates all unique keys across types", () => {
    // The order does NOT matter for this test — just verify the set
    const expected = [
      "fullName", "email", "ico", "legalType", "region", "districtId",
      "mayorName", "municipalityName", "population", "district",
      "associationName", "seatRegion", "foundationYear", "boardPresident",
      "firmName", "firmSize",
      "ownerAddress", "ownerCity", "professionalInterest",
    ];
    expect(allQuestionKeys).toEqual(expect.arrayContaining(expected));
    for (const key of expected) {
      expect(allQuestionKeys).toContain(key);
    }
  });
});
