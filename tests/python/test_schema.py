"""Schema loading and strict validation."""

from __future__ import annotations

import copy

import pytest

from exam_solver.schema import load_schema, sanitize, validate


def test_schemas_load():
    for name in ("problem_spec", "diagram_spec", "answer_spec", "validation_report", "exam_report"):
        schema = load_schema(name)
        assert schema["$schema"].startswith("https://json-schema.org")


def test_valid_diagram_passes(geometry_diagram):
    schema = load_schema("diagram_spec")
    assert validate(geometry_diagram, schema) == []


def test_unknown_geometry_field_is_rejected_after_sanitize(geometry_diagram):
    schema = load_schema("diagram_spec")
    broken = copy.deepcopy(geometry_diagram)
    broken["points"]["A"] = [0, 3]
    broken["magic"] = True
    cleaned = sanitize(broken, schema)
    assert "magic" not in cleaned
    assert validate(cleaned, schema) == []


def test_unknown_point_reference_is_not_a_schema_error(geometry_diagram):
    # Schema validation only checks shape; relation checks catch unknown points.
    schema = load_schema("diagram_spec")
    broken = copy.deepcopy(geometry_diagram)
    broken["segments"].append(["A", "Z"])
    cleaned = sanitize(broken, schema)
    assert validate(cleaned, schema) == []


def test_bad_point_type_is_reported(geometry_diagram):
    schema = load_schema("diagram_spec")
    broken = copy.deepcopy(geometry_diagram)
    broken["points"]["A"] = ["zero", 3]
    errors = validate(broken, schema)
    assert errors, "string coordinate must be rejected"


def test_diagram_type_discriminator_is_enforced(geometry_diagram):
    schema = load_schema("diagram_spec")
    broken = copy.deepcopy(geometry_diagram)
    broken["type"] = "painting"
    errors = validate(broken, schema)
    assert errors


def test_sanitize_coerces_numeric_strings():
    schema = load_schema("diagram_spec")
    spec = {
        "type": "force",
        "forces": [{"label": "mg", "angle_deg": "270", "magnitude": "10"}],
    }
    cleaned = sanitize(spec, schema)
    assert cleaned["forces"][0]["angle_deg"] == 270
    assert validate(cleaned, schema) == []


def test_problem_spec_required_fields():
    schema = load_schema("problem_spec")
    assert validate({"subject": "math"}, schema)
    ok = {"subject": "math", "problem_type": "other", "raw_text": "x"}
    assert validate(ok, schema) == []


def test_answer_spec_rejects_unknown_verification_kind(quadratic_answer):
    schema = load_schema("answer_spec")
    bad = copy.deepcopy(quadratic_answer)
    bad["verification"] = [{"kind": "trust_me", "claim": "it is correct"}]
    assert validate(bad, schema)


def test_sanitize_drops_unknown_answer_fields(quadratic_answer):
    schema = load_schema("answer_spec")
    bad = copy.deepcopy(quadratic_answer)
    bad["internal_debug"] = {"prompt": "..."}
    cleaned = sanitize(bad, schema)
    assert "internal_debug" not in cleaned
    assert validate(cleaned, schema) == []


def test_sanitize_resolves_nested_refs_in_oneof():
    """Regression: coordinate ranges use $ref and must survive sanitisation."""

    schema = load_schema("diagram_spec")
    spec = {
        "type": "coordinate",
        "x_range": ["-5", 5],
        "curves": [{"expr": "1/x", "domain": [0.1, 3]}],
    }
    cleaned = sanitize(spec, schema)
    assert cleaned["x_range"] == [-5, 5]
    assert validate(cleaned, schema) == []


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "circuit", "components": [{"kind": "resistor", "from": "A", "to": "B"}]},
        {"type": "chart", "series": [{"points": [[0, 1], [1, 2]]}]},
        {"type": "optics", "surfaces": [{"kind": "mirror", "from": [0, -1], "to": [0, 1]}], "rays": [{"points": [[-1, 1], [0, 0], [1, 1]]}]},
    ],
)
def test_other_diagram_types_validate(spec):
    schema = load_schema("diagram_spec")
    assert validate(spec, schema) == []
