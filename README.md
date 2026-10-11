# learnings-brain

## Project background
A 'second brain' to store information and learnings about data and AI
from work, studies, and self-learning. The objective is to create a lasting 
'single source of truth' for everything I've learned, which
can be easily retrieved through a chatbot.

The architecture is inspired by Sean's AI Stories' YouTube video about
AI Agent Harnesses and Loop Engineering (https://www.youtube.com/watch?v=GrNbuWWJYiI)
with tweaks made to incorporate recursive chunking, hybrid retrieval (vector and keyword), 
functionality for flagging contradictions and superceeding outdated information, and
evaluation using  (https://deepeval.com/docs/introduction).

This second brain differs from the typical ones in that it's designed to
run on a Cloudflare vector database, not an Obsidian-based second brain that is
stored locally and houses information in .md files (which this second brain was
originally built using). Learnings are still written as .md files, but they are
added through `git push`, never through the chatbot itself.

## Tech stack
Python, TypeScript, Cloudflare (Workers, D1, Vectorize, Workers AI), GitHub
(Pages and Actions), Gemini, LangChain, DeepEval

## Architecture

This second brain stores learning notes in a database, and uses RAG
(retrieval-augmented generation) to retrieve the most relevant information pertaining
to the question it is asked.

**Where things are stored or executed by**

| What | Where |
|---|---|
| Learning notes (single source of truth) | `learnings` folder in `.md` format |
| Chat page | `docs/`, served by GitHub Pages |
| Chatbot | A Cloudflare Worker in `brain-worker/` |
| Learning notes (episodes), facts| Cloudflare D1 tables |
| Vectors (chunks and facts) | Cloudflare Vectorize (`brain-episodes` and `brain-facts`) |
| Embedding and reranking function | Cloudflare Workers AI |
| Ingestion | GitHub Action (with `ingest/`) |
| Answers to questions, context sentences for chunks, fact summaries | Google Gemini LLM |

Data stored in D1 and Vectorize are derived from the markdown notes, so they can always be
rebuilt from `learnings/` if needed.

**Read and write access.** The chatbot can only answer questions (`POST /ask`)
and has no write function, so learnings cannot be added through the chat.
Learnings can only be added to the second brain using `git push` by me. Secrets are
encyrpted on GitHub, and the repo doesn't allow pull requests.

**Three memory types of the second brain**:

- **Procedural**: `brain-worker/skills.md`, fixed instructions for how the second brain 
  should respond to questions.
- **Episodic**: dated and chunked from learning notes. Each learning note gets a row in the D1 table 
  and is split into overlapping chunks (cut at markdown headings, with a recursive splitter used 
  for long sections at ~1,200 characters with 150 characters of overlap) so a long note
  isn't silently truncated by the embedding model's input limit, and a question can match one specific
  passage instead of a  whole learning note. Each passage/chunk is stored as a vector in `brain-episodes` and as a
  row in a D1 full-text table (`chunks_fts`, SQLite FTS5) for keyword search.
- **Semantic**: durable, standalone facts distilled from the learning notes, each with
  an optional topic tag, stored in D1's `facts` table plus the `brain-facts` index.

## Write path: how a learning note is ingested

```
learnings/*.md --git push to main branch --> ingested using GitHub Action
                (daily run at 20 00 UTC or manually)
  |
  v
1. Sync (affects new, edited, or deleted notes only)
   - Chunk at headings
   - Gemini writes a context sentence for each chunk
   - Workers AI embeds context and the chunk
   - Stored in: Vectorize `brain-episodes` (vectors)
                 D1 `chunks_fts` (keyword index)
                 D1 `entries` (the full note)
  |
  v
2. Consolidate (once 5 notes are pending or on the daily run)
   - Gemini reads the pending notes with the most similar existing facts
   - Add/update/supersede/flag contradictions
   - stored in D1 `facts` and Vectorize `brain-facts`
   - Contradictions stored in D1 `review_queue`
```

**1. Sync** (runs on every push that invovled `learnings/**`). `sync.py` compares the notes
in the repo with D1 by content hash, and only affetcs what has actually changed. A new or edited 
note is chunked and then, before embedding, one Gemini call writes a short context sentence for every chunk 
(what it's about and where it sits in the note), prepended to that chunk's text.
This is in line with Anthropic's Contextual Retrieval method (https://www.anthropic.com/engineering/contextual-retrieval), 
where a passage/chunk retrieved in isolation still carries information that a lone heading wouldn't.
The call to generate context sentences is retried up to three times on transient errors, with the 
fall back being 'title - heading' if all three tries fail. The context sentences and contextualised chunks are embedded and 
stored as vectors, and are also written to the keyword table which is used for the contextual BM25 portion of retrieval.
A deleted note is removed from D1 and Vectorize. The chunking settings are versioned per note, 
so changing them re-indexes every note without re-running consolidation, and a note in which indexing fails halfway 
is marked as stale and retried on the next ingestion run.

**2. Consolidate** (run after sync, with threshold gate). Once 5 notes are pending to be
ingested or on the daily run, Gemini (summariser) reads the pending notes alongside existing facts 
most similar to them (using cosine similarity) and runs `add`, `update`,`supersede` or `flag` operations, 
merging into semantic memory instead ingesting duplicates. A note that contradicts an existing 
fact is written to a review queue. A lock stops two runs from consolidating at the same time.

## Read path: how a question gets answered

```
chat page (docs/) --POST /ask--> Cloudflare Worker
  - Guardrails: maximum 5 questions per 60 seconds per visitor
                          question <= 500 characters
  - Embed: embedding questions (Cloudflare Workers AI)
  - Facts: vector search on `brain-facts`: top 8 with cosine similarity score 
            above 0.45 are retrieved
  - Episodes:
       - Vector keyword (BM25) search: top 25 with cosine similarity score above 0.45. Both searches
          run simultaneously
       - Merge by rank (reciprocal rank fusion). Keep 30 chunks.
       - Rerank with a cross-encoder, keep at most 8 with scores >= 0.02
  - Prompt: consists of skills.md, facts, chunks, the 3 newest notes, question
  - Gemini: answers only from the prompt (or says it doesn't know if no related episodes/facts are
            retrieved)
  - Reply: the answer plus Sources (facts and passages that matched/related to the question)
```

- **Guardrails**: Each visitor is identified by IP, and can only ask 5 questions every 60 seconds 
  (using Cloudflare's Workers Rate Limiting). Also, questions are capped at 500 characters. 
  Both are checked before any operations are run.
  **Embed**: Cloudflare Workers AI embeds the questions for matching with facts and episodes by 
  cosine similarity.
- **Facts**: A vector search is executed. Vectorize returns ids and facts' text comes
  from Cloudflare D1.
- **Episodes**: Three step processs to retrieve episodes. First, vector and keyword (BM25) 
  search run side by side, vector search finds chunks with a similar meaning, and keyword 
  search finds exact terms (e.g., function and variable names) that vector search can miss. 
  Second, the two lists of chunks and keywords are merged by rank (by cosine similarity) into 
  a shortlist of at most 30 chunks and keywords. Third, a reranker (`bge-reranker-base`, a 
  cross-encoder that reads the question and each chunks's actual text together) keeps at most 8 
  chunks, dropping any it scores below 0.02.
- **Prompt**: The instructions, facts, the matched chunks, and
  the first 600 characters of the 3 newest notes, and the question are prepended into
  a prompt for Gemini. The newest notes are never listed under Sources unless they also
  matched.
- **Gemini**: Only answers from what information it has access to, nothing else. Gemini will 
  refuse to answer if no information relevant to the question was found. Gemini's reply contains 
  citations to the specific facts and chunks it drew answers from. Transient errors for Gemini calls 
  are retried up to three times. An error message is shown if Gemini's free-tier call quota is reached. 
  The Gemini chatbot has no memory of earlier questions in the conversation.

If something goes wrong, the request degrades instead of failing completely. For example, if the
reranker call fails, episode retrieval falls back to the vector matches in cosine similarity rank 
order. If keyword search fails it carries on with vector search only.

## Evaluation

`eval/` feeds a set of questions against the deployed chatbot and scores the answers with 
DeepEval on answer relevancy, faithfulness, contextual precision/recall, using Gemini as the 
judge (LLM-as-a-judge). Can only be run manually.

Currently, no testing has been done yet, and no questions and answers are present in 
`eval/dataset.py`.

As each question-and-answer case calls Gemini once during evaluation, `run_eval.py`
keeps DeepEval's evaluation deliberately throttled to save Gemini calls, and results are cached. 

## Limitations

- Changing chunking settings requires re-embedding every note. Chunking settings
  are not optimised, and only configured as a starting point currently.
- Additionally, the retrieval settings (candidate counts, `MIN_SCORE=0.45`, rerank floor 
  `EPISODE_RERANK_MIN_SCORE=0.02`) are also a starting point.
- The chatbot runs on Gemini's free tier, limiting asks and is susceptible to transient errors 
  on Gemini's side.
- Deleting a note removes it from episodic memory, but facts already
  distilled from it are not retroactively removed, and each fact records every
  note in its batch as a source rather than the specific one it came from.
- The consolidation steps sends all pending notes to Gemini in one call, so having many and/or large 
  files pending consolidation may end up larger than the context window.
