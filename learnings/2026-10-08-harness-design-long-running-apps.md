---
title: "Harness design for long-running app builds: planner, generator, evaluator"
date: 2026-03-24
tags: [agent-harness, agents, multi-agent, evaluator, long-running-tasks, claude-agent-sdk, anthropic]
source: https://www.anthropic.com/engineering/harness-design-long-running-apps
---

# Harness design for long-running app builds: planner, generator, evaluator

Anthropic engineering post (March 2026) by Prithvi Rajasekaran of the Labs team, on getting Claude to produce high-quality frontend design and build full applications autonomously over multi-hour runs. Its core idea is a GAN-inspired split between an agent that generates work and a separate agent that evaluates it, and its main lesson is that every harness component encodes an assumption about what the model cannot do alone, which goes stale as models improve.

## Harness definition and the generator/evaluator pattern

A harness is the scaffolding around a model: orchestration, prompts, tools, and artifacts.

The generator/evaluator pattern borrows from GANs (generative adversarial networks): one agent produces work and a second agent grades it and writes a critique, which the generator then acts on.

Why separate them: a standalone evaluator is easier to tune to be sceptical than a generator is to criticise its own work. The post calls separating generation from evaluation a strong lever.

Caveat: the evaluator is still an LLM and stays lenient towards LLM output. Separation makes the leniency more tractable to tune, it does not remove it.

## Two failure modes of naive long-running agents

The post names two reasons simple long-running setups fall short:

- **Coherence loss and context anxiety:** over long tasks the agent loses the thread, and some models start wrapping up early because they believe they are near their context limit.
- **Self-evaluation bias:** an agent asked to judge its own work tends to approve it.

The earlier baseline harness had an initializer agent turn a product spec into a task list, and a coding agent implement one feature per session, leaving handoff artifacts for the next session.

## Context anxiety, context resets, and compaction

Definitions:

- **Context anxiety:** a model's tendency to wrap work up prematurely as it believes it is approaching its context limit.
- **Context reset:** clear the window, start a fresh agent, and pass it a structured handoff containing state and next steps. Gives a clean slate.
- **Compaction:** summarise the earlier conversation in place so the same agent continues. Keeps continuity but not a clean slate.

Model differences:

- Claude Sonnet 4.5 showed context anxiety, which is why resets were used.
- Claude Opus 4.5 largely removed it, so context resets were dropped and the build ran as one continuous session using the Claude Agent SDK's automatic compaction.

## Frontend design grading criteria: design quality, originality, craft, functionality

To make subjective design quality gradable, four criteria were given to both the generator and the evaluator:

1. **Design quality:** does the design feel like a coherent whole, with colours, typography, layout, imagery, and details creating a distinct mood and identity?
2. **Originality:** is there evidence of custom decisions? Template layouts, library defaults, and AI-generated patterns fail. A human designer should see deliberate creative choices.
3. **Craft:** technical execution, such as typography hierarchy, spacing consistency, colour harmony, and contrast ratios. A competence check that most reasonable implementations pass.
4. **Functionality:** can users understand the interface, find the primary actions, and complete tasks without guessing?

### Frontend criteria weighting and "AI slop"

Design quality and originality were weighted more heavily than craft and functionality, because Claude already did well on the latter two by default.

"AI slop" is the post's term for generic AI design patterns, such as purple gradients over white cards, that the criteria penalise.

## Calibrating the design evaluator and the effect of criteria wording

The evaluator was calibrated with few-shot examples and detailed score breakdowns to reduce score drift.

Wording steers output directly:

- Phrases such as "the best designs are museum quality" pushed outputs towards a particular visual convergence.
- Even the first iteration beat a baseline with no such prompt, suggesting the criteria language itself moved the model away from generic defaults, before any evaluator feedback.

## Frontend design loop: Playwright evaluator, 5 to 15 iterations

How the frontend harness ran:

