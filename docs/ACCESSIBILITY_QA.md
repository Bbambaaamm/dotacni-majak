# Accessibility QA

Automatické axe/Playwright testy jsou pouze první gate. Neprokazují plnou shodu s WCAG 2.2 AA.

## Automatický gate
CI spouští Chromium proti:
- homepage,
- výsledkům,
- detailu výzvy.

Kontroluje axe WCAG A/AA rules a funkční skip link.

## Povinný manuální gate před Public Beta
- [ ] celý hlavní tok pouze klávesnicí
- [ ] focus order odpovídá vizuálnímu pořadí
- [ ] focus je vždy viditelný
- [ ] NVDA/VoiceOver: homepage → search → result → detail → source
- [ ] 200% zoom bez ztráty obsahu/funkce
- [ ] 320 CSS px reflow
- [ ] statusy srozumitelné bez barev
- [ ] finance mají textový ekvivalent
- [ ] errors jsou asociované s inputy
- [ ] reduced motion
- [ ] touch targets
- [ ] dialogy/sheets mají focus management
- [ ] autentizace a share flow po jejich implementaci

Každý nalezený blocker dostane GitHub issue před beta release.
