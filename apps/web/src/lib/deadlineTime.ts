export function sourceDeadlineNeedsReview(value: string | null): boolean {
  if (value === null) return false; // Missing is UNKNOWN, not a malformed source date.
  const day = value.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) ||
      !Number.isFinite(Date.parse(`${day}T00:00:00Z`)) ||
      new Date(`${day}T00:00:00Z`).toISOString().slice(0, 10) !== day) return true;
  if (value.length === 10) return false; // Source date without an asserted clock.
  return !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    || !Number.isFinite(Date.parse(value));
}

// Show the source's clock and offset without converting to the viewer's timezone.
// Date-only and unrecognized values retain their original precision and spelling.
export function deadlineTime(value: string | null): string {
  if (!value) return "Není uvedeno";
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) ||
      Number.isNaN(Date.parse(value))) return value;
  return value.replace("T", " ").replace(/Z$/, " UTC");
}
