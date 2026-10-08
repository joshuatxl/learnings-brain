---
title: "Designing automated evals for AI agents (Anthropic Engineering)"
date: 2026-01-09
tags: [evals, agents, llm-as-judge, testing]
source: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
---

# Designing automated evals for AI agents (Anthropic Engineering)

Covers automated evals run during development without real users, for multi-turn, tool-using agents (coding, conversational, research, computer-use). Source: Anthropic Engineering, published Jan 2026.

## Eval vocabulary: task, trial, grader, transcript, outcome, harness, suite

- **Task** (problem/test case): one test with defined inputs and success criteria.
- **Trial**: one attempt at a task. Run several because outputs vary between runs.
- **Grader**: logic that scores some aspect of performance; a task can have several, each with multiple assertions/checks.
- **Transcript** (trace/trajectory): the full record of a trial, including tool calls and reasoning.
- **Outcome**: the final state of the environment, e.g. whether a reservation exists in the database, not whether the agent said "booked".
- **Evaluation harness**: infrastructure that runs tasks, records steps, grades, aggregates.
- **Agent harness (scaffold)**: what lets a model act as an agent. Evaluating "an agent" means evaluating harness plus model together.
- **Evaluation suite**: a set of tasks sharing a broad goal.

## Why agent evals are harder than single-turn evals

Agents use tools across many turns and modify environment state, so mistakes propagate and compound. Frontier models can also find valid solutions the eval didn't anticipate: Opus 4.5 "failed" a tau2-bench flight-booking task by finding a loophole in the policy that actually served the user better.

## Why build evals early: what breaks without them

Without evals, debugging is reactive (wait for complaints, reproduce manually, hope nothing else regressed), and teams can't separate real regressions from noise. Evals also force teams to pin down what success means for edge cases, and let teams adopt new models in days instead of weeks. Baselines for latency, token usage, cost per task and error rate come for free. Costs are visible upfront while benefits compound later.

## Code-based graders: strengths and weaknesses

Methods: string/regex/fuzzy match, fail-to-pass and pass-to-pass tests, static analysis (lint, types, security), outcome verification, tool-call verification, transcript metrics (turns, tokens). Strengths: fast, cheap, objective, reproducible, easy to debug. Weaknesses: brittle to valid variations, lack nuance, poor for subjective tasks.

## Model-based graders (LLM-as-judge): strengths, weaknesses, best practices

Methods: rubric scoring, natural-language assertions, pairwise comparison, reference-based evaluation, multi-judge consensus. Strengths: flexible, scalable, handles open-ended output. Weaknesses: non-deterministic, costlier, needs calibration against human graders.

Best practices:
- Give the judge an escape hatch such as returning "Unknown" when information is insufficient.
- Use structured rubrics per dimension and grade each dimension with a separate isolated judge.
- Calibrate closely with human experts, then only review occasionally.

## Human graders and combining grader scores

Human grading (SME review, crowdsourcing, spot checks, A/B tests, inter-annotator agreement) is the gold standard but expensive and slow; use it to calibrate model graders. Per task, combine grader scores as weighted (must reach a threshold), binary (all must pass), or hybrid.

## Capability evals vs regression evals

Capability (quality) evals ask what the agent can do well and should start at a low pass rate, giving a hill to climb. Regression evals ask whether it still handles everything it used to and should sit near 100%. Capability evals with high pass rates can graduate into the regression suite.

## pass@k vs pass^k for non-deterministic agents

- **pass@k**: probability of at least one success in k attempts. Rises with k. Good when one success is enough. pass@1 is the usual coding metric.
- **pass^k**: probability that all k trials succeed. Falls with k. Matters for customer-facing agents needing consistency.
- Example: 75% per-trial success over 3 trials gives 0.75^3, about 42%, for pass^3.
- At k=1 both equal the per-trial success rate.

## Evaluating coding agents

Deterministic graders fit well: do the tests pass? SWE-bench Verified (GitHub issues from Python repos, graded by running the test suite; must fix failing tests without breaking existing ones) and Terminal-Bench (end-to-end technical tasks like building a Linux kernel) both work this way. After outcome tests, also grade the transcript with code-quality heuristics or LLM rubrics. In practice unit tests plus an LLM quality rubric usually suffice; add other graders only as needed.

## Evaluating conversational agents

Interaction quality is part of what's evaluated. Combine a verifiable end state (ticket resolved, refund processed), a transcript constraint (e.g. under 10 turns) and an LLM rubric (tone, empathy, clear resolution, grounding in policy tool results). A second LLM often simulates the user. tau-Bench and tau2-Bench simulate multi-turn retail and airline scenarios this way. LLM graders are common because many tasks have several correct solutions.

## Evaluating research agents

No unit-test-style pass/fail: quality depends on context, experts disagree, and ground truth shifts. Combine groundedness checks (claims supported by retrieved sources), coverage checks (key facts that must appear), and source-quality checks (authoritative sources, not just first retrieved). Use exact match for objectively correct answers. Calibrate LLM rubrics often against expert humans. BrowseComp tests finding hard-to-find but easy-to-verify facts on the open web.

