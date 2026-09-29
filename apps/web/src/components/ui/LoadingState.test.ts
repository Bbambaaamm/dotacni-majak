import { describe, expect, test } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { LoadingState } from "./LoadingState";

function render(el: React.ReactElement): string {
  return renderToStaticMarkup(el);
}

describe("LoadingState", () => {
  test("renders role=status with aria-live polite for screen readers", () => {
    const html = render(React.createElement(LoadingState, { label: "Načítám" }));
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
  });

  test("shows visible text label (not spinner-only)", () => {
    const html = render(
      React.createElement(LoadingState, { label: "Načítám výsledky" }),
    );
    expect(html).toContain("Načítám výsledky");
  });

  test("spinner is aria-hidden so screen reader reads label only", () => {
    const html = render(React.createElement(LoadingState, { label: "Načítám" }));
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain("loading-state__spinner");
  });

  test("uses aria-label as fallback when no visible label", () => {
    const html = render(React.createElement(LoadingState, { label: "" }));
    expect(html).toContain('aria-label=');
  });

  test("default label is Czech", () => {
    const html = render(React.createElement(LoadingState));
    expect(html).toContain("Načítám");
  });

  test("respects size variants (sm/md/lg)", () => {
    const sm = render(React.createElement(LoadingState, { size: "sm" }));
    expect(sm).toContain("loading-state--sm");

    const md = render(React.createElement(LoadingState, { size: "md" }));
    expect(md).toContain("loading-state\"");

    const lg = render(React.createElement(LoadingState, { size: "lg" }));
    expect(lg).toContain("loading-state--lg");
  });
});
