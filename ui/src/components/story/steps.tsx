import type { CSSProperties, ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import type { ElementKind, Opportunity } from "@/api/types";
import { KIND_TEXT } from "@/lib/colors";
import { CountUp, type CountUpProps } from "@/components/CountUp";
import { YearBars } from "@/components/LandscapeView";
import { Button, IdBadge, Mono, TagBadge } from "@/components/ui/primitives";
import type { StoryData } from "@/components/story/useStoryData";

/** Step 0 is the hero; steps 1 to 7 are the numbered steps. */
export const STEP_COUNT = 8;
export const LAST_NUMBER = STEP_COUNT - 1;

export interface StepMeta {
  /** the mono line above the heading, e.g. "01 · DISCOVER · WHAT IS IN THE CORPUS?" (none for the hero) */
  eyebrow: string | null;
  heading: ReactNode;
}

export const STEPS: StepMeta[] = [
  { eyebrow: null, heading: null },
  { eyebrow: "01 · DISCOVER · WHAT IS IN THE CORPUS?", heading: "The corpus" },
  { eyebrow: "02 · CONNECT · WHAT DO THE PAPERS USE?", heading: "Methods and tasks" },
  { eyebrow: "03 · MAP · WHERE DO PAPERS CLUSTER?", heading: "Clusters" },
  { eyebrow: "04 · DETECT · WHICH COMBINATIONS ARE RARE?", heading: "Observed versus expected" },
  { eyebrow: "05 · SCORE · HOW STRONG IS THE SIGNAL?", heading: "Three signals and a confidence" },
  { eyebrow: "06 · EXPLAIN · WHAT IS THE EVIDENCE?", heading: "Evidence you can check" },
  { eyebrow: "07 · LIMITS · WHAT THIS IS NOT", heading: "A signal, not a verdict" },
];

/** "03 / 07": the step number and the number of numbered steps. */
export function counterText(step: number): string {
  return `${String(step).padStart(2, "0")} / ${String(LAST_NUMBER).padStart(2, "0")}`;
}

export interface StepProps {
  index: number;
  data: StoryData;
  /** true while the step is on screen (or always, when the steps are stacked); numerals count up and bars fill when it turns true */
  active: boolean;
  onOpenExplorer: () => void;
}

const formatInt = (n: number) => Math.round(n).toLocaleString("en-US");

/** A count-up that starts when its step becomes the active one (it is mounted afresh then). */
function Count({ active, ...props }: { active: boolean } & Omit<CountUpProps, "trigger">) {
  return <CountUp key={active ? "on" : "off"} trigger="mount" {...props} />;
}

/** A big mono numeral with its small mono label. */
function Figure({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mono-figure text-5xl text-foreground">{children}</div>
      <div className="mono-label mt-2">{label}</div>
    </div>
  );
}

/** A horizontal bar that fills from 0 to its share (0..1) when the step is active. */
function Bar({ label, share, active, color }: { label: string; share: number; active: boolean; color: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, share)) * 100);
  const fill: CSSProperties = { width: active ? `${pct}%` : "0%", background: color };
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-hover" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={1} aria-valuenow={share}>
      <div className="h-full rounded-full transition-[width] duration-1000 ease-out" style={fill} />
    </div>
  );
}

const SIGNAL_COLORS = { sparsity: "#F59E0B", semantic: "#38BDF8", temporal: "#A78BFA" } as const;

/** "Method × Task" in the tag colours, as on the Candidates screen. */
function PairTitle({ o }: { o: Opportunity }) {
  const parts = (["method", "dataset", "task", "setting"] as const).filter((k) => o.elements[k]);
  return (
    <p className="text-lg leading-snug font-medium">
      {parts.map((k: ElementKind, i) => (
        <span key={k}>
          {i > 0 ? <span className="mx-1.5 text-muted">×</span> : null}
          <span style={{ color: KIND_TEXT[k] }}>{o.elements[k]}</span>
        </span>
      ))}
    </p>
  );
}

/** The hero: the title, the subtitle and the corpus size from the API. */
function Hero({ data, active }: StepProps) {
  return (
    <div className="flex min-h-full flex-col justify-center gap-5">
      <h2 className="display-heading" style={{ fontSize: "clamp(2.8rem, 5vw, 4.5rem)" }}>
        Paper <span className="accent-word">Compass</span>
      </h2>
      <p className="text-lg text-muted">Finding what the literature has not connected yet.</p>
      {data.papers !== null ? (
        <p className="text-sm text-muted">
          An evidence-grounded exploration of a curated corpus of <Count active={active} value={data.papers} format={formatInt} className="mono-figure text-foreground" /> papers.
        </p>
      ) : null}
      <p className="mono-label mt-4">SCROLL TO BEGIN</p>
    </div>
  );
}

