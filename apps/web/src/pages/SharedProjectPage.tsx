import { useEffect, useState } from "react";

import { StatusBadge } from "../components/StatusBadge";
import {
  formatMinorMoney,
  loadSharedProject,
  sharedProjectTokenFromPath,
  type SharedProject,
} from "../lib/sharedProject";
import "./sharing.css";

type ViewState =
  | { status: "loading" }
  | { status: "ok"; project: SharedProject }
  | { status: "not-found" }
  | { status: "error" };

export function SharedProjectPage() {
  const [state, setState] = useState<ViewState>({ status: "loading" });

  useEffect(() => {
    const robots = ensureMeta("robots");
    const referrer = ensureMeta("referrer");
    const previousRobots = robots.getAttribute("content");
    const previousReferrer = referrer.getAttribute("content");
    robots.setAttribute("content", "noindex,nofollow");
    referrer.setAttribute("content", "no-referrer");

    return () => {
      restoreMeta(robots, previousRobots);
      restoreMeta(referrer, previousReferrer);
    };
  }, []);

  useEffect(() => {
    const token = sharedProjectTokenFromPath(window.location.pathname);
    if (!token) {
      setState({ status: "not-found" });
      return;
    }
    let active = true;
    void loadSharedProject(token).then((result) => {
      if (!active) return;
      setState(result);
    });
    return () => {
      active = false;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <section className="share-page" aria-busy="true">
        <p className="eyebrow">Sdílený projekt</p>
        <h1>Načítáme bezpečný přehled projektu…</h1>
        <p>Maják načítá pouze údaje určené ke sdílení.</p>
      </section>
    );
  }

  if (state.status === "not-found") {
    return (
      <section className="share-page">
        <StatusBadge kind="warning" label="Odkaz není dostupný" />
        <h1>Sdílený projekt jsme nenašli.</h1>
        <p>
          Odkaz mohl vypršet nebo být zrušen. Z bezpečnostních důvodů
          nerozlišujeme, která možnost nastala.
        </p>
        <p><a href="/">Přejít na Dotační maják</a></p>
      </section>
    );
  }

  if (state.status === "error") {
    return (
      <section className="share-page">
        <StatusBadge kind="unknown" label="Projekt teď nelze načíst" />
        <h1>Bezpečný přehled se nepodařilo načíst.</h1>
        <p>Zkuste stránku znovu později. Odkaz ani projekt tím neměníme.</p>
      </section>
    );
  }

  const { project } = state;
  const budget = formatMinorMoney(
    project.estimatedTotalBudgetMinor,
    project.currencyCode,
  );

  return (
    <article className="share-page">
      <header className="share-page__head">
        <div>
          <p className="eyebrow">Sdílený přehled projektu</p>
          <h1>{project.title ?? "Projekt bez názvu"}</h1>
          <p className="share-page__lead">{project.intent}</p>
        </div>
        <StatusBadge kind="info" label="Pouze pro čtení" />
      </header>

      <section className="share-card" aria-labelledby="share-summary">
        <h2 id="share-summary">Základní informace</h2>
        <dl className="share-facts">
          <div><dt>Rozpočet</dt><dd>{budget ?? "Neuveden"}</dd></div>
          <div><dt>Plánovaný začátek</dt><dd>{project.plannedStart ?? "Neuveden"}</dd></div>
          <div><dt>Plánovaný konec</dt><dd>{project.plannedEnd ?? "Neuveden"}</dd></div>
          <div>
            <dt>Aktualizováno</dt>
            <dd>{formatDateTime(project.updatedAt)}</dd>
          </div>
        </dl>
      </section>

      <aside className="share-notice" aria-label="Informace o sdíleném přehledu">
        <strong>Tento odkaz je pouze pro čtení.</strong>
        <p>
          Neobsahuje správcovský klíč, interní poznámky ani neveřejné údaje.
          Dotační maják není poskytovatelem dotace a tento přehled není
          oficiálním rozhodnutím poskytovatele.
        </p>
      </aside>
    </article>
  );
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Neznámé";
  return new Intl.DateTimeFormat("cs-CZ", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function ensureMeta(name: string): HTMLMetaElement {
  const existing = document.querySelector<HTMLMetaElement>(
    `meta[name="${name}"]`,
  );
  if (existing) return existing;
  const created = document.createElement("meta");
  created.name = name;
  document.head.append(created);
  return created;
}

function restoreMeta(element: HTMLMetaElement, value: string | null): void {
  if (value === null) {
    element.remove();
  } else {
    element.setAttribute("content", value);
  }
}
