"""Renderer behaviour: valid output, real structure, and failure modes."""

from __future__ import annotations

import json
import re

import pytest

from exam_solver.diagrams.coordinate import analyze_expression
from exam_solver.diagrams.render import render_diagram
from exam_solver.errors import SpecError


def svg_text(path) -> str:
    return path.read_text(encoding="utf-8")


def test_geometry_renders_points_labels_and_marks(tmp_path, geometry_diagram):
    result = render_diagram(geometry_diagram, out_dir=tmp_path, basename="geo", formats=("svg",))
    assert result.svg and result.png is None
    text = svg_text(tmp_path / "geo.svg")
    assert text.startswith("<svg")
    assert "<circle" in text  # point dots
    assert "<text" in text
    for label in ("A", "B", "C", "D"):
        assert f">{label}</text>" in text
    assert result.elements["points"] == 4
    assert result.elements["segments"] == 4
    # One right-angle mark plus two equal-length ticks.
    assert result.elements["marks"] == 3
    assert result.elements["labels"] == 4


def test_geometry_png_preview_is_written(tmp_path, geometry_diagram):
    result = render_diagram(geometry_diagram, out_dir=tmp_path, basename="geo_png", dpi=100)
    assert result.png is not None
    path = tmp_path / "geo_png.png"
    assert path.stat().st_size > 2000


def test_function_diagram_marks_key_points(tmp_path):
    spec = {
        "type": "function",
        "title": "y = x^2 - 2x - 3",
        "expression": "x**2 - 2*x - 3",
        "grid": True,
        "mark_key_points": True,
    }
    result = render_diagram(spec, out_dir=tmp_path, basename="func", formats=("svg",))
    text = svg_text(tmp_path / "func.svg")
    assert result.spec_type == "function"
    assert result.elements["key_points"] >= 3
    # Axes and tick labels are drawn.
    assert '>x</text>' in text and '>y</text>' in text
    # Key point labels are rounded numbers.
    assert "(-1, 0)" in text and "(1, -4)" in text


def test_function_analysis_is_symbolic():
    analysis = analyze_expression("x**2 - 2*x - 3").as_dict()
    assert analysis["roots"] == [-1.0, 3.0]
    assert analysis["extrema"] == [{"x": 1.0, "y": -4.0}]
    assert analysis["y_intercept"] == -3.0
    assert analysis["error"] is None


def test_rational_function_gets_asymptotes(tmp_path):
    analysis = analyze_expression("1/x").as_dict()
    assert 0.0 in analysis["vertical_asymptotes"]
    result = render_diagram(
        {"type": "coordinate", "curves": [{"expr": "1/x"}]},
        out_dir=tmp_path,
        basename="rational",
        formats=("svg",),
    )
    assert result.elements["curves"] == 1


def test_force_diagram_draws_every_force(tmp_path):
    spec = {
        "type": "force",
        "object": {"shape": "block", "label": "m"},
        "forces": [
            {"label": "mg", "angle_deg": 270, "magnitude": 20, "unit": "N"},
            {"label": "N", "angle_deg": 90, "magnitude": 20, "unit": "N"},
            {"label": "F", "angle_deg": 0, "magnitude": 12, "unit": "N"},
        ],
    }
    result = render_diagram(spec, out_dir=tmp_path, basename="force", formats=("svg",))
    text = svg_text(tmp_path / "force.svg")
    assert result.elements["forces"] == 3
    assert "mg" in text and "N = 20 N" in text and "F = 12 N" in text


def test_circuit_layout_has_topology(tmp_path):
    spec = {
        "type": "circuit",
        "components": [
            {"kind": "battery", "from": "A", "to": "B", "label": "E", "value": "6V"},
            {"kind": "resistor", "from": "B", "to": "C", "label": "R1", "value": "2Ω"},
            {"kind": "ammeter", "from": "C", "to": "D", "label": "A"},
            {"kind": "resistor", "from": "D", "to": "A", "label": "R2", "value": "4Ω"},
        ],
    }
    result = render_diagram(spec, out_dir=tmp_path, basename="circuit", formats=("svg",))
    text = svg_text(tmp_path / "circuit.svg")
    assert result.elements["components"] == 4
    assert result.elements["nodes"] == 4
    assert "R1" in text and "E" in text


def test_parallel_circuit_uses_two_branches(tmp_path):
    spec = {
        "type": "circuit",
        "components": [
            {"kind": "battery", "from": "A", "to": "B"},
            {"kind": "resistor", "from": "A", "to": "B", "label": "R1"},
            {"kind": "resistor", "from": "A", "to": "B", "label": "R2"},
        ],
    }
    result = render_diagram(spec, out_dir=tmp_path, basename="parallel", formats=("svg",))
    assert result.elements["components"] == 3


def test_optics_lens_and_rays(tmp_path):
    spec = {
        "type": "optics",
        "surfaces": [{"kind": "lens", "from": [0, -2], "to": [0, 2]}],
        "rays": [{"points": [[-4, 1.8], [0, 0.9], [4, 0]]}],
        "axis": {"from": [-5, 0], "to": [5, 0]},
        "focal_points": [{"at": [-2, 0], "label": "F"}],
    }
    result = render_diagram(spec, out_dir=tmp_path, basename="optics", formats=("svg",))
    text = svg_text(tmp_path / "optics.svg")
    assert result.elements["surfaces"] == 1
    assert result.elements["rays"] == 1
    assert ">F</text>" in text


def test_chart_renders_series(tmp_path):
    spec = {
        "type": "chart",
        "kind": "bar",
        "title": "实验数据",
        "series": [{"label": "组1", "points": [[1, 2], [2, 5], [3, 3]]}],
    }
    result = render_diagram(spec, out_dir=tmp_path, basename="chart", formats=("svg",))
    assert result.elements["curves"] == 1
    assert (tmp_path / "chart.svg").exists()


def test_invalid_spec_raises_with_errors(tmp_path):
    with pytest.raises(SpecError) as excinfo:
        render_diagram({"type": "geometry", "points": {"A": [0, 0]}, "segments": [["A", "Z"]]}, out_dir=tmp_path)
    assert excinfo.value.errors


def test_unknown_point_fails_at_render_time(tmp_path):
    with pytest.raises(Exception):
        render_diagram(
            {"type": "geometry", "points": {"A": [0, 0]}, "segments": [["A", "B"]]},
            out_dir=tmp_path,
        )


def test_geometry_escapes_text_labels(tmp_path):
    spec = {
        "type": "geometry",
        "points": {"A": [0, 0], "B": [1, 0]},
        "segments": [["A", "B"]],
        "title": "<script>alert(1)</script>",
    }
    render_diagram(spec, out_dir=tmp_path, basename="escape", formats=("svg",))
    text = svg_text(tmp_path / "escape.svg")
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_svg_has_no_nan(tmp_path, geometry_diagram):
    render_diagram(geometry_diagram, out_dir=tmp_path, basename="nan", formats=("svg",))
    text = svg_text(tmp_path / "nan.svg")
    assert "NaN" not in text
    assert "inf" not in text.lower()
    coordinates = re.findall(r'points="([^"]+)"', text)
    assert coordinates
