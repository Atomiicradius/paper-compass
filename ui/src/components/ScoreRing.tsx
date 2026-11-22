import { useEffect, useId, useState, type ReactNode } from "react";
import { scoreStrength, type Strength } from "@/lib/colors";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";

/** The two ends of a ring's gradient, by how strong the signal is (the colours of the score badge, with a neighbour). */
const GRADIENTS: Record<Strength, [string, string]> = {
  strong: ["#14B8A6", "#38BDF8"],
  moderate: ["#F59E0B", "#F97316"],
  weak: ["#94A3B8", "#64748B"],
};

const R = 44;
const CIRCUMFERENCE = 2 * Math.PI * R;

/** How much of the ring is filled (0..1) for a score of 0..100. Pure, so it can be tested. */
export function ringFill(score: number): number {
  return Math.min(1, Math.max(0, (Number.isFinite(score) ? score : 0) / 100));
}

/**
 * A score ring: a track and an arc with a gradient stroke, filled in proportion to a score out of 100, coloured by how strong
 * the signal is (teal, amber, grey as on the score badge). The arc draws itself when it appears (not with reduced motion). What
 * goes in the middle is up to the caller.
 */
export function ScoreRing({
  score, size = 44, strokeWidth = 8, children, className, testId,
}: { score: number; size?: number; strokeWidth?: number; children?: ReactNode; className?: string; testId?: string }) {
  const uid = useId().replace(/:/g, "");
  const reduced = usePrefersReducedMotion();
  const [drawn, setDrawn] = useState(reduced);
  useEffect(() => {
    if (reduced) {
      setDrawn(true);
      return;
    }
    const raf = requestAnimationFrame(() => setDrawn(true)); // start empty, then fill: the CSS transition draws the arc
    return () => cancelAnimationFrame(raf);
  }, [reduced]);
  const tone = scoreStrength(score);
  const [from, to] = GRADIENTS[tone.strength];
  const fill = ringFill(score);
  return (
    <div className={className} style={{ width: size, height: size, position: "relative" }} data-testid={testId} data-strength={tone.strength} data-fill={fill.toFixed(3)}>
      <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden style={{ transform: "rotate(-90deg)", overflow: "visible", filter: `drop-shadow(0 0 ${Math.max(2, size / 22)}px ${from}66)` }}>
        <defs>
          <linearGradient id={`ring-${uid}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={from} />
            <stop offset="100%" stopColor={to} />
          </linearGradient>
        </defs>
        <circle cx="50" cy="50" r={R} fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth={strokeWidth} />
        <circle
          cx="50" cy="50" r={R} fill="none" stroke={`url(#ring-${uid})`} strokeWidth={strokeWidth} strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE} strokeDashoffset={CIRCUMFERENCE * (1 - (drawn ? fill : 0))}
          style={{ transition: reduced ? "none" : "stroke-dashoffset 1100ms cubic-bezier(0.22, 1, 0.36, 1)" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  );
}
