# Search result actions — accessible context (#400)

On `/hledat`, each result card keeps its short visible action text while the accessible names of its detail link, official-source link, and relevance-response buttons include the actual grant title. This lets a screen-reader link/button list distinguish multiple results without suggesting that a thematic match proves applicant eligibility. The official-source link also announces that it opens a new tab.

Each relevance-feedback instance uses a React-generated heading ID for its `aria-labelledby` region. The visible region heading stays unchanged, while response button accessible names include the grant title on search cards; the single feedback section on a deep-linked grant detail remains usable without a title prop. IDs are not derived from potentially duplicate or untrusted source titles.

`tests/e2e/core-flow.spec.ts` checks two real D1-backed search results at desktop and mobile widths, per-card roles and accessible names, unique heading references, keyboard navigation to detail, axe WCAG checks, and horizontal reflow. Successful API responses are not mocked.
