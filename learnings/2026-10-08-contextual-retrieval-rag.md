---
title: "Contextual Retrieval: prepending chunk context to cut RAG retrieval failures"
date: 2024-09-19
tags: [rag, contextual-retrieval, embeddings, bm25, reranking, prompt-caching, anthropic]
source: https://www.anthropic.com/engineering/contextual-retrieval
---

# Contextual Retrieval: prepending chunk context to cut RAG retrieval failures

Anthropic engineering post (September 2024) by Daniel Ford. Traditional RAG loses context when a document is split into chunks, so relevant chunks often fail to be retrieved. Contextual Retrieval has an LLM write a short piece of chunk-specific context and prepends it to each chunk before embedding and BM25 indexing, cutting top-20 retrieval failures by 49%, or 67% with reranking added.

## When to skip RAG: knowledge bases under 200,000 tokens

If the whole knowledge base is under 200,000 tokens (about 500 pages), put all of it in the prompt and do no retrieval at all.

Prompt caching makes this practical: the post cites latency reduced by more than 2x and cost by up to 90% for the cached portion.

Retrieval is only needed once the knowledge base is too large for that.

## Standard RAG pipeline: chunk, embed, similarity search

RAG (Retrieval-Augmented Generation) retrieves relevant information from a knowledge base and adds it to the prompt.

Preprocessing:

1. Split the corpus into chunks, usually no more than a few hundred tokens.
2. Convert each chunk to a vector embedding with an embedding model.
3. Store the embeddings in a vector database that supports semantic-similarity search.

Runtime:

1. Embed the user query.
2. Find the most semantically similar chunks.
3. Add those chunks to the prompt for the generative model.

Embeddings are numerical vectors that encode meaning, so semantically similar text lands close together.

## Hybrid retrieval: combining embeddings with BM25 via rank fusion

Embeddings capture meaning but can miss exact matches. BM25 covers that gap.

- **TF-IDF** (Term Frequency-Inverse Document Frequency): a weighting of how important a word is to a document relative to a collection.
- **BM25** (Best Matching 25): a lexical ranking function built on TF-IDF that scores exact word or phrase matches, adjusted for document length and term-frequency saturation.
- **Rank fusion:** merging the ranked lists from different retrievers into one list, with deduplication.

Pipeline:

1. Chunk the corpus.
2. Create TF-IDF encodings and semantic embeddings for the chunks.
3. Use BM25 to find the top chunks by exact match.
4. Use embeddings to find the top chunks by semantic similarity.
5. Merge and deduplicate with rank fusion.
6. Add the top-K chunks to the prompt.

Example: a query for error code "TS-999". Embeddings may return general error-code content and miss the exact code. BM25 finds the exact string.

## The context problem: chunks lose the document they came from

Splitting documents into small chunks makes retrieval efficient, but a chunk on its own can lack the context needed to retrieve or use it.

Example from the post:

- Question: what was the revenue growth for ACME Corp in Q2 2023?
- A relevant chunk from an SEC filing says only that the company's revenue grew by 3% over the previous quarter.
- The chunk names neither the company nor the period, so it is hard to match to the question and hard to use even if retrieved.

## Contextual Retrieval: Contextual Embeddings and Contextual BM25

The method prepends chunk-specific explanatory context to each chunk before indexing it in both retrievers:

- **Contextual Embeddings:** embeddings computed on the context-prepended chunk.
- **Contextual BM25:** a BM25 index built on the same context-prepended chunks.

ACME example after contextualising: the chunk is prefixed with a statement that it comes from an SEC filing on ACME Corp's Q2 2023 performance and that the previous quarter's revenue was $314 million. The original sentence about 3% growth follows unchanged.

Alternatives the authors tested and found weaker:

- Adding a generic document summary to each chunk: very limited gains.
- Summary-based indexing: low performance in their evaluation.

Hypothetical document embeddings are mentioned as a different prior approach.

## Context-generation prompt for Contextual Retrieval

Annotating millions of chunks by hand is impractical, so an LLM writes the context. The post used Claude 3 Haiku. The output is usually 50 to 100 tokens per chunk.

