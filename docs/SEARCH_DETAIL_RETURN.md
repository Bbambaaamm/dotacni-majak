# Návrat z detailu do výsledků (dílčí #400)

Odkaz na detail přenáší pouze validovaný záměr/aplikované filtry/řazení a identifikátor zobrazené verze. Zpětný odkaz nespouští starý cursor: vyhledávání znovu načte aktuální první stránku z API a nanejvýš pět dalších cursor stránek. Po nalezení původní verze přesune klávesnicový focus na její odkaz, pokud už uživatel nepřešel jinam. Cíl zůstává v URL při probíhajícím načítání i po refreshi; po dokončení nebo změně filtru se odstraní. Změna filtru obnovu přeruší.

Při chybě, změně pořadí/verze nebo po dosažení rozpočtu stránek zůstávají načtené výsledky viditelné a stránka sděluje, že původní položku nebylo možné obnovit. Neznamená to zrušení výzvy. Pokračování je ruční; nedochází k uchování starých grantových faktů v prohlížeči. Přímý odkaz na detail bez kontextu dál vede na běžné `/hledat`.

Omezení: více než pět dalších stránek se automaticky neobnovuje, aktuální index se mohl změnit. Tento slice nenahrazuje celkové desktop/mobilní ani zdrojové acceptance #400/#401.
