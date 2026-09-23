import "./homepage.css";

import { StatusBadge } from "../components/StatusBadge";
import { buildIntentSearchUrl, intentExamples } from "../lib/intent";

const promiseItems = [
  {
    number: "01",
    title: "Najde.",
    text:
      "Nehledá jen přesná slova. Propojí váš záměr s širšími pojmy, které používají dotační programy.",
  },
  {
    number: "02",
    title: "Pohlídá.",
    text:
      "Když dnes vhodná výzva není, uložený projekt může sledovat nové možnosti, termíny a důležité změny.",
  },
  {
    number: "03",
    title: "Dotáhne.",
    text:
      "Ukáže, co splňujete, co ještě chybí, kolik skutečně potřebujete a co máte udělat jako další krok.",
  },
] as const;

const audiences = [
  ["Obce a města", "Infrastruktura, školy, sport, energie, kultura a veřejný prostor."],
  ["Spolky a neziskovky", "Činnost, vybavení, rekonstrukce a komunitní projekty."],
  ["Firmy a podnikatelé", "Technologie, energetika, digitalizace a inovace."],
  ["Školy a organizace", "Budovy, vybavení, vzdělávání a projektové aktivity."],
  ["Občané", "Programy dostupné fyzickým osobám, bydlení a energetické úspory."],
] as const;

