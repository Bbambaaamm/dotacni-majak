# Performance & Core Web Vitals

## Overview

Dotační maják targets **fast first meaningful paint on 3G-class mobile** and a
privacy-safe Core Web Vitals reporting pipeline. This document describes the
bundle budget, the Web Vitals targets, the mobile/desktop status definition,
and the privacy boundaries that are enforced by code and by test.

## Bundle budget

Defined as code in `apps/web/src/lib/webVitals.ts` as `DEFAULT_BUNDLE_BUDGET`.

| Budget field        | Limit    | Rationale                                     |
|---------------------|----------|-----------------------------------------------|
| `maxBytes`          | 200 KB   | Total JS for good LCP on 3G (400 Kbps).       |
| `maxChunks`         | 10       | Prevents waterfall of sequential requests.      |
| `maxAssetSize`      | 50 KB    | Per-chunk cap for streaming-first delivery.   |

These values are enforced by build-time checks (see `vite.config.ts`).
Lazy route loading is required for routes that exceed a 50 KB entry chunk.

## Mobile / desktop status

A page is considered **fast on mobile** when ALL Core Web Vitals are rated
**good** (see thresholds below) and the total JS bundle stays under `maxBytes`.

- **Fast (mobile)**: LCP ≤ 2.5 s AND INP ≤ 200 ms AND CLS ≤ 0.1.
- **Needs improvement**: any CWV exceeds the "good" threshold but not the "poor" threshold.
- **Poor (mobile)**: any CWV exceeds the "poor" threshold.

Desktop targets are the same (Core Web Vitals are device-agnostic). The
bundle budget is device-independent.

## Web Vitals thresholds

| Metric | Unit         | Good       | Poor      |
|--------|--------------|------------|-----------|
| LCP    | seconds      | ≤ 2.5 s    | > 4.0 s  |
| INP    | milliseconds | ≤ 200 ms   | > 500 ms |
| CLS    | ratio        | ≤ 0.10     | > 0.25   |
| FCP    | seconds      | ≤ 1.8 s    | > 3.0 s  |
| TTFB   | milliseconds | ≤ 200 ms   | > 600 ms |

Ratings are computed by `rateMetric()` in `webVitals.ts`. The function is pure
and tested at every boundary. NaN values are rated "poor" (fail-safe).

## Instrumentation architecture

`WebVitalsRegistry` collects `Metric` objects. Each metric has exactly four
fields: `name`, `value`, `rating`, `entries` (count of PerformanceEntry
objects). None of these fields contain URL paths, element content, or user PII.

`toReport()` returns a `WebVitalsReport` snapshot. This snapshot is safe to
forward to any analytics sink or log:

- No URL or pathname.
- No element innerHTML or text content.
- No userId, email, IP, or session ID.
- No search query text or grant metadata.

The report includes `fetchedAt` (ISO 8601 timestamp) for ordering only — it
contains no user-identifying information.

## Privacy / performance impact

- **No cookies or localStorage** are used by the instrumentation itself.
- **No network calls** are made by the instrumentation module; the consumer
  decides how (or whether) to forward `toReport()` output.
- **Bundle overhead**: `webVitals.ts` adds < 1 KB to initial JS.
- **Retention**: when a consumer forwards reports, they are retained for the
  same period as other anonymous usage diagnostics (no PII-bearing logs are
  kept). See `docs/PRIVACY.md` for the general retention policy.
- **Field data**: the thresholds above are based on Chrome UX Report (CrUX)
  field data. No individual user is tracked.

## Czech copy

All user-facing labels in the Web Vitals module are in English (technical
metric names). Czech localisation for any status UI is deferred to the
UI/UX slice. Documentation in this file is in Czech-friendly terms
("rychlost", "výkon", "mobilní připojení") but the formal metric names
remain in English per W3C/Web.dev convention.
