# Výsledky vyhledávání — ovládání načtené sady (#400)

`/hledat` načítá z `GET /api/search` nanejvýš 20 výsledků v pořadí relevance. Stav, poskytovatel a dostupnost termínu jsou filtry pouze nad právě načtenou sadou; přepnutí řazení podle nejbližšího uvedeného termínu nepřepočítává relevanci ani způsobilost. Neuvedený termín (UNKNOWN) zůstává odlišný od prošlého a při řazení je na konci. Přehled a aktivní odstranitelné filtry výslovně uvádějí toto omezení.

Nativní rozbalovací panel `<details>` se ovládá klávesnicí a na mobilu nevyžaduje hover. Žádné filtry nepřidávají tvrzení o financování ani způsobilosti. Na chybu API a prázdný index se zachovává původní fail-closed stav; E2E scénář používá skutečné API, D1 a seed výzvy, nikoli mock response.

Tento úzký PR neuzavírá #400: API zatím nemá kurzorové stránkování, globální facety ani bezpečně doložené finance filtry. Navazující slice musí definovat deterministický serverový kontrakt filtrů/řazení a stabilního cursoru; do té doby UI nesmí vydávat počet z první stránky za celkový počet shod.