export function HomePage() {
  return (
    <div className="home">
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero__content">
          <p className="eyebrow">Otevřená data · Ověřitelné zdroje · Zdarma</p>
          <h1 id="hero-title">
            Vaše nápady.
            <span>Více možností.</span>
          </h1>
          <p className="hero__lead">
            Dotační maják najde vhodné možnosti podpory, pohlídá nové výzvy
            a změny a pomůže vám celý proces dotáhnout až k připravené žádosti.
          </p>

          <form className="intent-box" action="/hledat" method="get">
            <label htmlFor="project-intent">Co chcete uskutečnit?</label>
            <textarea
              id="project-intent"
              name="intent"
              rows={3}
              required
              minLength={5}
              aria-describedby="intent-help"
              placeholder="Např. chceme zrekonstruovat tenisové kurty a nové osvětlení…"
            />
            <div className="intent-box__actions">
              <button className="button button--primary" type="submit">
                Najít možnosti
              </button>
              <a className="text-link" href="#jak-to-funguje">
                Jak to funguje
              </a>
            </div>
            <p id="intent-help" className="field-help">
              Nemusíte znát název dotace ani úřední terminologii. Stačí popsat
              svůj záměr vlastními slovy.
            </p>
          </form>

          <div className="example-links" aria-label="Příklady záměrů">
            <span>Zkuste třeba:</span>
            {intentExamples.map((example) => (
              <a key={example} href={buildIntentSearchUrl(example)}>
                {example}
              </a>
            ))}
          </div>
        </div>

        <div className="beacon-visual" aria-hidden="true">
          <div className="beacon-visual__beam beacon-visual__beam--one" />
          <div className="beacon-visual__beam beacon-visual__beam--two" />
          <div className="beacon-visual__tower">
            <div className="beacon-visual__light" />
          </div>
          <div className="beacon-visual__ground" />
        </div>
      </section>

      <section className="trust-strip" aria-label="Hlavní principy služby">
        <div>
          <strong>Oficiální zdroje</strong>
          <span>Podmínky propojujeme s původní dokumentací.</span>
        </div>
        <div>
          <strong>Hlídání změn</strong>
          <span>Sledujeme nové verze, podmínky a termíny.</span>
        </div>
        <div>
          <strong>Bez paywallu pro core</strong>
          <span>Základní veřejná funkce nemá být zamčená za předplatným.</span>
        </div>
        <div>
          <strong>Open source</strong>
          <span>Pokrytí i vývoj jsou transparentní.</span>
        </div>
      </section>

      <section className="section demo-section" aria-labelledby="demo-title">
        <div className="section-heading">
          <p className="eyebrow">Jak Maják přemýšlí</p>
          <h2 id="demo-title">Nemusíte znát úřední název programu.</h2>
          <p>
            Popíšete běžnou větou svůj záměr. Maják hledá i širší významové
            souvislosti a teprve potom odděleně ověřuje podmínky.
          </p>
        </div>

        <div className="demo-grid">
          <blockquote className="intent-quote">
            „Jsme obec s 3 200 obyvateli a chceme opravit dětské hřiště.“
          </blockquote>

          <article className="sample-card" aria-label="Ilustrační výsledek">
            <div className="sample-card__top">
              <StatusBadge kind="info" label="Ilustrační příklad" />
              <span>Nejde o aktuální výzvu</span>
            </div>
            <h3>Obnova veřejné infrastruktury</h3>
            <p className="match-band">Velmi dobrá tematická shoda</p>
            <ul className="reason-list">
              <li><span aria-hidden="true">✓</span> podporuje obdobný typ projektu</li>
              <li><span aria-hidden="true">✓</span> obec odpovídá typu žadatele</li>
              <li><span aria-hidden="true">?</span> potřebujeme znát rozpočet projektu</li>
            </ul>
            <div className="next-action">
              <span>Co teď?</span>
              <strong>Doplňte předpokládaný rozpočet.</strong>
            </div>
          </article>
        </div>
      </section>

      <section
        className="section promise-section"
        id="jak-to-funguje"
        aria-labelledby="promise-title"
      >
        <div className="section-heading">
          <p className="eyebrow">Jednoduchý princip</p>
          <h2 id="promise-title">Najde. Pohlídá. Dotáhne.</h2>
        </div>
        <div className="promise-grid">
          {promiseItems.map((item) => (
            <article key={item.title} className="promise-card">
              <span className="promise-card__number" aria-hidden="true">
                {item.number}
              </span>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
        </div>
        <div className="semantic-example" aria-label="Ukázka významového rozšíření">
          <span>tenisový kurt</span><b aria-hidden="true">→</b>
          <span>venkovní sportoviště</span><b aria-hidden="true">→</b>
          <span>sportovní zařízení</span><b aria-hidden="true">→</b>
          <span>sportovní infrastruktura</span>
        </div>
      </section>

      <section className="section result-preview" aria-labelledby="result-preview-title">
        <div className="section-heading">
          <p className="eyebrow">Vysvětlitelné výsledky</p>
          <h2 id="result-preview-title">
            Víte nejen co jsme našli, ale také proč.
          </h2>
        </div>

        <article className="grant-preview">
          <header>
            <div>
              <StatusBadge kind="info" label="Modelová karta" />
              <h3>Regionální sportovní infrastruktura</h3>
            </div>
            <span className="grant-preview__status">Lze podat žádost</span>
          </header>
          <div className="grant-preview__grid">
            <div>
              <h4>Proč ji vidíte</h4>
              <ul className="reason-list">
                <li><span aria-hidden="true">✓</span> modernizace sportovišť</li>
                <li><span aria-hidden="true">✓</span> typ žadatele odpovídá</li>
                <li><span aria-hidden="true">?</span> ověřit vztah k nemovitosti</li>
              </ul>
            </div>
            <div>
              <h4>Co ještě nevíme</h4>
              <p>Vlastnictví nebo dostatečně dlouhý nájem areálu.</p>
            </div>
            <div>
              <h4>Co udělat teď</h4>
              <p><strong>Doplňte vztah k nemovitosti.</strong></p>
            </div>
          </div>
          <footer>
            <span>Oficiální zdroj · konkrétní stránka dokumentu</span>
            <span>Aktuálnost se ověřuje u reálných dat</span>
          </footer>
        </article>
      </section>

      <section className="section finance-section" aria-labelledby="finance-title">
        <div className="section-heading">
          <p className="eyebrow">Finance bez zkratky</p>
          <h2 id="finance-title">
            „90% dotace“ nemusí znamenat jen 10 % vlastních peněz.
          </h2>
          <p>Modelový příklad ukazuje, proč Maják odděluje míru podpory od skutečné hotovosti.</p>
        </div>
        <div className="finance-card">
          <dl>
            <div><dt>Celý projekt</dt><dd>4 000 000 Kč</dd></div>
            <div><dt>Způsobilé náklady</dt><dd>3 500 000 Kč</dd></div>
            <div><dt>Dotace při 90 %</dt><dd>3 150 000 Kč</dd></div>
            <div><dt>Nezpůsobilé náklady + modelová DPH</dt><dd>500 000 Kč</dd></div>
          </dl>
          <div className="finance-card__result">
            <span>V modelovém příkladu musíte zajistit minimálně</span>
            <strong>850 000 Kč</strong>
          </div>
        </div>
      </section>

      <section className="section watch-section" aria-labelledby="watch-title">
        <div>
          <p className="eyebrow">Když dnes nic není</p>
          <h2 id="watch-title">Dnes nic vhodného? Maják hledá dál.</h2>
          <p>
            Nulový výsledek není slepá ulička. Uložený záměr může být znovu
            vyhodnocen, když se objeví nová nebo změněná výzva.
          </p>
        </div>
        <a className="button button--primary" href="/projekty">
          Pohlídat tento záměr
        </a>
      </section>

      <section className="section workspace-preview" aria-labelledby="workspace-title">
        <div className="section-heading">
          <p className="eyebrow">Od nálezu k žádosti</p>
          <h2 id="workspace-title">Vždy víte, co máte udělat teď.</h2>
          <p>
            Připravenost znamená dokončené konkrétní kroky — nikdy
            „pravděpodobnost získání dotace“.
          </p>
        </div>
        <div className="workspace-card">
          <div className="workspace-card__readiness">
            <span>Připravenost projektu</span>
            <strong>6 / 9 kroků</strong>
            <div className="progress-track" aria-label="6 z 9 kroků dokončeno">
              <span style={{ width: "66.7%" }} />
            </div>
          </div>
          <ol className="workspace-list">
            <li className="is-done">Ověřený typ žadatele</li>
            <li className="is-done">Lokalita projektu</li>
            <li className="is-next">
              <strong>Další krok:</strong> Doplňte vztah k nemovitosti
            </li>
            <li>Připravte položkový rozpočet</li>
          </ol>
        </div>
      </section>

      <section className="section changes-section" aria-labelledby="changes-title">
        <div className="section-heading">
          <p className="eyebrow">Pohlídá i změny</p>
          <h2 id="changes-title">Nejen nový dokument. Konkrétní rozdíl.</h2>
        </div>
        <div className="change-examples">
          <div>
            <span>Termín podání</span>
            <del>31. 1. 2027</del>
            <strong>28. 2. 2027</strong>
          </div>
          <div>
            <span>Maximální podpora</span>
            <del>90 %</del>
            <strong>80 %</strong>
          </div>
        </div>
        <p className="example-disclaimer">
          Modelová ukázka způsobu zobrazení změn, nikoliv informace o konkrétní výzvě.
        </p>
      </section>

      <section className="section audience-section" aria-labelledby="audience-title">
        <div className="section-heading">
          <p className="eyebrow">Pro koho</p>
          <h2 id="audience-title">Pro každého, kdo má projekt.</h2>
          <p>Nevíte, do které skupiny patříte? Nevadí. Začněte popisem záměru.</p>
        </div>
        <div className="audience-grid">
          {audiences.map(([title, text]) => (
            <article key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section evidence-section" aria-labelledby="evidence-title">
        <div>
          <p className="eyebrow">Důvěra</p>
          <h2 id="evidence-title">Nevěřte nám naslepo.</h2>
          <p>
            Kritické podmínky propojujeme s oficiálním dokumentem, verzí,
            stránkou nebo sekcí a datem kontroly. Co neumíme bezpečně potvrdit,
            označíme jako neověřené.
          </p>
        </div>
        <div className="evidence-card">
          <span>Modelový údaj</span>
          <strong>Maximální podpora: 80 %</strong>
          <small>Podmínky výzvy · str. 14 · ověřeno z oficiálního zdroje</small>
          <span className="evidence-card__note">
            V reálném detailu otevřete původní dokument.
          </span>
        </div>
      </section>

      <section className="section coverage-section" aria-labelledby="coverage-title">
        <div>
          <p className="eyebrow">Transparentní pokrytí</p>
          <h2 id="coverage-title">Co Maják skutečně sleduje?</h2>
          <p>
            Veřejně ukážeme stav každého připojeného zdroje, poslední úspěšnou
            kontrolu a známá omezení. Netvrdíme, že sledujeme všechno.
          </p>
        </div>
        <div className="coverage-card">
          <StatusBadge kind="success" label="První konektory jsou v projektu" />
          <ul>
            <li>EU Funding &amp; Tenders</li>
            <li>Národní sportovní agentura</li>
          </ul>
          <a href="/pokryti">Zobrazit pokrytí Majáku</a>
        </div>
      </section>

      <section className="section open-section" aria-labelledby="open-title">
        <p className="eyebrow">Veřejná data. Veřejný užitek.</p>
        <h2 id="open-title">Dotační maják je otevřený projekt.</h2>
        <p>
          Zdrojový kód, pokrytí zdrojů a způsob práce s daty jsou transparentní.
          Základní funkce nemají být skryté za paywallem.
        </p>
        <div className="action-row">
          <a
            className="button button--secondary"
            href="https://github.com/Bbambaaamm/dotacni-majak"
          >
            Projekt na GitHubu
          </a>
          <a className="text-link" href="/navrhnout-zdroj">
            Navrhnout chybějící zdroj
          </a>
        </div>
      </section>

      <section className="final-cta" aria-labelledby="final-cta-title">
        <h2 id="final-cta-title">
          Dobré projekty by neměly zůstat stát jen proto, že nikdo nenašel správnou možnost.
        </h2>
        <form action="/hledat" method="get">
          <label htmlFor="final-intent">Co chcete uskutečnit?</label>
          <div>
            <input
              id="final-intent"
              name="intent"
              required
              minLength={5}
              placeholder="Popište svůj projekt…"
            />
            <button className="button button--primary" type="submit">
              Najít možnosti
            </button>
          </div>
        </form>
        <p>Dotační maják — <strong>Najde. Pohlídá. Dotáhne.</strong></p>
      </section>
    </div>
  );
}
