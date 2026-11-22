# Search index EMPTY vs no query match (#400 partial)

`GET /search` returns `indexState: EMPTY` only when no active searchable grant call has a document for its own current version and a valid provider path. Retained old versions, a foreign `current_version_id`, and inactive documents do not prove that a live opportunity exists. The existence probe shares the identity/status joins used by result queries; it does not delete stored evidence or infer cancellation. The normal document triggers maintain FTS rows.

A READY index with no results for a query still means only that this query found no matching indexed calls, not that no support exists. The results screen explains EMPTY as no currently searchable active calls, links to source coverage, and avoids asserting that the database is entirely empty or that ingestion has necessarily never run.

Verification: `apps/api/tests/searchCurrentVersion.d1.test.ts` mutates real Miniflare D1 current pointers and status, calls the actual API handler, and proves READY/EMPTY transitions without destroying retained rows. The normal full-stack search E2E continues to exercise actual D1/API/browser results. This is a partial #400 correctness slice, not responsive/accessibility sign-off or beta GO.
