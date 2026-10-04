---
title: "Prompt engineering best practices: Anthropic's core and advanced techniques"
date: 2025-11-10
tags: [prompt-engineering, prompting, claude, llm, context-engineering, anthropic]
source: https://claude.com/blog/best-practices-for-prompt-engineering
---

# Prompt engineering best practices: Anthropic's core and advanced techniques

Anthropic's guide for Claude users (published November 2025, titled for 2026). Its central position: the best prompt is the one that reaches the goal reliably with the minimum necessary structure, not the longest or most complex one. Prompting is described as converging with context engineering for newer models: less scaffolding, more curation.

## Be explicit: state exactly what output you want

Modern models respond well to direct, unambiguous instructions and should not be left to infer what is wanted. If you want comprehensive output, ask for it. If you want specific features, list them.

Example: "Create an analytics dashboard" is vague. Adding a request to include as many relevant features and interactions as possible, and to go beyond the basics to a fully featured implementation, tells the model to exceed the minimum.

Practices:

- Lead with a direct action verb: Write, Analyze, Generate, Create.
- Skip preambles and go straight to the request.
- Say what the output should include, not only what to work on.
- State the quality and depth you expect.

## Give context and motivation: explain why, not just the rule

Explaining why something matters lets the model reason about the underlying goal and make better decisions on related cases the rule did not cover. This works especially well with newer models.

Example: a bare "NEVER use bullet points" is less effective than saying you prefer natural paragraphs because flowing prose is easier for you to read and bullets feel too formal for your casual learning style. The reason lets the model generalise to other formatting choices.

Context worth giving:

- The purpose of, or audience for, the output.
- Why a constraint exists.
- How the output will be used.
- What problem you are trying to solve.

## Be specific: constraints, audience, output structure, restrictions

The more specific the guidelines and requirements, the better the result.

Example: "Create a meal plan for a Mediterranean diet" is vague. A specific version: a Mediterranean plan for pre-diabetic management, 1,800 calories a day, emphasis on low glycemic foods, listing breakfast, lunch, dinner, and one snack with full nutritional breakdowns.

A prompt is specific enough when it includes:

- Clear constraints (word count, format, timeline).
- Relevant context (who the audience is, what the goal is).
- The desired output structure (table, list, paragraph).
- Requirements or restrictions (dietary needs, budget limits, technical constraints).

## Examples (one-shot and few-shot prompting): when to use them

Examples show instead of tell, and clarify subtle requirements that are hard to describe. They are not always necessary.

Use examples when:

- The format is easier to show than to describe.
- A specific tone or style is needed.
- The task involves subtle patterns or conventions.
- Plain instructions have not produced consistent results.

Gotcha: Claude 4.x and similar models pay very close attention to the details of examples. Make sure examples show the behaviour you want, and minimise any patterns you want to avoid, because those get copied too.

Start with one example (one-shot). Add more (few-shot) only if the output still does not match.

## Permission to express uncertainty reduces hallucinations

Explicitly allow the model to say it does not know instead of guessing. This reduces hallucination and makes responses more trustworthy.

Example wording: analyse this financial data and identify trends; if the data is insufficient to draw conclusions, say so instead of speculating.

In structured output, the equivalent is telling the model to return `null` for any value not clearly stated in the source.

## Prefilling the assistant response to force a format

Prefilling means starting the model's response for it, so it continues from your opening text. It is used through the API by adding an assistant message after the user message.

Use it when:

- The output must be JSON, XML, or another structured format.
- You want to skip conversational preamble.
- A specific voice or character must be maintained.
- You want control over how the response begins.

```python
messages = [
    {"role": "user", "content": "Extract name and price from this description as JSON."},
    {"role": "assistant", "content": "{"},
]
```

The model continues from the opening brace and returns only the JSON, instead of prefacing it with a sentence.

In a chat interface, approximate this with an explicit instruction: output only valid JSON with no preamble, and begin the response with an opening brace.

## Chain of thought prompting vs extended thinking

Chain of thought (CoT) asks for step-by-step reasoning before the answer. It helps complex analytical tasks.

Claude's extended thinking feature automates structured reasoning and is generally preferable to manual CoT when available. Manual CoT is still worth using when:

- Extended thinking is not available (the article gives the free Claude.ai plan as an example).
- You need transparent reasoning you can review.
- The task needs multiple analytical steps.
- You want to make sure specific factors are considered.

The two are complementary, not mutually exclusive: explicit CoT can still help on complex tasks even with extended thinking on.

### Three chain of thought implementations: basic, guided, structured

Three levels of control over the reasoning:

- **Basic:** add "Think step-by-step" to the instructions.
- **Guided:** name the reasoning stages. For a donor email: first consider what messaging would appeal given the donor's history, then which parts of the programme would resonate, then write the email.
- **Structured:** use tags to separate reasoning from the answer, so the answer can be extracted.

```text
Think before you write, inside <thinking> tags. First analyse what
messaging suits this donor, then pick the relevant programme aspects.
Then write the final email inside <email> tags.
```

## Controlling output format: say what to do, and match prompt style

Three ways to control formatting:

1. State what to do, not what to avoid. Instead of "do not use markdown", say the response should be smoothly flowing prose paragraphs.
2. Match the prompt's style to the output you want. Formatting in the prompt can influence the response, so reduce markdown in the prompt if you want little markdown back.
3. Be explicit about preferences when you need detailed control. For example: write reports in complete paragraphs, keep markdown mainly for inline code, code blocks, and simple headings, and use lists only for truly discrete items or when the user asks for one.

