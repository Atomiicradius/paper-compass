import { usePrefersReducedMotion } from "@/lib/reduced-motion";

/**
 * The ambient layer behind the whole app: three very soft teal and blue glows that drift a few pixels, a faint dot grid and
 * fine grain. It is only CSS (see `.ambient` in index.css) and an inline SVG, so it makes no request, and it never takes the
 * pointer. With reduced motion the glows stand still (`data-static`).
 */
export function Ambient() {
  const reduced = usePrefersReducedMotion();
  return (
    <div className="ambient" aria-hidden data-testid="ambient" data-static={reduced ? "" : undefined}>
      <span className="ambient-glow ambient-glow-a" />
      <span className="ambient-glow ambient-glow-b" />
      <span className="ambient-glow ambient-glow-c" />
      <span className="ambient-grid" />
      <span className="ambient-grain" />
    </div>
  );
}
