import { describe, expect, it } from "vitest";

import {
  CWV_THRESHOLDS,
  DEFAULT_BUNDLE_BUDGET,
  Metric,
  MetricName,
  MetricRating,
  rateMetric,
  recordMetric,
  WebVitalsRegistry,
  WebVitalsError,
} from "./webVitals";

const CORE_VITALS: MetricName[] = ["LCP", "INP", "CLS"];
const ALL_METRICS: MetricName[] = ["LCP", "INP", "CLS", "FCP", "TTFB"];

describe("rateMetric", () => {
  it("rates LCP correctly at boundaries", () => {
    expect(rateMetric("LCP", 2.5)).toBe("good");
    expect(rateMetric("LCP", 2.6)).toBe("needs-improvement");
    expect(rateMetric("LCP", 4.0)).toBe("needs-improvement");
    expect(rateMetric("LCP", 4.1)).toBe("poor");
  });

  it("rates INP correctly at boundaries", () => {
    expect(rateMetric("INP", 200)).toBe("good");
    expect(rateMetric("INP", 201)).toBe("needs-improvement");
    expect(rateMetric("INP", 500)).toBe("needs-improvement");
    expect(rateMetric("INP", 501)).toBe("poor");
  });

  it("rates CLS correctly at boundaries (ratio)", () => {
    expect(rateMetric("CLS", 0.1)).toBe("good");
    expect(rateMetric("CLS", 0.15)).toBe("needs-improvement");
    expect(rateMetric("CLS", 0.25)).toBe("needs-improvement");
    expect(rateMetric("CLS", 0.26)).toBe("poor");
  });

  it("rates FCP and TTFB correctly", () => {
    expect(rateMetric("FCP", 1.8)).toBe("good");
    expect(rateMetric("FCP", 3.0)).toBe("needs-improvement");
    expect(rateMetric("FCP", 3.1)).toBe("poor");
    expect(rateMetric("TTFB", 200)).toBe("good");
    expect(rateMetric("TTFB", 600)).toBe("needs-improvement");
    expect(rateMetric("TTFB", 601)).toBe("poor");
  });

  it("rates NaN as poor (fail-safe)", () => {
    expect(rateMetric("LCP", NaN)).toBe("poor");
  });
});

describe("recordMetric", () => {
  it("creates a valid metric with rating", () => {
    const m = recordMetric("LCP", 2.5, 3);
    expect(m).toEqual({ name: "LCP", value: 2.5, rating: "good", entries: 3 });
  });

  it("defaults entries to 1", () => {
    const m = recordMetric("CLS", 0.05);
    expect(m.entries).toBe(1);
  });

  it("throws WebVitalsError for NaN value", () => {
    expect(() => recordMetric("LCP", NaN)).toThrow(WebVitalsError);
    try {
      recordMetric("LCP", NaN);
      expect.fail("should have thrown");
    } catch (e) {
      expect((e as WebVitalsError).code).toBe("METRIC_VALUE_INVALID");
    }
  });

  it("throws WebVitalsError for negative value", () => {
    expect(() => recordMetric("INP", -1)).toThrowError(WebVitalsError);
  });

  it("throws WebVitalsError for non-number value", () => {
    expect(() => recordMetric("LCP", "2.5" as unknown as number)).toThrowError(
      WebVitalsError,
    );
  });

  it("throws WebVitalsError for Infinity value", () => {
    expect(() => recordMetric("LCP", Infinity)).toThrowError(WebVitalsError);
  });

  it("throws WebVitalsError for negative entries", () => {
    expect(() => recordMetric("LCP", 1.0, -1)).toThrowError(
      WebVitalsError,
    );
    try {
      recordMetric("LCP", 1.0, -1);
      expect.fail("should have thrown");
    } catch (e) {
      expect((e as WebVitalsError).code).toBe("METRIC_ENTRIES_INVALID");
    }
  });

  it("throws WebVitalsError for non-integer entries", () => {
    expect(() => recordMetric("LCP", 1.0, 1.5)).toThrowError(WebVitalsError);
  });
});

