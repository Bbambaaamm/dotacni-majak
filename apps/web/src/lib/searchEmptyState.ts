export function filteredEmptyMessage(projectBudgetCzk: string): string {
  if (projectBudgetCzk) {
    return "Při zvolených filtrech jsme mezi indexovanými výsledky nenašli grantovou výzvu s doloženým intervalem nákladů projektu v CZK, do kterého zadaná částka spadá. Výzvy s neznámými nebo neověřenými hranicemi tento filtr nezahrnuje. Nejde o posouzení vaší způsobilosti ani o potvrzení, že podpora neexistuje.";
  }
  return "Při zvolených filtrech nemáme v indexovaných výsledcích shodu pro tento záměr. Zkuste některý filtr upravit nebo zrušit.";
}
