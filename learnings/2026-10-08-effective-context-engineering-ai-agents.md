---
title: "Effective context engineering for AI agents: Anthropic's techniques"
date: 2025-09-29
tags: [context-engineering, agents, llm, compaction, agentic-memory, sub-agents, anthropic]
source: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
---

# Effective context engineering for AI agents: Anthropic's techniques

Post by Anthropic's Applied AI team (September 2025). Its guiding principle: find the smallest possible set of high-signal tokens that maximises the likelihood of the desired outcome, because context is a finite resource with diminishing marginal returns.

## Context engineering: definition and difference from prompt engineering

Context is the set of tokens included when sampling from an LLM. Context engineering is the set of strategies for curating and maintaining the optimal set of those tokens during inference, including everything that lands there outside the prompt.

How it differs from prompt engineering:

- Prompt engineering is about writing and organising instructions, especially system prompts. It suited one-shot classification and text generation tasks.
- Context engineering manages the whole context state: system instructions, tools, Model Context Protocol (MCP), external data, and message history.
- Writing a prompt is a discrete task. Context curation is iterative: it happens every time you decide what to pass to the model.

Anthropic frames it as the natural progression of prompt engineering. An agent running in a loop keeps generating data that could be relevant to the next turn, and that has to be repeatedly refined to fit a limited window.

## Context rot and the attention budget: why context is finite

