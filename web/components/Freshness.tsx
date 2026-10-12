import type { Freshness } from "@/lib/queries";
import { LocalTime } from "./LocalTime";

export function FreshnessLine({ f }: { f: Freshness }) {
  return (
    <p className="text-xs text-muted">
      Fixtures updated <LocalTime iso={f.latestFixtureFetch} /> · latest result in database {f.latestResultDate ?? "–"} ·
      forecasts made <LocalTime iso={f.latestForecast} /> (model {f.modelVersion ?? "–"}) · sources:{" "}
      {f.sources.length ? f.sources.join(", ") : "–"}
    </p>
  );
}