## Prompt chaining: sequential prompts trading latency for accuracy

Chaining splits a complex task into sequential steps with separate prompts, each output feeding the next. It cannot be done in a single prompt. It is usually built as a workflow or in code, but can be done manually in chat.

Example, a research summary in three prompts:

1. Summarise the medical paper, covering methodology, findings, and clinical implications.
2. Review that summary for accuracy, clarity, and completeness, and give graded feedback.
3. Improve the summary using the feedback.

Use it when:

- A complex request needs breaking into steps.
- Iterative refinement or multi-stage analysis is needed.
- Intermediate validation adds value.
- A single prompt gives inconsistent results.

Trade-off: more latency from multiple API calls, but often much better accuracy and reliability on complex tasks.

## XML tags: less necessary with modern models

XML tags were once the recommended way to structure prompts, especially with large amounts of data. Modern models understand structure well without them.

They may still help when:

- The prompt is extremely complex and mixes several types of content.
- You need to be certain about content boundaries.
- You are working with older model versions.

Modern alternative: clear headings, whitespace, and explicit language (for example "Using the athlete information below...") work as well for most cases with less overhead.

## Role prompting: do not over-constrain the persona

Role prompting assigns an expert persona, such as "You are a financial advisor". With modern models, heavy-handed role prompting is often unnecessary.

Caveat: overly specific roles can limit helpfulness. A plain "You are a helpful assistant" is often better than a world-renowned expert persona who only speaks jargon and never makes mistakes.

It may help when:

- Tone must stay consistent across many outputs.
- An application needs a specific persona.
- You want domain-expertise framing for a complex topic.

Modern alternative: state the perspective you want directly. "Analyze this portfolio, focusing on risk tolerance and long-term growth potential" is often more effective than assigning a role.

## Combining techniques: a JSON extraction prompt

The skill is selecting the right combination, not using every technique. A prompt that extracts financial metrics from a quarterly report can combine five techniques:

- Explicit instruction: name exactly which metrics to extract.
- Context: the data feeds automated processing, so the response must be only valid JSON with no preamble.
- Example structure: show the JSON shape expected.
- Permission to express uncertainty: use `null` for any metric not clearly stated.
- Format control: begin the response with an opening brace.

```json
{
  "revenue": "value with units",
  "profit_margin": "percentage",
  "growth_rate": "percentage"
}
```

## Decision framework for choosing prompt techniques

Work through these in order:

1. Is the request clear and explicit? If not, fix clarity first.
2. Is the task simple? Use only the core techniques: be specific, be clear, give context.
3. Does it need specific formatting? Use examples or prefilling.
4. Is it complex? Consider breaking it down with chaining.
5. Does it need reasoning? Use extended thinking if available, otherwise chain of thought.

Need-to-technique mapping:

- Specific output format: examples, prefilling, or explicit format instructions.
- Step-by-step reasoning: extended thinking or chain of thought.
- Complex multi-stage task: prompt chaining.
- Transparent reasoning: chain of thought with structured output.
- Preventing hallucinations: permission to say "I don't know".

## Troubleshooting prompts: symptom and fix

Common problems and what to change:

- Response too generic: add specificity, examples, or an explicit request for comprehensive output ("go beyond the basics").
- Off-topic or misses the point: be more explicit about the actual goal and give context on why you are asking.
- Inconsistent format: add few-shot examples or prefill the start of the response.
- Task too complex, results unreliable: chain multiple prompts, each doing one thing well.
- Unnecessary preamble: prefill, or ask to skip the preamble and go straight to the answer.
- Made-up information: explicitly permit "I don't know".
- Model suggests changes when you wanted them made: phrase it as an action ("Change this function"), not a question ("Can you suggest changes?").

Start simple, add complexity only when needed, and test whether each addition actually improves results.

## Common prompt engineering mistakes

Pitfalls the article lists:

- Over-engineering: longer, more complex prompts are not always better.
- Ignoring the basics: advanced techniques do not rescue an unclear core prompt.
- Assuming the model reads minds: ambiguity leaves room for misinterpretation.
- Using every technique at once: pick the ones that address the specific problem.
- Not iterating: the first prompt rarely works perfectly, so test and refine.
- Relying on outdated techniques: XML tags and heavy role prompting matter less now. Start with clear, explicit instructions.

## Long content: put critical details at the start or end, and split tasks

Advanced techniques cost tokens: examples, multiple prompts, and detailed instructions all add context overhead, so use them only where they justify it.

- Modern models, including Claude 4.x, have much better context awareness, which helps with the historical "lost-in-the-middle" problem of uneven attention across a long context.
- Splitting large tasks into small, discrete chunks still helps. The reason is focus, not context limits: a task with clear boundaries and a narrow scope produces better results than several objectives in one prompt.
- With long contexts, structure the information clearly and place the most critical details at the beginning or the end.

## Evaluating a prompt: four quick checks

The only way to know a prompt works is to test it. Quick checks:

- Does the output match the specific requirements?
- Did it work in one attempt, or need several iterations?
- Is the format consistent across multiple attempts?
- Does it avoid the common mistakes?

For objective measurement of prompt effectiveness, the article points to Anthropic's prompt engineering course.

## Session-wide instructions belong in CLAUDE.md or skills

Instructions that should apply to every session, not just one prompt, should move out of the prompt into CLAUDE.md files, skills, or other steering methods.

Prompt engineering remains a building block inside context engineering: each prompt becomes part of the larger context, alongside conversation history, attached files, and system instructions, that shapes the model's behaviour.
