// Show the source's clock and offset without converting to the viewer's timezone.
// Date-only and unrecognized values retain their original precision and spelling.
export function deadlineTime(value: string | null): string {
  if (!value) return "Není uvedeno";
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) ||
      Number.isNaN(Date.parse(value))) return value;
  return value.replace("T", " ").replace(/Z$/, " UTC");
}
