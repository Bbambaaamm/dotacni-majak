export type RouteId =
  | "home"
  | "search"
  | "projects"
  | "shared-project"
  | "grant-detail"
  | "compare"
  | "how-it-works"
  | "coverage"
  | "suggest-source"
  | "changelog"
  | "export-summary"
  | "not-found";

export interface AppRoute {
  id: RouteId;
  path: string;
  label: string;
}

export const routes: readonly AppRoute[] = [
  { id: "home", path: "/", label: "Domů" },
  { id: "search", path: "/hledat", label: "Najít dotaci" },
  { id: "projects", path: "/projekty", label: "Moje projekty" },
  { id: "grant-detail", path: "/dotace/regiony-2026", label: "Detail dotace" },
  { id: "compare", path: "/porovnat", label: "Porovnat výzvy" },
  { id: "export-summary", path: "/export/regiony-2026", label: "Export přehledu" },
] as const;

export const utilityRoutes: readonly AppRoute[] = [
  { id: "how-it-works", path: "/jak-to-funguje", label: "Jak to funguje" },
  { id: "coverage", path: "/pokryti", label: "Pokrytí Majáku" },
  { id: "suggest-source", path: "/navrhnout-zdroj", label: "Navrhnout zdroj" },
  { id: "changelog", path: "/changelog", label: "Changelog" },
] as const;

export function resolveRoute(pathname: string): AppRoute {
  const normalized = normalizePath(pathname);

  if (/^\/s\/[A-Za-z0-9_-]{40,128}$/.test(normalized)) {
    return {
      id: "shared-project",
      path: normalized,
      label: "Sdílený projekt",
    };
  }

  return (
    [...routes, ...utilityRoutes].find((route) => route.path === normalized) ?? {
      id: "not-found",
      path: normalized,
      label: "Stránka nenalezena",
    }
  );
}

export function normalizePath(pathname: string): string {
  if (!pathname || pathname === "/") return "/";
  const withoutQuery = pathname.split(/[?#]/, 1)[0] ?? "/";
  return "/" + withoutQuery.split("/").filter(Boolean).join("/");
}
