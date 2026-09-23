import { AppShell } from "./components/AppShell";
import { Button } from "./components/Button";
import { StatusBadge } from "./components/StatusBadge";
import { resolveRoute } from "./lib/routes";

function FoundationHome() {
  return (
    <section className="foundation-card" aria-labelledby="foundation-heading">
      <StatusBadge kind="info" label="Foundation aplikace" />
      <h1 id="foundation-heading">Dotační maják</h1>
      <p className="lead">Najde. Pohlídá. Dotáhne.</p>
      <p>
        Webová základna je připravená. Produktová homepage a skutečné výsledky
        budou implementované v navazujících issues.
      </p>
      <div className="action-row">
        <Button>Najít možnosti</Button>
        <Button variant="secondary">Pohlídat záměr</Button>
      </div>
    </section>
  );
}

function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className="foundation-card">
      <StatusBadge kind="unknown" />
      <h1>{title}</h1>
      <p>Tato část je připravená pro navazující implementační issue.</p>
    </section>
  );
}

function NotFound() {
  return (
    <section className="foundation-card">
      <StatusBadge kind="warning" label="Stránka nebyla nalezena" />
      <h1>Tady Maják zatím nesvítí.</h1>
      <p>Zkontrolujte adresu nebo pokračujte na hlavní stránku.</p>
      <p><a href="/">Přejít na hlavní stránku</a></p>
    </section>
  );
}

export function App() {
  const route = resolveRoute(window.location.pathname);

  let content;
  switch (route.id) {
    case "home":
      content = <FoundationHome />;
      break;
    case "search":
      content = <PlaceholderPage title="Najít dotaci" />;
      break;
    case "projects":
      content = <PlaceholderPage title="Moje projekty" />;
      break;
    default:
      content = <NotFound />;
  }

  return <AppShell>{content}</AppShell>;
}
