import { FormEvent, useEffect, useMemo, useState } from "react";

import { Button } from "../components/Button";
import { StatusBadge } from "../components/StatusBadge";
import { ProjectEligibility } from "../components/ProjectEligibility";
import {
  absoluteShareUrl,
  createAnonymousProject,
  createReadOnlyShare,
  revokeReadOnlyShare,
  type OwnedProject,
  type ShareLink,
} from "../lib/projectSharing";
import { projectPrefillFromSearch } from "../lib/projectPrefill";
import { createWorkspace, getWorkspace, listWorkspaces, updateTask, type WorkspaceResult } from "../lib/workspaceApi";
import { getProjectNotifications, type ProjectNotification } from "../lib/projectNotifications";
import {
  enableProjectWatch,
  getProjectWatch,
  setProjectWatchEnabled,
  type ProjectWatchRecord,
} from "../lib/projectWatch";
import "./sharing.css";

interface ManagedProject extends OwnedProject {
  title: string;
  intent: string;
}

function loadSessionProject(): ManagedProject | null {
  try {
    const raw = sessionStorage.getItem("dotacni-majak:active-project");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ManagedProject>;
    if (
      typeof parsed.projectId !== "string"
      || !/^prj_[a-f0-9]{32}$/.test(parsed.projectId)
      || typeof parsed.ownerCapability !== "string"
      || !/^[A-Za-z0-9_-]{40,128}$/.test(parsed.ownerCapability)
      || typeof parsed.title !== "string"
      || typeof parsed.intent !== "string"
    ) {
      sessionStorage.removeItem("dotacni-majak:active-project");
      return null;
    }
    return parsed as ManagedProject;
  } catch {
    return null;
  }
}

