import { Fragment } from "react";
import { ChevronRight } from "lucide-react";
import type { ElementKind, Opportunity } from "@/api/types";
import { KIND_COLORS, KIND_LABELS, KIND_TEXT } from "@/lib/colors";
import { useClosestWork } from "@/lib/closest-work";
import { pairKinds, SIGNAL_KEYS, SIGNAL_LABELS } from "@/lib/opportunities";
import { cn, formatNumber } from "@/lib/utils";
import { Badge, Button, IdBadge, Skeleton, Tip } from "@/components/ui/primitives";
import { SignalMeter } from "@/components/motion";
import { CountUp } from "@/components/CountUp";
import { ScoreRing } from "@/components/ScoreRing";
import { SIGNAL_COLORS, signalTip } from "@/components/candidate-signals";

/** The end of the scale of the observed-versus-expected track: the larger of the two (at least 1) plus 20 %. */
export function trackMax(observed: number, expected: number): number {
  return Math.max(observed, expected, 1) * 1.2;
}

/** Where the expected marker and the observed dot sit on the track (both 0..1 of its width, on one shared scale). */
export function trackPositions(observed: number, expected: number): { observed: number; expected: number } {
  const max = trackMax(observed, expected);
  return { observed: Math.min(1, Math.max(0, observed / max)), expected: Math.min(1, Math.max(0, expected / max)) };
}

/** The labelled ticks under the track: 0, the middle and the end of the scale, as text. */
export function trackTicks(observed: number, expected: number): { at: number; label: string }[] {
  const max = trackMax(observed, expected);
  const text = (v: number) => (v >= 10 ? String(Math.round(v)) : formatNumber(Math.round(v * 10) / 10, 1));
  return [0, 0.5, 1].map((at) => ({ at, label: at === 0 ? "0" : text(max * at) }));
}

/** The existing colour rule: a confidence below 0.5 (or none) is shown in the warning colour. */
export const isLowConfidence = (c: number | null | undefined) => (c ?? 0) < 0.5;

function ElementChip({ kind, name }: { kind: ElementKind; name: string }) {
  return (
    <div className="glass min-w-0 flex-1 rounded-2xl px-6 py-5" data-kind={kind} style={{ boxShadow: `0 0 0 1px ${KIND_COLORS[kind]}33, 0 12px 32px -16px ${KIND_COLORS[kind]}66` }}>
      <div className="mono-label flex items-center gap-1.5 text-[11px]">
        <span className="size-2 rounded-full" style={{ background: KIND_COLORS[kind] }} aria-hidden />
        {KIND_LABELS[kind]}
      </div>
      <div className="mt-1.5 font-display text-3xl leading-tight break-words xl:text-4xl" style={{ color: KIND_TEXT[kind] }}>{name}</div>
    </div>
  );
}

/** A glowing line between two element chips, from one kind's colour to the other's. Decoration only. */
function Connector({ from, to }: { from: ElementKind; to: ElementKind }) {
  return (
    <div aria-hidden className="relative mx-1 h-px w-8 shrink-0 sm:w-16" style={{ background: `linear-gradient(90deg, ${KIND_COLORS[from]}, ${KIND_COLORS[to]})`, boxShadow: `0 0 10px ${KIND_COLORS[from]}88, 0 0 14px ${KIND_COLORS[to]}66` }}>
      <span className="absolute top-1/2 left-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground/90" />
    </div>
  );
}

