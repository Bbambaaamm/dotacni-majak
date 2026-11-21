// Keep the calendar day printed by the source, not the viewer's local day.
// Ordering by instant belongs to the caller; displaying a timestamp does not
// imply that the call is still open or that its conditions were verified today.
export function sourceCalendarDate(value: string | null): string {
  if (!value) return "Není uvedeno";
  const match = /^(\d{4}-\d{2}-\d{2})(?:$|T\d{2}:\d{2})/.exec(value);
  if (!match || !Number.isFinite(Date.parse(value))) return value;

  const day = new Date(`${match[1]}T12:00:00Z`);
  if (!Number.isFinite(day.getTime()) || day.toISOString().slice(0, 10) !== match[1]) return value;
  return new Intl.DateTimeFormat("cs-CZ", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  }).format(day);
}