export function ProjectsPage() {
  const prefill = useMemo(
    () => projectPrefillFromSearch(window.location.search),
    [],
  );
  const [project, setProject] = useState<ManagedProject | null>(() => loadSessionProject());
  const [watch, setWatch] = useState<ProjectWatchRecord | null>(null);
  const [watchLoaded, setWatchLoaded] = useState(false);
  const [notifications, setNotifications] = useState<ProjectNotification[]>([]);
  const [notificationError, setNotificationError] = useState(false);
  const [share, setShare] = useState<ShareLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceResult | null>(null);
  const [workspaceList, setWorkspaceList] = useState<Array<{ id: string; grantCallId: string }>>([]);
  const [workspaceError, setWorkspaceError] = useState(false);
  const [eligibilityWritePending, setEligibilityWritePending] = useState(false);
  const [eligibilityRevision, setEligibilityRevision] = useState(0);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    setWorkspace(null);
    setWorkspaceList([]);
    setWorkspaceError(false);
    listWorkspaces(project.projectId, project.ownerCapability)
      .then(async (items) => {
        if (!cancelled) setWorkspaceList(items);
        const selected = items.find((item) => item.grantCallId === prefill.grantCallId) ?? items[0];
        if (selected) {
          const result = await getWorkspace(project.projectId, project.ownerCapability, selected.id);
          if (!cancelled) setWorkspace(result);
        }
      })
      .catch(() => { if (!cancelled) { setWorkspace(null); setWorkspaceError(true); } });
    return () => { cancelled = true; };
  }, [project, prefill.grantCallId]);

  async function handleWorkspace(projectOwner: ManagedProject, grantCallId: string) {
    setBusy(true);
    setWorkspaceError(false);
    try {
      const result = await createWorkspace(projectOwner.projectId, projectOwner.ownerCapability, grantCallId);
      setWorkspace(result);
      setWorkspaceList((items) => items.some((item) => item.id === result.workspace.id)
        ? items : [...items, { id: result.workspace.id, grantCallId }]);
      setMessage("Příprava žádosti byla založena. Před podáním ověřte neznámé podmínky v oficiálním zdroji.");
    } catch {
      setWorkspaceError(true);
      setMessage("Přípravu žádosti se nepodařilo bezpečně založit. Zkuste to znovu.");
    } finally { setBusy(false); }
  }


  const shareUrl = useMemo(
    () => (share ? absoluteShareUrl(share.sharePath) : null),
    [share],
  );

  useEffect(() => {
    if (!project) {
      setWatch(null);
      setWatchLoaded(true);
      return;
    }
    let cancelled = false;
    setWatchLoaded(false);
    getProjectWatch(project.projectId, project.ownerCapability)
      .then((value) => {
        if (!cancelled) {
          setWatch(value);
          setWatchLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setWatch(null);
          setWatchLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [project]);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    getProjectNotifications(project.projectId, project.ownerCapability)
      .then((items) => { if (!cancelled) setNotifications(items); })
      .catch(() => { if (!cancelled) setNotificationError(true); });
    return () => { cancelled = true; };
  }, [project]);

  async function refreshNotifications() {
    if (!project) return;
    setNotificationError(false);
    try {
      setNotifications(await getProjectNotifications(project.projectId, project.ownerCapability));
    } catch {
      setNotificationError(true);
    }
  }

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
      if (prefill.grantCallId) {
        await handleWorkspace(next, prefill.grantCallId);
      }

      if (prefill.autoWatch) {
        try {
          const createdWatch = await enableProjectWatch(
            next.projectId,
            next.ownerCapability,
          );
          setWatch(createdWatch);
          setWatchLoaded(true);
          setMessage(
            "Projekt je vytvořen a Maják ho hlídá. Správcovský klíč je tajný a po zavření relace ho Maják neumí obnovit.",
          );
        } catch {
          setMessage(
            "Projekt je vytvořen, ale hlídání se teď nepodařilo zapnout. Můžete ho zapnout níže.",
          );
        }
      } else {
        if (!prefill.grantCallId) setMessage(
          "Projekt je vytvořen. Správcovský klíč je tajný a po zavření relace ho Maják neumí obnovit.",
        );
      }
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
              defaultValue={prefill.intent}
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

      <section className="share-card" aria-labelledby="workspace-title">
        <h2 id="workspace-title">Příprava žádosti · Dotáhne</h2>
        {workspaceList.length > 0 && (
          <nav aria-label="Přípravy žádostí">
            <ul>{workspaceList.map((item) => (
              <li key={item.id}><Button variant="secondary" disabled={busy || eligibilityWritePending || workspaceError}
                onClick={async () => {
                  setBusy(true);
                  try { setWorkspace(await getWorkspace(project.projectId, project.ownerCapability, item.id)); }
                  catch { setWorkspace(null); setWorkspaceError(true); }
                  finally { setBusy(false); }
                }}>Otevřít přípravu: {item.grantCallId}</Button></li>
            ))}</ul>
          </nav>
        )}
        {prefill.grantCallId && workspace?.workspace.grantCallId !== prefill.grantCallId && (
          <Button disabled={busy || eligibilityWritePending} onClick={() => void handleWorkspace(project, prefill.grantCallId!)}>
            Připravit žádost k vybrané výzvě
          </Button>
        )}
        {workspaceError && (
          <div role="alert">
            <p>Přípravu žádosti nelze načíst. Zastaralé kroky nelze měnit; údaje nepovažujte za aktuální.</p>
            <Button variant="secondary" onClick={async () => {
              try {
                const items = await listWorkspaces(project.projectId, project.ownerCapability);
                setWorkspaceList(items);
                const selected = items.find((item) => item.grantCallId === prefill.grantCallId) ?? items[0];
                const fresh = selected ? await getWorkspace(project.projectId, project.ownerCapability, selected.id) : null;
                setWorkspace(fresh);
                setWorkspaceError(false);
              } catch { setWorkspace(null); setWorkspaceError(true); }
            }}>Zkusit načíst přípravu znovu</Button>
          </div>
        )}
        {workspace && !workspaceError && (
          <>
            <p>Výzva: <a href={`/dotace/${encodeURIComponent(workspace.workspace.grantCallId)}`}>Otevřít detail a oficiální zdroj</a></p>
            <p>Výchozí verze: <code>{workspace.workspace.baselineGrantVersionId}</code> · Aktuální verze: <code>{workspace.workspace.currentGrantVersionId}</code></p>
            <p><strong>Stav přípravy: {workspace.readiness.state}</strong> · Hotovo {workspace.readiness.completedCount} z {workspace.readiness.totalCount} kroků ({workspace.readiness.completionPercent} %). Toto není posouzení způsobilosti ani příslib dotace.</p>
            <h3>Co udělat teď?</h3>
            <p>{workspace.readiness.nextAction?.title ?? "Ověřte konečné znění u poskytovatele."}</p>
            {workspace.versionReview.required && (
              <div role="alert">
                <h3>Podmínky výzvy se od zahájení přípravy změnily</h3>
                <p>Než budete pokračovat, porovnejte verze a ověřte aktuální podmínky. Původní verze zůstává uložená.</p>
                <ul aria-label="Změny výzvy">{workspace.versionReview.diff.map((change, index) => (
                  <li key={`${change.field}-${index}`}><strong>{change.field}</strong>: {change.before ?? "neuvedeno"} → {change.after ?? "neuvedeno"}{change.evidenceId && ` · evidence ${change.evidenceId}`}</li>
                ))}</ul>
                {workspace.versionReview.diff.length === 0 && <p>Nová verze byla publikována; strukturovaný rozdíl není dostupný. Ověřte celé znění.</p>}
                <p>Aktuální verze zachycena {workspace.versionReview.currentCapturedAt}. Poslední pozorování záznamu u zdroje: {workspace.versionReview.sourceCheckedAt ?? "Není doloženo"}. Pozorování není ověření podmínek verze. {workspace.versionReview.sourceUrl && <a href={workspace.versionReview.sourceUrl} target="_blank" rel="noreferrer">Zkontrolovat zdroj ↗</a>}</p>
              </div>
            )}
            {workspace.versionReview.alerts.length > 0 && <p role="status">Upozornění na změny verzí: {workspace.versionReview.alerts.length}</p>}
            <h3>Kontrolní seznam</h3>
            <ul aria-label="Kontrolní seznam žádosti">{workspace.tasks.map((task) => (
              <li key={task.id}>
                <strong>{task.title}</strong> · {task.necessity} · {task.status}
                {task.reason_code && <small> · {task.reason_code}</small>}
                {task.source === "REQUIREMENT" && task.reason_code === "REQUIREMENT" && (
                  <Button variant="secondary" disabled={busy || eligibilityWritePending} onClick={async () => {
                    setBusy(true);
                    try { setWorkspace(await updateTask(project.projectId, project.ownerCapability, workspace.workspace.id, task.id, task.status === "DONE" ? "TODO" : "DONE")); }
                    catch { setWorkspaceError(true); }
                    finally { setBusy(false); }
                  }}>{task.status === "DONE" ? "Vrátit k ověření" : "Označit jako hotové"}</Button>
                )}
              </li>
            ))}</ul>
            <p>Neznámou způsobilost, finance a úplnost podmínek nelze označit za splněné bez samostatného ověření.</p>
            <Button variant="secondary" disabled={eligibilityWritePending} onClick={async () => {
              try { setWorkspace(await getWorkspace(project.projectId, project.ownerCapability, workspace.workspace.id)); setWorkspaceError(false); }
              catch { setWorkspaceError(true); }
            }}>Obnovit přípravu a změny</Button>
          </>
        )}
      </section>

      {workspace && !workspaceError && (
        <ProjectEligibility
          key={`${project.projectId}:${workspace.workspace.grantCallId}:${workspace.workspace.currentGrantVersionId}:${eligibilityRevision}`}
          grantCallId={workspace.workspace.grantCallId}
          ownerCapability={project.ownerCapability}
          onWritePendingChange={setEligibilityWritePending}
          onWriteCommitted={() => setEligibilityRevision((value) => value + 1)}
        />
      )}

      <section className="share-card" aria-labelledby="watch-title">
        <div className="share-page__head">
          <div>
            <h2 id="watch-title">Hlídání projektu</h2>
            <p>
              Maják bude tento záměr znovu porovnávat s novými a změněnými výzvami.
            </p>
          </div>
          {!watchLoaded ? (
            <StatusBadge kind="unknown" label="Načítáme stav hlídání" />
          ) : watch?.enabled ? (
            <StatusBadge kind="success" label="Maják tento projekt hlídá" />
          ) : watch ? (
            <StatusBadge kind="warning" label="Hlídání je pozastavené" />
          ) : (
            <StatusBadge kind="unknown" label="Hlídání není zapnuté" />
          )}
        </div>

        <div className="action-row">
          {!watch ? (
            <Button
              onClick={async () => {
                setBusy(true);
                setMessage(null);
                try {
                  const created = await enableProjectWatch(
                    project.projectId,
                    project.ownerCapability,
                  );
                  setWatch(created);
                  setMessage("Maják tento projekt nyní hlídá.");
                } catch {
                  setMessage("Hlídání se teď nepodařilo zapnout.");
                } finally {
                  setBusy(false);
                }
              }}
              disabled={busy || !watchLoaded}
            >
              Pohlídat tento projekt
            </Button>
          ) : (
            <Button
              variant={watch.enabled ? "tertiary" : "secondary"}
              onClick={async () => {
                setBusy(true);
                setMessage(null);
                try {
                  const updated = await setProjectWatchEnabled(
                    project.projectId,
                    project.ownerCapability,
                    !watch.enabled,
                  );
                  setWatch(updated);
                  setMessage(
                    updated.enabled
                      ? "Hlídání projektu je znovu aktivní."
                      : "Hlídání projektu je pozastavené.",
                  );
                } catch {
                  setMessage("Stav hlídání se teď nepodařilo změnit.");
                } finally {
                  setBusy(false);
                }
              }}
              disabled={busy || !watchLoaded}
            >
              {watch.enabled ? "Pozastavit hlídání" : "Znovu zapnout hlídání"}
            </Button>
          )}
        </div>
      </section>

      <section className="share-card" aria-labelledby="notifications-title">
        <h2 id="notifications-title">Upozornění projektu</h2>
        <p>Nové tematické možnosti ověřte podle oficiálních podmínek. Shoda neznamená způsobilost.</p>
        <Button variant="secondary" onClick={() => void refreshNotifications()}>
          Obnovit upozornění
        </Button>
        {notificationError ? (
          <p role="alert">Upozornění se teď nepodařilo načíst. Zkuste to znovu.</p>
        ) : notifications.length === 0 ? (
          <p role="status">Zatím nemáte žádná upozornění. Maják bude hledat dál.</p>
        ) : (
          <ul aria-label="Upozornění projektu">
            {notifications.map((item) => (
              <li key={item.id}>
                <strong>{item.title}</strong>
                <p>{item.body}</p>
                <a href={`/dotace/${encodeURIComponent(item.grantCallId)}`}>
                  Otevřít detail výzvy a ověřit podmínky
                </a>
              </li>
            ))}
          </ul>
        )}
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
