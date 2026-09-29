import { describe, expect, test } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Breadcrumbs } from "./Breadcrumbs";
import { breadcrumbsForPathname } from "../lib/breadcrumbs";

function render(el: React.ReactElement): string {
  return renderToStaticMarkup(el);
}

describe("breadcrumbsForPathname", () => {
  test("home route returns single home item (no link)", () => {
    const items = breadcrumbsForPathname("/");
    expect(items).toEqual([{ label: "Domů" }]);
    expect(items[0].href).toBeUndefined();
  });

  test("search route has home + search trail", () => {
    const items = breadcrumbsForPathname("/hledat");
    expect(items).toHaveLength(2);
    expect(items[0]).toEqual({ label: "Domů", href: "/" });
    expect(items[1]).toEqual({ label: "Najít dotaci" });
  });

  test("projects route has home + projects", () => {
    const items = breadcrumbsForPathname("/projekty");
    expect(items[0].href).toBe("/");
    expect(items[1].label).toBe("Moje projekty");
    expect(items[1].href).toBeUndefined();
  });

  test("grant-detail route has three-level trail", () => {
    const items = breadcrumbsForPathname("/dotace/regiony-2026");
    expect(items).toHaveLength(3);
    expect(items[0]).toEqual({ label: "Domů", href: "/" });
    expect(items[1]).toEqual({ label: "Najít dotaci", href: "/hledat" });
    expect(items[2]).toEqual({ label: "Detail dotace" });
  });

  test("unknown route falls back to home + route label", () => {
    const items = breadcrumbsForPathname("/neexistent");
    expect(items).toHaveLength(2);
    expect(items[0]).toEqual({ label: "Domů", href: "/" });
    expect(items[1].label).toBeTruthy();
    expect(items[1].href).toBeUndefined();
  });

  test("last item never has href (it is the current page)", () => {
    for (const path of ["/", "/hledat", "/projekty", "/porovnat",
                         "/dotace/regiony-2026", "/pokryti", "/jak-to-funguje"]) {
      const items = breadcrumbsForPathname(path);
      expect(items[items.length - 1].href).toBeUndefined();
    }
  });

  test("all non-last items have href", () => {
    for (const path of ["/hledat", "/projekty", "/dotace/regiony-2026"]) {
      const items = breadcrumbsForPathname(path);
      for (let i = 0; i < items.length - 1; i++) {
        expect(items[i].href).toBeDefined();
      }
    }
  });
});

describe("Breadcrumbs component", () => {
  test("renders nav with aria-label Kolace", () => {
    const html = render(React.createElement(Breadcrumbs, {
      items: [{ label: "Domů", href: "/" }, { label: "Hledání" }],
    }));
    expect(html).toContain('aria-label="Kolace"');
    expect(html).toContain('<nav');
  });

  test("renders ol > li structure", () => {
    const html = render(React.createElement(Breadcrumbs, {
      items: [{ label: "Domů", href: "/" }, { label: "Aktuální" }],
    }));
    expect(html).toContain("<ol");
    expect(html).toContain("<li");
  });

  test("last item uses aria-current=page (not a link)", () => {
    const html = render(React.createElement(Breadcrumbs, {
      items: [{ label: "Domů", href: "/" }, { label: "Aktuální" }],
    }));
    expect(html).toContain('aria-current="page"');
    // Last item should be a span, not an <a>
    expect(html).toContain("<span");
  });

  test("non-last items are links with href", () => {
    const html = render(React.createElement(Breadcrumbs, {
      items: [{ label: "Domů", href: "/" }, { label: "Aktuální" }],
    }));
    expect(html).toContain('href="/"');
    expect(html).toContain("Domů");
    expect(html).toContain("Aktuální");
  });

  test("visible text is present (not icon-only)", () => {
    const html = render(React.createElement(Breadcrumbs, {
      items: [{ label: "Domů", href: "/" }, { label: "Najít dotaci" }],
    }));
    expect(html).toContain("Domů");
    expect(html).toContain("Najít dotaci");
  });

  test("returns null for empty items array", () => {
    const html = render(React.createElement(Breadcrumbs, { items: [] }));
    expect(html).toBe("");
  });

  test("renders single item (home only)", () => {
    const html = render(React.createElement(Breadcrumbs, {
      items: [{ label: "Domů" }],
    }));
    expect(html).toContain('aria-current="page"');
    expect(html).toContain("Domů");
    expect(html).not.toContain("href=");
  });

  test("works with breadcrumbsForPathname integration", () => {
    const items = breadcrumbsForPathname("/hledat");
    const html = render(React.createElement(Breadcrumbs, { items }));
    expect(html).toContain('aria-label="Kolace"');
    expect(html).toContain("Domů");
    expect(html).toContain("Najít dotaci");
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('href="/"');
  });
});
