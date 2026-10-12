import type { ReactNode } from "react";

const KINDS = {
  fact: { label: "Observed facts", tone: "border-fact/50", chip: "bg-fact/15 text-fact" },
  model: { label: "Model estimate", tone: "border-model/50", chip: "bg-model/15 text-model" },
  ai: { label: "AI explanation", tone: "border-ai/50", chip: "bg-ai/15 text-ai" },
  quality: { label: "Data availability", tone: "border-warn/40", chip: "bg-warn/15 text-warn" },
} as const;

/** Every block says what kind of information it holds: facts, model estimates or AI text. */
export function Panel({ kind, title, children, className = "" }: { kind: keyof typeof KINDS; title: string; children: ReactNode; className?: string }) {
  const k = KINDS[kind];
  return (
    <section className={`rounded-lg border ${k.tone} bg-surface-1 p-4 ${className}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${k.chip}`}>{k.label}</span>
        <h2 className="text-sm font-semibold text-primary">{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function DataUnavailable({ what, impact }: { what: string; impact: string }) {
  return (
    <div className="rounded border border-dashed border-border px-3 py-2 text-sm">
      <div>
        <span className="font-medium text-primary">{what}:</span> <span className="text-warn">Data unavailable</span>
      </div>
      <p className="mt-0.5 text-xs text-muted">{impact}</p>
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-border bg-surface-1 p-4 text-sm text-secondary">{children}</div>;
}
