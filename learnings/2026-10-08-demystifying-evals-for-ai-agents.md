---
title: "Evals for AI agents: Anthropic's definitions, graders, and build roadmap"
date: 2026-01-09
tags: [evals, agents, llm-evaluation, graders, testing, anthropic]
source: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
---

# Evals for AI agents: Anthropic's definitions, graders, and build roadmap

Anthropic engineering post (January 2026) by Mikaela Grace, Jeremy Hadfield, Rodrigo Olivares, and Jiri De Jonghe. Agents take many turns, call tools, and change state, so mistakes compound and are harder to evaluate than single LLM calls. The post's position is that evals have visible upfront costs and benefits that compound over an agent's lifecycle.

## Agent eval vocabulary: task, trial, grader, transcript, outcome

An eval gives an AI an input and then grades its output. The post's terms:

- **Task:** a single test with defined inputs and success criteria.
- **Trial:** one attempt at a task. Multiple trials are run because outputs vary.
- **Grader:** logic that scores some aspect of performance. A task can have several graders, each with multiple assertions or checks.
- **Transcript** (also trace or trajectory): the full record of a trial, including outputs, tool calls, and reasoning.
- **Outcome:** the final state of the environment. A flight booking succeeds only if a reservation exists in the database, not because the agent says it booked one.
- **Evaluation suite:** a collection of tasks measuring a shared capability or behaviour.

## Evaluation harness vs agent harness

Two different pieces of infrastructure share the word harness:

- **Evaluation harness:** runs the tasks, records the steps, grades outputs, and aggregates results.
- **Agent harness** (or scaffold): the system that lets a model act as an agent.

Evaluating an agent means evaluating the agent harness and the model together, not the model alone. A score can change because the scaffold changed.

## Why build agent evals: what teams without them lose

Teams without evals are "flying blind" and react to user complaints. What evals provide:

- A forced, explicit definition of success.
- A way to tell real regressions from noise.
- Faster adoption of new models: days of testing with evals versus weeks without.
- Baselines for latency, token use, cost, and error rates.

## Code-based graders: methods, strengths, weaknesses

Methods:

- String matching (exact, regex, fuzzy).
- Binary tests (fail-to-pass and pass-to-pass).
- Static analysis (lint, type, security).
- Outcome verification.
- Tool-call verification (which tools, which parameters).
- Transcript analysis (turns, tokens).

Strengths: fast, cheap, objective, reproducible, easy to debug, good at verifying specific conditions.

Weaknesses: brittle to valid variations, lacks nuance, limited for subjective tasks.

## Model-based (LLM) graders: methods, strengths, weaknesses

Methods:

- Rubric scoring.
- Natural-language assertions.
- Pairwise comparison.
- Reference-based evaluation.
- Multi-judge consensus.

Strengths: flexible, scalable, captures nuance, handles open-ended tasks and freeform output.

Weaknesses: non-deterministic, more expensive than code, needs calibration against human graders.

## Human graders: methods, strengths, weaknesses

Methods:

- Subject-matter expert review.
- Crowdsourced judgment.
- Spot-check sampling.
- A/B testing.
- Inter-annotator agreement.

Strengths: gold-standard quality, matches expert user judgment, used to calibrate model-based graders.

Weaknesses: expensive, slow, often needs experts at scale.

## Combining grader scores: weighted, binary, hybrid

A task with several graders needs a rule for the overall result:

- **Weighted:** grader scores are combined and must reach a threshold.
- **Binary:** every grader must pass.
- **Hybrid:** a mix of the two.

## Capability evals vs regression evals

Two suites with opposite expected pass rates:

- **Capability evals** ask what the agent can do. They should start at a low pass rate, giving the team something to climb.
- **Regression evals** ask whether the agent still does what it used to. They should sit near 100% and guard against backsliding.

Capability evals that reach high pass rates can "graduate" into the regression suite.

## pass@k vs pass^k: measuring non-deterministic agents

Because agent output varies between trials, the post uses two metrics over k trials:

- **pass@k:** the probability of at least one success in k attempts. It rises as k grows. Use it when one success is enough.
- **pass^k:** the probability that all k trials succeed. It falls as k grows. Use it when consistency matters, as with customer-facing agents.

Numbers:

- At k=1 the two are identical.
- At k=10, pass@k approaches 100% while pass^k approaches 0%.
- A 75% per-trial success rate over three trials gives 0.75³ ≈ 42% for passing all three.

## Coding agent evals: deterministic tests plus transcript grading

