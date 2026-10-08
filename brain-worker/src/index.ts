/**
 * Read-only second-brain Worker.
 *
 * POST /ask { "question": string } -> { "answer": string, "citations": [...] }
 *
 * There is no write endpoint. Learnings are ingested only by the GitHub
 * Action in ../.github/workflows/ingest.yml, which runs on pushes to
 * learnings/** on main. See ../README.md.
 */
import skills from "../skills.md";
import { buildFtsQuery, fuseByRank } from "./lexical";

export interface Env {
  AI: Ai;
  DB: D1Database;
  FACTS_INDEX: VectorizeIndex;
  EPISODES_INDEX: VectorizeIndex;
  ASK_LIMITER: RateLimit;
  ALLOWED_ORIGIN: string;
  MODEL: string;
  EMBED_MODEL: string;
  GEMINI_API_KEY: string;
}

const TOP_K = 8; // Retrive top k number of facts (dsitilled notes) that have highest cosine similarity with the question

const MIN_SCORE = 0.45; // Configure a cosine similarity floor; facts with a score below the floor are excluded from retrieval

const EPISODE_CANDIDATE_K = 25; // Retrieve top k number of episode chunks that have the highest cosine similarity with the question for reranking

const KEYWORD_CANDIDATE_K = 25; // Retrieve top k number of episode chunks that best match the question's words (BM25 keyword search)

const RERANK_POOL = 30; // Maximum number of chunks, merged from vector and keyword search, sent to the reranker

const EPISODE_FINAL_K = 8; // Maximum number of episode chunks kept for the response

const EPISODE_RERANK_MIN_SCORE = 0.02; // Configure a reranker score floor; episodes scoring below it will be excluded from the response

const RERANK_MODEL = "@cf/baai/bge-reranker-base"; // Configure the Cloudflare reranker model

const MAX_QUESTION_CHARS = 500; //Configure maximum characters for questions. 

const MAX_OUTPUT_TOKENS = 400; // Configure maximum output tokens for faster responses. 

const RECENT_CHARS = 600;

const DEV_ORIGIN_RE = /^https?:\/\/localhost(:\d+)?$/; // Match localhost with a port for local testing. 

function allowedOrigin(env: Env, requestOrigin: string | null): string {
  if (requestOrigin === env.ALLOWED_ORIGIN || (requestOrigin && DEV_ORIGIN_RE.test(requestOrigin))) {
    return requestOrigin!;
  }
  return env.ALLOWED_ORIGIN;
}

function corsHeaders(origin: string): HeadersInit {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

function json(body: unknown, status: number, origin: string): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
  });
}

async function embed(env: Env, text: string): Promise<number[]> {
  const res = await env.AI.run(env.EMBED_MODEL as any, { text: [text] });
  return (res as any).data[0] as number[];
}

interface Fact {
  id: string;
  text: string;
  topic: string;
}

interface Episode {
  id: number;
  created_at: string;
  text: string;
}

interface EpisodeChunk {
  id: string; // "<entry id>:<chunk number>", the same id in Vectorize and the keyword table
  entryId: number;
  date: string;
  title: string;
  heading: string;
  text: string;
  cosine?: number; // only set for chunks found by vector search
}

// Vectorize returns fact ids; fetch facts from D1.
async function searchFacts(env: Env, vector: number[]): Promise<Fact[]> {
  const result = await env.FACTS_INDEX.query(vector, { topK: TOP_K, returnMetadata: "none" });
  const ids = result.matches.filter((m) => m.score >= MIN_SCORE).map((m) => m.id);
  if (!ids.length) return [];
  const placeholders = ids.map(() => "?").join(",");
  const rows = await env.DB.prepare(
    `SELECT id, text, topic FROM facts WHERE status = 'active' AND id IN (${placeholders})`
  )
    .bind(...ids)
    .all<Fact>();
  return rows.results ?? [];
}

