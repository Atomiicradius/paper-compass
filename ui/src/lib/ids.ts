/**
 * Paper ids. The API takes plain OpenAlex ids (W123...). The graph endpoint labels its nodes "Paper:W123", so an
 * id copied from the graph (or from a pasted OpenAlex URL) is reduced to the plain id before any API call.
 */
const URL_PREFIX = "https://openalex.org/";

export function normalizePaperId(raw: string | null | undefined): string {
  let s = (raw ?? "").trim();
  if (s.toLowerCase().startsWith(URL_PREFIX)) s = s.slice(URL_PREFIX.length);
  if (s.toLowerCase().startsWith("paper:")) s = s.slice("paper:".length);
  return s.trim();
}

/** Graph node ids look like "Paper:W123", "Method:3", "Author:A55". */
export function nodePaperId(nodeId: string): string {
  return normalizePaperId(nodeId);
}
