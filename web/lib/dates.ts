/** Fixtures are grouped by calendar day in this time zone (the product owner's); times are shown in the viewer's zone. */
export const GROUP_TZ = "Europe/Lisbon";

export function dayKey(iso: string, tz = GROUP_TZ): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso));
}

export function dayLabel(key: string, todayKey: string, tomorrowKey: string): string {
  if (key === todayKey) return "Today";
  if (key === tomorrowKey) return "Tomorrow";
  return new Date(`${key}T12:00:00Z`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
}