## Evaluating computer-use agents

Run the agent in a real or sandboxed GUI environment and verify the outcome, including backend state (an order actually placed, not just a confirmation page). WebArena checks URL and page state for browser tasks. OSWorld inspects file system, app configs, database contents and UI properties for full OS tasks. Tradeoff: DOM extraction is fast but token-heavy; screenshots are slower but more token-efficient. Evals can check the agent picks the right approach per context.

## Starting an eval set: 20-50 tasks from real failures

Don't wait for hundreds of tasks. Early on, each change has a large effect, so small samples suffice. Start with what you already test manually, plus bug-tracker and support-queue failures, prioritized by user impact. Evals get harder to build the longer you wait, because you end up reverse-engineering success criteria from a live system.

## Writing unambiguous tasks with reference solutions

A good task is one where two domain experts would independently reach the same pass/fail verdict. Everything the grader checks must be clear from the task description. Terminal-Bench example: a task asked for a script but gave no file path while the tests assumed one, so agents failed through no fault of their own. Write a reference solution that passes all graders to prove the task is solvable. With frontier models, a 0% pass rate across many trials (0% pass@100) usually signals a broken task, not an incapable agent.

## Balanced problem sets: test both when a behavior should and shouldn't happen

One-sided evals cause one-sided optimization. Example from building web search in Claude.ai: queries where the model should search (weather) and queries where it should answer from knowledge ("who founded Apple?"). Balancing undertriggering and overtriggering took many rounds of prompt and eval refinement.

## Stable, isolated environments for each trial

The eval agent should behave like the production agent, and each trial should start from a clean environment. Shared state (leftover files, cached data, resource exhaustion) causes correlated failures or inflated scores. Anthropic saw Claude gain an unfair advantage on some tasks by reading git history left over from previous trials.

## Grading outputs not paths, partial credit, and anti-cheating

Checking that the agent followed a specific sequence of tool calls is too rigid, since agents find valid approaches designers didn't anticipate; grade what was produced rather than the path. Give partial credit for multi-part tasks (identified the problem and verified the customer but failed to refund beats failing immediately). Design graders so the agent can't pass by exploiting loopholes.

## Broken evals mislead: CORE-Bench and METR examples

Opus 4.5 scored 42% on CORE-Bench until an Anthropic researcher found rigid grading (penalizing "96.12" when expecting "96.124991..."), ambiguous task specs, and irreproducible stochastic tasks; after fixes and a less constrained scaffold it scored 95%. METR found misconfigured tasks that told agents to optimize to a score threshold but required exceeding it, penalizing models that followed the instructions. Don't take eval scores at face value until someone has read the details and transcripts.

## Read transcripts to validate graders

Reading transcripts and grades from many trials is how you tell a genuine agent mistake from a grader rejecting a valid solution. Failures should seem fair: clear what the agent got wrong and why. Invest in tooling for viewing transcripts.

## Eval saturation: when a passing eval stops giving signal

An eval at 100% tracks regressions but shows no room for improvement. SWE-bench Verified went from roughly 30-40% to over 80% within about a year, so remaining gains look small even when capability jumps are large. Qodo initially underrated Opus 4.5 because its one-shot coding evals missed gains on longer, more complex tasks, and it built a new agentic eval framework in response.

## Maintaining eval suites and eval-driven development

Treat an eval suite as a living artifact with clear ownership. What worked at Anthropic: a dedicated evals team owns core infrastructure while domain experts and product teams contribute tasks and run evals, as routine as maintaining unit tests. Practice eval-driven development: write capability evals for planned behavior before the agent can do it, so a low starting pass rate shows which bets on future model capability pay off when a new model drops. PMs, customer success and sales can contribute tasks (e.g. via Claude Code PRs).

## Evals as one layer among production monitoring, A/B tests, feedback, and human review

- **Automated evals**: fast, reproducible, run on every commit; need upfront investment and can give false confidence if they drift from real usage.
- **Production monitoring**: real behavior at scale; reactive, noisy.
- **A/B testing**: measures real user outcomes; slow, needs traffic.
- **User feedback**: surfaces unanticipated problems; sparse and skewed to severe issues.
- **Manual transcript review**: builds intuition for failure modes; doesn't scale.
- **Systematic human studies**: gold-standard judgments for calibrating LLM graders; expensive and slow.

Like the Swiss cheese model, no single layer catches everything; combine them.

## Eval frameworks mentioned: Harbor, Braintrust, LangSmith, Langfuse, Arize

- **Harbor**: runs agents in containers at scale; ships Terminal-Bench 2.0.
- **Braintrust**: offline evals plus production observability; autoevals library has prebuilt scorers.
- **LangSmith**: tracing, offline/online evals, datasets, tight LangChain integration.
- **Langfuse**: open-source, self-hostable alternative (data residency).
- **Arize**: Phoenix (open-source tracing and evals) and AX (SaaS).

Frameworks are only as good as the tasks run through them; pick one quickly and invest in high-quality tasks and graders.
