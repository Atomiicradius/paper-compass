/**
 * Types for the FastAPI backend. The Opportunity shape is the contract in context/data-and-contracts.md
 * section 4; the other shapes follow api/schemas.py and api/api-shapes-o10.md (provisional until O10 is agreed).
 * Paper ids are plain OpenAlex ids ("W3028876793"). The graph endpoint prefixes node ids ("Paper:W...").
 */

export type ElementKind = "method" | "task" | "dataset" | "setting";

export interface Elements {
  method: string | null;
  task: string | null;
  dataset: string | null;
  setting: string | null;
}

export interface Signals {
  sparsity: number | null;
  semantic_compatibility: number | null;
  temporal_activity: number | null;
  graph_bridge_strength: number | null;
  method_compatibility: number | null;
}

export type EvidenceRole = "supports_A" | "supports_B" | "bridge" | "nearest_existing";

export interface Opportunity {
  opportunity_id: number;
  elements: Elements;
  corpus: { papers: number; cutoff_year: number };
  observed_count: number;
  expected_count: number;
  signals: Signals;
  confidence: number | null;
  score: number | null;
  weights_version: string | null;
  evidence: Record<EvidenceRole, string[]>;
}

export interface OpportunityList {
  total: number;
  items: Opportunity[];
  disclaimer: string;
}

/** POST /opportunities/{id}/explain */
export interface EvidencePaper {
  paper_id: string;
  title: string;
  year: number | null;
  venue: string | null;
  source_sentence: string | null;
  extractor: string | null;
  /** nearest_existing only */
  tier?: "exact" | "close";
  similarity?: number | null;
  uses?: string | null;
}

export interface PairElement {
  kind: ElementKind;
  id: number;
  name: string;
}

export interface Explanation {
  opportunity_id: number;
  evidence: {
    pair: { a: PairElement; b: PairElement };
    corpus: { cutoff_year: number; universe_size: number; n_a: number; n_b: number; observed: number; expected: number };
    yearly: { year: number; a: number; b: number; both: number }[];
    roles: Record<EvidenceRole, EvidencePaper[]>;
    limitations: string[];
  };
  summary: string;
  summary_source: "template" | "llm";
  summary_fallback_reason: string | null;
  citation_check: {
    ok: boolean;
    cited: string[];
    unknown: string[];
    uncited_markers_count: number;
    has_no_citations: boolean;
  };
  disclaimer: string;
}

export interface SearchHit {
  paper_id: string;
  title: string;
  year: number | null;
  venue: string | null;
  score: number;
  methods: string[];
  datasets: string[];
  tasks: string[];
  /** hybrid mode only: rank in the vector list and in the keyword list (null = not in that list) */
  vector_rank?: number | null;
  keyword_rank?: number | null;
}

export interface SearchRequest {
  query: string;
  top_k?: number;
  year_min?: number | null;
  year_max?: number | null;
  methods?: string[];
  datasets?: string[];
  tasks?: string[];
  match?: "same_experiment" | "any";
  mode?: "auto" | "vector" | "keyword" | "hybrid";
  collapse_same_title?: boolean;
}

export interface SearchResponse {
  query: string;
  mode: "vector" | "keyword" | "hybrid";
  score_type: "cosine_similarity" | "ts_rank" | "rrf_fused";
  model: string | null;
  note: string | null;
  results: SearchHit[];
}

export interface Paper {
  paper_id: string;
  title: string;
  year: number | null;
  abstract: string | null;
  doi: string | null;
  venue: string | null;
  authors: string[];
  topics: string[];
  methods: string[];
  datasets: string[];
  tasks: string[];
  cites: string[];
  cited_by: string[];
}

export type GraphLabel =
  | "Paper" | "Author" | "Venue" | "Institution" | "Method" | "Task" | "Dataset" | "Setting" | "Topic" | "Experiment" | "Result";

export interface GraphNode {
  id: string;
  label: GraphLabel;
  name: string | null;
  year: number | null;
}
export interface GraphEdge { source: string; target: string; type: string }
export interface PaperGraph {
  center: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** true when the paper has more neighbours than the limit allowed */
  truncated?: boolean;
  neighbors_total?: number;
}

export interface TrendItem {
  element_type: string;
  element_id: number;
  name: string;
  yearly: Record<string, number>;
  total: number;
  recent_share: number;
  growth: number;
  label: "emerging" | "declining" | "stable";
}

export interface ClusterSummary {
  cluster_id: number;
  size: number;
  year_min: number | null;
  year_max: number | null;
  top_elements: { name: string; n_papers: number }[];
  paper_ids: string[];
}
export interface Clusters {
  method: string;
  min_cluster_size: number;
  min_samples: number | null;
  pca_dims: number | null;
  n_papers: number;
  n_noise: number;
  clusters: ClusterSummary[];
}

/** Two clusters that are close in meaning but rarely cite each other (graph/bridges.py). */
export interface ClusterPair {
  a: number;
  b: number;
  cross_citations: number;
  citation_density: number;
  semantic_similarity: number;
  weakly_connected: boolean;
}

export interface Landscape {
  corpus: { papers: number; cutoff_year: number };
  papers_per_year: Record<string, number>;
  n_clusters: number;
  emerging: TrendItem[];
  declining: TrendItem[];
  weakly_connected_cluster_pairs: ClusterPair[];
  bridge_papers: { paper_id: string; own_cluster: number; linked_clusters: number[] }[];
  disclaimer: string;
}

export interface RelatedResponse {
  paper_id: string;
  score_type: string;
  model: string | null;
  results: SearchHit[];
}
