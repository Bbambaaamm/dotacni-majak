import { FormEvent, useMemo, useState } from "react";

import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import {
  absoluteShareUrl,
  createAnonymousProject,
  createReadOnlyShare,
  revokeReadOnlyShare,
  type OwnedProject,
  type ShareLink,
} from "../lib/projectSharing";
import "./sharing.css";

interface ManagedProject extends OwnedProject {
  title: string;
  intent: string;
}

export function ProjectsPage() {
  const [project, setProject] = useState<ManagedProject | null>(null);
  const [share, setShare] = useState<ShareLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const shareUrl = useMemo(
    () => (share ? absoluteShareUrl(share.sharePath) : null),
    [share],
  );

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    const data = new FormData(event.currentTarget);
    const title = String(data.get("title") ?? "").trim();
    const intent = String(data.get("intent") ?? "").trim();
    if (!intent) {
      setMessage("Popište nejdřív, co chcete uskutečnit.");
      return;
    }

    setBusy(true);
    try {
      const owned = await createAnonymousProject({
        title: title || null,
        naturalLanguageIntent: intent,
        currencyCode: "CZK",
      });
      const next = { ...owned, title: title || "Projekt bez názvu", intent };
      setProject(next);
      setShare(null);
      sessionStorage.setItem("dotacni-majak:active-project", JSON.stringify(next));
      setMessage(
        "Projekt je vytvořen. Správcovský klíč je tajný a po zavření relace ho Maják neumí obnovit.",
      );
    } catch {
      setMessage("Projekt se teď nepodařilo vytvořit. Zkuste to znovu později.");
    } finally {
      setBusy(false);
    }
  }

  async function handleShare() {
    if (!project) return;
    setBusy(true);
    setMessage(null);
    try {
      const issued = await createReadOnlyShare(
        project.projectId,
        project.ownerCapability,
        30,
      );
      setShare(issued);
      setMessage("Read-only odkaz je připravený. Platí 30 dní nebo do revokace.");
    } catch {
      setMessage("Sdílený odkaz se nepodařilo vytvořit. Ověřte správcovský klíč.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke() {
    if (!project || !share) return;
    setBusy(true);
    setMessage(null);
    try {
      await revokeReadOnlyShare(
        project.projectId,
        share.shareId,
        project.ownerCapability,
      );
      setShare(null);
      setMessage("Sdílený odkaz byl zrušen.");
    } catch {
      setMessage("Revokaci se teď nepodařilo dokončit.");
    } finally {
      setBusy(false);
    }
  }

  async function copy(value: string, success: string) {
    try {
      await navigator.clipboard.writeText(value);
      setMessage(success);
    } catch {
      setMessage("Kopírování není v tomto prohlížeči dostupné. Označte hodnotu ručně.");
    }
  }

  if (!project) {
    return (
      <div className="projects-page">
        <header>
          <p className="eyebrow">Moje projekty</p>
          <h1>Začněte projektem, který chcete financovat.</h1>
          <p className="share-page__lead">
            Pro první veřejnou verzi lze projekt založit bez registrace.
            Správu chrání jednorázově vydaný tajný klíč.
          </p>
        </header>

        <form className="project-form" onSubmit={handleCreate}>
          <label>
            Název projektu
            <input name="title" maxLength={200} placeholder="Např. Rekonstrukce tenisových kurtů" />
          </label>
          <label>
            Co chcete uskutečnit?
            <textarea
              name="intent"
              required
              maxLength={4000}
              rows={5}
              placeholder="Popište vlastními slovy svůj záměr…"
            />
          </label>
          <Button type="submit" disabled={busy}>
            {busy ? "Vytváříme projekt…" : "Vytvořit projekt"}
          </Button>
        </form>
        {message && <p className="form-message" role="status">{message}</p>}
      </div>
    );
  }

  return (
    <div className="projects-page">
      <header className="share-page__head">
        <div>
          <p className="eyebrow">Moje projekty</p>
          <h1>{project.title}</h1>
          <p className="share-page__lead">{project.intent}</p>
        </div>
        <StatusBadge kind="success" label="Projekt spravujete v této relaci" />
      </header>

      <section className="owner-secret" aria-labelledby="owner-key-title">
        <h2 id="owner-key-title">Správcovský klíč</h2>
        <p>
          Tento klíč umožňuje měnit sdílení projektu. Nikomu ho neposílejte.
          Server ukládá pouze jeho hash.
        </p>
        <code>{project.ownerCapability}</code>
        <Button
          variant="secondary"
          onClick={() => void copy(
            project.ownerCapability,
            "Správcovský klíč byl zkopírován.",
          )}
        >
          Zkopírovat správcovský klíč
        </Button>
      </section>

      <section className="share-card" aria-labelledby="share-title">
        <h2 id="share-title">Sdílet projekt pouze pro čtení</h2>
        <p>
          Sdílený odkaz nezpřístupní správcovský klíč, interní poznámky ani
          právo projekt měnit.
        </p>

        {!share ? (
          <Button onClick={() => void handleShare()} disabled={busy}>
            {busy ? "Vytváříme odkaz…" : "Vytvořit odkaz na 30 dní"}
          </Button>
        ) : (
          <div className="share-link-result">
            <label>
              Sdílený odkaz
              <input readOnly value={shareUrl ?? ""} />
            </label>
            <p>
              Platnost do{" "}
              <strong>{new Date(share.expiresAt).toLocaleDateString("cs-CZ")}</strong>.
            </p>
            <div className="action-row">
              <Button
                variant="secondary"
                onClick={() => shareUrl && void copy(
                  shareUrl,
                  "Sdílený odkaz byl zkopírován.",
                )}
              >
                Kopírovat odkaz
              </Button>
              <Button variant="tertiary" onClick={() => void handleRevoke()} disabled={busy}>
                Zrušit odkaz
              </Button>
            </div>
          </div>
        )}
      </section>

      {message && <p className="form-message" role="status">{message}</p>}
    </div>
  );
}