- **Generator:** produces an HTML/CSS/JS frontend from a user prompt, then revises based on the critique.
- **Evaluator:** uses the Playwright MCP to navigate the live page, take screenshots, score each criterion, and write a detailed critique.
- **Orchestration:** built on the Claude Agent SDK.
- **Loop:** 5 to 15 iterations per generation, with runs lasting up to about four hours.
- After each evaluation the generator chooses to refine the current direction or pivot to a new aesthetic.

Observations:

- Scores improved over iterations, then plateaued with headroom remaining. The article reports no numeric scores.
- Improvement was not always linear. The author sometimes preferred a middle iteration to the final one.
- Implementation complexity tended to grow across rounds.

## Dutch art museum example: the pivot at iteration 10

The prompt was a website for a fictional Dutch art museum.

- **Iteration 9:** a clean, dark-themed landing page. Polished but expected.
- **Iteration 10:** the generator scrapped that approach and built a spatial experience: a 3D room with a checkered floor rendered in CSS perspective, artwork placed free-form on the walls, and navigation between gallery rooms through doorways instead of scrolling or clicking.

The author described this as a creative leap not seen from single-pass generation.

## Three-agent full-stack harness: planner, generator, evaluator (V1, Opus 4.5)

The roles:

- **Planner:** expands a 1 to 4 sentence prompt into a full product spec. Told to be ambitious in scope, to stay high-level on technical design (to avoid cascading errors from early wrong details), and to weave in AI features. It had the frontend design skill to define a visual language.
- **Generator:** works in sprints, one feature at a time. Stack: React, Vite, FastAPI, SQLite (later PostgreSQL). Self-evaluates at the end of each sprint before QA and uses git for version control.
- **Evaluator:** uses the Playwright MCP to click through the running app and test the UI, API endpoints, and database state.

Agents communicate through files: one writes, another reads and replies in the same file or a new one.

## Sprint contracts and hard-threshold grading

Definitions:

- **Sprint:** a chunk of work covering one feature.
- **Sprint contract:** an agreement between generator and evaluator, made before building, on what "done" means for the sprint and how it will be tested.

Grading per sprint:

- The evaluator grades against the bugs it finds and four criteria: product depth, functionality, visual design, and code quality.
- Each criterion has a hard threshold. If any one fails, the sprint fails.
- Contracts were detailed: in the retro game maker build, sprint 3 alone had 27 evaluator criteria.

## Retro game maker: solo agent vs full harness (cost and quality)

The same prompt run two ways on Opus 4.5:

- **Solo agent:** 20 minutes, $9.
- **Full harness (V1):** 6 hours, $200, over 20 times the cost. The planner's spec had 16 features across 10 sprints.

Solo result:

- Layout wasted space with fixed-height panels.
- Rigid workflow with no guidance to create sprites and entities before populating a level.
- The game was broken: entities appeared but did not respond to input, because the wiring between entity definitions and the runtime was faulty, with nothing on the surface indicating it.

Full harness result:

- Canvas used the full viewport, richer sprite editor, and an AI integration that generated game parts from prompts. The game was playable.
- Remaining issues: rough physics (a character overlapped a platform after jumping on it), an AI-built level with a wall the character could not jump past, and a still-unclear workflow.

## Bugs the QA evaluator caught in the retro game maker

Three failures the evaluator found by exercising the running app:

- **Rectangle fill tool:** placed tiles only at the drag start and end points. A `fillRectangle` function existed but was not triggered properly on mouse-up.
- **Entity deletion:** the Delete key handler at `LevelEditor.tsx:892` required both `selection` and `selectedEntityId`, but clicking an entity set only `selectedEntityId`.
- **Animation frame reorder:** the `PUT /frames/reorder` route was defined after `/{frame_id}`, so FastAPI tried to parse "reorder" as an integer and returned 422.

The suggested fix for entity deletion was a looser condition:

```ts
selection || (selectedEntityId && activeLayer === 'entity')
```

The FastAPI one is a general gotcha: declare fixed paths before parameterised paths at the same level.

## Tuning the QA evaluator: it talks itself into approving

Out of the box, Claude as QA had two problems:

- It identified real issues and then talked itself into approving the work anyway.
- It tested superficially.

