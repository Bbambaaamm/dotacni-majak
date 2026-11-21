import { describe, expect, test } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { EmptyState } from "./EmptyState";

function render(el: React.ReactElement): string {
  return renderToStaticMarkup(el);
}

describe("EmptyState", () => {
  test("renders role=status for screen reader announcement", () => {
    const html = render(
      React.createElement(EmptyState, { title: "Žádné výsledky" }),
    );
    expect(html).toContain('role="status"');
    expect(html).toContain("Žádné výsledky");
  });

  test("icon is aria-hidden (text conveys meaning, not color alone)", () => {
    const html = render(
      React.createElement(EmptyState, { title: "Prázdný seznam" }),
    );
    expect(html).toContain('aria-hidden="true"');
  });

  test("renders description when provided", () => {
    const html = render(
      React.createElement(EmptyState, {
        title: "Žádné projekty",
        description: "Zatím nemáte žádné projekty.",
      }),
    );
    expect(html).toContain("Zatím nemáte žádné projekty.");
  });

  test("renders action when provided (Co mám udělat teď?)", () => {
    const html = render(
      React.createElement(EmptyState, {
        title: "Empty",
        action: React.createElement("button", { type: "button" }, "Přidat"),
      }),
    );
    expect(html).toContain("Přidat");
    expect(html).toContain("empty-state__action");
  });

  test("does not render action section when absent", () => {
    const html = render(
      React.createElement(EmptyState, { title: "Empty" }),
    );
    expect(html).not.toContain("empty-state__action");
  });

  test("title is always visible as text", () => {
    const html = render(
      React.createElement(EmptyState, { title: "No data" }),
    );
    expect(html).toContain("<h3");
    expect(html).toContain("No data");
  });
});