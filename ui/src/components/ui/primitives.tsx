import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import * as SliderPrimitive from "@radix-ui/react-slider";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { Check } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import type { ElementKind } from "@/api/types";
import { KIND_COLORS, KIND_LABELS, KIND_TEXT } from "@/lib/colors";
import { cn } from "@/lib/utils";

/* ----------------------------------------------------------------------------- Button */

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:opacity-90",
        outline: "border border-border bg-card hover:bg-hover",
        ghost: "hover:bg-hover",
        danger: "border border-warning/50 text-warning-text hover:bg-warning-soft",
      },
      size: { sm: "h-8 px-3", md: "h-9 px-4", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, type = "button", ...props }, ref) => (
  <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
));
Button.displayName = "Button";

/* ----------------------------------------------------------------------------- Badges */

export function Badge({ className, style, children, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap", className)}
      style={style}
      {...props}
    >
      {children}
    </span>
  );
}

/** Element tag in the semantic palette (Method blue, Task emerald, Dataset orange, Setting purple, Bridge rose). */
export function TagBadge({ kind, children, className }: { kind: ElementKind | "bridge"; children?: React.ReactNode; className?: string }) {
  const c = KIND_COLORS[kind];
  return (
    <Badge
      className={className}
      data-kind={kind}
      style={{ color: KIND_TEXT[kind], borderColor: `color-mix(in srgb, ${c} 45%, transparent)`, background: `color-mix(in srgb, ${c} 12%, transparent)` }}
    >
      <span className="size-1.5 rounded-full" style={{ background: c }} aria-hidden />
      {children ?? KIND_LABELS[kind]}
    </Badge>
  );
}

/** Monospace identifier chip, e.g. W3028876793. */
export function IdBadge({ id, className }: { id: string; className?: string }) {
  return (
    <span className={cn("rounded border border-border bg-hover px-1.5 py-0.5 font-mono text-[11px] text-muted", className)} title="OpenAlex id">
      {id}
    </span>
  );
}

/** A number or figure rendered in the mono face. */
export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("font-mono tabular-nums", className)}>{children}</span>;
}

/* ----------------------------------------------------------------------------- Tooltip */

export const TooltipProvider = TooltipPrimitive.Provider;

export function Tip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactElement; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TooltipPrimitive.Root delayDuration={150}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          collisionPadding={12}
          className="z-[100] max-w-xs rounded-lg border border-border bg-card px-3 py-2 text-xs leading-relaxed text-foreground shadow-xl"
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-card" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

/* ----------------------------------------------------------------------------- Tabs */

export const Tabs = TabsPrimitive.Root;

export const TabsList = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>>(({ className, ...props }, ref) => (
  <TabsPrimitive.List ref={ref} data-lenis-prevent className={cn("flex gap-1 overflow-x-auto rounded-xl border border-border bg-background p-1 scroll-thin", className)} {...props} />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef<HTMLButtonElement, React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors cursor-pointer",
      "hover:text-foreground data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn("mt-4 outline-none", className)} {...props} />
));
TabsContent.displayName = "TabsContent";

/* ----------------------------------------------------------------------------- Slider */

export function Slider({ className, "aria-label": ariaLabel, ...props }: React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>) {
  const n = (props.value ?? props.defaultValue ?? [0]).length;
  // the focusable elements are the thumbs, so they carry the accessible name (a range gets "minimum"/"maximum")
  const thumbLabel = (i: number) => (ariaLabel ? (n > 1 ? `${ariaLabel} ${i === 0 ? "minimum" : "maximum"}` : ariaLabel) : undefined);
  return (
    <SliderPrimitive.Root className={cn("relative flex h-5 w-full touch-none items-center select-none", className)} {...props}>
      <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-hover">
        <SliderPrimitive.Range className="absolute h-full bg-primary" />
      </SliderPrimitive.Track>
      {Array.from({ length: n }, (_, i) => (
        <SliderPrimitive.Thumb
          key={i}
          aria-label={thumbLabel(i)}
          className="block size-4 cursor-grab rounded-full border-2 border-primary bg-background shadow transition-transform hover:scale-110 active:cursor-grabbing"
        />
      ))}
    </SliderPrimitive.Root>
  );
}

/* ----------------------------------------------------------------------------- Checkbox / Switch */

export function Checkbox({ className, ...props }: React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      className={cn(
        "grid size-4 shrink-0 cursor-pointer place-content-center rounded border border-muted/60 bg-background transition-colors",
        "data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator>
        <Check className="size-3" strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export function Switch({ className, ...props }: React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn("relative h-5 w-9 shrink-0 cursor-pointer rounded-full bg-hover transition-colors data-[state=checked]:bg-primary", className)}
      {...props}
    >
      <SwitchPrimitive.Thumb className="block size-4 translate-x-0.5 rounded-full bg-foreground transition-transform data-[state=checked]:translate-x-[18px] data-[state=checked]:bg-primary-foreground" />
    </SwitchPrimitive.Root>
  );
}

/* ----------------------------------------------------------------------------- misc */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-hover", className)} aria-hidden />;
}

export function ErrorNote({ title = "Something went wrong", message, action }: { title?: string; message: string; action?: React.ReactNode }) {
  return (
    <div role="alert" className="rounded-xl border border-warning/50 bg-warning-soft p-4 text-sm">
      <p className="font-semibold text-warning-text">{title}</p>
      <p className="mt-1 break-words text-foreground/90">{message}</p>
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}
