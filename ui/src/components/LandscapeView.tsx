import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { Network } from "lucide-react";
import { api } from "@/api/client";
import type { Landscape, TrendItem } from "@/api/types";
import { KIND_COLORS } from "@/lib/colors";
import { useAsync, type AsyncState } from "@/lib/hooks";
import { Badge, Button, ErrorNote, IdBadge, Mono, Skeleton, Slider, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { fadeUp, stagger } from "@/components/motion";

function YearBars({ perYear }: { perYear: Record<string, number> }) {
  const years = Object.keys(perYear).map(Number).sort((a, b) => a - b);
  const max = Math.max(1, ...Object.values(perYear));
  const W = 720, H = 140, pad = 6;
  const bw = (W - 2 * pad) / Math.max(1, years.length);
  return (
    <svg viewBox={`0 0 ${W} ${H + 18}`} className="h-44 w-full" role="img" aria-label={`Papers per year from ${years[0]} to ${years[years.length - 1]}`}>
      {years.map((y, i) => {
        const v = perYear[String(y)] ?? 0;
        const h = (v / max) * (H - pad);
        return (
          <g key={y}>
            <rect x={pad + i * bw + 1} y={H - h} width={Math.max(1, bw - 2)} height={h} rx={2} fill={KIND_COLORS.method} opacity={0.85}>
              <title>{`${y}: ${v} papers`}</title>
            </rect>
          </g>
        );
      })}
      {years.filter((_, i) => i % Math.ceil(years.length / 8) === 0).map((y) => (
        <text key={y} x={pad + years.indexOf(y) * bw + bw / 2} y={H + 13} textAnchor="middle" className="fill-muted font-mono" fontSize="10">{y}</text>
      ))}
    </svg>
  );
}

function TrendList({ items, empty }: { items: TrendItem[]; empty: string }) {
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="space-y-1.5 p-0">
      {items.map((t) => (
        <li key={t.element_type + t.element_id} className="flex list-none items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-1.5 text-sm">
          <span className="truncate">{t.name}</span>
          <span className="flex shrink-0 items-center gap-3 font-mono text-xs text-muted">
            <span>{t.total} papers</span><span>recent {Math.round(t.recent_share * 100)}%</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function LandscapeView({ state, onOpenGraph }: { state: AsyncState<Landscape>; onOpenGraph: (id: string) => void }) {
  const clusters = useAsync((s) => api.clusters(s), []);
  const [kind, setKind] = useState<"method" | "task" | "dataset">("method");
  const trends = useAsync((s) => api.trends(kind, s), [kind]);
  const [minPapers, setMinPapers] = useState(5);
  const shown = useMemo(() => (trends.data ?? []).filter((t) => t.total >= minPapers), [trends.data, minPapers]);

  if (state.error) return <ErrorNote title="Could not load the landscape" message={state.error.message.replace(/^\d+: /, "")} action={<Button variant="outline" size="sm" onClick={state.reload}>Try again</Button>} />;
  if (!state.data) return <div className="space-y-3" aria-busy="true"><Skeleton className="h-48" /><Skeleton className="h-64" /></div>;
  const land = state.data;
  const total = Object.values(land.papers_per_year).reduce((a, b) => a + b, 0);

  return (
    <motion.section variants={stagger} initial="hidden" animate="show" aria-label="Landscape" className="space-y-8">
      <motion.header variants={fadeUp}>
        <h2 className="text-xl font-semibold tracking-tight">Landscape</h2>
        <p className="text-sm text-muted">How the analyzed corpus is spread over time, clusters and research elements. Counts are papers in this corpus, not the whole literature.</p>
      </motion.header>

      <motion.section variants={fadeUp} className="rounded-2xl border border-border bg-card p-4">
        <h3 className="mb-2 text-sm font-semibold tracking-wide text-muted uppercase">Papers per year <Mono className="ml-2 text-foreground normal-case">{total.toLocaleString()} with a year</Mono></h3>
        <YearBars perYear={land.papers_per_year} />
      </motion.section>

      <motion.section variants={fadeUp} className="space-y-3">
        <h3 className="text-sm font-semibold tracking-wide text-muted uppercase">Clusters</h3>
        {clusters.error ? <ErrorNote title="Clusters unavailable" message={clusters.error.message.replace(/^\d+: /, "")} /> : !clusters.data ? <Skeleton className="h-40" /> : (
          <>
            <p className="text-xs text-muted">
              HDBSCAN on SPECTER2 embeddings (PCA {clusters.data.pca_dims ?? "none"}, min cluster size {clusters.data.min_cluster_size}). {clusters.data.n_noise.toLocaleString()} of {clusters.data.n_papers.toLocaleString()} papers belong to no cluster.
            </p>
            <div data-lenis-prevent className="overflow-x-auto rounded-2xl border border-border">
              <table className="w-full min-w-[520px] text-sm">
                <thead className="bg-hover text-left text-xs text-muted uppercase"><tr><th className="px-3 py-2">Cluster</th><th className="px-3 py-2">Papers</th><th className="px-3 py-2">Years</th><th className="px-3 py-2">Most frequent elements</th></tr></thead>
                <tbody>
                  {clusters.data.clusters.map((c) => (
                    <tr key={c.cluster_id} className="border-t border-border">
                      <td className="px-3 py-2 font-mono">{c.cluster_id}</td>
                      <td className="px-3 py-2 font-mono">{c.size}</td>
                      <td className="px-3 py-2 font-mono">{c.year_min}–{c.year_max}</td>
                      <td className="px-3 py-2">{c.top_elements.length ? c.top_elements.slice(0, 4).map((e) => `${e.name} (${e.n_papers})`).join(", ") : <span className="text-muted">none extracted</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </motion.section>

      {land.weakly_connected_cluster_pairs.length > 0 ? (
        <motion.section variants={fadeUp} className="space-y-3" aria-label="Weakly connected cluster pairs">
          <h3 className="text-sm font-semibold tracking-wide text-muted uppercase">Weakly connected cluster pairs</h3>
          <p className="text-xs text-muted">
            Clusters that are close in meaning but whose papers rarely cite each other. A signal for human review, not proof that the
            two areas are unconnected: the corpus is small and citations outside it are not counted.
          </p>
          <div data-lenis-prevent className="overflow-x-auto rounded-2xl border border-border">
            <table className="w-full min-w-[440px] text-sm">
              <thead className="bg-hover text-left text-xs text-muted uppercase">
                <tr><th className="px-3 py-2">Clusters</th><th className="px-3 py-2">Similarity</th><th className="px-3 py-2">Cross-citations</th></tr>
              </thead>
              <tbody>
                {land.weakly_connected_cluster_pairs.map((p) => (
                  <tr key={p.a + "-" + p.b} className="border-t border-border">
                    <td className="px-3 py-2 font-mono">{p.a} ↔ {p.b}</td>
                    <td className="px-3 py-2 font-mono">{p.semantic_similarity.toFixed(3)}</td>
                    <td className="px-3 py-2 font-mono">{p.cross_citations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.section>
      ) : null}

      <motion.section variants={fadeUp} className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h3 className="text-sm font-semibold tracking-wide text-muted uppercase">Temporal evolution</h3>
          <label className="flex items-center gap-3 text-xs text-muted">
            Hide elements with fewer than <Mono className="text-foreground">{minPapers}</Mono> papers
            <Slider className="w-32" min={1} max={30} step={1} value={[minPapers]} onValueChange={([v]) => setMinPapers(v ?? 1)} aria-label="Minimum papers" />
          </label>
        </div>
        <Tabs value={kind} onValueChange={(v) => setKind(v as typeof kind)}>
          <TabsList aria-label="Element type">
            {(["method", "task", "dataset"] as const).map((k) => <TabsTrigger key={k} value={k}><span className="size-2 rounded-full" style={{ background: KIND_COLORS[k] }} />{k[0]?.toUpperCase() + k.slice(1)}s</TabsTrigger>)}
          </TabsList>
          {(["method", "task", "dataset"] as const).map((k) => (
            <TabsContent key={k} value={k}>
              {trends.error ? <ErrorNote title="Trends unavailable" message={trends.error.message.replace(/^\d+: /, "")} /> : trends.loading ? <Skeleton className="h-40" /> : (
                <div className="grid gap-5 md:grid-cols-2">
                  <div><h4 className="mb-2 text-sm font-medium">Emerging <Badge className="border-border bg-hover font-mono">{shown.filter((t) => t.label === "emerging").length}</Badge></h4><TrendList items={shown.filter((t) => t.label === "emerging")} empty="None at this threshold." /></div>
                  <div><h4 className="mb-2 text-sm font-medium">Declining <Badge className="border-border bg-hover font-mono">{shown.filter((t) => t.label === "declining").length}</Badge></h4><TrendList items={shown.filter((t) => t.label === "declining")} empty="None at this threshold." /></div>
                </div>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </motion.section>

      <motion.section variants={fadeUp} className="space-y-3">
        <h3 className="text-sm font-semibold tracking-wide text-muted uppercase">Bridge papers</h3>
        <p className="text-xs text-muted">Papers whose citation links reach several clusters. Many are foundational papers that clustering left in no cluster.</p>
        <ul className="space-y-1.5 p-0">
          {land.bridge_papers.slice(0, 10).map((b) => (
            <li key={b.paper_id} className="flex list-none items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2 text-sm">
              <span className="flex items-center gap-2"><IdBadge id={b.paper_id} /><span className="text-xs text-muted">{b.own_cluster === -1 ? "no cluster" : `cluster ${b.own_cluster}`} → clusters {b.linked_clusters.join(", ")}</span></span>
              <Button size="sm" variant="ghost" onClick={() => onOpenGraph(b.paper_id)}><Network className="size-3.5" /> Graph</Button>
            </li>
          ))}
        </ul>
      </motion.section>
    </motion.section>
  );
}
