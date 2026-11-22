import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { gsap, ScrollTrigger } from "@/lib/gsap";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";
import { cn } from "@/lib/utils";
import { useScrollTarget, useScroller } from "@/components/SmoothScroll";
import { counterText, STEP_COUNT, StepPanel } from "@/components/story/steps";
import { useStoryData, type StoryData } from "@/components/story/useStoryData";

// the canvas is decoration: it is its own chunk, loaded after the story page, and not at all with reduced motion
const NetworkCanvas = lazy(() => import("@/components/story/NetworkCanvas"));
// the particle sphere of step 0 is its own chunk too
const ParticleSphere = lazy(() => import("@/components/story/ParticleSphere"));

export interface StoryViewProps {
  /** go to the explorer (the Candidates screen) */
  onOpenExplorer: () => void;
}

/** The step (0..7) that a scroll progress (0..1) through the pinned stage belongs to. */
export function stepFromProgress(progress: number): number {
  const p = Number.isFinite(progress) ? progress : 0;
  return Math.min(STEP_COUNT - 1, Math.max(0, Math.floor(p * STEP_COUNT)));
}

const FALLBACK_STAGE_HEIGHT = 640; // used until the scrolling pane has been measured

/**
 * The story page: a full-height stage, pinned while the visitor scrolls through the steps. The page scrolls inside
 * the centre pane (the Lenis scroller), so the stage is `position: sticky` in a section that is as tall as all the
 * steps together, and a GSAP ScrollTrigger on that scroller turns the scroll progress into the current step. The
 * counter, the progress rail and the transition between steps follow that step.
 *
 * With `prefers-reduced-motion: reduce` nothing is pinned and nothing animates: the steps are stacked.
 */
export default function StoryView({ onOpenExplorer }: StoryViewProps) {
  const data = useStoryData();
  const reduced = usePrefersReducedMotion();
  return reduced ? <StackedStory data={data} onOpenExplorer={onOpenExplorer} /> : <PinnedStory data={data} onOpenExplorer={onOpenExplorer} />;
}

/** The reduced-motion layout: every step in its own card, in normal flow, with its numbers shown as they are. */
function StackedStory({ data, onOpenExplorer }: { data: StoryData; onOpenExplorer: () => void }) {
  return (
    <section aria-label="Story" className="mx-auto max-w-3xl space-y-6 p-6 py-10">
      {/* reduced motion: the sphere is drawn once and does not move */}
      <div className="relative h-72" data-testid="story-sphere-still">
        <Suspense fallback={null}>
          <ParticleSphere visible still centerX={0.5} />
        </Suspense>
      </div>
      {Array.from({ length: STEP_COUNT }, (_, i) => (
        <div key={i} className="glass rounded-2xl p-7" data-step={i}>
          <StepPanel index={i} data={data} active onOpenExplorer={onOpenExplorer} />
        </div>
      ))}
    </section>
  );
}

