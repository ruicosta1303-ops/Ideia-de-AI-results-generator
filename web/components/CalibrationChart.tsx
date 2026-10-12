import { pct } from "@/lib/analysis";
import type { CalibrationBin } from "@/lib/types";

interface Series {
  name: string;
  colorVar: string; // CSS variable, e.g. "--home"
  bins: CalibrationBin[];
}

const W = 320;
const H = 320;
const PAD = 36;
const LEFT = 52; // room for the rotated axis title and tick labels
const x = (p: number) => LEFT + p * (W - LEFT - PAD);
const y = (p: number) => H - PAD - p * (H - 2 * PAD);

/** Reliability diagram: predicted probability (x) against how often it happened (y).
 *  Points on the dashed diagonal are perfectly calibrated. Hover a point for its numbers. */
export function CalibrationChart({ series }: { series: Series[] }) {
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-sm" role="img" aria-label="Calibration chart">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} stroke="var(--border)" strokeWidth={1} />
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth={1} />
            <text x={x(t)} y={H - PAD + 14} textAnchor="middle" fontSize={10} fill="var(--text-muted)">{pct(t)}</text>
            <text x={LEFT - 6} y={y(t) + 3} textAnchor="end" fontSize={10} fill="var(--text-muted)">{pct(t)}</text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--text-muted)" strokeDasharray="4 4" strokeWidth={1} />
        <text x={(LEFT + W - PAD) / 2} y={H - 4} textAnchor="middle" fontSize={11} fill="var(--text-secondary)">Predicted probability</text>
        <text x={12} y={H / 2} textAnchor="middle" fontSize={11} fill="var(--text-secondary)" transform={`rotate(-90 12 ${H / 2})`}>
          How often it happened
        </text>
        {series.map((s) => {
          const pts = s.bins.filter((b) => b.count > 0 && b.mean_predicted != null && b.observed_rate != null);
          return (
            <g key={s.name}>
              <polyline
                fill="none"
                stroke={`var(${s.colorVar})`}
                strokeWidth={2}
                points={pts.map((b) => `${x(b.mean_predicted!)},${y(b.observed_rate!)}`).join(" ")}
              />
              {pts.map((b) => (
                <g key={b.lower}>
                  <circle cx={x(b.mean_predicted!)} cy={y(b.observed_rate!)} r={12} fill="transparent">
                    <title>{`${s.name}: predicted ${pct(b.mean_predicted, 1)}, happened ${pct(b.observed_rate, 1)} (${b.count} outcomes)`}</title>
                  </circle>
                  <circle cx={x(b.mean_predicted!)} cy={y(b.observed_rate!)} r={4} fill={`var(${s.colorVar})`} stroke="var(--surface-1)" strokeWidth={2} pointerEvents="none" />
                </g>
              ))}
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-secondary">
        {series.map((s) => (
          <span key={s.name} className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-4" style={{ background: `var(${s.colorVar})` }} /> {s.name}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 border-t border-dashed border-muted" /> perfect calibration
        </span>
      </figcaption>
    </figure>
  );
}
