"""Benchmark dataset integrity and ground-truth consistency.

The benchmark does not claim end-to-end accuracy by itself. What it does prove
here is that every recorded expected answer is actually consistent: the same
SymPy / unit machinery the plugin uses accepts it, and the diagram-decision
labels agree with the rules under test in ``tests/node/benchmark.test.mjs``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from exam_solver.validators import validate_math, validate_physics

BENCHMARK = Path(__file__).resolve().parents[2] / "benchmark" / "cases.jsonl"

REQUIRED_KEYS = {
    "id",
    "subject",
    "grade",
    "problem_type",
    "question_format",
    "text",
    "answer",
    "solution",
    "checks",
    "needs_diagram",
    "diagram_type",
}
SUBJECTS = {"math", "physics"}
DIAGRAM_TYPES = {"none", "geometry", "coordinate", "function", "force", "circuit", "optics", "chart"}


def load_cases() -> list[dict]:
    cases = []
    for line_number, line in enumerate(BENCHMARK.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:  # pragma: no cover - broken data
            raise AssertionError(f"benchmark line {line_number} is not valid JSON: {exc}") from exc
    return cases


CASES = load_cases()


def test_benchmark_size():
    assert len(CASES) >= 30, f"expected at least 30 cases, found {len(CASES)}"


def test_benchmark_structure():
    for case in CASES:
        missing = REQUIRED_KEYS - set(case)
        assert not missing, f"{case.get('id')}: missing keys {missing}"
        assert case["subject"] in SUBJECTS
        assert isinstance(case["text"], str) and case["text"].strip()
        assert isinstance(case["answer"], str) and case["answer"].strip()
        assert isinstance(case["checks"], list)
        assert isinstance(case["needs_diagram"], bool)
        assert case["diagram_type"] in DIAGRAM_TYPES


def test_benchmark_ids_are_unique():
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids)), "duplicate benchmark ids"


def test_benchmark_coverage():
    subjects = {case["subject"] for case in CASES}
    assert subjects == {"math", "physics"}
    math_cases = [case for case in CASES if case["subject"] == "math"]
    physics_cases = [case for case in CASES if case["subject"] == "physics"]
    assert len(math_cases) >= 12
    assert len(physics_cases) >= 8
    diagram_cases = [case for case in CASES if case["needs_diagram"]]
    assert len(diagram_cases) >= 8, "the benchmark must include diagram-requiring problems"
    types = {case["diagram_type"] for case in diagram_cases}
    assert {"geometry", "function", "force"} <= types
    assert {"circuit", "optics"} & types


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_ground_truth_checks_pass(case):
    problem = {
        "subject": case["subject"],
        "problem_type": case["problem_type"],
        "question_format": case["question_format"],
        "raw_text": case["text"],
    }
    answer = {
        "steps": [
            {
                "step": 1,
                "content": case["solution"],
                "reason": "标准解法",
                "score_relevance": "key",
            }
        ],
        "final_answer": case["answer"],
        "verification": case["checks"],
    }
    math_report = validate_math(problem, answer)
    assert math_report["passed"], f"{case['id']} math checks failed: {math_report['contradictions']}"
    if case["subject"] == "physics":
        physics_report = validate_physics(problem, answer)
        assert physics_report["passed"], f"{case['id']} unit checks failed: {physics_report['contradictions']}"


@pytest.mark.parametrize("case", [case for case in CASES if case["checks"]], ids=lambda case: case["id"])
def test_every_declared_check_is_executed(case):
    problem = {"subject": case["subject"], "problem_type": case["problem_type"], "raw_text": case["text"]}
    answer = {
        "steps": [{"step": 1, "content": case["solution"], "score_relevance": "key"}],
        "final_answer": case["answer"],
        "verification": case["checks"],
    }
    report = validate_math(problem, answer)
    executed = [check for check in report["checks"] if not check.get("skipped")]
    if case["subject"] == "physics":
        # unit_check claims are executed by the physics validator.
        executed += [
            check
            for check in validate_physics(problem, answer)["checks"]
            if not check.get("skipped")
        ]
    # Every declared verification claim must be represented in a report.
    for index, claim in enumerate(case["checks"]):
        assert any(
            check["name"].startswith(str(claim.get("kind"))) for check in executed
        ), f"{case['id']} claim {index} ({claim.get('kind')}) was not executed"
