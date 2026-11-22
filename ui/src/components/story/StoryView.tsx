import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { CountUp } from "@/components/CountUp";
import { useStoryData } from "@/components/story/useStoryData";

export interface StoryViewProps {
  /** go to the explorer (the Candidates screen) */
  onOpenExplorer: () => void;
}

/** The story page: the default landing view. It leads into the explorer. */
export default function StoryView({ onOpenExplorer }: StoryViewProps) {
  const data = useStoryData();
  return (
    <section aria-label="Story" className="mx-auto flex min-h-[calc(100svh-8rem)] max-w-3xl flex-col justify-center gap-6 p-6">
      <h2 className="display-heading" style={{ fontSize: "clamp(3rem, 6vw, 5.5rem)" }}>
        Paper <span className="accent-word">Compass</span>
      </h2>
      <p className="text-lg text-muted">Finding what the literature has not connected yet.</p>
      {data.papers !== null ? (
        <p className="mono-label">
          An evidence-grounded exploration of a curated corpus of <CountUp value={data.papers} format={(n) => Math.round(n).toLocaleString("en-US")} className="text-foreground" /> papers.
        </p>
      ) : null}
      <div>
        <Button onClick={onOpenExplorer}>
          Open the explorer <ArrowRight className="size-4" />
        </Button>
      </div>
    </section>
  );
}
