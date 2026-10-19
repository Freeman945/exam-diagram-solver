"""Deterministic examiner rubric."""

from __future__ import annotations

from exam_solver.examiner.scorer import grade_answer


def make_problem(**overrides):
    problem = {
        "subject": "math",
        "problem_type": "equation_solving",
        "question_format": "written_solution",
    }
    problem.update(overrides)
    return problem


def make_answer(**overrides):
    answer = {
        "steps": [
            {"step": 1, "content": "x^2-5x+6=(x-2)(x-3)", "reason": "十字相乘", "score_relevance": "key"},
            {"step": 2, "content": "所以 (x-2)(x-3)=0", "reason": "原方程等价变形", "score_relevance": "normal"},
            {"step": 3, "content": "所以 x=2 或 x=3", "reason": "零因子", "score_relevance": "key"},
        ],
        "final_answer": "故 x = 2 或 x = 3。",
    }
    answer.update(overrides)
    return answer


def passing_validation():
    return {
        "passed": True,
        "checks": [{"name": "ok", "passed": True, "severity": "error"}],
        "contradictions": [],
        "recommended_revision": [],
    }


def test_clean_answer_scores_full_marks():
    report = grade_answer(make_problem(), make_answer(), passing_validation())
    assert report["estimated_score"] == report["max_score"]
    assert report["revision_required"] is False
    assert report["source"] == "internal_estimate"


def test_missing_final_answer_loses_half():
    report = grade_answer(make_problem(), make_answer(final_answer=""), passing_validation())
    assert report["estimated_score"] <= report["max_score"] / 2
    assert report["revision_required"] is True


def test_explicit_answer_without_keyword_is_not_penalised():
    """A precise answer such as “第1问：x=2；第2问：13” is a conclusion."""

    report = grade_answer(
        make_problem(),
        make_answer(final_answer="第1问：x=2 或 x=3；第2问：x1^2+x2^2=13。"),
        passing_validation(),
    )
    assert not any("结论" in item["reason"] for item in report["lost_points"])


def test_question_mark_answer_is_penalised():
    report = grade_answer(make_problem(), make_answer(final_answer="所以答案是什么呢？"), passing_validation())
    assert any("结论" in item["reason"] for item in report["lost_points"])


def test_too_short_answer_is_penalised():
    report = grade_answer(make_problem(), make_answer(final_answer="2"), passing_validation())
    assert any("结论" in item["reason"] for item in report["lost_points"])


def test_validation_failure_forces_revision():
    validation = {
        "passed": False,
        "checks": [{"name": "equation_substitution", "passed": False, "severity": "error"}],
        "contradictions": ["equation_substitution: residual = 2"],
    }
    report = grade_answer(make_problem(), make_answer(), validation)
    assert report["revision_required"] is True
    assert any("验证" in item["reason"] for item in report["lost_points"])


def test_missing_unit_penalised_for_physics():
    problem = make_problem(subject="physics", problem_type="kinematics")
    answer = make_answer(final_answer="故 v = 10。", steps=[{"step": 1, "content": "v=10", "score_relevance": "key"}])
    report = grade_answer(problem, answer, passing_validation())
    assert any("单位" in item["reason"] for item in report["lost_points"])


def test_required_diagram_missing_is_penalised():
    report = grade_answer(
        make_problem(),
        make_answer(),
        passing_validation(),
        diagram={"rendered": False, "role": "final_answer"},
    )
    assert any("图" in item["reason"] for item in report["lost_points"])


def test_diagram_present_is_a_strength():
    report = grade_answer(
        make_problem(),
        make_answer(),
        passing_validation(),
        diagram={"rendered": True, "role": "final_answer"},
    )
    assert any("图" in item for item in report["strengths"])


def test_proof_without_connectors_is_penalised():
    problem = make_problem(problem_type="geometry_proof", question_format="proof")
    answer = make_answer(
        steps=[
            {"step": 1, "content": "AB=AC", "score_relevance": "key"},
            {"step": 2, "content": "D 是中点", "score_relevance": "normal"},
            {"step": 3, "content": "AD⊥BC", "score_relevance": "key"},
        ]
    )
    report = grade_answer(problem, answer, passing_validation())
    assert any("逻辑" in item["reason"] for item in report["lost_points"])


def test_shortcut_words_are_penalised():
    answer = make_answer(
        steps=[
            {"step": 1, "content": "显然 x=2", "score_relevance": "key"},
            {"step": 2, "content": "易得 x=3", "score_relevance": "key"},
            {"step": 3, "content": "所以 x=2 或 x=3", "score_relevance": "normal"},
        ]
    )
    report = grade_answer(make_problem(), answer, passing_validation())
    assert any("显然" in item["reason"] for item in report["lost_points"])


def test_concise_mode_does_not_require_full_derivation():
    report = grade_answer(make_problem(), make_answer(), passing_validation(), answer_mode="concise")
    assert report["revision_required"] is False


def test_score_never_negative():
    validation = {
        "passed": False,
        "checks": [
            {"name": f"check{i}", "passed": False, "severity": "error"} for i in range(12)
        ],
        "contradictions": [f"check{i}" for i in range(12)],
    }
    report = grade_answer(make_problem(), make_answer(final_answer=""), validation)
    assert report["estimated_score"] >= 0
    assert report["score_ratio"] >= 0
