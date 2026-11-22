import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion, useMotionValue, useSpring, useTransform } from "motion/react";
import { X } from "lucide-react";
import { clamp01, cn } from "@/lib/utils";
import { Button, Tip } from "@/components/ui/primitives";

/** Count-up number driven by a spring (physics-based), re-targeted whenever `value` changes. */
export function SpringNumber({ value, className, format = (n: number) => String(Math.round(n)) }: { value: number; className?: string; format?: (n: number) => string }) {
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { stiffness: 120, damping: 18, mass: 0.8 });
  const text = useTransform(spring, (n) => format(n));
  React.useEffect(() => {
    mv.set(value);
  }, [value, mv]);
  return <motion.span className={className}>{text}</motion.span>;
}

/**
 * A 0..1 meter. The fill has a fixed width inside a clipped wrapper and slides in from x: -100% to 0
 * with an ease-out transition on mount.
 */
export function SignalMeter({
  label, value, color, tip, delay = 0, className,
}: {
  label: string; value: number | null; color: string; tip: React.ReactNode; delay?: number; className?: string;
}) {
  const v = value == null ? 0 : clamp01(value);
  return (
    <Tip content={tip}>
      <div className={cn("group cursor-help", className)} data-testid={"meter-" + label.toLowerCase()}>
        <div className="mb-1 flex items-center justify-between text-[11px] text-muted">
          <span className="font-medium uppercase tracking-wide">{label}</span>
          <span className="font-mono tabular-nums text-foreground">{value == null ? "n/a" : v.toFixed(2)}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-hover" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={1} aria-valuenow={v}>
          <motion.div
            className="h-full rounded-full"
            style={{ width: `${v * 100}%`, background: color }}
            initial={{ x: "-100%" }}
            animate={{ x: "0%" }}
            transition={{ duration: 0.7, ease: "easeOut", delay }}
          />
        </div>
      </div>
    </Tip>
  );
}

/**
 * Right-hand slide-over. Spring transition (damping 25, stiffness 180) for the panel and a backdrop whose
 * blur animates from 0px to md (12px). Built on Radix Dialog for focus trapping, Escape and ARIA.
 */
export function SlideOver({
  open, onClose, title, description, children, widthClass = "w-full max-w-2xl",
}: {
  open: boolean; onClose: () => void; title: string; description: string; children: React.ReactNode; widthClass?: string;
}) {
  const returnFocusTo = React.useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <AnimatePresence>
        {open ? (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <motion.div
                className="fixed inset-0 z-40 bg-black/40"
                initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
                animate={{ opacity: 1, backdropFilter: "blur(12px)" }}
                exit={{ opacity: 0, backdropFilter: "blur(0px)" }}
                transition={{ duration: 0.25 }}
              />
            </Dialog.Overlay>
            <Dialog.Content
              asChild
              forceMount
              // remember what had focus when the panel opened (this runs just before Radix moves focus into it) and give
              // it back on close; Radix's own restore does not survive the exit animation
              onOpenAutoFocus={() => { returnFocusTo.current = document.activeElement as HTMLElement | null; }}
              onCloseAutoFocus={(e) => {
                e.preventDefault();
                const el = returnFocusTo.current;
                if (el?.isConnected) el.focus({ preventScroll: true });
              }}
            >
              <motion.div
                data-lenis-prevent
                className={cn("fixed inset-y-0 right-0 z-50 flex flex-col border-l border-border bg-card shadow-2xl", widthClass)}
                initial={{ x: "100%" }}
                animate={{ x: 0 }}
                exit={{ x: "100%" }}
                transition={{ type: "spring", damping: 25, stiffness: 180 }}
              >
                <Dialog.Title className="sr-only">{title}</Dialog.Title>
                <Dialog.Description className="sr-only">{description}</Dialog.Description>
                <div className="absolute right-3 top-3 z-10">
                  <Tip content="Close (Esc)" side="left">
                    <Button variant="ghost" size="icon" aria-label="Close panel" onClick={onClose}>
                      <X className="size-4" />
                    </Button>
                  </Tip>
                </div>
                {children}
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        ) : null}
      </AnimatePresence>
    </Dialog.Root>
  );
}

/** Container that staggers its motion children (fade in, y 10 -> 0). Use `fadeUp` on each child. */
export const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
export const fadeUp = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" as const } } };
