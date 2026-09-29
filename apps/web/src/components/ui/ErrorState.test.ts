import { describe, expect, test } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ErrorState } from "./ErrorState";

function render(el: React.ReactElement): string {
  return renderToStaticMarkup(el);
}

describe("ErrorState", () => {
  test("renders role=alert for immediate screen reader announcement", () => {
    const html = render(
      React.createElement(ErrorState, { title: "Nastala chyba" }),
    );
    expect(html).toContain('role="alert"');
    expect(html).toContain("Nastala chyba");
  });

  test("icon is aria-hidden (text conveys the error, not color alone)", () => {
    const html = render(
      React.createElement(ErrorState, { title: "Chyba" }),
    );
    expect(html).toContain('aria-hidden="true"');
  });

  test("unknown variant surfaces ambiguity (UNKNOWN != FAIL invariant)", () => {
    const html = render(
      React.createElement(ErrorState, {
        title: "Nelze určit stav",
        description: "Data nejsou dostupná.",
        variant: "unknown",
      }),
    );
    expect(html).toContain("error-state--unknown");
    expect(html).toContain("Nelze určit stav");
    expect(html).toContain("Data nejsou dostupná.");
  });

  test("error variant uses definite error styling (no unknown class)", () => {
    const html = render(
      React.createElement(ErrorState, {
        title: "Selhání",
        variant: "error",
      }),
    );
    expect(html).toContain("error-state");
    expect(html).not.toContain("error-state--unknown");
  });

  test("renders retry action when provided (Co mám udělat teď?)", () => {
    const html = render(
      React.createElement(ErrorState, {
        title: "Chyba",
        action: React.createElement("button", { type: "button" }, "Zkusit znovu"),
      }),
    );
    expect(html).toContain("Zkusit znovu");
    expect(html).toContain("error-state__action");
  });

  test("description is optional", () => {
    const html = render(
      React.createElement(ErrorState, { title: "Chyba" }),
    );
    expect(html).toContain("error-state");
  });

  test("default variant is error", () => {
    const html = render(
      React.createElement(ErrorState, { title: "Default" }),
    );
    expect(html).not.toContain("error-state--unknown");
  });
});