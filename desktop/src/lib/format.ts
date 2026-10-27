export function countdown(seconds: number): string {
  const total = Math.max(0, Math.ceil(Number.isFinite(seconds) ? seconds : 0));
  if (total >= 86400)
    return `${Math.floor(total / 86400)}d ${Math.floor((total % 86400) / 3600)}h`;
  const h = Math.floor(total / 3600),
    m = Math.floor((total % 3600) / 60),
    s = total % 60;
  return h
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}
export function dateTime(timestamp: number | null | undefined, zone?: string) {
  if (!timestamp || !Number.isFinite(timestamp)) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: zone,
  }).format(new Date(timestamp * 1000));
}
export function localInput(timestamp?: number | null, zone?: string) {
  const value = timestamp ? new Date(timestamp * 1000) : new Date();
  if (zone)
    return new Intl.DateTimeFormat("sv-SE", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .format(value)
      .replace(" ", "T");
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
export function unixInput(value: string) {
  return value ? new Date(value).getTime() / 1000 : null;
}
export function hotkeyName(key: string) {
  return (
    (
      {
        right_ctrl: "Right Ctrl",
        left_ctrl: "Left Ctrl",
        right_alt: "Right Alt",
        left_alt: "Left Alt",
        f8: "F8",
        f9: "F9",
      } as Record<string, string>
    )[key] ?? key
  );
}
