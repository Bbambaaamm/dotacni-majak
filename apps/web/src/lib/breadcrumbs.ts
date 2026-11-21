import { resolveRoute, type RouteId } from "./routes";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

/**
 * Breadcrumb trail for each known route.
 *
 * The LAST item intentionally has no `href` — it is the current page
 * and is rendered with `aria-current="page"`.
 * Every intermediate item links back so users can navigate up the hierarchy.
 */
const breadcrumbMap: Partial<Record<RouteId, BreadcrumbItem[]>> = {
  home: [{ label: "Domů" }],
  search: [
    { label: "Domů", href: "/" },
    { label: "Najít dotaci" },
  ],
  projects: [
    { label: "Domů", href: "/" },
    { label: "Moje projekty" },
  ],
  "grant-detail": [
    { label: "Domů", href: "/" },
    { label: "Najít dotaci", href: "/hledat" },
    { label: "Detail dotace" },
  ],
  compare: [
    { label: "Domů", href: "/" },
    { label: "Porovnat výzvy" },
  ],
  coverage: [
    { label: "Domů", href: "/" },
    { label: "Pokrytí Majáku" },
  ],
  "how-it-works": [
    { label: "Domů", href: "/" },
    { label: "Jak to funguje" },
  ],
  "suggest-source": [
    { label: "Domů", href: "/" },
    { label: "Navrhnout zdroj" },
  ],
  changelog: [
    { label: "Domů", href: "/" },
    { label: "Changelog" },
  ],
  "export-summary": [
    { label: "Domů", href: "/" },
    { label: "Export přehledu" },
  ],
  "shared-project": [
    { label: "Domů", href: "/" },
    { label: "Sdílený projekt" },
  ],
  "not-found": [
    { label: "Domů", href: "/" },
    { label: "Stránka nenalezena" },
  ],
};

/**
 * Build a breadcrumb trail for the given pathname.
 *
 * Returns a non-empty array — the fallback for unknown routes is
 * Domů + route label, so the breadcrumbs always show at least the home link.
 */
export function breadcrumbsForPathname(pathname: string): BreadcrumbItem[] {
  const route = resolveRoute(pathname);
  return breadcrumbMap[route.id] ?? [
    { label: "Domů", href: "/" },
    { label: route.label },
  ];
}
