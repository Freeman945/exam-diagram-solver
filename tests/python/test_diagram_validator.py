"""Coordinate-level checks between a diagram and the stated relations."""

from __future__ import annotations

import copy

from exam_solver.validators.diagram_validator import validate_diagram


def test_fixture_diagram_matches_its_problem(geometry_diagram, geometry_problem):
    report = validate_diagram(geometry_diagram, geometry_problem)
    assert report["passed"], report["contradictions"]
    names = {check["name"] for check in report["checks"]}
    assert "relation:equal_length:AB-AC" in names
    assert "relation:midpoint:D-BC" in names
    assert "relation:perpendicular:AD-BC" in names


def test_perpendicular_violation_is_caught(geometry_diagram):
    broken = copy.deepcopy(geometry_diagram)
    broken["points"]["D"] = [1, 0.4]
    report = validate_diagram(broken, {"visual_relations": [{"type": "perpendicular", "objects": ["AD", "BC"]}]})
    assert not report["passed"]
    assert any("perpendicular" in item for item in report["contradictions"])


def test_collinear_violation_is_caught(geometry_diagram):
    broken = copy.deepcopy(geometry_diagram)
    broken["points"]["D"] = [0, 1]
    report = validate_diagram(broken, {"visual_relations": [{"type": "collinear", "objects": ["B", "D", "C"]}]})
    assert not report["passed"]


def test_equal_length_violation_is_caught(geometry_diagram):
    broken = copy.deepcopy(geometry_diagram)
    broken["points"]["A"] = [0.5, 3]
    report = validate_diagram(broken, {"visual_relations": [{"type": "equal_length", "objects": ["AB", "AC"]}]})
    assert not report["passed"]


def test_point_on_segment_accepts_both_spellings(geometry_diagram):
    for objects in (["D", "BC"], ["D", "B", "C"]):
        report = validate_diagram(geometry_diagram, {"visual_relations": [{"type": "point_on_segment", "objects": objects}]})
        assert report["passed"], report["contradictions"]


def test_point_on_circle(geometry_diagram):
    spec = copy.deepcopy(geometry_diagram)
    spec["circles"] = [{"center": "D", "through": "A", "label": "circle_D"}]
    passing = validate_diagram(spec, {"visual_relations": [{"type": "point_on_circle", "objects": ["A", "circle_D"]}]})
    assert passing["passed"], passing["contradictions"]
    failing = validate_diagram(spec, {"visual_relations": [{"type": "point_on_circle", "objects": ["B", "circle_D"]}]})
    assert not failing["passed"]


def test_concyclic_detection(geometry_diagram):
    report = validate_diagram(geometry_diagram, {"visual_relations": [{"type": "concyclic", "objects": ["A", "B", "C"]}]})
    # Three points are always concyclic, so this must pass.
    assert report["passed"]
    report = validate_diagram(
        geometry_diagram,
        {"visual_relations": [{"type": "concyclic", "objects": ["A", "B", "C", "D"]}]},
    )
    # D is inside the triangle, so it cannot be on the circumcircle.
    assert not report["passed"]


def test_unsupported_relation_is_skipped_not_failed(geometry_diagram):
    report = validate_diagram(geometry_diagram, {"visual_relations": [{"type": "angle_equals", "objects": ["ABC", "DEF"]}]})
    assert report["passed"]
    assert any(check.get("skipped") for check in report["checks"])


def test_structure_check_reports_undefined_point(geometry_diagram):
    broken = copy.deepcopy(geometry_diagram)
    broken["segments"].append(["A", "Z"])
    report = validate_diagram(broken, {})
    assert not report["passed"]
    assert any("Z" in item for item in report["contradictions"])


def test_coincident_points_warn(geometry_diagram):
    broken = copy.deepcopy(geometry_diagram)
    broken["points"]["E"] = [0, 0]
    report = validate_diagram(broken, {})
    warnings = [check for check in report["checks"] if check["name"] == "geometry:distinct_points"]
    assert warnings and warnings[0]["passed"] is False


def test_non_geometry_diagrams_skip_relation_checks():
    report = validate_diagram({"type": "force", "forces": [{"label": "mg", "angle_deg": 270}]}, {})
    assert report["passed"]
    assert report["coverage"]["skipped_checks"] >= 1