The prompt has two inputs and one instruction. The version below is paraphrased, not the article's exact wording, but the placeholder names are the article's:

```text
<document>
{{WHOLE_DOCUMENT}}
</document>

Here is the chunk to situate within the whole document:
<chunk>
{{CHUNK_CONTENT}}
</chunk>

Give a short, succinct context that situates this chunk within
the overall document, to improve search retrieval of the chunk.
Answer with only the context and nothing else.
```

The returned context is prepended to the chunk before embedding it and before building the BM25 index.

## Contextual Retrieval cost: $1.02 per million document tokens with prompt caching

Every chunk needs the whole document as input, which would be expensive if resent each time. Prompt caching fixes this: the document is loaded into the cache once and each per-chunk request reuses it.

The post's cost estimate:

- 800-token chunks.
- 8k-token documents.
- 50 tokens of instructions.
- 100 tokens of generated context per chunk.

Result: a one-time cost of $1.02 per million document tokens to generate the contextualised chunks, using Claude 3 Haiku pricing at the time.

## Contextual Retrieval results: top-20 failure rate from 5.7% to 1.9%

Metric: 1 minus recall@20, the share of relevant chunks not retrieved in the top 20. Lower is better. Recall@K is the share of relevant items found in the top K.

Top-20 retrieval failure rate, averaged across datasets:

- Baseline embeddings: 5.7%
- Contextual Embeddings: 3.7% (35% reduction)
- Contextual Embeddings + Contextual BM25: 2.9% (49% reduction)
- Contextual Embeddings + Contextual BM25 + reranking: 1.9% (67% reduction)

### Contextual Retrieval evaluation methodology

How the numbers were produced:

- Domains tested: codebases, fiction, arXiv papers, and science papers.
- Embedding models, retrieval strategies, and evaluation metrics were all varied.
- The headline charts use the best-performing embedding configuration, Gemini Text 004, and the top 20 chunks.
- Contextualising improved results for every embedding and source combination tested.
- Figures are averages across domains, so individual datasets vary.
- Appendix I has 1 minus recall@20 by dataset and configuration. Appendix II has recall@10, recall@5, and sample questions per dataset.

## Reranking: retrieve 150 candidates, keep the top 20

Reranking is a second scoring pass that reorders a larger candidate set by relevance to the query.

Pipeline used in the post:

1. Run initial retrieval for a broad candidate set (top 150).
2. Pass the candidates and the user query to a reranking model.
3. The reranker scores each chunk for relevance and importance. Keep the top 20.
4. Pass those chunks to the generative model.

The reranker tested was Cohere's. Voyage also offers one, which the authors did not test.

Trade-offs:

- Reranking adds a runtime step and some latency, even though chunks are scored in parallel.
- Reranking more candidates can improve accuracy but raises cost and latency. Tune it per use case.

## Contextual Retrieval implementation considerations

Choices that affect results:

- **Chunk boundaries:** chunk size, boundaries, and overlap all affect retrieval.
- **Embedding model:** Contextual Retrieval helped every model tested, but some benefited more. Gemini and Voyage embeddings performed particularly well.
- **Custom contextualiser prompts:** a prompt tailored to the domain can beat the generic one. Example: including a glossary of key terms that are defined in other documents.
- **Number of chunks:** 5, 10, and 20 were tested, and 20 performed best. More chunks raise recall but can distract the model, so test for your own use case.
- **Tell the model what is what:** response generation may improve if the model is told which part of a retrieved chunk is the generated context and which is the original text.
- **Always run evals** on your own data.

## Contextual Retrieval conclusions: the gains stack

The post's summary findings:

1. Embeddings plus BM25 beats embeddings alone.
2. Voyage and Gemini had the best embeddings among those tested.
3. Passing the top 20 chunks to the model beats the top 10 or top 5.
4. Adding context to chunks substantially improves retrieval.
5. Reranking beats no reranking.
6. The improvements stack: contextual embeddings, contextual BM25, reranking, and 20 chunks together gave the best results.

Dating caveat (mine, not the post's): the specific models named (Claude 3 Haiku, Gemini Text 004, the Cohere reranker of the time) and the $1.02 cost figure are from September 2024. The technique is the durable part.
