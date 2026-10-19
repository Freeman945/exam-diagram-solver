"""Unit, dimension and magnitude checks."""

from __future__ import annotations

from exam_solver.validators.physics_validator import parse_quantities, parse_unit, validate_physics

PHYSICS_PROBLEM = {
    "subject": "physics",
    "problem_type": "kinematics",
    "raw_text": "物体以 2m/s² 加速 5s，初速 0，求末速度。",
}

MATH_PROBLEM = {"subject": "math", "problem_type": "equation_solving"}


def answer(final, verification=None):
    return {
        "steps": [{"step": 1, "content": "v = u + a t = 2×5 = 10 m/s", "score_relevance": "key"}],
        "final_answer": final,
        "verification": verification or [],
    }


def test_parse_unit_dimensions():
    assert parse_unit("m/s")[0] == {"L": 1, "T": -1}
    assert parse_unit("kg·m/s^2")[0] == {"L": 1, "T": -2, "M": 1}
    assert parse_unit("N")[0] == parse_unit("kg*m/s^2")[0]
    assert parse_unit("Ω")[0] == parse_unit("V/A")[0]
    assert parse_unit("m/s^2")[0] == {"L": 1, "T": -2}
    assert parse_unit("mystery") is None


def test_parse_quantities_reads_units():
    quantities = parse_quantities("v = 10 m/s，方向向右")
    assert quantities[0]["symbol"] == "v"
    assert quantities[0]["value"] == 10
    assert quantities[0]["unit"] == "m/s"


def test_parse_quantities_reads_scientific_notation():
    quantities = parse_quantities("E = 2.5×10^3 J")
    assert quantities[0]["value"] == 2500
    assert quantities[0]["unit"] == "J"


def test_correct_units_pass():
    report = validate_physics(
        PHYSICS_PROBLEM,
        answer(
            "故 v = 10 m/s，方向与加速度方向相同。",
            [{"kind": "unit_check", "value": "10", "unit": "m/s", "dimension": "velocity"}],
        ),
    )
    assert report["passed"], report["contradictions"]


def test_wrong_dimension_is_an_error():
    report = validate_physics(PHYSICS_PROBLEM, answer("故 v = 10 N。"))
    assert not report["passed"]
    assert any("dimension" in item for item in report["contradictions"])


def test_missing_unit_is_an_error_for_physics():
    report = validate_physics(PHYSICS_PROBLEM, answer("故 v = 10。"))
    assert not report["passed"]


def test_absurd_magnitude_is_caught():
    report = validate_physics(PHYSICS_PROBLEM, answer("故 v = 1.0×10^20 m/s。"))
    assert not report["passed"]


def test_declared_unit_check_mismatch():
    report = validate_physics(
        PHYSICS_PROBLEM,
        answer(
            "故 v = 10 m/s。",
            [{"kind": "unit_check", "value": "10", "unit": "J", "dimension": "velocity"}],
        ),
    )
    assert not report["passed"]


def test_math_problems_are_not_penalised_for_units():
    report = validate_physics(MATH_PROBLEM, answer("故 x = 2。"))
    assert report["passed"]
    assert all(check["severity"] == "info" for check in report["checks"])


def test_resistance_dimension_is_correct():
    report = validate_physics(
        {"subject": "physics", "problem_type": "circuit"},
        answer(
            "故 R = 6 Ω。",
            [{"kind": "unit_check", "value": "6", "unit": "Ω", "dimension": "resistance"}],
        ),
    )
    assert report["passed"], report["contradictions"]
