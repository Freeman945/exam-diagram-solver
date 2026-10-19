"""Diagram engine: declarative DiagramSpec -> deterministic drawing."""

from .canvas import Canvas, MplCanvas, RenderError, SVGCanvas, Style
from .render import RenderResult, render_diagram, validate_diagram_spec

__all__ = [
    "Canvas",
    "MplCanvas",
    "SVGCanvas",
    "Style",
    "RenderError",
    "RenderResult",
    "render_diagram",
    "validate_diagram_spec",
]
