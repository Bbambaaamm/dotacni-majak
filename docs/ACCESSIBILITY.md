# Accessibility

Cíl produktu: **WCAG 2.2 AA foundation a release gate**.

## Povinné zásady
- semantic HTML,
- plná keyboard navigace,
- výrazný visible focus,
- všechny formuláře mají labels/instructions/errors,
- status nikdy pouze barvou,
- touch targets přibližně 44×44 px nebo odpovídající bezpečná plocha,
- 200% zoom a reflow bez ztráty obsahu,
- screen-reader kompatibilita,
- reduced motion,
- kontrast dle WCAG,
- drag/drop má alternativu,
- kritické informace nejsou pouze v hover/tooltipu.

## Status komponenty
Používat text + ikonu + případně barvu:
- ✓ Splněno
- ✕ Nesplněno
- ? Potřebujeme doplnit
- ! Zatím neumíme bezpečně ověřit

## Finance
Grafy jsou doplněk. Vždy existuje textová/tabulková reprezentace přesných částek.

## Testing
Automatické testy nestačí.

Před beta/v1.0:
- keyboard-only walkthrough,
- screen reader walkthrough klíčových toků,
- 200% zoom,
- mobile reflow,
- error-state audit,
- accessible authentication,
- manual focus order review.

## Feedback
Veřejná aplikace musí obsahovat cestu pro nahlášení accessibility problému.
