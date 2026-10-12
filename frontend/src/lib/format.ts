export function formatKickoff(value: string | null, locale?: string): string {
  if (!value) return "Kickoff time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Kickoff time unavailable";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(date);
}