// Each vector from an episode is one chunk of a note; no D1 lookup for the actual episode text is needed because the chunk text and heading are stored in the vector's metadata.
async function candidateEpisodes(env: Env, vector: number[]): Promise<EpisodeChunk[]> {
  const result = await env.EPISODES_INDEX.query(vector, { topK: EPISODE_CANDIDATE_K, returnMetadata: "all" });
  return result.matches.flatMap((m) => {
    if (m.score < MIN_SCORE) return [];
    const md = (m.metadata ?? {}) as Record<string, string | number>;
    if (!md.text) return [];
    return [
      {
        id: m.id,
        entryId: Number(md.entry_id),
        date: String(md.created_at ?? ""),
        title: String(md.title ?? ""),
        heading: String(md.heading ?? ""),
        text: String(md.text),
        cosine: m.score,
      },
    ];
  });
}

// Keyword (BM25) search over the chunks table in D1. Catches exact terms (function names, acronyms) that vector search can miss.
// If the table is missing or the query fails, returns nothing so vector search still answers on its own.
async function keywordEpisodes(env: Env, question: string): Promise<EpisodeChunk[]> {
  const match = buildFtsQuery(question);
  if (!match) return [];
  try {
    const rows = await env.DB.prepare(
      "SELECT id, entry_id, created_at, title, heading, text FROM chunks_fts WHERE chunks_fts MATCH ? " +
        "ORDER BY bm25(chunks_fts, 0, 0, 0, 1.0, 2.0, 1.0, 1.0) LIMIT ?"
    )
      .bind(match, KEYWORD_CANDIDATE_K)
      .all<{ id: string; entry_id: number; created_at: string; title: string; heading: string; text: string }>();
    return (rows.results ?? []).map((r) => ({
      id: r.id,
      entryId: Number(r.entry_id),
      date: String(r.created_at ?? ""),
      title: r.title,
      heading: r.heading,
      text: r.text,
    }));
  } catch (e) {
    console.error("keyword search failed, using vector search only:", (e as Error).message);
    return [];
  }
}

// Cosine similarity compares the question and each chunk. The reranker reads the question and each candidate vector's actual text together in one pass, so it judges relevance directly.
// The reranker scores below EPISODE_RERANK_MIN_SCORE are dropped.
// Falls back to the cosine ordering on any failure
async function rerankEpisodes(env: Env, question: string, candidates: EpisodeChunk[]): Promise<EpisodeChunk[]> {
  if (!candidates.length) return candidates;
  try {
    const res = await env.AI.run(RERANK_MODEL as any, {
      query: question,
      contexts: candidates.map((c) => ({ text: c.text })),
      top_k: EPISODE_FINAL_K,
    });

    const ranked = (res as any).response as { id: number; score: number }[];
    return ranked
      .filter((r) => r.score >= EPISODE_RERANK_MIN_SCORE)
      .map((r) => candidates[r.id])
      .filter((c): c is EpisodeChunk => c !== undefined);
  } catch (e) {
    // Only chunks that passed the cosine floor are kept, so keyword-only matches can't slip in unchecked.
    console.error("rerank failed, falling back to cosine order:", (e as Error).message);
    return candidates.filter((c) => c.cosine !== undefined).slice(0, EPISODE_FINAL_K);
  }
}

// Vector search and keyword search run side by side, their results are merged by rank, and the reranker picks the best.
async function searchEpisodes(env: Env, question: string, vector: number[]): Promise<EpisodeChunk[]> {
  const [semantic, keyword] = await Promise.all([candidateEpisodes(env, vector), keywordEpisodes(env, question)]);
  const candidates = fuseByRank([semantic, keyword]).slice(0, RERANK_POOL);
  return rerankEpisodes(env, question, candidates);
}

async function recentEpisodes(env: Env, n: number): Promise<Episode[]> {
  const rows = await env.DB.prepare(
    "SELECT id, created_at, text FROM entries ORDER BY id DESC LIMIT ?"
  )
    .bind(n)
    .all<Episode>();
  return rows.results ?? [];
}

class GeminiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function askGemini(env: Env, prompt: string): Promise<string> {
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${env.MODEL}:generateContent` +
    `?key=${env.GEMINI_API_KEY}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0.2,
        maxOutputTokens: MAX_OUTPUT_TOKENS,
        thinkingConfig: { thinkingBudget: 0 },
      },
    }),
  });
  if (!res.ok) throw new GeminiError(res.status, await res.text());
  const data = (await res.json()) as any;
  const parts = data.candidates?.[0]?.content?.parts ?? [];
  const text = parts.map((p: any) => p.text ?? "").join("").trim();
  if (!text) {
    console.error("empty Gemini answer, finishReason:", data.candidates?.[0]?.finishReason, "parts:", parts.length);
  }
  return text;
}

