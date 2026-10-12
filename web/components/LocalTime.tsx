"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/** Shows a timestamp in the viewer's own time zone. The server render shows UTC. */
export function LocalTime({ iso, mode = "datetime" }: { iso: string | null; mode?: "datetime" | "time" | "date" }) {
  const isClient = useSyncExternalStore(subscribe, () => true, () => false);
  if (!iso) return <span className="text-muted">time TBC</span>;
  const d = new Date(iso);
  const opts: Intl.DateTimeFormatOptions =
    mode === "time"
      ? { hour: "2-digit", minute: "2-digit" }
      : mode === "date"
        ? { weekday: "short", day: "numeric", month: "short" }
        : { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" };
  if (!isClient) {
    // Deterministic on server and during hydration (Intl output differs between Node and browsers).
    const t = d.toISOString();
    const text = mode === "time" ? `${t.slice(11, 16)} UTC` : mode === "date" ? t.slice(0, 10) : `${t.slice(0, 10)} ${t.slice(11, 16)} UTC`;
    return <time dateTime={iso}>{text}</time>;
  }
  return <time dateTime={iso}>{d.toLocaleString(undefined, opts)}</time>;
}