/** The three closest existing papers of the opportunity (from the explain call). Hidden if the call fails or finds none. */
function ClosestExistingWork({ opportunityId }: { opportunityId: number }) {
  const work = useClosestWork(opportunityId);
  if (work.status === "failed" || (work.status === "loaded" && work.papers.length === 0)) return null;
  return (
    <section aria-label="Closest existing work" data-testid="closest-work" aria-busy={work.status === "loading"}>
      <h3 className="mono-label mb-3">Closest existing work</h3>
      {work.status === "loading" ? (
        <div className="space-y-2" data-testid="closest-work-skeleton">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}
        </div>
      ) : (
        <ul className="space-y-2 p-0">
          {work.papers.map((p) => (
            <li key={p.paper_id} className="glass flex list-none items-center justify-between gap-3 rounded-xl px-4 py-2.5 text-sm">
              <span className="min-w-0 break-words">{p.title}</span>
              <IdBadge id={p.paper_id} className="shrink-0" />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * The detail of the selected candidate: its elements as two large glass chips joined by a glowing connector, a large score ring
 * (counted up) next to the observed-versus-expected track with a labelled scale, the three signals as equal cards, the
 * confidence, the button that opens the evidence, and the closest existing work.
 */
export function CandidateDetail({
  opportunity: o, rank, score, scoreLabel, onOpenEvidence,
}: { opportunity: Opportunity; rank: number; score: number; scoreLabel: string; onOpenEvidence: (o: Opportunity) => void }) {
  const kinds = pairKinds(o.elements);
  const pos = trackPositions(o.observed_count, o.expected_count);
  const ticks = trackTicks(o.observed_count, o.expected_count);
  const low = isLowConfidence(o.confidence);
  return (
    <section aria-label="Selected candidate" data-testid="candidate-detail" data-lenis-prevent className="scroll-thin glass space-y-8 overflow-x-hidden rounded-3xl p-6 xl:p-8 lg:h-full lg:overflow-y-auto">
      <p className="mono-label">#{rank} · opportunity {o.opportunity_id}</p>

      <div className="flex flex-wrap items-stretch gap-y-3">
        {kinds.map((k, i) => (
          <Fragment key={k}>
            {i > 0 ? <div className="flex items-center"><Connector from={kinds[i - 1]!} to={k} /></div> : null}
            <ElementChip kind={k} name={o.elements[k] as string} />
          </Fragment>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-10 gap-y-6">
        <Tip content={`${scoreLabel}`} side="right">
          {/* keyed by the opportunity: choosing another one counts up again */}
          <div className="cursor-help" data-testid="score-badge">
            <ScoreRing key={o.opportunity_id} score={score} size={190} strokeWidth={7}>
              <div className="text-center">
                <div className="mono-label text-[11px]">Score</div>
                <CountUp key={o.opportunity_id} trigger="mount" value={score} className="mono-figure text-6xl" />
              </div>
            </ScoreRing>
          </div>
        </Tip>

        <div className="min-w-64 flex-1 space-y-5">
          <div>
            <div className="relative h-8" role="img" aria-label={`Observed ${o.observed_count}, expected ${formatNumber(o.expected_count, 1)} (on one scale)`} data-testid="observed-expected-track">
              <div className="absolute top-1/2 right-0 left-0 h-3 -translate-y-1/2 rounded-full bg-hover" />
              <div className="absolute top-1/2 h-7 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--tick)]" style={{ left: `${pos.expected * 100}%` }} data-testid="expected-marker" />
              <div className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-primary shadow-[0_0_10px_color-mix(in_srgb,var(--primary)_60%,transparent)]" style={{ left: `${pos.observed * 100}%` }} data-testid="observed-dot" />
            </div>
            {/* the scale: 0, the middle and the end of the track, in the same units as the two numbers */}
            <div className="relative mt-1 h-4 font-mono text-[10px] text-muted" aria-hidden data-testid="track-scale">
              {ticks.map((t) => (
                <span key={t.at} className={cn("absolute", t.at === 0 ? "left-0" : t.at === 1 ? "right-0" : "-translate-x-1/2")} style={t.at > 0 && t.at < 1 ? { left: `${t.at * 100}%` } : undefined}>{t.label}</span>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge className="gap-1.5 border-border bg-hover font-mono"><span className="size-2 rounded-full bg-primary" aria-hidden />Observed Count: {o.observed_count}</Badge>
              <Badge className="gap-1.5 border-border bg-hover font-mono"><span className="h-3 w-0.5 rounded-full bg-[var(--tick)]" aria-hidden />Expected: {formatNumber(o.expected_count, 1)}</Badge>
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
          <SignalMeter key={k} card label={SIGNAL_LABELS[k]} value={o.signals[k]} color={SIGNAL_COLORS[k]} tip={signalTip(k, o)} delay={0.1 * i} />
        ))}
      </div>

      <Button onClick={() => onOpenEvidence(o)}>
        Evidence &amp; explanation <ChevronRight className="size-4" />
      </Button>

      <ClosestExistingWork key={o.opportunity_id} opportunityId={o.opportunity_id} />
    </section>
  );
}
