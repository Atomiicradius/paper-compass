import { Network, SearchX } from "lucide-react";
import { api } from "@/api/client";
import type { SearchHit, SearchResponse } from "@/api/types";
import { useAsync, type AsyncState } from "@/lib/hooks";
import { normalizePaperId } from "@/lib/ids";
import { plainText } from "@/lib/text";
import { Badge, Button, ErrorNote, IdBadge, Mono, Skeleton, TagBadge } from "@/components/ui/primitives";
import { SlideOver } from "@/components/motion";
import { Reveal } from "@/components/Reveal";

export function PapersView({
  state, submitted, notes = [], onOpenPaper,
}: {
  state: AsyncState<SearchResponse>; submitted: boolean; notes?: string[]; onOpenPaper: (id: string) => void;
}) {
  if (!submitted) {
    return (
      <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted">
        <p>Describe a research idea in the search box above and press Search. Method, task and dataset filters narrow the results.</p>
      </div>
    );
  }
  if (state.error) {
    return <ErrorNote title="Search failed" message={state.error.message.replace(/^\d+: /, "")} action={<Button variant="outline" size="sm" onClick={state.reload}>Try again</Button>} />;
  }
  if (state.loading || !state.data) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Searching">
        <p className="text-sm text-muted">Searching… the first vector search loads the SPECTER2 model and can take a few minutes.</p>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="glass flex gap-4 rounded-2xl p-4" data-testid="paper-skeleton">
            <Skeleton className="h-12 w-12 shrink-0" />
            <div className="flex-1 space-y-2"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3 w-1/3" /><Skeleton className="h-5 w-1/2" /></div>
          </div>
        ))}
      </div>
    );
  }
  const res = state.data;
  // the meter shows each score against the best score of this result list (display only; the number is unchanged)
  const best = Math.max(...res.results.map((h) => h.score), 0);
  return (
    <section aria-label="Paper search results" className="space-y-4">
      <Reveal as="header" self trigger="mount" className="space-y-2">
        <p className="text-sm text-muted">
          <b className="text-foreground">{res.results.length}</b> results for “{res.query}” · mode <Mono>{res.mode}</Mono> · score <Mono>{res.score_type}</Mono>
          {res.note ? <> · {res.note}</> : null}
        </p>
        {notes.map((n) => <p key={n} role="note" className="rounded-lg border border-warning/50 bg-warning-soft px-3 py-2 text-xs text-warning-text">{n}</p>)}
      </Reveal>
      {res.results.length === 0 ? (
        <div className="grid place-items-center gap-2 rounded-2xl border border-dashed border-border p-10 text-sm text-muted">
          <SearchX className="size-6" /> No papers matched. Try other words or remove filters.
        </div>
      ) : (
        <Reveal as="ul" key={res.query + res.results.length} className="space-y-3 p-0">
          {res.results.map((h, i) => <HitCard key={h.paper_id} hit={h} rank={i + 1} best={best} onOpen={onOpenPaper} />)}
        </Reveal>
      )}
    </section>
  );
}

function HitCard({ hit: h, rank, best, onOpen }: { hit: SearchHit; rank: number; best: number; onOpen: (id: string) => void }) {
  const fraction = best > 0 ? Math.min(1, Math.max(0, h.score / best)) : 0;
  return (
    <li className="defer-paint list-none" data-testid="paper-card">
      <button
        type="button"
        onClick={() => onOpen(h.paper_id)}
        className="glass group flex w-full cursor-pointer items-start gap-4 rounded-2xl p-4 text-left transition-[translate,border-color] duration-300 hover:-translate-y-0.5 hover:border-primary/60"
      >
        <div className="w-14 shrink-0 text-center">
          <div className="font-display text-5xl leading-none text-foreground/80" data-testid="paper-rank">{rank}</div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-base leading-snug font-semibold">{h.title}</h3>
              <p className="mt-0.5 text-xs text-muted">{h.year ?? "n.d."} · {h.venue ?? "venue unknown"}</p>
            </div>
            <div className="w-24 shrink-0 text-right">
              <div className="mono-figure text-lg">{h.vector_rank !== undefined ? h.score.toFixed(4) : h.score.toFixed(3)}</div>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-hover" role="meter" aria-label="Score relative to the best result" aria-valuemin={0} aria-valuemax={1} aria-valuenow={Number(fraction.toFixed(3))} data-testid="paper-meter">
                <div className="h-full rounded-full bg-gradient-to-r from-primary to-[#38BDF8]" style={{ width: `${fraction * 100}%` }} />
              </div>
              <div className="mono-label mt-1 text-[10px]">score</div>
            </div>
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {h.methods.map((m) => <TagBadge key={"m" + m} kind="method">{m}</TagBadge>)}
            {h.tasks.map((m) => <TagBadge key={"t" + m} kind="task">{m}</TagBadge>)}
            {h.datasets.map((m) => <TagBadge key={"d" + m} kind="dataset">{m}</TagBadge>)}
            {h.vector_rank !== undefined || h.keyword_rank !== undefined ? (
              <>
                <Badge className="border-border bg-hover font-mono" title="Rank in the vector (SPECTER2) list">vector {h.vector_rank != null ? "#" + h.vector_rank : "–"}</Badge>
                <Badge className="border-border bg-hover font-mono" title="Rank in the keyword list">keyword {h.keyword_rank != null ? "#" + h.keyword_rank : "–"}</Badge>
              </>
            ) : null}
            <IdBadge id={h.paper_id} className="ml-auto" />
          </div>
        </div>
      </button>
    </li>
  );
}

