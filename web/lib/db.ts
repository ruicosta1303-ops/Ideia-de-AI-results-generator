import "server-only";
import postgres from "postgres";

/** Server-side database client. DATABASE_URL is a server-only environment variable:
 *  it is never sent to the browser (no NEXT_PUBLIC_ prefix, and this module is server-only). */
const url = process.env.DATABASE_URL;

declare global {
  var __sql: ReturnType<typeof postgres> | undefined;
}

export const sql = url ? (globalThis.__sql ??= postgres(url, { max: 3, idle_timeout: 20, prepare: false })) : null;

export class DatabaseNotConfigured extends Error {
  constructor() {
    super("DATABASE_URL is not set on the server");
  }
}

export function db() {
  if (!sql) throw new DatabaseNotConfigured();
  return sql;
}