LLMs, like humans, lose focus or get confused past a certain point. The post cites context rot (from Chroma's research): as the number of tokens in the context window grows, the model's ability to accurately recall information from that context falls.

Key points:

- Some models degrade more gently than others, but the effect appears across all models.
- LLMs have an "attention budget", comparable to human working memory. Every new token uses some of it.
- The result is a performance gradient, not a hard cliff. Models stay highly capable at long contexts but show reduced precision for information retrieval and long-range reasoning.

## Why attention degrades with context length: transformer constraints

The post gives three architectural reasons for attention scarcity:

- Transformers let every token attend to every other token, which means n² pairwise relationships for n tokens. As context grows, the model's ability to capture those relationships is stretched thin.
- Training data contains more short sequences than long ones, so models have less experience with, and fewer specialised parameters for, context-wide dependencies.
- Techniques such as position encoding interpolation let models handle longer sequences by adapting them to the smaller context they were trained on, at the cost of some degradation in understanding token position.

## System prompt altitude: between hardcoded logic and vague guidance

System prompts should be extremely clear, use simple and direct language, and present ideas at the "right altitude" for the agent. That is the zone between two failure modes:

- Too low: engineers hardcode complex, brittle if-else logic into the prompt to force exact behaviour. This creates fragility and maintenance burden.
- Too high: vague, high-level guidance that gives the model no concrete signal for the desired output, or falsely assumes shared context.

The target is specific enough to guide behaviour effectively, while flexible enough to give the model strong heuristics it can apply itself.

## System prompt structure and starting from a minimal prompt

Structure: organise the prompt into distinct sections and delineate them with XML tags or Markdown headers. The exact formatting is probably becoming less important as models improve.

```text
<background_information> ... </background_information>
<instructions> ... </instructions>
## Tool guidance
## Output description
```

Process:

- Aim for the minimal set of information that fully outlines the expected behaviour.
- Minimal does not mean short. The agent still needs enough information up front to behave as intended.
- Start by testing a minimal prompt with the best model available.
- Then add clear instructions and examples based on the failure modes found in that initial testing.

## Tool design for context efficiency: minimal, non-overlapping tool sets

Tools define the contract between an agent and its information and action space. They should promote efficiency in two ways: returning token-efficient information, and encouraging efficient agent behaviour.

Qualities of a good tool, like functions in a well-designed codebase:

- Self-contained and robust to error.
- Extremely clear about its intended use.
- Minimal overlap in functionality with other tools.
- Input parameters that are descriptive, unambiguous, and play to the model's strengths.

Common failure mode: bloated tool sets that cover too much or create ambiguous choices about which tool to use. The test: if a human engineer cannot say definitively which tool applies in a situation, the agent cannot be expected to do better. A minimal viable tool set also makes context easier to maintain and prune over long interactions.

## Few-shot examples: diverse canonical examples, not edge-case lists

Few-shot prompting is still strongly advised. The mistake is stuffing a laundry list of edge cases into the prompt to spell out every possible rule. Anthropic does not recommend that.

Instead, curate a set of diverse, canonical examples that portray the expected behaviour. For an LLM, examples act as the pictures worth a thousand words.

The overall guidance across system prompts, tools, examples, and message history is to keep context informative yet tight.

## Agent definition: LLMs autonomously using tools in a loop

Since the earlier "Building effective agents" post, Anthropic has settled on a simple definition of an agent: LLMs autonomously using tools in a loop. The post says the field is converging on this paradigm.

As models get more capable, agent autonomy can scale: smarter models can navigate nuanced problem spaces independently and recover from errors.

## Just-in-time context retrieval: lightweight references loaded at runtime

Many applications use embedding-based retrieval before inference to surface context. Teams are increasingly augmenting this with "just in time" strategies.

How it works: instead of pre-processing all relevant data, the agent keeps lightweight identifiers (file paths, stored queries, web links) and uses tools to load the data into context at runtime.

Example: Claude Code doing data analysis over large databases. The model writes targeted queries, stores the results, and uses Bash commands such as `head` and `tail` to examine large volumes of data without ever loading the full objects into context.

The analogy is human cognition: people do not memorise whole corpuses, they rely on external indexing systems such as file systems, inboxes, and bookmarks to retrieve things on demand.

## Metadata as signal and progressive disclosure for agents

References carry metadata that helps the agent decide how to use information:

- Location and naming: `test_utils.py` in a `tests` folder implies a different purpose from the same filename in `src/core_logic/`.
- Folder hierarchies, naming conventions, and timestamps tell both humans and agents how and when to use something.

Progressive disclosure means the agent discovers relevant context incrementally through exploration. Each interaction informs the next decision: file size suggests complexity, naming hints at purpose, timestamps can stand in for relevance.

The agent builds understanding layer by layer, keeps only what is necessary in working memory, and uses note-taking for persistence. This keeps it focused on relevant subsets instead of exhaustive but possibly irrelevant information.

## Just-in-time retrieval trade-offs and the hybrid strategy

Costs of runtime exploration:

- It is slower than retrieving pre-computed data.
- It needs opinionated engineering so the model has the right tools and heuristics to navigate.
- Without guidance, an agent can waste context by misusing tools, chasing dead ends, or missing key information.

Hybrid strategy: retrieve some data up front for speed, and let the agent explore further at its discretion. Claude Code does this. CLAUDE.md files are dropped into context up front, while `glob` and `grep` let it find files just in time, which avoids stale indexes and complex syntax trees.

The right level of autonomy depends on the task. The post suggests hybrid may suit less dynamic content such as legal or finance work. The general advice is "do the simplest thing that works", with the expectation that design will trend towards less human curation as models improve.

## Long-horizon tasks: why bigger context windows are not the fix

Long-horizon tasks are those where the token count exceeds the context window, spanning tens of minutes to multiple hours of continuous work. Examples are large codebase migrations and comprehensive research projects.

Waiting for larger context windows is not expected to solve this. For the foreseeable future, windows of all sizes will be subject to context pollution and information relevance problems, at least where the strongest agent performance is wanted.

Anthropic's three techniques for this are compaction, structured note-taking, and multi-agent (sub-agent) architectures.

## Compaction: summarise the conversation and restart the context window

Compaction takes a conversation nearing the context window limit, summarises it, and starts a new context window with the summary. It is typically the first lever to pull for long-term coherence.

How Claude Code does it:

- The message history is passed to the model to summarise and compress the most critical details.
- It keeps architectural decisions, unresolved bugs, and implementation details.
- It discards redundant tool outputs and messages.
- The agent continues with the compressed context plus the five most recently accessed files.

Risk: overly aggressive compaction can lose subtle but critical context whose importance only becomes clear later.

### Tuning a compaction prompt: recall first, then precision

Recommended process for engineers building compaction:

1. Tune the compaction prompt on complex agent traces.
2. First maximise recall, so the prompt captures every relevant piece of information from the trace.
3. Then iterate to improve precision by removing superfluous content.

Tool result clearing is the safest, lightest-touch form of compaction. Once a tool has been called deep in the message history, the agent rarely needs to see the raw result again. At the time of the post this had just launched as a feature on the Claude Developer Platform.

## Structured note-taking (agentic memory): notes persisted outside context

The agent regularly writes notes to memory outside the context window, and those notes are pulled back into context later. This gives persistent memory with minimal overhead.

Examples of the pattern:

- Claude Code creating a to-do list.
- A custom agent maintaining a `NOTES.md` file.

It lets the agent track progress across complex tasks and keep critical context and dependencies that would otherwise be lost across dozens of tool calls.

Alongside the Sonnet 4.5 launch, Anthropic released a memory tool in public beta on the Claude Developer Platform. It is file-based and lets agents build knowledge bases over time, maintain project state across sessions, and reference previous work without keeping it all in context.

### Claude playing Pokémon: agentic memory outside coding

The post uses Claude playing Pokémon to show memory working in a non-coding domain:

- The agent keeps precise tallies across thousands of game steps, for example noting that it has trained in Route 1 for the last 1,234 steps and Pikachu has gained 8 levels towards a target of 10.
- Without being prompted on memory structure, it develops maps of explored regions, records which key achievements are unlocked, and keeps notes on which attacks work best against which opponents.
- After a context reset, it reads its own notes and continues multi-hour training sequences or dungeon explorations.

This coherence across summarisation steps makes long-horizon strategies possible that would not be if everything had to stay in the context window.

## Sub-agent architectures: clean contexts returning condensed summaries

Instead of one agent holding state for a whole project, specialised sub-agents handle focused tasks with clean context windows.

How it works:

- The main agent coordinates with a high-level plan.
- Sub-agents do deep technical work or use tools to find relevant information.
- Each sub-agent may explore extensively, using tens of thousands of tokens or more.
- It returns only a condensed, distilled summary, often 1,000 to 2,000 tokens.

Benefit: separation of concerns. The detailed search context stays isolated in the sub-agents, and the lead agent focuses on synthesising and analysing results. Anthropic's multi-agent research system showed a substantial improvement over single-agent systems on complex research tasks using this pattern.

## Choosing between compaction, note-taking, and sub-agents

The choice depends on the task:

- Compaction: keeps conversational flow for tasks needing extensive back-and-forth.
- Note-taking: suits iterative development with clear milestones.
- Multi-agent architectures: suit complex research and analysis where parallel exploration pays off.

The post's closing view is that smarter models need less prescriptive engineering and can operate with more autonomy, but treating context as a precious, finite resource will stay central to building reliable agents.
