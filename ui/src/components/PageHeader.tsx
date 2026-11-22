import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Reveal } from "@/components/Reveal";

export interface PageHeaderProps {
  /** the serif title (an accent word may be wrapped in <span className="accent-word">) */
  title: ReactNode;
  /** one line under the title */
  description: ReactNode;
  /** the buttons on the right: the Filters button and the screen's own actions */
  actions?: ReactNode;
  /** under the title row: the active filter chips */
  children?: ReactNode;
  className?: string;
}

/**
 * The header every screen shares: a serif title and a one-line description on the left, an actions row on the right (the
 * Filters button and any action the screen has of its own), and the active filter chips underneath.
 */
export function PageHeader({ title, description, actions, children, className }: PageHeaderProps) {
  return (
    <Reveal as="header" self trigger="mount" className={cn("space-y-4", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0 max-w-3xl">
          <h2 className="display-heading mb-1.5">{title}</h2>
          <p className="text-sm text-muted">{description}</p>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2" data-testid="page-actions">{actions}</div> : null}
      </div>
      {children}
    </Reveal>
  );
}
