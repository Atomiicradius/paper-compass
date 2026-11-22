import type { ElementKind, GraphLabel } from "@/api/types";

/** Semantic tagging palette, identical in both themes. */
export const KIND_COLORS: Record<ElementKind | "bridge", string> = {
  method: "#3B82F6", // blue
  task: "#10B981", // emerald
  dataset: "#F97316", // orange
  setting: "#8B5CF6", // purple
  bridge: "#EC4899", // rose / pink
};

/** Text colours for the same hues: accessible shades per theme (see index.css). Dots, borders, charts and graph
 * nodes keep the exact hex above. */
export const KIND_TEXT: Record<ElementKind | "bridge", string> = {
  method: "var(--tag-text-method)",
  task: "var(--tag-text-task)",
  dataset: "var(--tag-text-dataset)",
  setting: "var(--tag-text-setting)",
  bridge: "var(--tag-text-bridge)",
};

export const KIND_LABELS: Record<ElementKind | "bridge", string> = {
  method: "Method",
  task: "Task",
  dataset: "Dataset",
  setting: "Setting",
  bridge: "Bridge",
};

/** Node colours: the four element kinds and bridge use the palette above; the rest are neutral. */
export const GRAPH_COLORS: Record<GraphLabel | "Bridge", string> = {
  Method: KIND_COLORS.method,
  Task: KIND_COLORS.task,
  Dataset: KIND_COLORS.dataset,
  Setting: KIND_COLORS.setting,
  Bridge: KIND_COLORS.bridge,
  Paper: "#0EA5E9",
  Author: "#EAB308",
  Venue: "#94A3B8",
  Institution: "#64748B",
  Topic: "#14B8A6",
  Experiment: "#A3A3A3",
  Result: "#A3A3A3",
};

export type Strength = "strong" | "moderate" | "weak";

/** Score badge colour by strength: >= 70 strong, >= 50 moderate, below weak. */
export function scoreStrength(score: number | null | undefined): { strength: Strength; color: string; text: string; label: string } {
  const s = score ?? 0;
  if (s >= 70) return { strength: "strong", color: "#14B8A6", text: "var(--score-strong)", label: "Strong signal" };
  if (s >= 50) return { strength: "moderate", color: "#F59E0B", text: "var(--score-moderate)", label: "Moderate signal" };
  return { strength: "weak", color: "#94A3B8", text: "var(--score-weak)", label: "Weak signal" };
}

export function isElementKind(x: string): x is ElementKind {
  return x === "method" || x === "task" || x === "dataset" || x === "setting";
}