Deterministic tests are the natural grader for coding agents: does the code run and do the tests pass. Benchmarks named are SWE-bench Verified and Terminal-Bench. The post adds transcript grading for code quality and tool use on top of tests.

In practice, real coding evals usually rely on unit tests plus one LLM rubric, with other graders added only as needed.

### Coding agent eval example: fix-auth-bypass task config

The post's example task is fixing an authentication bypass, graded by five graders at once. The sketch below is reconstructed from a description of that example, not copied from the article:

```yaml
task:
  id: fix-auth-bypass_1
graders:
  - deterministic_tests   # empty and null passwords rejected
  - llm_rubric            # code-quality rubric
  - static_analysis       # ruff, mypy, bandit
  - state_check           # security log: event_type "auth_blocked"
  - tool_calls            # read_file, edit_file, run_tests
tracked_metrics:
  transcript: [n_turns, n_toolcalls, n_total_tokens]
  latency: [time_to_first_token, output_tokens_per_sec, time_to_last_token]
```

## Conversational agent evals: end state, transcript limits, simulated users

Conversational agents are graded by combining:

- End-state checks (was the ticket resolved, was the refund processed).
- Transcript constraints such as a turn limit.
- LLM rubrics for tone and quality of resolution.

A second LLM usually simulates the user, which is unusual among eval types. τ-Bench and τ2-Bench do this: one model plays a user persona while the agent works through retail support and airline booking scenarios. Anthropic's alignment auditing agents use the same approach for extended adversarial conversations.

The post's support-refund example, reconstructed from a description, not copied:

```yaml
graders:
  - llm_rubric:    # empathy, clear resolution, grounded in fetch_policy
  - state_check:   # ticket "resolved", refund "processed"
  - tool_calls:    # verify_identity, process_refund (amount <= 100),
                   # send_confirmation
  - transcript:
      max_turns: 10
```

## Research agent evals: groundedness, coverage, source quality

Research quality depends on context, so several checks are combined:

- **Groundedness:** claims are supported by the retrieved sources.
- **Coverage:** the key facts a good answer must include are present.
- **Source quality:** sources are authoritative, not just the first ones retrieved.
- **Exact match:** for questions with objective answers.

An LLM grader can flag unsupported claims and coverage gaps and check the synthesis for coherence. These rubrics need frequent calibration with experts. BrowseComp is the benchmark named.

## Computer use agent evals: check environment state, not claims

Computer use agents are evaluated on outcomes in real or sandboxed environments:

- WebArena checks URL and page state, plus backend state such as whether an order was actually placed.
- OSWorld inspects file-system state, application configs, database contents, and UI element properties.

Tool-choice example from Claude for Chrome: DOM-based interaction is fast but token-heavy, which suits summarising Wikipedia text. Screenshots are slower but more token-efficient, which suits finding a laptop case on Amazon, where extracting the full DOM is expensive. Evals checked that the agent picked the right tool for each context.

## Eval roadmap steps 0-1: start early with 20-50 tasks from real failures

Step 0, start early:

- Teams often wait until they have hundreds of tasks. 20 to 50 simple tasks drawn from real failures is enough to begin.
- Early in development each change has a large effect, so small samples are sufficient to see it.
- Evals get harder to build the longer you wait.

Step 1, start from what you already check manually:

- Use pre-release manual checks and common user tasks.
- Once in production, convert bug-tracker and support-queue failures into test cases, prioritised by user impact.

## Eval roadmap step 2: unambiguous tasks with reference solutions

A task is well specified if two domain experts would independently reach the same pass/fail verdict.

- Ambiguity example, found while auditing Terminal-Bench: a task asks for a script without naming a file path, but the tests assume a specific path. The agent fails through no fault of its own.
- A 0% pass rate across many trials (for example pass@100 of 0%) usually signals a broken task, not an incapable agent.
- Write a reference solution: a known-good output that passes all graders. It proves the task is solvable and the graders are correctly configured.

## Eval roadmap step 3: balanced problem sets (should and should not)

Test both the cases where a behaviour should occur and the cases where it should not. One-sided evals produce one-sided optimisation.

Example: Claude.ai's web search evals covered queries that need a search (the weather) and queries that do not (who founded Apple). Balancing under-triggering against over-triggering took many rounds of refining both the prompts and the eval.

## Eval roadmap step 4: isolated trials and a stable environment

Each trial should start from a clean environment. Shared state between trials causes correlated failures or inflated scores.

