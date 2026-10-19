"""The JSON protocol used by the Node host plugin."""

from __future__ import annotations

import json

from exam_solver.ops import handle_request


def test_ping():
    response = handle_request({"op": "ping", "payload": {}})
    assert response["ok"] is True
    assert response["data"]["pong"] is True
    assert response["data"]["engine_version"]


def test_status_reports_features():
    response = handle_request({"op": "status", "payload": {}})
    assert response["ok"] is True
    assert "sympy" in response["data"]["features"]
    assert response["data"]["python"]


def test_unknown_op_is_a_structured_error():
    response = handle_request({"op": "explode", "payload": {}})
    assert response["ok"] is False
    assert response["error"]["code"] == "unknown_op"


def test_invalid_request_is_a_structured_error():
    response = handle_request({})
    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request"


def test_validate_spec_returns_sanitized_copy(quadratic_problem):
    spec = dict(quadratic_problem)
    spec["extra_field"] = "should be dropped"
    response = handle_request({"op": "validate_spec", "payload": {"kind": "problem", "spec": spec}})
    assert response["ok"] is True
    data = response["data"]
    assert data["valid"] is True
    assert "extra_field" not in data["sanitized"]
    assert data["removed_top_level_keys"] == ["extra_field"]


def test_validate_spec_reports_errors():
    response = handle_request(
        {"op": "validate_spec", "payload": {"kind": "diagram", "spec": {"type": "geometry"}}}
    )
    assert response["ok"] is True
    assert response["data"]["valid"] is False
    assert response["data"]["errors"]


def test_render_diagram_op(tmp_path, geometry_diagram):
    response = handle_request(
        {
            "op": "render_diagram",
            "payload": {
                "diagram": geometry_diagram,
                "outDir": str(tmp_path),
                "basename": "ops-diagram",
                "formats": ["svg"],
            },
        }
    )
    assert response["ok"] is True
    assert response["data"]["files"]["svg"].endswith("ops-diagram.svg")


def test_validate_diagram_op(geometry_diagram, geometry_problem):
    response = handle_request(
        {"op": "validate_diagram", "payload": {"diagram": geometry_diagram, "problemSpec": geometry_problem}}
    )
    assert response["ok"] is True
    assert response["data"]["passed"] is True


def test_validate_diagram_op_reports_schema_failure():
    response = handle_request(
        {"op": "validate_diagram", "payload": {"diagram": {"type": "geometry", "points": {}}}}
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_diagram_spec"


def test_validate_solution_op(quadratic_problem, quadratic_answer):
    response = handle_request(
        {
            "op": "validate_solution",
            "payload": {"problemSpec": quadratic_problem, "answerSpec": quadratic_answer},
        }
    )
    assert response["ok"] is True
    assert response["data"]["passed"] is True
    assert response["data"]["checks"]


def test_grade_answer_op(quadratic_problem, quadratic_answer):
    validation = handle_request(
        {"op": "validate_solution", "payload": {"problemSpec": quadratic_problem, "answerSpec": quadratic_answer}}
    )["data"]
    response = handle_request(
        {
            "op": "grade_answer",
            "payload": {
                "problemSpec": quadratic_problem,
                "answerSpec": quadratic_answer,
                "validationReport": validation,
            },
        }
    )
    assert response["ok"] is True
    assert response["data"]["max_score"] > 0
    assert response["data"]["source"] == "internal_estimate"


def test_batch_requests_run_in_one_process(quadratic_problem, quadratic_answer):
    response = handle_request(
        {
            "ops": [
                {"op": "ping", "payload": {}},
                {"op": "validate_solution", "payload": {"problemSpec": quadratic_problem, "answerSpec": quadratic_answer}},
                {"op": "does_not_exist", "payload": {}},
            ]
        }
    )
    assert response["ok"] is False
    assert [item["ok"] for item in response["results"]] == [True, True, False]


def test_analyze_function_op():
    response = handle_request({"op": "analyze_function", "payload": {"expression": "x**2 - 4"}})
    assert response["ok"] is True
    assert response["data"]["roots"] == [-2.0, 2.0]


def test_responses_are_ascii_escaped():
    response = handle_request(
        {"op": "validate_spec", "payload": {"kind": "problem", "spec": {"subject": "math", "problem_type": "other", "raw_text": "中文题干"}}}
    )
    encoded = json.dumps(response, ensure_ascii=True)
    assert "\\u4e2d" in encoded