/** Paper details in a slide-over: authors, extracted elements, abstract, citations and related papers. */
export function PaperDrawer({
  paperId, onClose, onOpenPaper, onOpenGraph,
}: {
  paperId: string | null; onClose: () => void; onOpenPaper: (id: string) => void; onOpenGraph: (id: string) => void;
}) {
  const id = paperId ? normalizePaperId(paperId) : null;
  const paper = useAsync((s) => api.paper(id as string, s), [id], id != null);
  const related = useAsync((s) => api.related(id as string, 6, s), [id], id != null);
  const p = paper.data && paper.data.paper_id === id ? paper.data : null;
  return (
    <SlideOver open={id != null} onClose={onClose} title={p ? p.title : "Paper details"} description="Details of one paper in the analyzed corpus">
      <div data-lenis-prevent className="scroll-thin flex-1 space-y-5 overflow-y-auto p-5 pr-16">
        {paper.error ? (
          <ErrorNote title="Could not load this paper" message={paper.error.message.replace(/^\d+: /, "")} action={<Button variant="outline" size="sm" onClick={paper.reload}>Try again</Button>} />
        ) : !p ? (
          <div className="space-y-3" aria-busy="true"><Skeleton className="h-8 w-3/4" /><Skeleton className="h-24" /><Skeleton className="h-40" /></div>
        ) : (
          <Reveal trigger="mount" className="space-y-5">
            <header className="space-y-2">
              <h2 className="display-heading display-md">{p.title}</h2>
              <p className="text-sm text-muted">
                {p.year ?? "n.d."} · {p.venue ?? "venue unknown"}
                {p.doi ? <> · <a className="text-primary underline" href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer">DOI</a></> : null}
              </p>
              <div className="flex flex-wrap items-center gap-2"><IdBadge id={p.paper_id} />
                <Button size="sm" variant="outline" onClick={() => onOpenGraph(p.paper_id)}><Network className="size-3.5" /> Show in graph</Button>
              </div>
            </header>
            <p className="text-sm"><span className="font-medium">Authors: </span>{p.authors.length ? p.authors.join(", ") : <span className="text-muted">none recorded</span>}</p>
            <div className="flex flex-wrap gap-1.5">
              {p.methods.map((m) => <TagBadge key={"m" + m} kind="method">{m}</TagBadge>)}
              {p.tasks.map((m) => <TagBadge key={"t" + m} kind="task">{m}</TagBadge>)}
              {p.datasets.map((m) => <TagBadge key={"d" + m} kind="dataset">{m}</TagBadge>)}
              {p.methods.length + p.tasks.length + p.datasets.length === 0 ? <Badge className="border-border bg-hover text-muted">no elements extracted</Badge> : null}
            </div>
            {p.abstract ? (
              <section><h3 className="mb-1 mono-label">Abstract</h3><p className="text-sm leading-relaxed">{plainText(p.abstract)}</p></section>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <IdList title={`Cites (${p.cites.length} in corpus)`} ids={p.cites} onOpen={onOpenPaper} />
              <IdList title={`Cited by (${p.cited_by.length} in corpus)`} ids={p.cited_by} onOpen={onOpenPaper} />
            </div>
            <section>
              <h3 className="mb-2 mono-label">Related by embedding</h3>
              {related.loading ? <Skeleton className="h-24" /> : related.error ? (
                <p className="text-xs text-muted">{related.error.message.replace(/^\d+: /, "")}</p>
              ) : (
                <ul className="space-y-1.5 p-0">
                  {related.data?.results.map((r) => (
                    <li key={r.paper_id} className="list-none">
                      <button type="button" onClick={() => onOpenPaper(r.paper_id)} className="flex w-full cursor-pointer items-baseline justify-between gap-3 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-hover">
                        <span className="truncate">{r.title} <span className="text-muted">({r.year ?? "n.d."})</span></span>
                        <Mono className="shrink-0 text-xs text-muted">{r.score.toFixed(3)}</Mono>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </Reveal>
        )}
      </div>
    </SlideOver>
  );
}

function IdList({ title, ids, onOpen }: { title: string; ids: string[]; onOpen: (id: string) => void }) {
  return (
    <section>
      <h3 className="mb-1 mono-label">{title}</h3>
      {ids.length === 0 ? <p className="text-xs text-muted">none</p> : (
        <ul className="flex flex-wrap gap-1 p-0">
          {ids.slice(0, 12).map((i) => (
            <li key={i} className="list-none">
              <button type="button" onClick={() => onOpen(i)} className="cursor-pointer rounded border border-border bg-hover px-1.5 py-0.5 font-mono text-[11px] text-muted hover:border-primary hover:text-foreground">{i}</button>
            </li>
          ))}
          {ids.length > 12 ? <li className="list-none self-center text-[11px] text-muted">+{ids.length - 12} more</li> : null}
        </ul>
      )}
    </section>
  );
}
