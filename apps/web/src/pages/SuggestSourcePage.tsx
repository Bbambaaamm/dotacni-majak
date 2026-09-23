import { FormEvent, useState } from "react";

import {
  createSourceSuggestion,
  LocalSourceSuggestionStore,
} from "../lib/sourceSuggestion";
import { StatusBadge } from "../components/StatusBadge";
import "./suggest-source.css";

export function SuggestSourcePage() {
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");
  const [message, setMessage] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);

    try {
      const suggestion = createSourceSuggestion({
        id: crypto.randomUUID(),
        name: String(form.get("name") ?? ""),
        url: String(form.get("url") ?? ""),
        providerName: String(form.get("provider") ?? ""),
        note: String(form.get("note") ?? ""),
        createdAt: new Date().toISOString(),
      });
      new LocalSourceSuggestionStore(window.localStorage).save(suggestion);
      setStatus("saved");
      setMessage(
        "Návrh byl uložen do fronty k ručnímu ověření v tomto prohlížeči.",
      );
      event.currentTarget.reset();
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof Error
          ? error.message
          : "Návrh se nepodařilo ověřit.",
      );
    }
  }

  return (
    <article className="suggest-source-page">
      <header>
        <p className="eyebrow">Rozšiřování pokrytí</p>
        <h1>Navrhněte chybějící dotační zdroj</h1>
        <p className="results-lead">
          Znáte oficiální portál obce, kraje, MAS nebo poskytovatele, který
          Maják ještě nesleduje? Pošlete nám odkaz k ověření.
        </p>
      </header>

      <aside className="suggest-source-notice">
        <StatusBadge kind="info" label="Každý návrh prochází ručním review" />
        <p>
          Odeslaná URL se nikdy automaticky nestane oficiálním zdrojem a
          automaticky nespustí crawler. Nejprve ověříme autoritu, způsob
          získávání dat a bezpečnost.
        </p>
      </aside>

      <form className="suggest-source-form" onSubmit={submit}>
        <label>
          Název zdroje
          <input
            name="name"
            required
            minLength={2}
            maxLength={160}
            autoComplete="off"
          />
        </label>

        <label>
          Oficiální HTTPS adresa
          <input
            name="url"
            required
            type="url"
            inputMode="url"
            placeholder="https://..."
            autoComplete="url"
          />
        </label>

        <label>
          Poskytovatel <span>(volitelné)</span>
          <input name="provider" maxLength={160} autoComplete="organization" />
        </label>

        <label>
          Poznámka <span>(volitelné)</span>
          <textarea
            name="note"
            maxLength={1000}
            rows={5}
            placeholder="Např. kde na webu jsou aktuální výzvy nebo dokumenty."
          />
        </label>

        <button className="button button--primary" type="submit">
          Odeslat k ověření
        </button>
      </form>

      {status !== "idle" ? (
        <p
          className={
            status === "saved"
              ? "suggest-source-status suggest-source-status--success"
              : "suggest-source-status suggest-source-status--error"
          }
          role={status === "error" ? "alert" : "status"}
        >
          {message}
        </p>
      ) : null}

      <p className="fine-print">
        V této fázi se návrh ukládá pouze lokálně. Produkční synchronizace do
        review fronty bude zapojena přes API bez automatického schválení.
      </p>
    </article>
  );
}
