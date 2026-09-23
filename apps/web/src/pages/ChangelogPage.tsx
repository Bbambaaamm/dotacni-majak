import "./changelog.css";

interface ChangeGroup {
  title: string;
  items: readonly string[];
}

interface ChangeRelease {
  date: string;
  groups: readonly ChangeGroup[];
}

const releases: readonly ChangeRelease[] = [
  {
    date: "23. 9. 2026",
    groups: [
      {
        title: "Nově umíme",
        items: [
          "Sledovat první české, evropské a regionální dotační zdroje.",
          "Vysvětlit, proč se výzva zobrazuje, a oddělit relevanci od způsobilosti.",
          "Hlídání změn, zdrojů, projektů a upozornění.",
          "Pracovní prostor žádosti, finance a historické obdobné projekty.",
        ],
      },
      {
        title: "Důvěryhodnost a bezpečnost",
        items: [
          "RAW-first zpracování a neměnné verze zdrojových dokumentů.",
          "Dohledatelnost kritických údajů k oficiálnímu zdroji.",
          "Ochrana proti hromadným chybným změnám při výpadku parseru.",
          "Bezpečná síťová a dokumentová ingestion vrstva.",
        ],
      },
    ],
  },
  {
    date: "22. 9. 2026",
    groups: [
      {
        title: "Vznik projektu",
        items: [
          "Vznikl Dotační maják — Najde. Pohlídá. Dotáhne.",
          "Definovali jsme canonical datový model a Source Adapter Contract.",
          "Projekt je navržen jako open-source a zero-cost-first.",
        ],
      },
    ],
  },
];

export function ChangelogPage() {
  return (
    <article className="changelog-page">
      <header className="changelog-page__header">
        <p className="eyebrow">Otevřený vývoj</p>
        <h1>Co je v Majáku nového</h1>
        <p className="results-lead">
          Zveřejňujeme podstatné změny produktu a pokrytí. Tato stránka není
          historií změn jednotlivých dotačních výzev — ty mají vlastní
          change timeline a oficiální zdroje.
        </p>
      </header>

      <ol className="changelog-list">
        {releases.map((release) => (
          <li key={release.date} className="changelog-release">
            <time>{release.date}</time>
            <div className="changelog-release__content">
              {release.groups.map((group) => (
                <section key={group.title}>
                  <h2>{group.title}</h2>
                  <ul>
                    {group.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </li>
        ))}
      </ol>

      <footer className="changelog-page__footer">
        <p>
          Technické detaily a jednotlivé změny kódu jsou veřejné také v
          GitHub repository.
        </p>
        <a href="https://github.com/Bbambaaamm/dotacni-majak">
          Otevřít GitHub
        </a>
      </footer>
    </article>
  );
}
