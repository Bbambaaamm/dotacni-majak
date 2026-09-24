import assert from "node:assert/strict";
import test from "node:test";

import { euFundingRefreshConfig } from "../../scripts/local_refresh_config.mjs";

test("default EU Funding local coverage is an explicit partial sample", () => {
  assert.deepEqual(euFundingRefreshConfig({}), {
    args: ["--limit", "75"],
    coverage: { mode: "partial", limit: 75 },
  });
});

test("all enables uncapped local EU Funding import", () => {
  assert.deepEqual(euFundingRefreshConfig({ DEV_EU_FUNDING_LIMIT: "all" }), {
    args: [],
    coverage: { mode: "full" },
  });
});

test("positive integer overrides the development sample size", () => {
  assert.deepEqual(euFundingRefreshConfig({ DEV_EU_FUNDING_LIMIT: "150" }), {
    args: ["--limit", "150"],
    coverage: { mode: "partial", limit: 150 },
  });
});

for (const invalid of ["0", "-1", "75x", "1.5", "", "  "]) {
  test(`invalid EU Funding limit fails closed: ${JSON.stringify(invalid)}`, () => {
    assert.throws(
      () => euFundingRefreshConfig({ DEV_EU_FUNDING_LIMIT: invalid }),
      /DEV_EU_FUNDING_LIMIT/,
    );
  });
}
