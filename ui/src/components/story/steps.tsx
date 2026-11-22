import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { CountUp } from "@/components/CountUp";
import { Button } from "@/components/ui/primitives";
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
  /** true while the step is on screen (or always, when the steps are stacked); numerals count up when it turns true */
  active: boolean;
  onOpenExplorer: () => void;
}

const formatInt = (n: number) => Math.round(n).toLocaleString("en-US");

/** The hero: the title, the subtitle and the corpus size from the API. */
function Hero({ data, active }: StepProps) {
  return (
    <div className="flex h-full flex-col justify-center gap-5">
      <h2 className="display-heading" style={{ fontSize: "clamp(2.8rem, 5vw, 4.5rem)" }}>
        Paper <span className="accent-word">Compass</span>
      </h2>
      <p className="text-lg text-muted">Finding what the literature has not connected yet.</p>
      {data.papers !== null ? (
        <p className="text-sm text-muted">
          An evidence-grounded exploration of a curated corpus of{" "}
          <CountUp key={active ? "on" : "off"} trigger="mount" value={data.papers} format={formatInt} className="mono-figure text-foreground" /> papers.
        </p>
      ) : null}
      <p className="mono-label mt-4">SCROLL TO BEGIN</p>
    </div>
  );
}

/** The body of a step below its heading. */
function Body({ index, onOpenExplorer }: StepProps) {
  if (index === LAST_NUMBER) {
    return (
      <div className="mt-2">
        <Button onClick={onOpenExplorer}>
          Open the explorer <ArrowRight className="size-4" />
        </Button>
      </div>
    );
  }
  return null;
}

/** One step: the eyebrow, the heading and the body. */
export function StepPanel(props: StepProps) {
  const { index } = props;
  if (index === 0) return <Hero {...props} />;
  const meta = STEPS[index]!;
  return (
    <div className="flex h-full flex-col gap-4">
      <p className="mono-label">{meta.eyebrow}</p>
      <h3 className="display-heading display-md">{meta.heading}</h3>
      <Body {...props} />
    </div>
  );
}
