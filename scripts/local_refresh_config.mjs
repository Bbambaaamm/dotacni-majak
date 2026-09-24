export function euFundingRefreshConfig(env = process.env) {
  const raw = String(env.DEV_EU_FUNDING_LIMIT ?? "75").trim();

  if (raw.toLowerCase() === "all") {
    return {
      args: [],
      coverage: { mode: "full" },
    };
  }

  if (!/^[1-9]\d*$/.test(raw)) {
    throw new Error(
      "DEV_EU_FUNDING_LIMIT musí být kladné celé číslo nebo 'all'.",
    );
  }

  const limit = Number(raw);
  if (!Number.isSafeInteger(limit)) {
    throw new Error(
      "DEV_EU_FUNDING_LIMIT je mimo bezpečný celočíselný rozsah.",
    );
  }

  return {
    args: ["--limit", String(limit)],
    coverage: { mode: "partial", limit },
  };
}
