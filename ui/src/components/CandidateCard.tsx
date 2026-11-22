import { motion } from "motion/react";
import { ChevronRight } from "lucide-react";
import type { Opportunity } from "@/api/types";
import { scoreStrength } from "@/lib/colors";
import { opportunityTitle, SIGNAL_KEYS, SIGNAL_LABELS, type SignalKey } from "@/lib/opportunities";
import { Badge, Mono, TagBadge, Tip } from "@/components/ui/primitives";
import { SignalMeter } from "@/components/motion";
import { CountUp } from "@/components/CountUp";
import { KIND_TEXT } from "@/lib/colors";
import { cn, formatNumber } from "@/lib/utils";

const SIGNAL_COLORS: Record<SignalKey, string> = {
  sparsity: "#F59E0B",
  semantic_compatibility: "#38BDF8",
  temporal_activity: "#A78BFA",
};

function signalTip(key: SignalKey, o: Opportunity) {
  const exp = formatNumber(o.expected_count);
  switch (key) {
    case "sparsity":
      return (
        <div className="space-y-1.5">
          <p className="font-semibold">Sparsity: how much rarer than expected</p>
          <p>
            <Mono>1 − (observed + 1) / (expected + 1)</Mono>, clipped to 0..1. Here observed = <Mono>{o.observed_count}</Mono>, expected = <Mono>{exp}</Mono>.
          </p>
          <p>
            Expected = n<sub>A</sub> × n<sub>B</sub> / N, with every count taken over the <b>same universe</b> of N papers in which both kinds of
            element were extracted, and only papers up to {o.corpus.cutoff_year}. Counts are distinct papers, never experiment rows.
          </p>
        </div>
      );
    case "semantic_compatibility":
      return (
        <div className="space-y-1.5">
          <p className="font-semibold">Semantic compatibility</p>
          <p>Percentile rank, across the candidates, of the cosine similarity between the SPECTER2 embedding centroids of the papers using each element. Higher = the two elements live in related areas.</p>
        </div>
      );
    case "temporal_activity":
      return (
        <div className="space-y-1.5">
          <p className="font-semibold">Temporal activity</p>
          <p>Percentile rank of how active both elements are recently: their share of papers in the last 3 years and their 5-year trend slope.</p>
        </div>
      );
  }
}

/** Colour a Method × Task title: each part in its tag colour. */
function Title({ o }: { o: Opportunity }) {
  const parts = (["method", "dataset", "task", "setting"] as const).filter((k) => o.elements[k]);
  return (
    <>
      {parts.map((k, i) => (
        <span key={k}>
          {i > 0 ? <span className="mx-1.5 text-muted">×</span> : null}
          <span style={{ color: KIND_TEXT[k] }}>{o.elements[k]}</span>
        </span>
      ))}
    </>
  );
}

export function CandidateCard({
  opportunity: o, rank, selected, onOpen, score, scoreLabel,
}: {
  opportunity: Opportunity; rank: number; selected: boolean; onOpen: (o: Opportunity) => void;
  /** score to show (stored score, or the what-if score) */
  score: number; scoreLabel: string;
}) {
  const tone = scoreStrength(score);
  const kinds = (["method", "dataset", "task", "setting"] as const).filter((k) => o.elements[k]);
  return (
    <article
      className={cn(
        // the title button's ::after covers the whole card, so the card is one click target and one tab stop
        "glass defer-paint group relative cursor-pointer rounded-2xl p-4 transition-[translate,border-color,box-shadow] duration-300 hover:-translate-y-0.5",
        "hover:border-primary/60 has-[:focus-visible]:border-primary",
        selected ? "border-primary" : "border-border",
      )}
      data-testid="candidate-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="mono-label mb-1">
            #{rank} · opportunity {o.opportunity_id}
          </p>
          <motion.h3 layoutId={`title-${o.opportunity_id}`} className="display-heading display-sm">
            <button
              type="button"
              aria-label={`Open evidence for ${opportunityTitle(o.elements)}`}
              aria-pressed={selected}
              onClick={() => onOpen(o)}
              className="cursor-pointer text-left outline-none after:absolute after:inset-0 after:z-0 after:rounded-2xl after:content-[''] focus-visible:after:ring-2 focus-visible:after:ring-primary"
            >
              <Title o={o} />
            </button>
          </motion.h3>
          <div className="relative z-10 mt-2 flex flex-wrap gap-1.5">
            {kinds.map((k) => (
              <TagBadge key={k} kind={k} />
            ))}
          </div>
        </div>
        <Tip content={`${tone.label}. ${scoreLabel}`} side="left">
          <div
            className="relative z-10 shrink-0 rounded-xl border px-3 py-1.5 text-center"
            style={{ borderColor: `color-mix(in srgb, ${tone.color} 55%, transparent)`, background: `color-mix(in srgb, ${tone.color} 14%, transparent)`, color: tone.text }}
            data-testid="score-badge"
          >
            <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em]">Score</div>
            <CountUp value={score} className="mono-figure text-3xl" />
          </div>
        </Tip>
      </div>

      <div className="relative z-10 mt-3 flex flex-wrap items-center gap-1.5">
        <Badge className="border-border bg-hover font-mono">Observed Count: {o.observed_count}</Badge>
        <Badge className="border-border bg-hover font-mono">Expected: {formatNumber(o.expected_count, 1)}</Badge>
        <Tip content="min(1, expected / 5): a low observed count means little when few papers were expected.">
          <Badge className={cn("font-mono", (o.confidence ?? 0) < 0.5 ? "border-warning/50 bg-warning-soft text-warning-text" : "border-border bg-hover")}>
            Confidence: {o.confidence == null ? "n/a" : o.confidence.toFixed(2)}
          </Badge>
        </Tip>
      </div>

      <div className="relative z-10 mt-4 grid grid-cols-3 gap-4">
        {SIGNAL_KEYS.map((k, i) => (
          <SignalMeter key={k} label={SIGNAL_LABELS[k]} value={o.signals[k]} color={SIGNAL_COLORS[k]} tip={signalTip(k, o)} delay={0.1 * i} />
        ))}
      </div>

      <div className="mt-3 flex items-center justify-end text-xs text-muted transition-colors group-hover:text-foreground">
        Evidence &amp; explanation <ChevronRight className="size-3.5" />
      </div>
    </article>
  );
}
