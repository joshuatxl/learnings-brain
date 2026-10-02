---
title: "Building effective agents: Anthropic's workflow and agent patterns"
date: 2024-12-19
tags: [agents, llm, workflows, tool-design, prompt-engineering, anthropic]
source: https://www.anthropic.com/engineering/building-effective-agents
---

# Building effective agents: Anthropic's workflow and agent patterns

Anthropic's December 2024 guidance, drawn from working with dozens of teams: the most successful LLM agent builds used simple, composable patterns, not complex frameworks or specialised libraries. The page now carries a note that the tooling landscape has changed since then and points to Anthropic's Managed Agents material for their current approach.

## Workflows vs agents: the architectural distinction

Anthropic calls everything in this space an "agentic system" and splits it in two:

- **Workflow:** LLMs and tools are orchestrated through code paths defined in advance. The developer decides the steps.
- **Agent:** the LLM directs its own process and tool use, and keeps control over how the task gets done.

Workflows give predictability and consistency on well-defined tasks. Agents fit when flexibility and model-driven decisions are needed at scale.

## Default to the simplest solution before building anything agentic

Find the simplest solution that works and add complexity only when it demonstrably improves outcomes. That can mean building no agentic system at all.

- Agentic systems usually trade latency and cost for better task performance, so check that the trade is worth it.
- For many applications, a single LLM call improved with retrieval and in-context examples is enough.
- The order of escalation is: simple prompt, then evaluate and optimise it, then multi-step agentic systems only when simpler options fall short.
- The patterns are not prescriptive. Combine and reshape them, and measure performance as you iterate.

## Agent frameworks: start with the raw LLM API

Frameworks named in the article: Claude Agent SDK, Strands Agents SDK (AWS), Rivet (drag-and-drop workflow builder), and Vellum (GUI for building and testing workflows).

- What they help with: standard low-level work such as calling LLMs, defining and parsing tools, and chaining calls.
- What they cost: extra abstraction layers that can hide the underlying prompts and responses, which makes debugging harder. They also tempt you to add complexity a simpler setup would not need.
- Recommendation: start by calling LLM APIs directly, since many patterns take only a few lines of code.
- If you do use a framework, understand the code underneath. Wrong assumptions about what happens under the hood are a common source of customer error.
- Moving to production, do not hesitate to strip out abstraction layers and build with basic components.

## Augmented LLM: the basic building block

The foundation of every pattern is an LLM extended with retrieval, tools, and memory. Current models can use these actively: writing their own search queries, choosing tools, and deciding what to retain.

Two things to focus on when implementing it:

- Tailor the augmentations to your specific use case.
- Give the LLM an easy, well-documented interface to them.

Model Context Protocol (MCP) is one way to implement this: a simple client implementation gives access to an ecosystem of third-party tools. All the patterns below assume each LLM call has these augmentations.

## Prompt chaining workflow: fixed sequential steps with gates

A task is split into a sequence of steps, and each LLM call works on the output of the previous one. Programmatic checks ("gates") can sit on intermediate steps to confirm the process is still on track.

- Use when: the task breaks cleanly into fixed subtasks.
- Trade-off: more latency in exchange for higher accuracy, because each call has an easier job.
- Example: write marketing copy, then translate it.
- Example: write an outline, check it against criteria, then write the document from the outline.

## Routing workflow: classify the input, then dispatch it

An input is classified and sent to a specialised follow-up task. This separates concerns and allows more specialised prompts. Without it, optimising for one type of input can hurt performance on others.

- Use when: there are distinct categories better handled separately, and classification can be done accurately, by an LLM or a traditional classifier.
- Example: send customer service queries (general questions, refund requests, technical support) to different downstream processes, prompts, and tools.
- Example: send easy or common questions to a smaller, cheaper model and hard or unusual ones to a more capable model.

## Parallelization workflow: sectioning and voting

LLM calls run simultaneously and their outputs are aggregated in code. Two variants:

- **Sectioning:** split the task into independent subtasks that run in parallel.
- **Voting:** run the same task several times to get diverse outputs.

Use when subtasks can be parallelised for speed, or when several perspectives or attempts are needed for higher confidence. On complex tasks with multiple considerations, LLMs generally do better when each consideration gets its own call.

### Parallelization examples

Concrete uses of each variant from the article:

- Sectioning, guardrails: one instance handles the user query while another screens it for inappropriate content. This tends to beat having one call do both.
- Sectioning, evals: each call evaluates a different aspect of model performance on a prompt.
- Voting, code review: several different prompts review code for vulnerabilities and flag problems.
- Voting, content moderation: multiple prompts assess different aspects, with different vote thresholds to balance false positives against false negatives.

## Orchestrator-workers workflow: dynamic task decomposition

A central LLM breaks the task down at run time, delegates pieces to worker LLMs, and synthesises their results.