The fix took several rounds of reading the evaluator's logs and updating the QA prompt wherever its judgment diverged from the author's.

## Simplifying the harness for Opus 4.6: what was removed and kept

Changes from V1 (Opus 4.5) to V2 (Opus 4.6):

- **Sprints removed.** Opus 4.6 plans more carefully and sustains tasks longer, so the generator builds in one continuous run.
- **Evaluator kept, moved to a single pass at the end** instead of per sprint.
- **Planner kept.** Without it, the generator under-scoped the product.
- **Added:** prompting so the generator builds a proper AI agent that drives the app's own features through tools. Training data on this was thin, so it needed tuning.

Method lesson: the first attempt cut too much at once, performance dropped, and the author could not tell which parts were load-bearing. The approach that worked was removing one component at a time and measuring the effect.

## When an evaluator agent is worth its cost

The evaluator's value depends on whether the task sits beyond what the current model does reliably on its own.

- On Opus 4.5 that boundary was close, so the evaluator caught many issues.
- On Opus 4.6 many tasks fell inside the generator's ability, making per-sprint grading unnecessary overhead.
- Parts of a build at the edge of the model's capability still benefited from evaluation.

So an evaluator is not a fixed yes or no decision. It should be placed where the model is unreliable, and that location moves with each model release.

## DAW build on the simplified harness: per-agent time and cost

Prompt: build a fully featured digital audio workstation (DAW) in the browser using the Web Audio API. Run on the V2 harness with Opus 4.6.

- Planner: 4.7 min, $0.46
- Build round 1: 2 hr 7 min, $71.08
- QA round 1: 8.8 min, $3.24
- Build round 2: 1 hr 2 min, $36.89
- QA round 2: 6.8 min, $3.09
- Build round 3: 10.9 min, $5.88
- QA round 3: 9.6 min, $4.06
- Total: 3 hr 50 min, $124.70

The article's text says "about 4 hours". The per-step figures total 3 hr 50 min.

Building dominates the cost. Planning and QA together are a small fraction of the total.

## DAW build: what QA found and what the result could do

QA round 1 praised design fidelity, the AI agent, and the backend, but found core features were display-only:

- Clips could not be dragged.
- No instrument panels (synth knobs, drum pads).
- No visual effect editors (EQ curves, compressor meters).

QA round 2 found:

- Audio recording was a stub: the button toggled but did not capture microphone input.
- Clip resize by edge drag and clip split were not implemented.
- Effect visualisations were numeric sliders, not graphical.

Outcome: a working arrangement view, mixer, and transport in the browser. By prompting alone, the in-app agent set tempo and key, laid down a melody, built drums, adjusted mixer levels, and added reverb.

Limits: the author called it far from professional, with weak song composition. Claude cannot hear, which limited QA feedback on musical quality.

## Harness design lessons: components encode stale-able assumptions

The post's stated lessons:

- Each harness component encodes an assumption about what the model cannot do alone. Stress-test those assumptions, because they go stale as models improve.
- Prefer the simplest solution and add complexity only when needed (citing "Building effective agents").
- When a new model arrives, re-examine the harness: remove parts that no longer carry weight, and add parts that enable new capability.
- Decompose complex tasks and use specialised agents where there is headroom.
- Experiment with the target model, read its traces on realistic problems, and tune against the outcomes you want.
- The space of interesting harness designs does not shrink as models improve. It shifts.

The post also mentions the "Ralph Wiggum method", a community approach using hooks or scripts to keep agents in continuous iteration loops.

## Costs and limits of multi-agent harnesses

What the harness costs and where it still falls short:

- Harnesses add cost, latency, token overhead, and orchestration complexity: $200 versus $9 for the game maker, and $124.70 for the DAW.
- Output was still imperfect: physics bugs, layout issues, unintuitive interactions, and undiscovered bugs in deeply nested features. The author sees more headroom in verification.
- The generator lacked product intuition in places, such as an unclear build order in the game maker.
- Results come from specific prompts and the author's own preferences, so they may not generalise.
- Future models may make parts of this scaffolding unnecessary.
