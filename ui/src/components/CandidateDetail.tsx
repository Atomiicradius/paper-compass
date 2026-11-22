import { Fragment } from "react";
import { ChevronRight } from "lucide-react";
import type { ElementKind, Opportunity } from "@/api/types";
import { KIND_COLORS, KIND_LABELS, KIND_TEXT } from "@/lib/colors";
import { pairKinds, SIGNAL_KEYS, SIGNAL_LABELS } from "@/lib/opportunities";
import { cn, formatNumber } from "@/lib/utils";
import { Badge, Button, Tip } from "@/components/ui/primitives";
import { SignalMeter } from "@/components/motion";
import { CountUp } from "@/components/CountUp";
import { ScoreRing } from "@/components/ScoreRing";
import { SIGNAL_COLORS, signalTip } from "@/components/candidate-signals";

/** Where the expected marker and the observed dot sit on the track (both 0..1 of its width, on one shared scale). */
export function trackPositions(observed: number, expected: number): { observed: number; expected: number } {
  const max = Math.max(observed, expected, 1) * 1.2;
  return { observed: Math.min(1, Math.max(0, observed / max)), expected: Math.min(1, Math.max(0, expected / max)) };
}

/** The existing colour rule: a confidence below 0.5 (or none) is shown in the warning colour. */
export const isLowConfidence = (c: number | null | undefined) => (c ?? 0) < 0.5;

function ElementChip({ kind, name }: { kind: ElementKind; name: string }) {
  return (
    <div className="glass min-w-0 rounded-2xl px-5 py-4" data-kind={kind} style={{ boxShadow: `0 0 0 1px ${KIND_COLORS[kind]}33, 0 12px 32px -16px ${KIND_COLORS[kind]}66` }}>
      <div className="mono-label flex items-center gap-1.5 text-[10px]">
        <span className="size-1.5 rounded-full" style={{ background: KIND_COLORS[kind] }} aria-hidden />
        {KIND_LABELS[kind]}
      </div>
      <div className="mt-1 font-display text-2xl leading-tight break-words" style={{ color: KIND_TEXT[kind] }}>{name}</div>
    </div>
  );
}

/** A glowing line between two element chips, from one kind's colour to the other's. Decoration only. */
function Connector({ from, to }: { from: ElementKind; to: ElementKind }) {
  return (
    <div aria-hidden className="relative mx-1 h-px w-8 shrink-0 sm:w-14" style={{ background: `linear-gradient(90deg, ${KIND_COLORS[from]}, ${KIND_COLORS[to]})`, boxShadow: `0 0 10px ${KIND_COLORS[from]}88, 0 0 14px ${KIND_COLORS[to]}66` }}>
      <span className="absolute top-1/2 left-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground/90" />
    </div>
  );
}

/**
 * The detail of the selected candidate: its elements as two large glass chips joined by a glowing connector, a large score ring
 * (counted up), observed versus expected on one track, the three signals, the confidence, and the button that opens the evidence.
 */
export function CandidateDetail({
  opportunity: o, rank, score, scoreLabel, onOpenEvidence,
}: { opportunity: Opportunity; rank: number; score: number; scoreLabel: string; onOpenEvidence: (o: Opportunity) => void }) {
  const kinds = pairKinds(o.elements);
  const pos = trackPositions(o.observed_count, o.expected_count);
  const low = isLowConfidence(o.confidence);
  return (
    <section aria-label="Selected candidate" data-testid="candidate-detail" className="glass space-y-6 rounded-3xl p-6">
      <p className="mono-label">#{rank} · opportunity {o.opportunity_id}</p>

      <div className="flex flex-wrap items-center gap-y-3">
        {kinds.map((k, i) => (
          <Fragment key={k}>
            {i > 0 ? <Connector from={kinds[i - 1]!} to={k} /> : null}
            <ElementChip kind={k} name={o.elements[k] as string} />
          </Fragment>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-8 gap-y-5">
        <Tip content={`${scoreLabel}`} side="right">
          {/* keyed by the opportunity: choosing another one counts up again */}
          <div className="cursor-help" data-testid="score-badge">
            <ScoreRing key={o.opportunity_id} score={score} size={148} strokeWidth={7}>
              <div className="text-center">
                <div className="mono-label text-[10px]">Score</div>
                <CountUp key={o.opportunity_id} trigger="mount" value={score} className="mono-figure text-5xl" />
              </div>
            </ScoreRing>
          </div>
        </Tip>

        <div className="min-w-56 flex-1 space-y-4">
          <div>
            <div className="relative h-8" role="img" aria-label={`Observed ${o.observed_count}, expected ${formatNumber(o.expected_count, 1)} (on one scale)`} data-testid="observed-expected-track">
              <div className="absolute top-1/2 right-0 left-0 h-2 -translate-y-1/2 rounded-full bg-hover" />
              <div className="absolute top-1/2 h-6 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--tick)]" style={{ left: `${pos.expected * 100}%` }} data-testid="expected-marker" />
              <div className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-primary shadow-[0_0_10px_color-mix(in_srgb,var(--primary)_60%,transparent)]" style={{ left: `${pos.observed * 100}%` }} data-testid="observed-dot" />
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <Badge className="border-border bg-hover font-mono">Observed Count: {o.observed_count}</Badge>
              <Badge className="border-border bg-hover font-mono">Expected: {formatNumber(o.expected_count, 1)}</Badge>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Tip content="min(1, expected / 5): a low observed count means little when few papers were expected.">
              <Badge className={cn("font-mono", low ? "border-warning/50 bg-warning-soft text-warning-text" : "border-border bg-hover")}>
                Confidence: {o.confidence == null ? "n/a" : o.confidence.toFixed(2)}
              </Badge>
            </Tip>
            {low ? <span className="text-xs font-medium text-warning-text">Low confidence</span> : null}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {SIGNAL_KEYS.map((k, i) => (
          <SignalMeter key={k} label={SIGNAL_LABELS[k]} value={o.signals[k]} color={SIGNAL_COLORS[k]} tip={signalTip(k, o)} delay={0.1 * i} />
        ))}
      </div>

      <Button onClick={() => onOpenEvidence(o)}>
        Evidence &amp; explanation <ChevronRight className="size-4" />
      </Button>
    </section>
  );
}
