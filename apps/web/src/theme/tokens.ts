/**
 * Design tokens for Dotační maják — v1
 *
 * Extracted from docs/DESIGN_SYSTEM.md and styles.css.
 * Provides type-safe, reusable design constants consumed by UI components.
 *
 * Priority order: Srozumitelnost → důvěra → další krok → estetika.
 */
export const colors = {
  // Brand
  navy: "#0b2d48",
  teal: "#087f8c",
  cyan: "#20b8cd",
  // Core
  ink: "#17212b",
  page: "#f8fafc",
  border: "#dce4ea",
  info: "#0b7285",
  // Semantic
  success: "#16865c",
  warning: "#a86100",
  error: "#c83e4d",
  // Neutrals
  surface: "#ffffff",
  muted: "#52606d",
} as const;

export type ColorName = keyof typeof colors;

/** Spacing scale — 4px grid (4/8/12/16/24/32/48/64/96). */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xl2: 32,
  xl3: 48,
  xl4: 64,
  xl5: 96,
} as const;

export type SpacingName = keyof typeof spacing;

/** Border radius. */
export const radii = {
  control: 12,
  card: 16,
  full: 9999,
} as const;

/** Typography. */
export const typography = {
  family: {
    body: "Inter, system-ui, -apple-system, BlinkMacSystemFont, " +
          "\"Segoe UI\", Roboto, sans-serif",
  },
  fontSize: {
    xs: 12,
    sm: 14,
    base: 16,
    lg: 18,
    xl: 20,
    xl2: 24,
    xl3: 32,
  },
  fontWeight: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
    black: 900,
  },
} as const;

/** Breakpoints (mobile-first). */
export const breakpoints = {
  mobile: 0,
  tablet: 768,
  desktop: 1280,
} as const;

/** Semantic status → design token mapping. */
export const statusColor = {
  success: colors.success,
  warning: colors.warning,
  error: colors.error,
  info: colors.info,
  unknown: colors.muted,
} as const;

export const STATUS_KINDS = ["success", "warning", "error", "info", "unknown"] as const;
