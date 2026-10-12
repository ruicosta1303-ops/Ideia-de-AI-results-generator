import { getFreshness } from "@/lib/queries";

/** Shown whenever the database contains development-only synthetic data. */
export async function SyntheticBanner() {
  let sources: string[] = [];
  try {
    sources = (await getFreshness()).sources;
  } catch {
    return null;
  }
  if (!sources.some((s) => s.toUpperCase().includes("SYNTHETIC"))) return null;
  return (
    <div className="bg-warn px-4 py-2 text-center text-sm font-semibold text-black">
      Development data: these matches and numbers are SYNTHETIC test data, not real football.
    </div>
  );
}
