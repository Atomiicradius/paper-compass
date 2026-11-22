import type { ElementKind } from "@/api/types";

/* ------------------------------------------------------------------------------------------------
 * Entity highlighting in source sentences
 * ---------------------------------------------------------------------------------------------- */

export interface Entity { name: string; kind: ElementKind }
export interface Segment { text: string; kind?: ElementKind }

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * A regex source for one entity name. The extractor linked the sentence through aliases, so the exact canonical
 * name may not appear: "Masked Language Modeling" should also match "masked language models". Multi-word names
 * therefore match word stems (each word of 5+ letters is cut to its stem and may continue with letters), and
 * single words match exactly with an optional plural ending.
 */
export function entityPattern(name: string): string | null {
  const words = name.trim().split(/[\s-]+/).filter(Boolean);
  if (words.length === 0) return null;
  if (words.length === 1) return "\\b" + escapeRe(words[0] as string) + "(?:s|es)?\\b";
  const parts = words.map((w) => {
    if (w.length < 5) return escapeRe(w);
    const stem = w.slice(0, Math.max(4, w.length - 3));
    return escapeRe(stem) + "[a-z]*";
  });
  return "\\b" + parts.join("[\\s-]+") + "\\b";
}

/** Split text into plain and highlighted segments. Earlier entities win on overlap; matching is case-insensitive. */
export function highlightSegments(text: string, entities: readonly Entity[]): Segment[] {
  const ranges: { start: number; end: number; kind: ElementKind }[] = [];
  for (const e of entities) {
    const src = entityPattern(e.name);
    if (!src) continue;
    const re = new RegExp(src, "gi");
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (m[0].length === 0) { re.lastIndex++; continue; }
      const start = m.index, end = m.index + m[0].length;
      if (!ranges.some((r) => start < r.end && end > r.start)) ranges.push({ start, end, kind: e.kind });
    }
  }
  ranges.sort((a, b) => a.start - b.start);
  const out: Segment[] = [];
  let pos = 0;
  for (const r of ranges) {
    if (r.start > pos) out.push({ text: text.slice(pos, r.start) });
    out.push({ text: text.slice(r.start, r.end), kind: r.kind });
    pos = r.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos) });
  return out.length ? out : [{ text }];
}

/* ------------------------------------------------------------------------------------------------
 * Citation markers in the explanation summary
 * ---------------------------------------------------------------------------------------------- */

export type SummaryToken = { type: "text"; text: string } | { type: "citation"; paperId: string };

/** Split a line on [paper:W123] markers. */
export function tokenizeCitations(line: string): SummaryToken[] {
  const out: SummaryToken[] = [];
  const re = /\[paper:([^\]\s]+)\]/g;
  let pos = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line)) !== null) {
    if (m.index > pos) out.push({ type: "text", text: line.slice(pos, m.index) });
    out.push({ type: "citation", paperId: m[1] as string });
    pos = m.index + m[0].length;
  }
  if (pos < line.length) out.push({ type: "text", text: line.slice(pos) });
  return out;
}

export type Block =
  | { type: "heading"; text: string }
  | { type: "bullet"; tokens: SummaryToken[] }
  | { type: "paragraph"; tokens: SummaryToken[] };

/** The summary is a small markdown subset: "## heading", "- bullet" and paragraphs. */
export function parseSummary(summary: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of summary.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (/^#{1,6}\s+/.test(line)) blocks.push({ type: "heading", text: line.replace(/^#{1,6}\s+/, "") });
    else if (/^[-*]\s+/.test(line)) blocks.push({ type: "bullet", tokens: tokenizeCitations(line.replace(/^[-*]\s+/, "")) });
    else blocks.push({ type: "paragraph", tokens: tokenizeCitations(line) });
  }
  return blocks;
}

export type CitationStatus = "verified" | "unknown";

/**
 * A cited paper is verified only when the API's citation check lists it as cited and it is not in `unknown`,
 * AND it is one of the evidence papers the drawer actually shows. Anything else is flagged, never assumed fine.
 */
export function citationStatus(
  paperId: string,
  check: { cited: readonly string[]; unknown: readonly string[] },
  evidenceIds: ReadonlySet<string>,
): CitationStatus {
  if (check.unknown.includes(paperId)) return "unknown";
  return check.cited.includes(paperId) && evidenceIds.has(paperId) ? "verified" : "unknown";
}

/* ------------------------------------------------------------------------------------------------
 * Abstracts that carry markup
 * ---------------------------------------------------------------------------------------------- */

const ENTITIES: Record<string, string> = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&apos;": "'", "&nbsp;": " " };

/** Display text for an abstract: tags (HTML, JATS) removed, common entities decoded, whitespace collapsed. Display
 * only; nothing is written back. A "<" not followed by a tag name (as in "x < y") is left alone. */
export function plainText(s: string): string {
  return s
    .replace(/<\/?[A-Za-z][A-Za-z0-9:_-]*(?:\s[^<>]*)?\/?>/g, "")
    .replace(/&(?:amp|lt|gt|quot|apos|nbsp|#39);/g, (m) => ENTITIES[m] ?? m)
    .replace(/\s+/g, " ")
    .trim();
}
