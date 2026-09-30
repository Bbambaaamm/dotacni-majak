// Core Web Vitals instrumentation — privacy-safe.
//
// Captures ONLY metric values, ratings, and entry counts.
// No URLs, no element content, no PII are ever recorded.
// Consumers provide their own onReport callback to forward
// a WebVitalsReport to an analytics endpoint or log sink.
//
// See docs/PERFORMANCE.md for thresholds, targets, and privacy policy.

/** Names of the Web Vitals metrics tracked by this module. */
export type MetricName = "LCP" | "INP" | "CLS" | "FCP" | "TTFB";

/** Rating assigned to a metric value based on standard thresholds. */
export type MetricRating = "good" | "needs-improvement" | "poor";

/** A single recorded metric. `entries` is a count, never PII. */
export interface Metric {
  name: MetricName;
  /** Value in the metric's natural unit (s, ms, ratio). */
  value: number;
  rating: MetricRating;
  /** Count of PerformanceEntry objects that contributed. */
  entries: number;
}

/** A timestamped, privacy-safe snapshot of all recorded metrics. */
export interface WebVitalsReport {
  lcp: Metric | null;
  inp: Metric | null;
  cls: Metric | null;
  fcp: Metric | null;
  ttfb: Metric | null;
  fetchedAt: string;
}

/**
 * Thresholds for rating a metric value.
 * Units: LCP/FCP/TTFFB in seconds or milliseconds as noted by the key.
 * Source: Chrome UX Report / Web.dev field-data thresholds.
 */
export const CWV_THRESHOLDS: Record<MetricName, { good: number; poor: number }> =
  {
    LCP: { good: 2.5, poor: 4.0 },    // seconds
    INP: { good: 200, poor: 500 },    // milliseconds
    CLS: { good: 0.1, poor: 0.25 },   // ratio (unitless)
    FCP: { good: 1.8, poor: 3.0 },    // seconds
    TTFB: { good: 200, poor: 600 },   // milliseconds
  };

export class WebVitalsError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

/**
 * Rates a metric value. Pure function — no DOM access, fully testable.
 *
 * Rating semantics follow Chrome UX Report:
 *   - "good" when value <= good threshold
 *   - "needs-improvement" when good < value <= poor
 *   - "poor" when value > poor threshold
 */
export function rateMetric(name: MetricName, value: number): MetricRating {
  const t = CWV_THRESHOLDS[name];
  if (Number.isNaN(value)) return "poor";
  if (value <= t.good) return "good";
  if (value <= t.poor) return "needs-improvement";
  return "poor";
}

/**
 * Creates a validated Metric object from raw values.
 *
 * Throws {@link WebVitalsError} for invalid inputs
 * (NaN, negative, non-integer entries count).
 */
export function recordMetric(
  name: MetricName,
  value: number,
  entries = 1,
): Metric {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new WebVitalsError(
      "METRIC_VALUE_INVALID",
      `Invalid value for ${name}: ${value}`,
    );
  }
  if (
    typeof entries !== "number" ||
    !Number.isInteger(entries) ||
    entries < 0
  ) {
    throw new WebVitalsError(
      "METRIC_ENTRIES_INVALID",
      `Invalid entries count for ${name}: ${entries}`,
    );
  }
  return { name, value, rating: rateMetric(name, value), entries };
}

/**
 * Registry that accumulates metrics and exposes privacy-safe reporting.
 *
 * In production this would be populated from the `web-vitals` npm package
 * callbacks. For testing, metrics are recorded directly via `record()`.
 */
export class WebVitalsRegistry {
  private readonly metrics = new Map<MetricName, Metric>();

  /** Record (or replace) a metric. Returns the full Metric object. */
  record(name: MetricName, value: number, entries = 1): Metric {
    const metric = recordMetric(name, value, entries);
    this.metrics.set(name, metric);
    return metric;
  }

  /** Retrieve a single metric, or null if not yet recorded. */
  get(name: MetricName): Metric | null {
    return this.metrics.get(name) ?? null;
  }

  /** All recorded metrics in insertion order. */
  getAll(): Metric[] {
    return Array.from(this.metrics.values());
  }

  size(): number {
    return this.metrics.size;
  }

  /** Remove all recorded metrics. */
  clear(): void {
    this.metrics.clear();
  }

  /**
   * Merge from another registry. Metrics that exist in both are
   * overwritten by the other registry's value.
   */
  merge(other: WebVitalsRegistry): this {
    for (const metric of other.getAll()) {
      this.metrics.set(metric.name, metric);
    }
    return this;
  }

  /** True if all three Core Web Vitals have been recorded. */
  hasAllCoreVitals(): boolean {
    return (
      this.get("LCP") !== null &&
      this.get("INP") !== null &&
      this.get("CLS") !== null
    );
  }

  /** True when all Core Web Vitals are present and rated "good". */
  isCoreVitalsPass(): boolean {
    const lcp = this.get("LCP");
    const inp = this.get("INP");
    const cls = this.get("CLS");
    return (
      lcp !== null &&
      inp !== null &&
      cls !== null &&
      lcp.rating === "good" &&
      inp.rating === "good" &&
      cls.rating === "good"
    );
  }

  /** True when any Core Web Vital is rated "poor". */
  hasCoreVitalsIssue(): boolean {
    return (["LCP", "INP", "CLS"] as MetricName[]).some((name) => {
      const m = this.get(name);
      return m !== null && m.rating === "poor";
    });
  }

  /**
   * Overall page-experience rating across all recorded metrics.
   * Returns "unknown" when no metrics have been recorded.
   */
  getRating(): "good" | "needs-improvement" | "poor" | "unknown" {
    if (this.metrics.size === 0) return "unknown";
    if (this.getAll().some((m) => m.rating === "poor")) return "poor";
    if (this.getAll().some((m) => m.rating === "needs-improvement")) {
      return "needs-improvement";
    }
    return "good";
  }

  /**
   * Privacy-safe snapshot — NO PII, NO URLs, NO element content.
   * Safe to forward to any analytics sink or log.
   */
  toReport(): WebVitalsReport {
    return {
      lcp: this.get("LCP"),
      inp: this.get("INP"),
      cls: this.get("CLS"),
      fcp: this.get("FCP"),
      ttfb: this.get("TTFB"),
      fetchedAt: new Date().toISOString(),
    };
  }
}

/**
 * Bundle budget targets for the web app.
 * Enforced at build via `vite build --mode production`.
 * See docs/PERFORMANCE.md for rationale.
 */
export interface BundleBudget {
  /** Maximum total JS bundle size in bytes. */
  maxBytes: number;
  /** Maximum number of JS chunks. */
  maxChunks: number;
  /** Maximum size of a single asset chunk in bytes. */
  maxAssetSize: number;
}

/** Default bundle budget — conservative for 3G-class mobile. */
export const DEFAULT_BUNDLE_BUDGET: BundleBudget = {
  maxBytes: 200_000,    // 200 KB total JS (good first-use on 3G)
  maxChunks: 10,
  maxAssetSize: 50_000,  // 50 KB per chunk
};
