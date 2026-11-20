export function safeOfficialUrl(value: string | null | undefined): string | null {
  if (!value || value !== value.trim() || /[\u0000-\u001f\u007f]/.test(value)) return null;
  try {
    const url = new URL(value);
    if ((url.protocol !== "https:" && url.protocol !== "http:") ||
        !url.hostname || url.username || url.password) return null;
    return value;
  } catch {
    return null;
  }
}
