#!/usr/bin/env python
"""Render the example diagram gallery with the real engine.

    python scripts/make_example_diagrams.py

Every file under ``examples/diagrams`` is produced by
``exam_solver.diagrams.render.render_diagram`` - the same code path the plugin
uses - so the gallery can never drift from the renderer.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from exam_solver.diagrams.render import render_diagram  # noqa: E402

OUT = ROOT / "examples" / "diagrams"

SPECS: dict[str, dict] = {
    "geometry_triangle": {
        "type": "geometry",
        "title": "等腰三角形与中线",
        "points": {"A": [0, 3.2], "B": [-2.6, 0], "C": [2.6, 0], "D": [0, 0]},
        "segments": [["A", "B"], ["A", "C"], ["B", "C"], ["A", "D"]],
        "marks": [
            {"type": "right_angle", "at": "D", "arms": ["A", "B"]},
            {"type": "equal_length", "segments": [["A", "B"], ["A", "C"]], "tick": 1},
        ],
        "labels": {"A": True, "B": True, "C": True, "D": True},
    },
    "geometry_circle": {
        "type": "geometry",
        "title": "圆内接三角形",
        "points": {"A": [-2.0, 0.0], "B": [2.0, 0.0], "C": [0.0, 2.0], "O": [0.0, 0.0]},
        "segments": [["A", "B"], ["B", "C"], ["C", "A"], ["O", "A"], ["O", "B"], ["O", "C"]],
        "circles": [{"center": "O", "radius": 2.0, "label": "⊙O"}],
        "marks": [{"type": "angle", "at": "C", "arms": ["A", "B"], "label": "90°"}],
        "labels": {"A": True, "B": True, "C": True, "O": False},
    },
    "function_parabola": {
        "type": "function",
        "title": "y = x² − 2x − 3",
        "expression": "x**2 - 2*x - 3",
        "grid": True,
        "mark_key_points": True,
        "axis_labels": {"x": "x", "y": "y"},
    },
    "function_rational": {
        "type": "coordinate",
        "title": "反比例函数与直线",
        "curves": [
            {"expr": "1/x", "label": "y = 1/x"},
            {"expr": "x/3", "label": "y = x/3"},
        ],
        "points": [{"x": 1.732, "y": 0.577, "label": "P", "style": "filled"}],
        "guides": [{"from": [1.732, 0], "to": [1.732, 0.577]}, {"from": [0, 0.577], "to": [1.732, 0.577]}],
        "grid": True,
    },
    "force_block": {
        "type": "force",
        "title": "粗糙水平面上的物块",
        "object": {"shape": "block", "label": "m"},
        "forces": [
            {"label": "N", "angle_deg": 90, "magnitude": 20, "unit": "N"},
            {"label": "mg", "angle_deg": 270, "magnitude": 20, "unit": "N"},
            {"label": "F", "angle_deg": 0, "magnitude": 10, "unit": "N"},
            {"label": "f", "angle_deg": 180, "magnitude": 4, "unit": "N"},
        ],
        "acceleration": {"label": "a", "angle_deg": 0},
        "axes": True,
        "coordinate_note": "取向右为正方向",
    },
    "force_incline": {
        "type": "force",
        "title": "斜面上的物块",
        "object": {"shape": "incline", "label": "m"},
        "incline_angle": 30,
        "forces": [
            {"label": "mg", "angle_deg": 270, "magnitude": 10, "unit": "N"},
            {"label": "N", "angle_deg": 120, "magnitude": 8.7, "unit": "N"},
            {"label": "f", "angle_deg": 150, "magnitude": 5, "unit": "N"},
        ],
    },
    "circuit_series": {
        "type": "circuit",
        "title": "串联电路",
        "components": [
            {"kind": "battery", "from": "A", "to": "B", "label": "E", "value": "6 V"},
            {"kind": "resistor", "from": "B", "to": "C", "label": "R1", "value": "2 Ω"},
            {"kind": "ammeter", "from": "C", "to": "D", "label": "A"},
            {"kind": "resistor", "from": "D", "to": "A", "label": "R2", "value": "4 Ω"},
        ],
        "current_arrows": [{"from": "A", "to": "B", "label": "I"}],
    },
    "circuit_parallel": {
        "type": "circuit",
        "title": "并联电路",
        "components": [
            {"kind": "battery", "from": "A", "to": "B", "label": "E", "value": "3 V"},
            {"kind": "resistor", "from": "A", "to": "B", "label": "R1", "value": "2 Ω"},
            {"kind": "resistor", "from": "A", "to": "B", "label": "R2", "value": "4 Ω"},
        ],
    },
    "optics_mirror": {
        "type": "optics",
        "title": "平面镜反射",
        "surfaces": [{"kind": "mirror", "from": [0, -2], "to": [0, 2], "label": "平面镜"}],
        "normals": [{"from": [-1.4, 0], "to": [1.2, 0]}],
        "rays": [{"points": [[-3, 2.4], [0, 0], [3, 2.4]], "label": "反射光线"}],
        "labels": [{"at": [0.12, 0.32], "text": "法线"}],
    },
    "optics_lens": {
        "type": "optics",
        "title": "凸透镜成像",
        "surfaces": [{"kind": "lens", "from": [0, -2.2], "to": [0, 2.2], "label": "凸透镜"}],
        "axis": {"from": [-5, 0], "to": [5.5, 0]},
        "focal_points": [{"at": [-2, 0], "label": "F"}, {"at": [2, 0], "label": "F'"}],
        "rays": [{"points": [[-4, 1.8], [0, 0.9], [4, 0]], "label": "折射光线"}],
    },
    "chart_experiment": {
        "type": "chart",
        "kind": "line",
        "title": "小车速度—时间图象",
        "x_label": "t/s",
        "y_label": "v/(m·s⁻¹)",
        "series": [{"label": "实测", "points": [[0, 0], [0.1, 0.4], [0.2, 0.9], [0.3, 1.3], [0.4, 1.8], [0.5, 2.2]]}],
    },
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, spec in SPECS.items():
        result = render_diagram(spec, out_dir=OUT, basename=name, formats=("svg", "png"), dpi=140)
        print(f"{name}: {result.spec_type} {result.elements} -> {result.svg}, {result.png}")


if __name__ == "__main__":
    main()