function ElementList({ label, kind, items }: { label: string; kind: ElementKind; items: StoryData["topMethods"] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="mono-label mb-2">{label}</div>
      <ul className="space-y-1.5 p-0">
        {items.map((t) => (
          <li key={t.element_id} className="flex list-none items-center justify-between gap-3 text-sm">
            <TagBadge kind={kind}>{t.name}</TagBadge>
            <span className="font-mono text-xs text-muted">{t.total} papers</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The body of a numbered step, below its heading. Anything the API did not provide is simply not shown. */
function Body({ index, data, active, onOpenExplorer }: StepProps) {
  const top = data.top;
  switch (index) {
    case 1:
      return (
        <>
          {data.papers !== null ? (
            <Figure label="Papers">
              <Count active={active} value={data.papers} format={formatInt} />
            </Figure>
          ) : null}
          {data.papersPerYear ? <YearBars perYear={data.papersPerYear} /> : null}
        </>
      );
    case 2:
      return (
        <>
          <p className="text-sm leading-relaxed text-muted">Methods, tasks and datasets are extracted from titles and abstracts by a rule-based extractor (rules-v1).</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <ElementList label="Methods" kind="method" items={data.topMethods} />
            <ElementList label="Tasks" kind="task" items={data.topTasks} />
          </div>
        </>
      );
    case 3:
      return (
        <>
          <div className="flex flex-wrap gap-8">
            {data.clusterCount !== null ? (
              <Figure label="Clusters">
                <Count active={active} value={data.clusterCount} format={formatInt} />
              </Figure>
            ) : null}
            {data.papersInNoCluster !== null ? (
              <Figure label="Papers in no cluster">
                <Count active={active} value={data.papersInNoCluster} format={formatInt} />
              </Figure>
            ) : null}
          </div>
          <p className="text-sm text-muted">HDBSCAN on SPECTER2 embeddings.</p>
        </>
      );
    case 4: {
      if (!top) return null;
      const max = Math.max(top.observed_count, top.expected_count, Number.MIN_VALUE);
      return (
        <>
          <PairTitle o={top} />
          <div className="space-y-4">
            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="mono-label">Observed</span>
                <span className="mono-figure text-2xl text-foreground">
                  <Count active={active} value={top.observed_count} format={formatInt} />
                </span>
              </div>
              <Bar label="Observed" share={top.observed_count / max} active={active} color="var(--primary)" />
            </div>
            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="mono-label">Expected</span>
                <span className="mono-figure text-2xl text-foreground">
                  <Count active={active} value={top.expected_count} decimals={1} />
                </span>
              </div>
              <Bar label="Expected" share={top.expected_count / max} active={active} color="#F59E0B" />
            </div>
          </div>
          {data.universeN !== null ? (
            <div className="glass inline-block rounded-xl px-3 py-2">
              <div className="mono-label text-[10px]">Universe N</div>
              <div className="mono-figure mt-1 text-2xl">
                <Count active={active} value={data.universeN} format={formatInt} />
              </div>
            </div>
          ) : null}
        </>
      );
    }
    case 5: {
      const s = top?.signals;
      const displayedConfidence = top?.confidence === null || top?.confidence === undefined ? null : Number(top.confidence.toFixed(2));
      const rows: { label: string; value: number | null | undefined; color: string }[] = [
        { label: "Sparsity", value: s?.sparsity, color: SIGNAL_COLORS.sparsity },
        { label: "Semantic", value: s?.semantic_compatibility, color: SIGNAL_COLORS.semantic },
        { label: "Temporal", value: s?.temporal_activity, color: SIGNAL_COLORS.temporal },
      ];
      return (
        <>
          <div className="space-y-3">
            {rows.map((r) =>
              r.value === null || r.value === undefined ? null : (
                <div key={r.label}>
                  <div className="mb-1.5 flex items-baseline justify-between">
                    <span className="mono-label">{r.label}</span>
                    <span className="font-mono text-sm text-foreground">
                      <Count active={active} value={r.value} decimals={2} />
                    </span>
                  </div>
                  <Bar label={r.label} share={r.value} active={active} color={r.color} />
                </div>
              ),
            )}
          </div>
          {top?.confidence !== null && top?.confidence !== undefined ? (
            <Figure label="Confidence">
              <Count active={active} value={top.confidence} decimals={2} />
            </Figure>
          ) : null}
          {/* only when the confidence shown (two decimals) is below 1.00; at 1.00 there is nothing lowering it */}
          {displayedConfidence !== null && displayedConfidence < 1 ? <p className="text-sm text-muted">Low expected counts lower the confidence.</p> : null}
        </>
      );
    }
    case 6:
      return (
        <>
          {data.evidence.length > 0 ? (
            <ul className="space-y-3 p-0">
              {data.evidence.map((e) => (
                <li key={e.paper_id} className="list-none">
                  <IdBadge id={e.paper_id} />
                  <p className="mt-1 text-sm leading-snug">
                    {e.title}
                    {e.year !== null ? <span className="text-muted"> ({e.year})</span> : null}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
          {data.verifiedCitations !== null ? (
            <p className="text-sm">
              <Mono className="text-foreground">
                <Count active={active} value={data.verifiedCitations} format={formatInt} />
              </Mono>{" "}
              citations verified
            </p>
          ) : null}
        </>
      );
    case LAST_NUMBER:
      return (
        <>
          <p className="text-sm leading-relaxed text-muted">
            A candidate opportunity is a signal for human review, not proof of a research gap. Counts come from rule-based extraction over a curated corpus, not the whole literature.
          </p>
          <div className="mt-2">
            <Button onClick={onOpenExplorer}>
              Open the explorer <ArrowRight className="size-4" />
            </Button>
          </div>
        </>
      );
    default:
      return null;
  }
}

/** One step: the eyebrow, the heading and the body. */
export function StepPanel(props: StepProps) {
  const { index } = props;
  if (index === 0) return <Hero {...props} />;
  const meta = STEPS[index]!;
  return (
    <div className="flex min-h-full flex-col justify-center gap-4">
      <p className="mono-label">{meta.eyebrow}</p>
      <h3 className="display-heading display-md">{meta.heading}</h3>
      <Body {...props} />
    </div>
  );
}
