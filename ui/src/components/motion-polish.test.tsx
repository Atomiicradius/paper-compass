import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button, Skeleton, TooltipProvider } from "@/components/ui/primitives";
import { CandidatesView } from "@/components/CandidatesView";
import { LandscapeView } from "@/components/LandscapeView";
import { EMPTY_FILTERS } from "@/lib/opportunities";

const css = readFileSync("src/index.css", "utf-8");
const loading = { data: null, error: null, loading: true, reload: () => {} };

describe("motion polish", () => {
  it("skeletons shimmer, and the shimmer is switched off with reduced motion", () => {
    render(<Skeleton className="h-4" />);
    expect(document.querySelector(".shimmer")).not.toBeNull();
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.shimmer \{ animation: none/);
  });

  it("Candidates and Landscape show shimmer placeholders while loading", () => {
    const c = render(<TooltipProvider><CandidatesView state={loading} filters={EMPTY_FILTERS} selectedId={null} onSelect={() => {}} onClearFilters={() => {}} /></TooltipProvider>);
    expect(screen.getByTestId("candidates-skeleton").querySelectorAll(".shimmer").length).toBeGreaterThan(3);
    c.unmount();
    render(<TooltipProvider><LandscapeView state={loading} onOpenGraph={() => {}} /></TooltipProvider>);
    expect(screen.getByTestId("landscape-skeleton").querySelectorAll(".shimmer").length).toBe(3);
  });

  it("buttons have a pressed state that is switched off with reduced motion", () => {
    render(<Button>Go</Button>);
    const cls = screen.getByRole("button").className;
    expect(cls).toMatch(/active:scale-\[0\.97\]/);
    expect(cls).toMatch(/motion-reduce:active:scale-100/);
  });

  it("the screen-enter animation and the shared focus ring are defined, and screen-enter is off with reduced motion", () => {
    expect(css).toMatch(/\.screen-enter \{ animation: screen-enter/);
    expect(css).toMatch(/\.screen-enter \{ animation: none; \}/);
    expect(css).toMatch(/\[class\*="outline-none"\]:focus-visible \{ outline: 2px solid var\(--ring\)/);
  });
});
