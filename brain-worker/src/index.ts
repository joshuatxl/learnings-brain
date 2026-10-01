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

export interface Env {
  AI: Ai;
  DB: D1Database;
  FACTS_INDEX: VectorizeIndex;
  EPISODES_INDEX: VectorizeIndex;
  ALLOWED_ORIGIN: string;
  MODEL: string;
  EMBED_MODEL: string;
  GEMINI_API_KEY: string;
}

const TOP_K = 5;
// Cosine similarity floor for a Vectorize match to count as relevant at all --
// without this, topK always returns its 5 "closest" results even when none
// are actually related to the question. Calibrated against real matches
// (0.617-0.768) on this corpus; conservative enough not to cut genuine hits.
const MIN_SCORE = 0.45;
const MAX_QUESTION_CHARS = 500;
const MAX_OUTPUT_TOKENS = 400; // shorter cap = Gemini finishes generating sooner
const RECENT_CHARS = 600; // most of a recent (not-matched) note that goes into the prompt

// The deployed site is the only origin allowed in production. localhost is
// also allowed so the page can be tested before it's published — this only
// affects which origins a browser lets read the response; there's no write
// path or auth for it to weaken.
const DEV_ORIGIN_RE = /^https?:\/\/localhost(:\d+)?$/;

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

/** One matching passage (chunk) of a note. */
interface EpisodeChunk {
  entryId: number;
  date: string;
  title: string;
  heading: string;
  text: string;
}

/** Vectorize returns fact ids only; fetch the facts themselves from D1. */
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

/** Each episodic vector is one chunk of a note, and its text travels in the
 * vector's metadata, so no D1 lookup is needed. */
async function searchEpisodes(env: Env, vector: number[]): Promise<EpisodeChunk[]> {
  const result = await env.EPISODES_INDEX.query(vector, { topK: TOP_K, returnMetadata: "all" });
  return result.matches.flatMap((m) => {
    if (m.score < MIN_SCORE) return [];
    const md = (m.metadata ?? {}) as Record<string, string | number>;
    if (!md.text) return [];
    return [
      {
        entryId: Number(md.entry_id),
        date: String(md.created_at ?? ""),
        title: String(md.title ?? ""),
        heading: String(md.heading ?? ""),
        text: String(md.text),
      },
    ];
  });
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

const MAX_ATTEMPTS = 3; // total tries before giving up, e.g. for a transient 503 "high demand"

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Retries askGemini on transient failures, up to MAX_ATTEMPTS total. A 429
 * (rate limit) is never retried -- it won't clear within one request, and
 * retrying would only spend more of an already-exhausted quota. */
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

  // recentEpisodes doesn't need the embedding, so it can run alongside it
  // instead of waiting for it — the two vector searches do need the
  // embedding and so start only once it resolves.
  const [vector, recent] = await Promise.all([embed(env, question), recentEpisodes(env, 3)]);
  const [facts, chunks] = await Promise.all([searchFacts(env, vector), searchEpisodes(env, vector)]);

  // A recent note is redundant if one of its passages already matched, and is
  // capped so a long note can't bloat the prompt (a longer prompt is slower).
  const matchedNotes = new Set(chunks.map((c) => c.entryId));
  const matchedLines = chunks.map((c) => `[${c.date} · ${c.title}${c.heading ? ` § ${c.heading}` : ""}] ${c.text}`);
  const recentLines = recent
    .filter((e) => !matchedNotes.has(e.id))
    .map((e) => `[${e.created_at.slice(0, 10)}] ${e.text.slice(0, RECENT_CHARS)}`);
  // Gemini sees both -- recency is genuinely useful context -- but only
  // genuine similarity matches are shown as "Sources", so citations never
  // list a note just because it happens to be new and unrelated.
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
