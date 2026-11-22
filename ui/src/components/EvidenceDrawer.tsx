import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, BadgeCheck, CircleHelp, Network, Send, ShieldAlert } from "lucide-react";
import { api, ApiError } from "@/api/client";
import type { EvidencePaper, EvidenceRole, Explanation, Opportunity, PairElement } from "@/api/types";
import { KIND_COLORS, KIND_TEXT } from "@/lib/colors";
import { useAsync } from "@/lib/hooks";
import { opportunityTitle } from "@/lib/opportunities";
import { citationStatus, highlightSegments, parseSummary, type Entity, type SummaryToken } from "@/lib/text";
import { cn, formatNumber } from "@/lib/utils";
import { Badge, Button, ErrorNote, IdBadge, Mono, Skeleton, TagBadge, Tabs, TabsContent, TabsList, TabsTrigger, Tip } from "@/components/ui/primitives";
import { SlideOver, SpringNumber } from "@/components/motion";
import { scoreStrength } from "@/lib/colors";

const ROLES: { role: EvidenceRole; label: string }[] = [
  { role: "supports_A", label: "Supports A" },
  { role: "supports_B", label: "Supports B" },
  { role: "bridge", label: "Bridge Work" },
  { role: "nearest_existing", label: "Nearest Existing" },
];

function roleHint(role: EvidenceRole, a: PairElement, b: PairElement) {
  const A = <TagBadge kind={a.kind}>{a.name}</TagBadge>;
  const B = <TagBadge kind={b.kind}>{b.name}</TagBadge>;
  switch (role) {
    case "supports_A":
      return <>Papers that use {A} <b>without</b> {B}: evidence that the first element is well established.</>;
    case "supports_B":
      return <>Papers that use {B} <b>without</b> {A}: evidence that the second element is well established.</>;
    case "bridge":
      return <><TagBadge kind="bridge" /> Papers whose citations connect the two groups above.</>;
    case "nearest_existing":
      return <>The closest existing work in the corpus (exact co-use first, then similar papers). <b>Read these before treating the combination as new.</b></>;
  }
}

