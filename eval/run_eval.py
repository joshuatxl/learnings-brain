"""Runs eval/dataset.py's questions against the live Worker and scores the
results with DeepEval. Manual only -- see ../README.md's Evaluation section.

Usage:
    pip install -r requirements-eval.txt
    export GEMINI_API_KEY=...      # used here as DeepEval's judge model,
                                    # separate from the Worker's own key
    python -m eval.run_eval

Rate limits: each case costs one call to the Worker (which itself calls
Gemini) plus one Gemini call per metric run against it here -- roughly 5
calls per case against the same free-tier quota the Worker uses. Kept
deliberately serial and throttled (see EVAL_MAX_CONCURRENT/EVAL_THROTTLE_S
below) rather than DeepEval's default of up to 20 concurrent judge calls,
which would spike well past a 20-requests/minute limit. CacheConfig is on,
so re-running after fixing one failing case doesn't re-spend quota on the
cases that already passed.
"""
from __future__ import annotations

import os
import sys

import requests
from deepeval import evaluate
from deepeval.evaluate.configs import AsyncConfig, CacheConfig, DisplayConfig, ErrorConfig
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.models import GeminiModel
from deepeval.test_case import LLMTestCase

from eval.dataset import CASES
from ingest.config import GEMINI_API_KEY, SUMMARY_MODEL

WORKER_URL = os.environ.get("WORKER_URL", "https://learnings-brain.joshuatxl.workers.dev")
EVAL_MAX_CONCURRENT = 2
EVAL_THROTTLE_S = 2.0


def ask_worker(question: str) -> dict:
    resp = requests.post(f"{WORKER_URL}/ask", json={"question": question}, timeout=90)
    resp.raise_for_status()
    return resp.json()


def build_test_case(case) -> LLMTestCase | None:
    try:
        data = ask_worker(case.question)
    except requests.RequestException as e:
        print(f"  skip {case.question!r}: Worker call failed ({e})")
        return None
    if "answer" not in data:
        print(f"  skip {case.question!r}: Worker returned an error ({data.get('error')})")
        return None

    citations = data.get("citations", {})
    retrieval_context = [f["text"] for f in citations.get("facts", [])] + citations.get("notes", [])
    return LLMTestCase(
        input=case.question,
        actual_output=data["answer"],
        expected_output=case.expected_output,
        retrieval_context=retrieval_context or None,
    )


def main() -> None:
    if not CASES:
        print("eval/dataset.py has no cases yet -- nothing to run. See its docstring.")
        return
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set (needed for DeepEval's judge model).")
        sys.exit(1)

    print(f"Fetching answers for {len(CASES)} question(s) from {WORKER_URL} ...")
    test_cases = [tc for tc in (build_test_case(c) for c in CASES) if tc is not None]
    if not test_cases:
        print("No test cases could be built (every Worker call failed or errored).")
        return

    judge = GeminiModel(model=SUMMARY_MODEL, api_key=GEMINI_API_KEY, temperature=0.0)
    metrics = [
        AnswerRelevancyMetric(model=judge),
        FaithfulnessMetric(model=judge),
        ContextualPrecisionMetric(model=judge),
        ContextualRecallMetric(model=judge),
    ]

    evaluate(
        test_cases=test_cases,
        metrics=metrics,
        async_config=AsyncConfig(run_async=True, max_concurrent=EVAL_MAX_CONCURRENT, throttle_value=EVAL_THROTTLE_S),
        cache_config=CacheConfig(write_cache=True, use_cache=True),
        error_config=ErrorConfig(ignore_errors=True, skip_on_missing_params=True),
        display_config=DisplayConfig(show_indicator=False),
    )


if __name__ == "__main__":
    main()
