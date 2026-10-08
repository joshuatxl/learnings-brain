// Helpers for keyword (BM25) search. Kept free of Worker bindings so they can be tested on their own.

// Common words that match almost every chunk and say nothing about the question.
const STOPWORDS = new Set([
  "a", "about", "after", "all", "also", "an", "and", "any", "are", "as", "at", "be", "been", "but", "by", "can",
  "did", "do", "does", "for", "from", "get", "had", "has", "have", "how", "i", "if", "in", "into", "is", "it",
  "its", "me", "my", "no", "not", "of", "on", "or", "so", "than", "that", "the", "their", "then", "there",
  "these", "they", "this", "to", "was", "we", "were", "what", "when", "where", "which", "who", "why", "will",
  "with", "would", "you", "your",
]);

const MAX_TERMS = 12;

// Turns a question into a safe FTS5 query: the meaningful words, each quoted so that characters FTS5 treats as
// syntax (- : * ( ) and so on) can't break the query, joined with OR so a chunk only needs to match some of them
// and BM25 ranks the ones matching more (and rarer) words higher. Returns null when nothing is left to search for.
export function buildFtsQuery(question: string): string | null {
  const words = question.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];
  const terms = [...new Set(words.filter((w) => w.length > 1 && !STOPWORDS.has(w)))].slice(0, MAX_TERMS);
  return terms.length ? terms.map((t) => `"${t}"`).join(" OR ") : null;
}

// Reciprocal rank fusion: merges several ranked lists into one by summing 1 / (k + rank) for each item, so
// anything ranked well in either list rises and an item found by both rises most. Uses ranks rather than scores
// because cosine similarity and BM25 are on unrelated scales. Items are matched by id; the first list's copy wins.
export function fuseByRank<T extends { id: string }>(lists: T[][], k = 60): T[] {
  const score = new Map<string, number>();
  const item = new Map<string, T>();
  for (const list of lists) {
    list.forEach((entry, rank) => {
      score.set(entry.id, (score.get(entry.id) ?? 0) + 1 / (k + rank + 1));
      if (!item.has(entry.id)) item.set(entry.id, entry);
    });
  }
  return [...item.values()].sort((a, b) => score.get(b.id)! - score.get(a.id)!);
}