- In some internal evals, Claude gained an unfair advantage by examining git history left over from earlier trials.
- Shared resource limits (such as CPU or memory) also make trials non-independent.

## Eval roadmap step 5: grader design rules

Rules for designing graders:

- Order of preference: deterministic graders where possible, LLM graders where needed, human graders for validation.
- Grade the outcome, not a rigid sequence of steps, so valid creative approaches are not punished.
- Give partial credit. A support agent that identifies the problem and verifies the customer but fails the refund is better than one that fails immediately.
- Calibrate LLM judges against human experts and use structured rubrics.
- Give LLM judges an "Unknown" option so they are not forced to hallucinate a verdict.
- Use one isolated LLM judge per dimension instead of one judge scoring everything.
- Make graders resistant to hacks and shortcuts.

## Grader bugs that understate agents: CORE-Bench, METR, τ2-bench

Examples of eval flaws producing misleading scores:

- CORE-Bench: Opus 4.5 first scored 42%. Problems included rigid grading that penalised "96.12" when "96.124991…" was expected, ambiguous specs, and irreproducible tasks. After fixes and a less constrained scaffold, the score was 95%.
- METR found misconfigured tasks that asked the model to reach a score threshold but graded for exceeding it, penalising models that followed instructions.
- On a τ2-bench flight problem, Opus 4.5 found a policy loophole that gave the user a better outcome, and so "failed" the eval as written.

## Eval roadmap step 6: read the transcripts

Without reading transcripts and grades, you cannot tell whether a failure is an agent error or a grader bug, or whether the graders work at all.

- Failures should be fair and clearly explained when you read them.
- Do not trust a score until someone has read the transcripts behind it.
- Anthropic built internal tooling for viewing transcripts.

## Eval roadmap step 7: monitor for eval saturation

An eval at 100% still catches regressions but gives no signal for improvement.

- SWE-bench Verified is nearing saturation at over 80%. The article gives the starting point as 40% a year earlier in one place and 30% in another.
- Qodo was initially unimpressed by Opus 4.5 because their one-shot coding evals did not capture its gains on longer tasks. They built a new agentic eval to see the difference.
- Revise evals that turn out to be unfair or ambiguous.

## Eval roadmap step 8: long-term ownership and eval-driven development

How to keep suites healthy:

- A dedicated eval team owns the infrastructure. Domain experts and product teams contribute most of the tasks.
- Treat eval ownership like unit-test maintenance.
- Eval-driven development: define evals for planned capabilities before the agent can do them.
- Non-engineers such as product managers, customer success managers, and salespeople can contribute eval tasks as pull requests using Claude Code.

## How Claude Code, Descript, and Bolt built their evals

Team examples from the post:

- **Claude Code:** began with fast iteration on user feedback, then added evals for concision and file edits, then for over-engineering.
- **Descript:** graded on three dimensions: don't break things, do what I asked, do it well. They moved from manual grading to LLM graders with periodic human calibration, and run two separate suites.
- **Bolt:** started evals after the agent was already popular. In three months they built a system using static analysis, browser agents, and LLM judges.

## Automated evals alongside monitoring, A/B tests, and human review

The post compares six methods:

- **Automated evals:** fast, reproducible, no user impact, can run on every commit. Costs: upfront investment, maintenance, and false confidence if they diverge from real usage.
- **Production monitoring:** ground truth from live metrics, but reactive because users hit the problem first.
- **A/B testing:** measures real outcomes, but slow, needs traffic, and only tests deployed changes.
- **User feedback:** sparse, self-selected, skews towards severe issues.
- **Manual transcript review:** builds intuition, but time-intensive and does not scale.
- **Systematic human studies:** gold standard, but expensive and slow.

Swiss cheese analogy: no single layer catches every issue, so failures that slip through one layer can be caught by another.

### When to use each evaluation method

Timing guidance:

- Automated evals: first line of defence before launch and in CI/CD, run on each change and each model upgrade.
- Production monitoring: starts after launch.
- A/B testing: once there is enough traffic.
- User feedback and transcript review: ongoing.
- Human studies: for calibrating LLM graders or judging subjective outputs.

## Eval frameworks named: Harbor, Braintrust, LangSmith, Langfuse, Arize

Tools listed in the post's appendix: Harbor, Braintrust (with autoevals), LangSmith, Langfuse, and Arize (Phoenix and AX).

The advice is to pick a framework quickly and spend the effort on the quality of the eval tasks and graders, since that is where the value is.
