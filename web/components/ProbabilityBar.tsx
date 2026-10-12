import { pct } from "@/lib/analysis";

interface Props {
  home: number;
  draw: number;
  away: number;
  homeLabel?: string;
  awayLabel?: string;
  compact?: boolean;
}

/** Stacked 1X2 bar. Segment colours carry identity only; every value is also written as text. */
export function ProbabilityBar({ home, draw, away, homeLabel = "Home", awayLabel = "Away", compact = false }: Props) {
  const segs = [
    { key: "home", label: `${homeLabel} win`, value: home, color: "bg-home" },
    { key: "draw", label: "Draw", value: draw, color: "bg-draw" },
    { key: "away", label: `${awayLabel} win`, value: away, color: "bg-away" },
  ];
  return (
    <div>
      <div
        className={`flex w-full gap-[2px] ${compact ? "h-2" : "h-3"}`}
        role="img"
        aria-label={segs.map((s) => `${s.label} ${pct(s.value)}`).join(", ")}
      >
        {segs.map((s, i) => (
          <div
            key={s.key}
            className={`group relative ${s.color} ${i === 0 ? "rounded-l" : ""} ${i === 2 ? "rounded-r" : ""}`}
            style={{ width: `${Math.max(s.value * 100, 0.5)}%` }}
          >
            <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded border border-border bg-surface-2 px-2 py-1 text-xs text-primary group-hover:block">
              {s.label}: {pct(s.value, 1)}
            </span>
          </div>
        ))}
      </div>
      <div className={`mt-1 grid grid-cols-3 tabular ${compact ? "text-xs" : "text-sm"}`}>
        {segs.map((s, i) => (
          <div key={s.key} className={`flex items-center gap-1 ${i === 1 ? "justify-center" : i === 2 ? "justify-end" : ""}`}>
            <span className={`inline-block h-2 w-2 rounded-full ${s.color}`} aria-hidden />
            <span className="text-secondary">{compact ? (i === 0 ? "1" : i === 1 ? "X" : "2") : s.label}</span>
            <span className="font-semibold text-primary">{pct(s.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
