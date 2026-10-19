"""SymPy-backed solution validation."""

from __future__ import annotations

import copy

from exam_solver.validators.math_validator import parse_assignments, validate_math


def test_valid_solution_passes(quadratic_problem, quadratic_answer):
    report = validate_math(quadratic_problem, quadratic_answer)
    assert report["passed"], report["contradictions"]
    assert report["coverage"]["claimed_checks"] == len(quadratic_answer["verification"])


def test_wrong_root_is_caught(quadratic_problem, quadratic_answer):
    bad = copy.deepcopy(quadratic_answer)
    bad["verification"] = [
        {"kind": "equation_substitution", "equation": "x**2-5*x+6=0", "assignments": {"x": "4"}}
    ]
    report = validate_math(quadratic_problem, bad)
    assert not report["passed"]
    assert "residual" in report["contradictions"][0]


def test_wrong_derivative_is_caught(quadratic_problem, quadratic_answer):
    bad = copy.deepcopy(quadratic_answer)
    bad["verification"] = [{"kind": "derivative", "expression": "x**3", "variable": "x", "claimed": "3*x"}]
    report = validate_math(quadratic_problem, bad)
    assert not report["passed"]


def test_integral_check_uses_antiderivative(quadratic_problem, quadratic_answer):
    good = copy.deepcopy(quadratic_answer)
    good["verification"] = [{"kind": "integral", "expression": "2*x", "variable": "x", "claimed": "x**2"}]
    assert validate_math(quadratic_problem, good)["passed"]
    bad = copy.deepcopy(quadratic_answer)
    bad["verification"] = [{"kind": "integral", "expression": "2*x", "variable": "x", "claimed": "x**3"}]
    assert not validate_math(quadratic_problem, bad)["passed"]


def test_definite_integral(quadratic_problem, quadratic_answer):
    claim = {
        "kind": "integral",
        "expression": "x",
        "variable": "x",
        "claimed": "1/2",
        "lower": "0",
        "upper": "1",
    }
    answer = copy.deepcopy(quadratic_answer)
    answer["verification"] = [claim]
    assert validate_math(quadratic_problem, answer)["passed"]


def test_identity_with_trigonometry(quadratic_problem, quadratic_answer):
    answer = copy.deepcopy(quadratic_answer)
    answer["verification"] = [{"kind": "identity", "lhs": "sin(2*x)", "rhs": "2*sin(x)*cos(x)"}]
    assert validate_math(quadratic_problem, answer)["passed"]


def test_numeric_tolerance(quadratic_problem, quadratic_answer):
    answer = copy.deepcopy(quadratic_answer)
    answer["verification"] = [{"kind": "numeric", "expression": "sqrt(2)", "expected": "1.414", "tolerance": 1e-3}]
    assert validate_math(quadratic_problem, answer)["passed"]
    answer["verification"] = [{"kind": "numeric", "expression": "sqrt(2)", "expected": "1.5", "tolerance": 1e-6}]
    assert not validate_math(quadratic_problem, answer)["passed"]


def test_unparsable_claim_is_skipped_not_failed(quadratic_problem, quadratic_answer):
    answer = copy.deepcopy(quadratic_answer)
    answer["verification"] = [{"kind": "identity", "lhs": "%%%", "rhs": "1"}]
    report = validate_math(quadratic_problem, answer)
    assert report["passed"]
    assert report["coverage"]["skipped_checks"] >= 1


def test_auto_derived_substitution_when_solver_provides_none(quadratic_problem):
    answer = {
        "steps": [{"step": 1, "content": "x=2 或 x=3", "score_relevance": "key"}],
        "final_answer": "故 x = 2 或 x = 3。",
        "verification": [],
    }
    report = validate_math(quadratic_problem, answer)
    auto_checks = [check for check in report["checks"] if check["name"].startswith("equation_substitution")]
    assert len(auto_checks) == 2
    assert all(check["passed"] for check in auto_checks)


def test_auto_derived_substitution_catches_bad_final_answer(quadratic_problem):
    answer = {
        "steps": [{"step": 1, "content": "x=4", "score_relevance": "key"}],
        "final_answer": "故 x = 4。",
        "verification": [],
    }
    report = validate_math(quadratic_problem, answer)
    assert not report["passed"]


def test_parse_assignments_handles_chinese_lists():
    assignments = parse_assignments("所以 x = 2 或 x = 3，y = -1。")
    assert assignments["x"] == ["2", "3"]
    assert assignments["y"] == ["-1"]


def test_parse_assignments_ignores_bare_expressions():
    assignments = parse_assignments("x = 2 + sqrt(3)")
    assert assignments.get("x", []) == []


def test_missing_final_answer_fails(quadratic_problem):
    report = validate_math(quadratic_problem, {"steps": [], "final_answer": ""})
    assert not report["passed"]
