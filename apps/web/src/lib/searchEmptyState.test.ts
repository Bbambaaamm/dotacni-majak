import { describe, expect, it } from "vitest";

import { filteredEmptyMessage } from "./searchEmptyState";

describe("filtered search empty state", () => {
  it("describes the verified catalog cost interval without declaring rejection or absence", () => {
    const message = filteredEmptyMessage("500000");
    expect(message).toContain("mezi indexovanými výsledky");
    expect(message).toContain("doloženým intervalem nákladů projektu v CZK");
    expect(message).toContain("neznámými nebo neověřenými hranicemi");
    expect(message).toContain("Nejde o posouzení vaší způsobilosti");
    expect(message).toContain("ani o potvrzení, že podpora neexistuje");
  });

  it("limits other filtered zero states to indexed results", () => {
    expect(filteredEmptyMessage("")).toContain("v indexovaných výsledcích");
    expect(filteredEmptyMessage("")).toContain("některý filtr upravit nebo zrušit");
  });
});
