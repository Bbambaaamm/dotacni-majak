import termsPayload from "../../../data/ontology/v1/terms.json";
import synonymsPayload from "../../../data/ontology/v1/synonyms.json";
import edgesPayload from "../../../data/ontology/v1/edges.json";

interface TermItem {
  code: string;
  name: string;
  active?: boolean;
}

interface SynonymItem {
  term: string;
  text: string;
  weight?: number;
}

interface EdgeItem {
  from: string;
  to: string;
  relation: string;
  weight?: number;
}

function normalize(value: string): string {
  return value
    .toLocaleLowerCase("cs-CZ")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

const terms = (termsPayload.terms as TermItem[]).filter((item) => item.active !== false);
const names = new Map(terms.map((item) => [item.code, item.name]));
const synonyms = synonymsPayload.synonyms as SynonymItem[];
const edges = edgesPayload.edges as EdgeItem[];

const phrases = [
  ...terms.map((item) => ({
    term: item.code,
    normalized: normalize(item.name),
    weight: 1,
  })),
  ...synonyms.map((item) => ({
    term: item.term,
    normalized: normalize(item.text),
    weight: item.weight ?? 1,
  })),
].sort((a, b) => b.normalized.length - a.normalized.length);

const outgoing = new Map<string, EdgeItem[]>();
for (const edge of edges) {
  const list = outgoing.get(edge.from) ?? [];
  list.push(edge);
  outgoing.set(edge.from, list);
}

export function expandIntentTerms(intent: string): string[] {
  const normalizedIntent = ` ${normalize(intent)} `;
  const scores = new Map<string, number>();
  const queue: Array<{ term: string; score: number; depth: number }> = [];

  for (const phrase of phrases) {
    if (!phrase.normalized) continue;
    if (!normalizedIntent.includes(` ${phrase.normalized} `)) continue;
    const previous = scores.get(phrase.term) ?? 0;
    if (phrase.weight > previous) {
      scores.set(phrase.term, phrase.weight);
      queue.push({ term: phrase.term, score: phrase.weight, depth: 0 });
    }
  }

  while (queue.length) {
    const current = queue.shift()!;
    if (current.depth >= 3) continue;
    for (const edge of outgoing.get(current.term) ?? []) {
      if (!["BROADER", "RELATED", "PART_OF"].includes(edge.relation)) continue;
      const score = current.score * (edge.weight ?? 1) * 0.95;
      if (score < 0.5) continue;
      if ((scores.get(edge.to) ?? 0) >= score) continue;
      scores.set(edge.to, score);
      queue.push({ term: edge.to, score, depth: current.depth + 1 });
    }
  }

  const resolvedCodes = [...scores.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([code]) => code);

  const output: string[] = [];
  for (const code of resolvedCodes) {
    const canonical = names.get(code);
    if (canonical) output.push(canonical);
    for (const synonym of synonyms) {
      if (synonym.term === code && (synonym.weight ?? 1) >= 0.75) {
        output.push(synonym.text);
      }
    }
  }

  return [...new Set(output)].slice(0, 24);
}