- Use when: the subtasks cannot be predicted in advance.
- Difference from parallelization: the shape looks similar, but here the subtasks are not predefined. The orchestrator decides them based on the specific input.
- Example: coding products that change multiple files, where how many files and what changes depend on the task.
- Example: search tasks that gather and analyse information from multiple sources.

## Evaluator-optimizer workflow: generate and critique in a loop

One LLM call produces a response and another evaluates it and gives feedback, repeating in a loop.

- Use when: evaluation criteria are clear and iterative refinement gives measurable value.
- Two signs of a good fit: responses demonstrably improve when a human articulates feedback, and an LLM is capable of giving that kind of feedback.
- Example: literary translation, where an evaluator catches nuances the translator missed.
- Example: complex search needing several rounds, where the evaluator decides whether more searching is warranted.

## Autonomous agents: an LLM using tools in a loop

Agents are typically just LLMs using tools in a loop, driven by feedback from the environment. Implementation is often straightforward even when the tasks are sophisticated, which is why toolset design and documentation matter so much.

How an agent run goes:

- It starts from a command from, or a discussion with, the human user.
- Once the task is clear, it plans and operates independently, returning to the human for information or judgement when needed.
- At each step it needs "ground truth" from the environment (tool call results, code execution) to assess progress.
- It can pause for human feedback at checkpoints or when blocked.
- It ends on completion, and commonly also has stopping conditions such as a maximum number of iterations to keep control.

## When to use autonomous agents, and their risks

Use agents for open-ended problems where the number of steps cannot be predicted and a fixed path cannot be hardcoded. The LLM may run for many turns, so you need some level of trust in its decision-making. Autonomy makes agents suited to scaling tasks in trusted environments.

Risks and mitigations:

- Higher costs than workflows.
- Compounding errors across steps.
- Mitigate with extensive testing in sandboxed environments and appropriate guardrails.

Anthropic's own examples: a coding agent for SWE-bench tasks (edits across many files from a task description), and the computer use reference implementation.

## Three core principles for implementing agents

Anthropic's summary principles:

1. Keep the agent's design simple.
2. Prioritise transparency by explicitly showing the agent's planning steps.
3. Craft the agent-computer interface (ACI) carefully through thorough tool documentation and testing.

The stated payoff is agents that are reliable, maintainable, and trusted by users, not just powerful.

## Where agents add the most value: four task traits

Agents add the most value on tasks that:

- need both conversation and action,
- have clear success criteria,
- enable feedback loops,
- integrate meaningful human oversight.

### Customer support as an agent use case

Support fits open-ended agents because interactions follow a conversation while needing external information and actions. Tools can pull customer data, order history, and knowledge base articles. Actions such as refunds and ticket updates can be done programmatically. Success is measurable through user-defined resolutions. Some companies charge only for successful resolutions, which signals confidence in their agents.

### Coding as an agent use case

Coding fits because solutions are verifiable through automated tests, agents can iterate using test results as feedback, the problem space is well-defined and structured, and output quality can be measured objectively. Caveat: automated tests verify functionality, but human review is still needed to check solutions fit broader system requirements.

## Tool format choice: pick formats the model can write easily

The same action can often be specified several ways (a file edit as a diff or a full rewrite, code inside markdown or inside JSON). These are losslessly convertible for software, but not equally easy for an LLM to write.

- A diff needs the chunk header's line counts before the new code is written.
- Code inside JSON needs extra escaping of newlines and quotes compared with markdown.

Guidelines for choosing a format:

- Give the model enough tokens to think before it writes itself into a corner.
- Keep the format close to what appears naturally in text on the internet.
- Avoid formatting overhead, such as keeping an accurate count of thousands of lines or string-escaping code.

## Agent-computer interface (ACI): writing good tool definitions

Tool definitions deserve as much prompt engineering attention as the main prompt. Rule of thumb: invest as much effort in the ACI as goes into human-computer interfaces.

- Put yourself in the model's position. If a human would have to think hard about how to use the tool from its description and parameters, the model will too.
- A good definition often includes example usage, edge cases, input format requirements, and clear boundaries from other tools.
- Rename parameters and rewrite descriptions to be more obvious, as if writing a docstring for a junior developer. This matters most when there are many similar tools.
- Test with many example inputs, watch what mistakes the model makes, and iterate.
- Poka-yoke the tools: change the arguments so mistakes are harder to make.

## SWE-bench example: absolute filepaths as poka-yoke

While building their SWE-bench agent, Anthropic spent more time optimising tools than the overall prompt.

The specific failure: the model made mistakes with tools that took relative filepaths once the agent had moved out of the root directory. The fix was to change the tool to always require absolute filepaths, after which the model used it without errors.

The lesson is to remove the possibility of the mistake in the tool's interface instead of instructing the model to avoid it.
