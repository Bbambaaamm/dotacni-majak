export type RouteId =
  | "home"
  | "search"
  | "projects"
  | "how-it-works"
  | "coverage"
  | "suggest-source"
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
] as const;

export const utilityRoutes: readonly AppRoute[] = [
  { id: "how-it-works", path: "/jak-to-funguje", label: "Jak to funguje" },
  { id: "coverage", path: "/pokryti", label: "Pokrytí Majáku" },
  { id: "suggest-source", path: "/navrhnout-zdroj", label: "Navrhnout zdroj" },
] as const;

export function resolveRoute(pathname: string): AppRoute {
  const normalized = normalizePath(pathname);
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
