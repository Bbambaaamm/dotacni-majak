import { describe, expect, test } from "vitest";

import {
  STATUS_KINDS,
  colors,
  spacing,
  statusColor,
  typography,
} from "./tokens";

describe("design tokens", () => {
  test("colors match DESIGN_SYSTEM.md v1", () => {
    expect(colors.navy).toBe("#0b2d48");
    expect(colors.teal).toBe("#087f8c");
    expect(colors.cyan).toBe("#20b8cd");
    expect(colors.ink).toBe("#17212b");
    expect(colors.page).toBe("#f8fafc");
    expect(colors.border).toBe("#dce4ea");
    expect(colors.success).toBe("#16865c");
    expect(colors.warning).toBe("#a86100");
    expect(colors.error).toBe("#c83e4d");
  });

  test("spacing follows 4px grid (4/8/12/16/24/32/48/64/96)", () => {
    expect(spacing.xs).toBe(4);
    expect(spacing.sm).toBe(8);
    expect(spacing.md).toBe(12);
    expect(spacing.lg).toBe(16);
    expect(spacing.xl).toBe(24);
    expect(spacing.xl2).toBe(32);
    expect(spacing.xl3).toBe(48);
    expect(spacing.xl4).toBe(64);
    expect(spacing.xl5).toBe(96);
  });

  test("all spacing values are multiples of 4", () => {
    for (const key of Object.keys(spacing)) {
      const value = spacing[key as keyof typeof spacing];
      expect(value % 4).toBe(0);
    }
  });

  test("statusColor maps every status kind to a color", () => {
    for (const kind of STATUS_KINDS) {
      expect(statusColor[kind]).toBeDefined();
    }
    expect(statusColor.success).toBe(colors.success);
    expect(statusColor.error).toBe(colors.error);
    expect(statusColor.unknown).toBe(colors.muted);
  });

  test("STATUS_KINDS includes success/warning/error/info/unknown", () => {
    expect(STATUS_KINDS).toEqual(["success", "warning", "error", "info", "unknown"]);
  });

  test("typography has Inter family and tabular numerals note", () => {
    expect(typography.family.body).toContain("Inter");
    expect(typography.fontWeight.bold).toBe(700);
    expect(typography.fontWeight.black).toBe(900);
  });
});