function Highlighted({ text, entities }: { text: string; entities: Entity[] }) {
  const segs = useMemo(() => highlightSegments(text, entities), [text, entities]);
  return (
    <>
      {segs.map((s, i) =>
        s.kind ? (
          <mark
            key={i}
            data-kind={s.kind}
            className="rounded px-0.5 font-medium"
            style={{ color: KIND_TEXT[s.kind], background: `color-mix(in srgb, ${KIND_COLORS[s.kind]} 16%, transparent)` }}
          >
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </>
  );
}

function EvidenceCard({
  paper, role, pair, entities, highlighted, onOpenGraph,
}: {
  paper: EvidencePaper; role: EvidenceRole; pair: { a: PairElement; b: PairElement }; entities: Entity[]; highlighted: boolean;
  onOpenGraph: (paperId: string) => void;
}) {
  return (
    <motion.li
      id={`ev-${paper.paper_id}`}
      layout="position"
      animate={highlighted ? { boxShadow: "0 0 0 2px var(--cite)" } : { boxShadow: "0 0 0 0px transparent" }}
      transition={{ duration: 0.3 }}
      className="list-none rounded-xl border border-border bg-background p-3"
      data-testid="evidence-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm leading-snug font-semibold">{paper.title}</p>
          <p className="mt-0.5 text-xs text-muted">
            {paper.year ?? "n.d."} · {paper.venue ?? "venue unknown"}
          </p>
        </div>
        <IdBadge id={paper.paper_id} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {role === "supports_A" ? <TagBadge kind={pair.a.kind}>{pair.a.name}</TagBadge> : null}
        {role === "supports_B" ? <TagBadge kind={pair.b.kind}>{pair.b.name}</TagBadge> : null}
        {role === "bridge" ? <TagBadge kind="bridge">Bridge</TagBadge> : null}
        {role === "nearest_existing" ? (
          paper.tier === "exact" ? (
            <>
              <TagBadge kind={pair.a.kind}>{pair.a.name}</TagBadge>
              <TagBadge kind={pair.b.kind}>{pair.b.name}</TagBadge>
              <Badge className="border-border bg-hover">exact: uses both</Badge>
            </>
          ) : (
            <Badge className="border-cite/50 bg-cite-soft text-cite">
              close{paper.similarity != null ? <> · similarity <Mono>{paper.similarity.toFixed(3)}</Mono></> : null}
            </Badge>
          )
        ) : null}
        <Button variant="ghost" size="sm" className="ml-auto h-7 px-2 text-xs" onClick={() => onOpenGraph(paper.paper_id)}>
          <Network className="size-3.5" /> Graph
        </Button>
      </div>
      {paper.source_sentence ? (
        <blockquote className="mt-2 rounded-lg border border-border bg-card p-2.5 text-xs leading-relaxed text-foreground/90">
          <Highlighted text={paper.source_sentence} entities={entities} />
          {paper.extractor ? <span className="mt-1 block font-mono text-[10px] text-muted">source sentence · {paper.extractor}</span> : null}
        </blockquote>
      ) : (
        <p className="mt-2 text-xs text-muted italic">No source sentence stored for this paper.</p>
      )}
    </motion.li>
  );
}

function CitationChip({
  paperId, status, title, onClick,
}: {
  paperId: string; status: "verified" | "unknown"; title: string | null; onClick: () => void;
}) {
  const ok = status === "verified";
  return (
    <Tip
      content={
        ok ? (
          <span><b>Verified</b>: this paper is in the retrieved evidence set.{title ? <> <br />{title}</> : null}</span>
        ) : (
          <span><b>Not verified</b>: this paper is not in the evidence set shown here, so the statement is not grounded. Treat it with care.</span>
        )
      }
    >
      <button
        type="button"
        onClick={onClick}
        disabled={!ok}
        data-status={status}
        className={cn(
          "mx-0.5 inline-flex cursor-pointer items-center gap-1 rounded-md border px-1.5 py-0.5 align-baseline font-mono text-[11px] transition-colors disabled:cursor-not-allowed",
          ok ? "border-cite/50 bg-cite-soft text-cite hover:bg-cite/20" : "border-warning/60 bg-warning-soft text-warning-text",
        )}
      >
        {ok ? <BadgeCheck className="size-3" /> : <ShieldAlert className="size-3" />}
        {paperId}
      </button>
    </Tip>
  );
}

function SummaryTokens({ tokens, render }: { tokens: SummaryToken[]; render: (id: string) => React.ReactNode }) {
  return (
    <>
      {tokens.map((t, i) => (t.type === "text" ? <span key={i}>{t.text}</span> : <span key={i}>{render(t.paperId)}</span>))}
    </>
  );
}

function Sparkline({ data, a, b }: { data: Explanation["evidence"]["yearly"]; a: PairElement; b: PairElement }) {
  const rows = data.filter((d) => d.year >= 2010);
  if (rows.length < 2) return null;
  const W = 320, H = 70, pad = 4;
  const max = Math.max(1, ...rows.flatMap((r) => [r.a, r.b, r.both]));
  const x = (i: number) => pad + (i / (rows.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - (v / max) * (H - 2 * pad);
  const line = (key: "a" | "b" | "both") => rows.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`).join(" ");
  return (
    <figure className="rounded-xl border border-border bg-background p-3">
      <figcaption className="mb-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
        <span className="font-medium text-foreground">Papers per year</span>
        <span style={{ color: KIND_TEXT[a.kind] }}>● {a.name}</span>
        <span style={{ color: KIND_TEXT[b.kind] }}>● {b.name}</span>
        <span style={{ color: KIND_TEXT.bridge }}>● both</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-20 w-full" role="img" aria-label={`Papers per year for ${a.name}, ${b.name} and both, ${rows[0]?.year} to ${rows[rows.length - 1]?.year}`}>
        <path d={line("b")} fill="none" stroke={KIND_COLORS[b.kind]} strokeWidth="1.8" />
        <path d={line("a")} fill="none" stroke={KIND_COLORS[a.kind]} strokeWidth="1.8" />
        <path d={line("both")} fill="none" stroke={KIND_COLORS.bridge} strokeWidth="1.8" strokeDasharray="4 3" />
      </svg>
      <div className="flex justify-between font-mono text-[10px] text-muted"><span>{rows[0]?.year}</span><span>max {max}/yr</span><span>{rows[rows.length - 1]?.year}</span></div>
    </figure>
  );
}

function AskBox({ opportunity }: { opportunity: Opportunity }) {
  const [q, setQ] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      await api.rag(`${q.trim()} (opportunity ${opportunity.opportunity_id})`);
      setNote("Answer received.");
    } catch (err) {
      setNote(err instanceof ApiError && err.status === 501
        ? "Free-form questions are not available yet: the RAG client is still an open decision (O5). The explanation above is grounded in the retrieved evidence."
        : (err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-2" aria-label="Ask a question">
      <label htmlFor="ask" className="text-xs font-medium text-muted">Ask about this opportunity</label>
      <div className="flex gap-2">
        <input
          id="ask" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Which papers come closest?"
          className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-background px-3 text-sm outline-none focus-visible:border-primary"
        />
        <Button type="submit" size="sm" className="h-9" disabled={busy || !q.trim()}><Send className="size-3.5" /> Ask</Button>
      </div>
      {note ? <p className="text-xs text-muted" role="status">{note}</p> : null}
    </form>
  );
}

/**
 * The drawer's content for one opportunity. It is mounted with key={opportunity_id}, so switching to another
 * opportunity starts with a fresh tab, no highlighted paper and a new request, with no reset effects.
 */
function EvidenceBody({ o, onOpenGraph }: { o: Opportunity; onOpenGraph: (paperId: string) => void }) {
  const state = useAsync((s) => api.explain(o.opportunity_id, s), [o.opportunity_id]);
  const ex = state.data;

  const [tab, setTab] = useState<EvidenceRole>("supports_A");
  const [flash, setFlash] = useState<string | null>(null);
  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 2200);
    return () => clearTimeout(t);
  }, [flash]);

  const evidenceIds = useMemo(() => new Set(ex ? Object.values(ex.evidence.roles).flat().map((p) => p.paper_id) : []), [ex]);
  const titles = useMemo(() => new Map(ex ? Object.values(ex.evidence.roles).flat().map((p) => [p.paper_id, p.title] as const) : []), [ex]);
  const entities: Entity[] = useMemo(() => (ex ? [
    { name: ex.evidence.pair.a.name, kind: ex.evidence.pair.a.kind }, { name: ex.evidence.pair.b.name, kind: ex.evidence.pair.b.kind },
  ] : []), [ex]);

  function goToPaper(paperId: string) {
    if (!ex) return;
    const role = ROLES.find((r) => ex.evidence.roles[r.role].some((p) => p.paper_id === paperId));
    if (!role) return;
    setTab(role.role);
    setFlash(paperId);
    // wait for the tab content to mount, then bring the card into view
    setTimeout(() => document.getElementById(`ev-${paperId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 120);
  }

  const tone = scoreStrength(o.score);
  const check = ex?.citation_check;
  const verifiedCount = check ? check.cited.filter((id) => citationStatus(id, check, evidenceIds) === "verified").length : 0;
  const allVerified = !!check && check.ok && check.cited.length > 0 && verifiedCount === check.cited.length;

  return (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="space-y-3 border-b border-border p-5 pr-16">
            <div
              role="note"
              className="flex items-start gap-2.5 rounded-xl border border-warning/60 bg-warning-soft px-3.5 py-2.5 text-sm font-medium text-warning-text"
              data-testid="warning-banner"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              A candidate opportunity is a signal for human review, not proof of a research gap.
            </div>
            <div className="flex items-start justify-between gap-3">
              <motion.h2 layoutId={`title-${o.opportunity_id}`} className="text-xl leading-snug font-semibold tracking-tight">
                {(["method", "dataset", "task", "setting"] as const).filter((k) => o.elements[k]).map((k, i) => (
                  <span key={k}>{i > 0 ? <span className="mx-1.5 text-muted">×</span> : null}<span style={{ color: KIND_TEXT[k] }}>{o.elements[k]}</span></span>
                ))}
              </motion.h2>
              <div className="shrink-0 rounded-xl border px-3 py-1 text-center" style={{ borderColor: tone.color, color: tone.text }}>
                <div className="text-[10px] font-semibold uppercase tracking-wider">Score</div>
                <SpringNumber value={o.score ?? 0} className="font-mono text-xl font-bold" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              {[
                ["Observed", String(o.observed_count), "Distinct papers using both elements together."],
                ["Expected", formatNumber(o.expected_count), "n_A × n_B / N over the same universe of papers."],
                ["Universe N", ex ? String(ex.evidence.corpus.universe_size) : "…", "Papers up to the cutoff in which both kinds of element were extracted."],
                ["Cutoff", String(o.corpus.cutoff_year), "Only papers published up to this year are counted."],
              ].map(([k, v, tip]) => (
                <Tip key={k} content={tip}>
                  <div className="cursor-help rounded-lg border border-border bg-background px-3 py-2">
                    <div className="text-[10px] tracking-wide text-muted uppercase">{k}</div>
                    <div className="font-mono text-base font-semibold tabular-nums">{v}</div>
                  </div>
                </Tip>
              ))}
            </div>
          </div>

          <div className="scroll-thin min-h-0 flex-1 space-y-6 overflow-y-auto p-5">
            {state.error ? (
              <ErrorNote
                title="Could not load the explanation"
                message={state.error instanceof ApiError && state.error.status === 422
                  ? `${state.error.detail} (the explanation needs exactly one pair of method, dataset or task).`
                  : state.error.message.replace(/^\d+: /, "")}
                action={<Button variant="outline" size="sm" onClick={state.reload}>Try again</Button>}
              />
            ) : !ex ? (
              <div className="space-y-3" aria-busy="true" aria-label="Loading evidence">
                <Skeleton className="h-24" /><Skeleton className="h-40" /><Skeleton className="h-56" />
              </div>
            ) : (
              <>
                <section aria-label="Why this is a candidate" className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold tracking-wide uppercase text-muted">Why? Evidence-grounded explanation</h3>
                    <Tip content={check?.ok ? "Every cited paper is part of the retrieved evidence set." : "At least one citation could not be verified."}>
                      <Badge
                        data-testid="citation-check"
                        className={cn(allVerified ? "border-cite/50 bg-cite-soft text-cite" : "border-warning/60 bg-warning-soft text-warning-text")}
                      >
                        {allVerified ? <BadgeCheck className="size-3" /> : <CircleHelp className="size-3" />}
                        {allVerified ? `${verifiedCount} citations verified` : check && check.cited.length === 0 ? "no citations to verify" : "citation check failed"}
                      </Badge>
                    </Tip>
                  </div>
                  <div className="space-y-1.5 rounded-xl border border-border bg-background p-4 text-sm leading-relaxed">
                    {parseSummary(ex.summary).map((b, i) =>
                      b.type === "heading" ? (
                        <h4 key={i} className="pt-2 text-xs font-semibold tracking-wide text-primary uppercase first:pt-0">{b.text}</h4>
                      ) : (
                        <p key={i} className={cn(b.type === "bullet" && "relative pl-4 before:absolute before:left-1 before:content-['•']")}>
                          <SummaryTokens
                            tokens={b.tokens}
                            render={(id) => (
                              <CitationChip
                                paperId={id}
                                status={check ? citationStatus(id, check, evidenceIds) : "unknown"}
                                title={titles.get(id) ?? null}
                                onClick={() => goToPaper(id)}
                              />
                            )}
                          />
                        </p>
                      ),
                    )}
                  </div>
                  <p className="text-[11px] text-muted">
                    Summary source: <Mono>{ex.summary_source}</Mono>
                    {ex.summary_fallback_reason ? <> (fallback: {ex.summary_fallback_reason})</> : null}. Click a violet citation to jump to that paper.
                  </p>
                </section>

                <Sparkline data={ex.evidence.yearly} a={ex.evidence.pair.a} b={ex.evidence.pair.b} />

                <section aria-label="Evidence chain" className="space-y-2">
                  <h3 className="text-sm font-semibold tracking-wide uppercase text-muted">Evidence chain</h3>
                  <Tabs value={tab} onValueChange={(v) => setTab(v as EvidenceRole)}>
                    <TabsList aria-label="Evidence role">
                      {ROLES.map(({ role, label }) => (
                        <TabsTrigger key={role} value={role}>
                          {label}
                          <span className="rounded-full bg-hover px-1.5 font-mono text-[10px]">{ex.evidence.roles[role].length}</span>
                        </TabsTrigger>
                      ))}
                    </TabsList>
                    {ROLES.map(({ role }) => (
                      <TabsContent key={role} value={role}>
                        <p className="mb-3 flex flex-wrap items-center gap-1.5 text-xs text-muted">{roleHint(role, ex.evidence.pair.a, ex.evidence.pair.b)}</p>
                        {ex.evidence.roles[role].length === 0 ? (
                          <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted">No papers in this group for this opportunity.</p>
                        ) : (
                          <ul className="space-y-3 p-0">
                            {ex.evidence.roles[role].map((p) => (
                              <EvidenceCard key={p.paper_id} paper={p} role={role} pair={ex.evidence.pair} entities={entities} highlighted={flash === p.paper_id} onOpenGraph={onOpenGraph} />
                            ))}
                          </ul>
                        )}
                      </TabsContent>
                    ))}
                  </Tabs>
                </section>

                <section aria-label="Limitations" className="space-y-2">
                  <h3 className="text-sm font-semibold tracking-wide uppercase text-muted">Limitations</h3>
                  <ul className="space-y-1.5 pl-4 text-xs leading-relaxed text-muted">
                    {ex.evidence.limitations.map((l, i) => <li key={i} className="list-disc">{l}</li>)}
                  </ul>
                </section>

                <AskBox opportunity={o} />
              </>
            )}
          </div>
        </div>
  );
}

export function EvidenceDrawer({
  opportunity, onClose, onOpenGraph,
}: {
  opportunity: Opportunity | null; onClose: () => void; onOpenGraph: (paperId: string) => void;
}) {
  // keep showing the last opportunity while the drawer animates out: remember it by adjusting state during render
  // (React's documented alternative to an effect or a ref for "derived from props" state)
  const [shown, setShown] = useState<Opportunity | null>(opportunity);
  if (opportunity && opportunity !== shown) setShown(opportunity);
  const o = opportunity ?? shown;
  return (
    <SlideOver
      open={opportunity != null}
      onClose={onClose}
      title={o ? `Evidence for ${opportunityTitle(o.elements)}` : "Evidence"}
      description="Evidence chain and grounded explanation for a candidate research opportunity"
    >
      {o ? <EvidenceBody key={o.opportunity_id} o={o} onOpenGraph={onOpenGraph} /> : null}
    </SlideOver>
  );
}
