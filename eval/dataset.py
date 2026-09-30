"""The evaluation question set. Empty until there are real notes to write
real questions against -- see ../README.md's Evaluation section for why.

expected_output is a reference answer, used only by the two metrics that need
ground truth (ContextualPrecisionMetric, ContextualRecallMetric). Leave it
None to skip just those two for a case and still get AnswerRelevancy and
Faithfulness."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    question: str
    expected_output: str | None = None
    tags: list[str] = field(default_factory=list)


CASES: list[EvalCase] = [
    # Add real cases once real notes are ingested. Shape, not a real case:
    # EvalCase(
    #     question="What have I learned about RAG?",
    #     expected_output=(
    #         "RAG retrieves the most relevant passages by embedding similarity "
    #         "before the LLM generates an answer, rather than relying only on "
    #         "what the model already knows."
    #     ),
    #     tags=["rag"],
    # ),
]
