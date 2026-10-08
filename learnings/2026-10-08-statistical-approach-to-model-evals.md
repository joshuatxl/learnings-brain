---
title: "Error bars for LLM evals: Anthropic's five statistical recommendations"
date: 2024-11-19
tags: [evals, statistics, standard-error, confidence-intervals, llm-evaluation, anthropic]
source: https://www.anthropic.com/research/statistical-approach-to-model-evals
---

# Error bars for LLM evals: Anthropic's five statistical recommendations

Anthropic research post (November 2024) summarising the paper "Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations" (arXiv:2411.00640). It addresses one question: when one model beats another on a benchmark, is the gap real or an artifact of which questions happened to be in the eval? Formulas in this note marked "standard result" are textbook statistics added for completeness, not quoted from the post.

## Question universe: an eval score estimates an underlying skill

The framing behind all five recommendations:

- An eval is many questions, each scored separately. The headline score is usually the simple average.
- The **question universe** is a hypothetical population of all possible questions of the kind the eval samples. The actual eval is treated as a random draw from it.
- The **observed average** is the score measured on the eval's actual questions.
- The **theoretical average** is the score across the whole question universe. This is the model's underlying skill, and it is what should be estimated, because it does not depend on the luck of the draw.

Analytic robustness: if a new eval with the same difficulty distribution were built, the conclusions should generally still hold.

## Recommendation 1: report the standard error and 95% confidence interval

By the Central Limit Theorem (CLT), means of random samples from the same distribution tend towards a normal distribution under mild conditions. This holds even though eval questions are unrelated to each other, such as MMLU items ranging from virology to algebra.

- **Standard error of the mean (SEM):** the standard deviation of the sampling distribution of the mean. It measures how precise the score estimate is.
- **95% confidence interval:** mean ± 1.96 × SEM.

```text
SEM    = s / sqrt(n)          (standard result)
95% CI = mean ± 1.96 × SEM
```

Here `s` is the standard deviation of the per-question scores and `n` is the number of questions.

Recommendation: report the SEM and 95% CI alongside every eval score.

## Recommendation 2: cluster standard errors when questions share a passage

Many evals group several questions around one shared item. Reading comprehension benchmarks such as DROP, QuAC, RACE, and SQuAD ask multiple questions about the same passage.

- Those questions are not independent draws. Several questions on one passage carry less information than the same number of questions on different passages.
- A naive CLT calculation therefore underestimates the SEM.
- The consequence is detecting a difference between models that does not actually exist.

Fix: compute **clustered standard errors**, clustering on the **unit of randomization**, which is the level at which questions were effectively sampled (the passage). The technique is borrowed from the social sciences, and the paper gives the formulas.

Size of the effect: on popular evals, clustered standard errors can be over three times as large as naive ones.

## Recommendation 3: reduce within-question variance (law of total variance)

A model's score on a single question splits into two parts:

- The **mean score** for that question: the expected score if the model were asked it infinitely many times.
- A **random component**: the realised score minus that mean.

By the law of total variance, the variance of the score is the average within-question variance plus the variance of the question-level means. Shrinking the random (within-question) part shrinks the overall SEM.

```text
Var(score) = E[ Var(score | question) ] + Var( E[score | question] )
```

Standard consequence: averaging K independent samples per question divides the first term by K and leaves the second unchanged. Resampling cannot remove the variance that comes from which questions were drawn.

### Resampling answers for chain-of-thought evals

With chain-of-thought (CoT) reasoning the answer is path dependent, so it varies between runs.

- Sample several answers per question from the same model and average them per question.
- Use those question-level averages in the CLT and SEM calculations.
- The post gives no specific number of resamples. Power analysis (recommendation 5) is the tool for choosing it.
- The Inspect evals framework computes standard errors this way through its `epochs` parameter.

### Next-token probabilities for non-chain-of-thought evals

Without CoT the answer is not path dependent, and the random component can often be removed entirely.

- Example: for a multiple-choice question whose correct answer is "B", use the model's probability of emitting the token "B" as the question's score, instead of sampling an answer and grading it right or wrong.
- This gives the question's mean score directly with no sampling noise.
- At the time of writing, the authors were not aware of any open-source evals framework implementing this.

## Recommendation 4: compare models with paired differences, not a two-sample test

Eval scores only mean something relative to other scores.

- A two-sample t-test using each model's SEM is valid but ignores that both models answered the same questions.
- A **paired-differences test** compares the models question by question. This removes the variance due to question difficulty and isolates the variance in the responses.
- The standard error of the mean difference depends on the Pearson correlation between the two models' per-question scores. Higher correlation gives a smaller standard error.

```text
SE_diff = sqrt( SE_A^2 + SE_B^2 - 2 * rho * SE_A * SE_B )   (standard result)
```

Key number: per-question score correlations between frontier models on popular evals are roughly 0.3 to 0.7. Frontier models tend to get the same questions right and wrong, so pairing is a free variance reduction.

Recommendation: when comparing models, report mean differences, standard errors, confidence intervals, and correlations for each pair.

### Paired differences worked example (my own illustration)

Illustrative numbers, not from the post. Two models each have SEM = 1.5 percentage points on the same questions.

- Unpaired (rho = 0): SE_diff = sqrt(1.5² + 1.5²) ≈ 2.12 points.
- Paired with rho = 0.5: SE_diff = sqrt(2.25 + 2.25 − 2 × 0.5 × 2.25) = 1.5 points.

A 3.5-point gap is 1.65 standard errors unpaired (not significant at the 95% level) but 2.33 standard errors paired (significant). Same data, different conclusion, purely from using the pairing.

## Recommendation 5: use power analysis to size an eval

**Statistical power** is the probability that a test detects a real difference when one exists. Small evals give wide confidence intervals, so only large capability gaps reach significance and small ones are missed.

Power analysis links four quantities, any one of which can be solved for from the other three:

- Number of observations (questions).
- Power.
- False positive rate (significance level).
- Effect size (for example a 3-percentage-point gap).

The paper shows how to state a hypothesis such as "Model A beats Model B by 3 percentage points" and compute how many questions are needed to test it against the null hypothesis that they are tied.

### What power analysis is used for in evals

Practical uses listed in the post:

- Deciding how many times to resample answers per question.
- Deciding how small a random subsample of questions can be while keeping the desired power.
- Deciding that an eval with too few questions is not worth running for a particular pair of models.
- Helping authors of new evals choose how many questions to include.

## Checklist for reporting LLM eval results with statistical rigour

The five recommendations as a checklist:

1. Report the SEM and 95% CI with every score.
2. If questions share a passage or other common source, cluster the standard errors on that unit.
3. Reduce within-question noise: resample and average for CoT evals, or use next-token probabilities for non-CoT evals.
4. Compare models with paired differences and report the correlation.
5. Run a power analysis to check the eval is large enough to detect the difference you care about.

Caveat from the post: statistics is only one part of a "science of evals" that is still underdeveloped. Error bars tell you how precise a measurement is, not whether the eval measures the right thing.
