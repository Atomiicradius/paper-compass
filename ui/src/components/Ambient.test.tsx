import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { installSpotlight, useSpotlight } from "@/lib/spotlight";
import { setReducedMotion } from "@/test/motion";
import { Ambient } from "@/components/Ambient";

const css = readFileSync(join(process.cwd(), "src", "index.css"), "utf-8");

describe("Ambient layer", () => {
  let restore = () => {};
  afterEach(() => restore());

  it("is decoration: hidden from assistive technology, with three glows, a dot grid and grain", () => {
    const { container } = render(<Ambient />);
    const root = screen.getByTestId("ambient");
    expect(root).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelectorAll(".ambient-glow")).toHaveLength(3);
    expect(container.querySelector(".ambient-grid")).not.toBeNull();
    expect(container.querySelector(".ambient-grain")).not.toBeNull();
    expect(root).not.toHaveAttribute("data-static");
  });

  it("stands still with reduced motion (the glows get no animation)", () => {
    restore = setReducedMotion(true);
    render(<Ambient />);
    expect(screen.getByTestId("ambient")).toHaveAttribute("data-static");
    expect(css).toMatch(/\.ambient\[data-static\] \.ambient-glow \{ animation: none; \}/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\) \{\s*\.ambient-glow \{ animation: none; \}/);
  });
});

describe("the ambient and glass CSS", () => {
  it("makes no request: every url() is an inline data URI and nothing is imported from outside", () => {
    const urls = [...css.matchAll(/url\(([^)]*)\)/g)].map((m) => m[1]!.trim().replace(/^["']/, ""));
    expect(urls.length).toBeGreaterThan(0);
    for (const u of urls) expect(u.startsWith("data:")).toBe(true);
    expect(css).not.toMatch(/@import url/);
    expect(css).not.toMatch(/@import "https?:/);
  });

  it("drifts the glows by at most 20 px", () => {
    const shifts = [...css.matchAll(/--d[xy]:\s*(-?\d+)px/g)].map((m) => Math.abs(Number(m[1])));
    expect(shifts.length).toBeGreaterThanOrEqual(6); // x and y for each of the three glows
    for (const px of shifts) expect(px).toBeLessThanOrEqual(20);
  });

  it("gives a rounded glass card a gradient hairline and a spotlight, and switches the spotlight off with reduced motion", () => {
    expect(css).toMatch(/\.glass:not\(\.rounded-none\)::before \{[^}]*linear-gradient\(145deg, var\(--hair-a\)/s);
    expect(css).toMatch(/mask-composite: exclude/);
    expect(css).toMatch(/\.glass:hover \{\s*--spot-image: radial-gradient\([^)]*var\(--mx, 50%\) var\(--my, 50%\)/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\.glass:hover \{ --spot-image: none; \}/);
  });

  it("defines the hairline and the spotlight in both themes", () => {
    for (const v of ["--hair-a", "--hair-b", "--hair-c", "--spot-color", "--glow-opacity", "--grid-dot", "--grain-opacity"]) {
      expect(css.split(v + ":").length - 1).toBeGreaterThanOrEqual(2); // :root and .dark
    }
  });
});

describe("spotlight handler", () => {
  let frames: Array<() => void> = [];
  const flush = () => frames.splice(0).forEach((f) => f());

  function setup() {
    frames = [];
    vi.stubGlobal("requestAnimationFrame", (cb: () => void) => (frames.push(cb), frames.length));
    vi.stubGlobal("cancelAnimationFrame", () => {});
    document.body.innerHTML = `<div class="glass" id="outer"><div class="glass" id="inner"><span id="text">x</span></div></div><p id="plain">y</p>`;
    for (const id of ["outer", "inner"]) {
      vi.spyOn(document.getElementById(id)!, "getBoundingClientRect").mockReturnValue({ left: id === "outer" ? 100 : 150, top: 50, right: 400, bottom: 300, width: 300, height: 250, x: 0, y: 0, toJSON: () => ({}) } as DOMRect);
    }
  }
  const move = (target: Element, x: number, y: number) => {
    const e = new Event("pointermove", { bubbles: true }) as Event & { clientX: number; clientY: number };
    Object.assign(e, { clientX: x, clientY: y });
    target.dispatchEvent(e);
  };
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("writes the pointer position into the card under the pointer and the card around it, once per frame", () => {
    setup();
    const remove = installSpotlight();
    move(document.getElementById("text")!, 260, 120);
    move(document.getElementById("text")!, 270, 130); // a second event in the same frame
    expect(frames).toHaveLength(1);
    flush();
    expect(document.getElementById("inner")!.style.getPropertyValue("--mx")).toBe("120px"); // 270 - 150
    expect(document.getElementById("inner")!.style.getPropertyValue("--my")).toBe("80px"); // 130 - 50
    expect(document.getElementById("outer")!.style.getPropertyValue("--mx")).toBe("170px"); // 270 - 100
    remove();
  });

  it("ignores the pointer over anything that is not a glass card", () => {
    setup();
    const remove = installSpotlight();
    move(document.getElementById("plain")!, 5, 5);
    flush();
    expect(document.getElementById("outer")!.style.getPropertyValue("--mx")).toBe("");
    remove();
  });

  it("is one listener on the document, not one per card, and it is removed again", () => {
    setup();
    const add = vi.spyOn(document, "addEventListener");
    const rem = vi.spyOn(document, "removeEventListener");
    const remove = installSpotlight();
    expect(add.mock.calls.filter((c) => c[0] === "pointermove")).toHaveLength(1);
    remove();
    expect(rem).toHaveBeenCalledWith("pointermove", expect.any(Function));
    move(document.getElementById("text")!, 200, 100);
    expect(frames).toHaveLength(0); // nothing listens any more
  });

  it("is not installed at all with reduced motion", () => {
    const restore = setReducedMotion(true);
    const add = vi.spyOn(document, "addEventListener");
    function Host() {
      useSpotlight();
      return null;
    }
    render(<Host />);
    expect(add.mock.calls.filter((c) => c[0] === "pointermove")).toHaveLength(0);
    restore();
  });

  it("is installed (once) when motion is allowed", () => {
    const add = vi.spyOn(document, "addEventListener");
    function Host() {
      useSpotlight();
      return null;
    }
    const { unmount } = render(<Host />);
    expect(add.mock.calls.filter((c) => c[0] === "pointermove")).toHaveLength(1);
    unmount();
  });
});