function PinnedStory({ data, onOpenExplorer }: { data: StoryData; onOpenExplorer: () => void }) {
  const { scroller, ready } = useScrollTarget();
  const scrollerEl = useScroller();
  const sectionRef = useRef<HTMLElement>(null);
  const panelsRef = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  const prevStep = useRef(0);
  const ctxRef = useRef<{ add: (fn: () => void) => unknown } | null>(null);

  // the height of one screen of the scrolling pane: the stage is one screen tall, the section is all the steps tall
  const [stageH, setStageH] = useState(0);
  useLayoutEffect(() => {
    if (!scrollerEl) return;
    const measure = () => setStageH(scrollerEl.clientHeight);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(scrollerEl);
    return () => ro.disconnect();
  }, [scrollerEl]);
  const h = stageH > 0 ? stageH : FALLBACK_STAGE_HEIGHT;
  useEffect(() => {
    ScrollTrigger.refresh(); // the section changed height
  }, [h]);

  // scroll progress through the section -> the current step
  useLayoutEffect(() => {
    const el = sectionRef.current;
    if (!el || !ready) return;
    const st = ScrollTrigger.create({
      trigger: el,
      scroller: scroller ?? undefined,
      start: "top top",
      end: "bottom bottom",
      onUpdate: (self) => setStep(stepFromProgress(self.progress)),
    });
    setStep(stepFromProgress(st?.progress ?? 0));
    return () => st?.kill?.();
  }, [ready, scroller]);

  // the steps are stacked in one panel; all but the first start hidden (GSAP hides them, so assistive technology and the
  // keyboard skip them too), and the context kills every tween when the page unmounts
  useLayoutEffect(() => {
    const root = panelsRef.current;
    if (!root) return;
    const panels = Array.from(root.children);
    const ctx = gsap.context(() => {
      gsap.set(panels, { autoAlpha: 0, y: 24 });
      gsap.set(panels[0] ?? [], { autoAlpha: 1, y: 0 });
    }, root);
    ctxRef.current = ctx as unknown as { add: (fn: () => void) => unknown };
    prevStep.current = 0;
    return () => {
      ctx.revert();
      ctxRef.current = null;
    };
  }, []);

  // enter and leave transitions between the previous and the current step
  useEffect(() => {
    const root = panelsRef.current;
    const prev = prevStep.current;
    if (!root || prev === step) return;
    prevStep.current = step;
    const dir = step > prev ? 1 : -1;
    const panels = Array.from(root.children);
    ctxRef.current?.add(() => {
      panels.forEach((p, i) => {
        if (i !== step && i !== prev) gsap.set(p, { autoAlpha: 0 });
      });
      if (panels[prev]) gsap.to(panels[prev], { autoAlpha: 0, y: -24 * dir, duration: 0.35, ease: "power2.in", overwrite: true });
      if (panels[step]) gsap.fromTo(panels[step], { autoAlpha: 0, y: 24 * dir }, { autoAlpha: 1, y: 0, duration: 0.6, delay: 0.15, ease: "power3.out", overwrite: true });
    });
  }, [step]);

  // a dot of the rail scrolls to the middle of its step
  const goTo = useCallback(
    (i: number) => {
      const el = sectionRef.current;
      if (!el || !scrollerEl) return;
      const top = el.getBoundingClientRect().top - scrollerEl.getBoundingClientRect().top + scrollerEl.scrollTop;
      const span = el.offsetHeight - scrollerEl.clientHeight;
      scrollerEl.scrollTop = top + ((i + 0.5) / STEP_COUNT) * span;
    },
    [scrollerEl],
  );

  return (
    <section ref={sectionRef} aria-label="Story" className="relative" style={{ height: h * STEP_COUNT }}>
      <div className="sticky top-0 overflow-hidden" style={{ height: h }} data-testid="story-stage">
        <Suspense fallback={null}>
          {/* step 0 is the sphere; it fades out as the network canvas takes over from step 1 */}
          <ParticleSphere visible={step === 0} />
          <NetworkCanvas step={step} groupSizes={data.clusterSizes} />
        </Suspense>
        <nav aria-label="Story steps" className="absolute top-1/2 left-5 z-10 flex -translate-y-1/2 flex-col gap-3">
          {Array.from({ length: STEP_COUNT }, (_, i) => (
            <button
              key={i}
              type="button"
              aria-label={i === 0 ? "Go to the start" : `Go to step ${i}`}
              aria-current={i === step ? "step" : undefined}
              onClick={() => goTo(i)}
              className={cn(
                "cursor-pointer rounded-full border transition-all duration-300",
                i === step ? "size-3 border-primary bg-primary" : "size-2 border-muted/60 bg-transparent hover:border-primary",
              )}
            />
          ))}
        </nav>

        <div className="absolute inset-0 flex items-center justify-end p-4 lg:pr-16">
          <div className="glass relative h-[min(34rem,100%)] w-full max-w-[34rem] rounded-2xl">
            <div ref={panelsRef} className="absolute inset-0">
              {Array.from({ length: STEP_COUNT }, (_, i) => (
                <div key={i} data-step={i} data-lenis-prevent className="scroll-thin absolute inset-0 overflow-y-auto p-7">
                  <StepPanel index={i} data={data} active={i === step} onOpenExplorer={onOpenExplorer} />
                </div>
              ))}
            </div>
          </div>
        </div>

        <p data-testid="story-counter" className="absolute bottom-6 left-14 z-10 font-mono text-lg tracking-[0.16em] text-muted">
          {counterText(step)}
        </p>
      </div>
    </section>
  );
}