const MAX_ATTEMPTS = 3; // total tries before giving up when encountering transient errors

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Retries askGemini on transient errors, exceot 429 (rate-limit) errors
async function askGeminiWithRetry(env: Env, prompt: string): Promise<string> {
  for (let attempt = 1; ; attempt++) {
    try {
      return await askGemini(env, prompt);
    } catch (e) {
      if (e instanceof GeminiError && e.status === 429) throw e;
      if (attempt >= MAX_ATTEMPTS) throw e;
      console.error(`askGemini attempt ${attempt} failed, retrying:`, (e as Error).message);
      await sleep(500 * attempt);
    }
  }
}

function bulletList(items: string[]): string {
  return items.length ? items.map((i) => `- ${i}`).join("\n") : "(none)";
}

async function handleAsk(request: Request, env: Env, origin: string): Promise<Response> {
  // Limit each visitor (by IP) to 5 questions per 60 seconds (set in wrangler.toml). Checked first so a
  // flood is rejected before any embedding, search or Gemini work is done.
  const visitor = request.headers.get("CF-Connecting-IP") ?? "unknown";
  const { success } = await env.ASK_LIMITER.limit({ key: visitor });
  if (!success) {
    return json({ error: "You're asking too quickly. Please wait a minute and try again." }, 429, origin);
  }

  let body: { question?: unknown };
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400, origin);
  }
  const question = typeof body.question === "string" ? body.question.trim() : "";
  if (!question) return json({ error: "a Question is required" }, 400, origin);
  if (question.length > MAX_QUESTION_CHARS) {
    return json({ error: `The question must be under ${MAX_QUESTION_CHARS} characterss` }, 400, origin);
  }

  // recentEpisodes don't need the embedding.
  const [vector, recent] = await Promise.all([embed(env, question), recentEpisodes(env, 3)]);
  const [facts, chunks] = await Promise.all([searchFacts(env, vector), searchEpisodes(env, question, vector)]);

  // A recent note is redundant if one of its passages is already matched, and is capped so a long note cannot bloat the promp to Gemini
  const matchedNotes = new Set(chunks.map((c) => c.entryId));
  const matchedLines = chunks.map((c) => `[${c.date} · ${c.title}${c.heading ? ` § ${c.heading}` : ""}] ${c.text}`);
  const recentLines = recent
    .filter((e) => !matchedNotes.has(e.id))
    .map((e) => `[${e.created_at.slice(0, 10)}] ${e.text.slice(0, RECENT_CHARS)}`);

  // Gemini receives recent notes and matched responses, but only responses that genuinely match the question are shown as 'Sources'
  const episodeLines = [...matchedLines, ...recentLines];

  const factLines = facts.map((f) => `(${f.id}) ${f.text}${f.topic ? ` [${f.topic}]` : ""}`);

  const prompt =
    `${skills}\n\n` +
    `## Facts\n${bulletList(factLines)}\n\n` +
    `## Related notes\n${bulletList(episodeLines)}\n\n` +
    `## Question\n${question}`;

  let answer: string;
  try {
    answer = await askGeminiWithRetry(env, prompt);
  } catch (e) {
    if (e instanceof GeminiError && e.status === 429) {
      return json(
        { error: "We've hit Gemini's free tier limit for the chatbot, try again tomorrow!" },
        429,
        origin
      );
    }
    console.error(`askGemini failed after ${MAX_ATTEMPTS} attempts:`, (e as Error).message);
    return json({ error: "Something went wrong generating an answer. Please try again later." }, 502, origin);
  }

  return json(
    {
      answer,
      citations: {
        facts: facts.map((f) => ({ id: f.id, text: f.text, topic: f.topic })),
        notes: matchedLines,
      },
    },
    200,
    origin
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = allowedOrigin(env, request.headers.get("Origin"));
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(origin) });
    }
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/ask") {
      return handleAsk(request, env, origin);
    }
    return json({ error: "Not found" }, 404, origin);
  },
};