describe("WebVitalsRegistry", () => {
  it("records and retrieves a metric", () => {
    const r = new WebVitalsRegistry();
    const m = r.record("LCP", 2.0, 1);
    expect(r.get("LCP")).toBe(m);
    expect(m.rating).toBe("good");
  });

  it("returns null for unrecorded metrics", () => {
    const r = new WebVitalsRegistry();
    expect(r.get("LCP")).toBeNull();
    expect(r.get("INP")).toBeNull();
    expect(r.get("CLS")).toBeNull();
  });

  it("getAll returns metrics in insertion order", () => {
    const r = new WebVitalsRegistry();
    r.record("LCP", 2.0);
    r.record("INP", 150);
    r.record("CLS", 0.05);
    expect(r.getAll().map((m) => m.name)).toEqual(["LCP", "INP", "CLS"]);
  });

  it("size reflects number of unique metrics recorded", () => {
    const r = new WebVitalsRegistry();
    expect(r.size()).toBe(0);
    r.record("LCP", 2.0);
    expect(r.size()).toBe(1);
    r.record("LCP", 2.5); // overwrite, not add
    expect(r.size()).toBe(1);
    r.record("CLS", 0.1);
    expect(r.size()).toBe(2);
  });

  it("clear removes all metrics", () => {
    const r = new WebVitalsRegistry();
    r.record("LCP", 2.0);
    r.record("CLS", 0.1);
    r.clear();
    expect(r.size()).toBe(0);
    expect(r.getAll()).toEqual([]);
  });

  it("merge overwrites existing metrics with newer values", () => {
    const a = new WebVitalsRegistry();
    const b = new WebVitalsRegistry();
    a.record("LCP", 2.0);
    b.record("LCP", 3.5); // worse
    b.record("INP", 400);
    a.merge(b);
    expect(a.get("LCP")?.value).toBe(3.5);
    expect(a.get("LCP")?.rating).toBe("needs-improvement");
    expect(a.get("INP")?.value).toBe(400);
    expect(a.size()).toBe(2);
  });

  it("hasAllCoreVitals is true only when LCP, INP, CLS all present", () => {
    const r = new WebVitalsRegistry();
    expect(r.hasAllCoreVitals()).toBe(false);
    r.record("LCP", 2.0);
    expect(r.hasAllCoreVitals()).toBe(false);
    r.record("INP", 100);
    expect(r.hasAllCoreVitals()).toBe(false);
    r.record("CLS", 0.05);
    expect(r.hasAllCoreVitals()).toBe(true);
  });

  it("isCoreVitalsPass requires all three good", () => {
    const r = new WebVitalsRegistry();
    r.record("LCP", 2.0);
    r.record("INP", 100);
    r.record("CLS", 0.05);
    expect(r.isCoreVitalsPass()).toBe(true);

    r.record("LCP", 3.0); // still in range, not poor
    expect(r.isCoreVitalsPass()).toBe(false);
    expect(r.hasCoreVitalsIssue()).toBe(false);

    r.record("CLS", 0.5); // poor
    expect(r.isCoreVitalsPass()).toBe(false);
    expect(r.hasCoreVitalsIssue()).toBe(true);
  });

  it("hasCoreVitalsIssue is false when all are good or needs-improvement", () => {
    const r = new WebVitalsRegistry();
    r.record("LCP", 3.0); // needs-improvement
    r.record("INP", 300); // needs-improvement
    r.record("CLS", 0.2); // needs-improvement
    expect(r.hasCoreVitalsIssue()).toBe(false);
  });

  it("getRating is unknown when empty", () => {
    const r = new WebVitalsRegistry();
    expect(r.getRating()).toBe("unknown");
  });

  it("getRating is good when all metrics are good", () => {
    const r = new WebVitalsRegistry();
    r.record("LCP", 1.0);
    r.record("INP", 50);
    r.record("CLS", 0.05);
    r.record("FCP", 0.9);
    r.record("TTFB", 100);
    expect(r.getRating()).toBe("good");
  });

  it("getRating is poor when any metric is poor (even if not Core Vitals)", () => {
    const r = new WebVitalsRegistry();
    r.record("FCP", 5.0); // poor, not a Core Web Vital
    expect(r.getRating()).toBe("poor");
  });

  it("getRating is needs-improvement when no poor but some ni", () => {
    const r = new WebVitalsRegistry();
    r.record("LCP", 1.0);
    r.record("FCP", 2.0); // needs-improvement
    expect(r.getRating()).toBe("needs-improvement");
  });

  it("toReport returns all five metric slots with null when absent", () => {
    const r = new WebVitalsRegistry();
    r.record("LCP", 2.0);
    const report = r.toReport();
    expect(report.lcp).not.toBeNull();
    expect(report.inp).toBeNull();
    expect(report.cls).toBeNull();
    expect(report.fcp).toBeNull();
    expect(report.ttfb).toBeNull();
  });

  it("toReport fetchedAt is an ISO timestamp string", () => {
    const r = new WebVitalsRegistry();
    r.record("LCP", 1.0);
    const t = r.toReport().fetchedAt;
    expect(typeof t).toBe("string");
    expect(new Date(t).getTime()).not.toBeNaN();
  });
});

describe("privacy — toReport contains no PII", () => {
  it("toReport never includes URL, pathname, or element content fields", () => {
    const r = new WebVitalsRegistry();
    for (const name of ALL_METRICS) {
      r.record(name, 1.0);
    }
    const report = r.toReport();
    const json = JSON.stringify(report);

    // No PII-like or location fields
    const forbidden = ["url", "href", "pathname", "origin", "element", "innerHTML", "text", "textContent", "userId", "user_id", "email", "ip"];
    for (const key of forbidden) {
      expect(json).not.toContain(`"${key}"`);
    }
  });

  it("Metric objects contain only name, value, rating, entries", () => {
    const m = recordMetric("LCP", 2.0, 3);
    const keys = Object.keys(m);
    expect(keys.sort()).toEqual(["entries", "name", "rating", "value"]);
  });
});

describe("constants", () => {
  it("CWV_THRESHOLDS has correct values for all five metrics", () => {
    for (const name of ALL_METRICS) {
      expect(CWV_THRESHOLDS[name]).toBeDefined();
      expect(CWV_THRESHOLDS[name].good).toBeLessThanOrEqual(
        CWV_THRESHOLDS[name].poor,
      );
    }
    expect(CWV_THRESHOLDS.LCP.good).toBe(2.5);
    expect(CWV_THRESHOLDS.LCP.poor).toBe(4.0);
    expect(CWV_THRESHOLDS.CLS.good).toBeCloseTo(0.1);
    expect(CWV_THRESHOLDS.CLS.poor).toBeCloseTo(0.25);
  });

  it("DEFAULT_BUNDLE_BUDGET has conservative values", () => {
    expect(DEFAULT_BUNDLE_BUDGET.maxBytes).toBe(200_000);
    expect(DEFAULT_BUNDLE_BUDGET.maxChunks).toBe(10);
    expect(DEFAULT_BUNDLE_BUDGET.maxAssetSize).toBe(50_000);
  });
});
