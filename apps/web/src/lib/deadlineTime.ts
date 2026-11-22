export function sourceDeadlineNeedsReview(value: string | null): boolean {
  if (value === null) return false; // Missing is UNKNOWN, not a malformed source date.
  const day = value.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) ||
      !Number.isFinite(Date.parse(`${day}T00:00:00Z`)) ||
      new Date(`${day}T00:00:00Z`).toISOString().slice(0, 10) !== day) return true;
  if (value.length === 10) return false; // Source date without an asserted clock.
  return !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}:\d{2})$/.test(value)
    || !Number.isFinite(Date.parse(value));
}

// Compare only equally precise, validated source bounds. A date-only boundary
// cannot be ordered against a clock time without inventing a timezone/cutoff.
export function conflictingDeadlineBounds(start: string | null, end: string | null): boolean {
  if (!start || !end || sourceDeadlineNeedsReview(start) || sourceDeadlineNeedsReview(end)) return false;
  if ((start.length === 10) !== (end.length === 10)) return false;
  return start.length === 10 ? end < start : Date.parse(end) < Date.parse(start);
}

// Show the source's clock and offset without converting to the viewer's timezone.
// Date-only and unrecognized values retain their original precision and spelling.
export function deadlineTime(value: string | null): string {
  if (!value) return "Není uvedeno";
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}:\d{2})$/.test(value) ||
      Number.isNaN(Date.parse(value))) return value;
  return value.replace("T", " ").replace(/Z$/, " UTC");
}
