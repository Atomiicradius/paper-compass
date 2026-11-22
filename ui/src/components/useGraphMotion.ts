import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, type RefObject } from "react";
import type { ForceGraphMethods } from "react-force-graph-2d";
import { gsap } from "@/lib/gsap";
import type { ViewGraph } from "@/lib/graph";
import {
  buildAdjacency, distancesFromCenter, easeToward, highlightSet, labelTargets, newPaintState, stepLabelAlpha, type PaintNode,
} from "@/lib/graph-paint";

/** how long the camera takes to glide to a clicked node */
export const GLIDE_MS = 800;
/** the zoom a click glides to, at least (it never zooms out) */
export const GLIDE_ZOOM = 2.2;
export const REVEAL_SECONDS = 2.4;

interface Options {
  view: ViewGraph | null;
  /** changes when a new graph arrives: the entrance plays again */
  dataKey: unknown;
  centerId: string | null;
  selectedId: string | null;
  fgRef: RefObject<ForceGraphMethods | undefined>;
  boxRef: RefObject<HTMLElement | null>;
  /** prefers-reduced-motion: no entrance, no drift, no particles, no pulsing, no glide */
  reduced: boolean;
  /** a large graph: the particles are left out */
  large?: boolean;
}

/**
 * Everything that moves in the research graph, apart from the force layout itself:
 * - the entrance: a GSAP timeline raises `reveal` from 0 to 1; the painters show nodes by distance from the selected
 *   paper (nearest first) and draw the links in afterwards;
 * - idle motion: two endless tweens drive the clock of the gentle drift and the particles, and the phase of the rings;
 * - hover: the node under the pointer and its neighbours stay lit while everything else dims (eased);
 * - labels fade in and out as the label rule changes (selected paper, clicked node, hovered node, best-connected nodes);
 * - a click glides the camera to the node.
 * Every tween lives in one gsap context, which is reverted when the graph unmounts or a new graph arrives.
 * With reduced motion nothing is tweened: the values are set to their end state and jump when they change.
 */
export function useGraphMotion({ view, dataKey, centerId, selectedId, fgRef, boxRef, reduced, large = false }: Options) {
  const paint = useRef(newPaintState(!reduced));
  const targets = useRef<Set<string>>(new Set());
  const lastFrame = useRef(0);
  // the tweens that can be paused while the tab is hidden
  const loops = useRef<Array<{ pause: () => unknown; resume: () => unknown }>>([]);
  const adjacency = useMemo(() => (view ? buildAdjacency(view.links) : new Map<string, Set<string>>()), [view]);
  const nodeIds = useMemo(() => view?.nodes.map((n) => n.id) ?? [], [view]);
  const redraw = useCallback(() => (fgRef.current as { refresh?: () => void } | undefined)?.refresh?.(), [fgRef]);

  // may anything animate? (also resets the loops' values when it is switched off)
  useLayoutEffect(() => {
    const st = paint.current;
    st.animate = !reduced;
    st.particles = !large;
    if (reduced) {
      st.reveal = 1;
      st.time = 0;
      st.ring = 0;
    }
  }, [reduced, large]);

  // who is the selected paper, who was clicked, and which nodes carry a label
  useEffect(() => {
    const st = paint.current;
    st.centerId = centerId;
    st.selectedId = selectedId;
    st.hoverId = null;
    st.highlight = null;
    targets.current = labelTargets({ nodes: view?.nodes ?? [], centerId, selectedId, hoverId: null });
    redraw(); // the canvas pauses its redraw when nothing moves
  }, [view, centerId, selectedId, redraw]);

  // the entrance and the idle loops
  useEffect(() => {
    const st = paint.current;
    if (reduced || !dataKey) {
      st.reveal = 1;
      st.time = 0;
      st.ring = 0;
      redraw();
      return;
    }
    st.reveal = 0;
    st.time = 0;
    st.ring = 0;
    const ctx = gsap.context(() => {
      const entrance = gsap.timeline().to(st, { reveal: 1, duration: REVEAL_SECONDS, ease: "power2.out" });
      const clock = gsap.to(st, { time: 3600, duration: 3600, ease: "none" }); // the clock of the drift and the particles
      const rings = gsap.to(st, { ring: 1, duration: 3.8, ease: "none", repeat: -1 }); // the slow rings around the selected paper
      loops.current = [entrance, clock, rings];
    });
    return () => {
      loops.current = [];
      ctx.revert();
    };
  }, [dataKey, reduced, redraw]);

  // nothing is drawn or tweened while the tab is hidden (the browser stops animation frames anyway; this also stops the
  // layout simulation and the GSAP clock, so the time spent hidden does not jump the animation forward)
  useEffect(() => {
    const onVisibility = () => {
      const fg = fgRef.current;
      if (document.hidden) {
        fg?.pauseAnimation();
        loops.current.forEach((t) => t.pause());
      } else {
        fg?.resumeAnimation();
        loops.current.forEach((t) => t.resume());
        lastFrame.current = 0; // no big time step after the pause
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [fgRef]);

  // called before each frame is drawn
  const onRenderFramePre = useCallback(() => {
    const st = paint.current;
    const now = performance.now();
    const dt = lastFrame.current ? Math.min(0.1, (now - lastFrame.current) / 1000) : 0.016;
    lastFrame.current = now;
    const step = st.animate ? dt : 10; // with reduced motion the values go straight to where they are heading
    st.dim = easeToward(st.dim, st.highlight ? 1 : 0, step, 7);
    stepLabelAlpha(st.labelAlpha, nodeIds, targets.current, step);
    if (st.animate && st.reveal < 1 && view) st.distance = distancesFromCenter(view.nodes as PaintNode[], st.centerId);
  }, [nodeIds, view]);

  const onNodeHover = useCallback(
    (node: object | null) => {
      const st = paint.current;
      const id = node ? (node as PaintNode).id : null;
      st.hoverId = id;
      st.highlight = highlightSet(adjacency, id);
      targets.current = labelTargets({ nodes: view?.nodes ?? [], centerId: st.centerId, selectedId: st.selectedId, hoverId: id });
      if (boxRef.current) boxRef.current.style.cursor = id ? "pointer" : "";
      redraw();
    },
    [adjacency, view, boxRef, redraw],
  );

  /** glide the camera to a node, eased (instantly with reduced motion) */
  const glideTo = useCallback(
    (node: object) => {
      const fg = fgRef.current;
      const n = node as PaintNode;
      if (!fg || n.x === undefined || n.y === undefined) return;
      const ms = paint.current.animate ? GLIDE_MS : 0;
      fg.centerAt(n.x, n.y, ms);
      fg.zoom(Math.max(fg.zoom(), GLIDE_ZOOM), ms);
    },
    [fgRef],
  );

  return { paint, onRenderFramePre, onNodeHover, glideTo };
}
