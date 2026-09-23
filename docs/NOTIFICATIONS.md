# Notifications

## Kanály
MVP:
- in-app,
- Web Push jako opt-in provider abstraction.

E-mail není hard dependency.

## Privacy
Push payload nekopíruje celý natural-language projektový záměr. Nese pouze stručnou zprávu a notification ID.

Web Push endpoint/keys se v persistence modelu ukládají jako ciphertext fields; konkrétní encryption/key-management implementation patří do security/deployment vrstvy.

## Deduplikace
Každý logical notification request má `dedupe_base`. Channel přidá vlastní suffix.

Stejný outbox event proto nevytvoří dvakrát stejnou in-app/push zprávu.

## Project Watch
Pozitivní notifikace:
- MATCHED,
- NEEDS_INFORMATION.

Verified INELIGIBLE, finance-not-applicable a weak relevance nevytvářejí „nová možnost“ notifikaci.

## Change events
- CRITICAL / IMPORTANT → in-app + push (pokud opt-in),
- INFORMATIONAL → in-app,
- EDITORIAL → bez notifikace.

## Deadline reminders
Default thresholdy:
60 / 30 / 14 / 7 / 3 / 1 den.

Planner generuje threshold pouze v odpovídající kalendářní den a dedupe key zajišťuje jednorázové doručení.

## Fallback
Selhání Web Push nesmí odstranit nebo blokovat in-app notification.
