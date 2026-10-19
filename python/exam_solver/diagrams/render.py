"""Diagram render dispatch: validate the spec, draw it, publish files."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..errors import EngineError, SpecError
from ..schema import format_errors, load_schema, sanitize, validate
from .canvas import MplCanvas, RenderError, SVGCanvas
from .circuit import render_circuit
from .coordinate import render_chart, render_coordinate
from .force import render_force
from .geometry import render_geometry
from .optics import render_optics

__all__ = ["render_diagram", "validate_diagram_spec", "RenderResult"]


@dataclass
class RenderResult:
    svg: str | None = None
    png: str | None = None
    width: int = 760
    height: int = 560
    spec_type: str = ""
    elements: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": {"svg": self.svg, "png": self.png},
            "width": self.width,
            "height": self.height,
            "spec_type": self.spec_type,
            "elements": self.elements,
            "warnings": self.warnings,
            "duration_ms": self.duration_ms,
        }


def validate_diagram_spec(spec: Any) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Sanitize then strictly validate a DiagramSpec.

    Returns the sanitized spec plus remaining errors. The caller decides
    whether to repair (LLM round-trip) or fail.
    """

    if not isinstance(spec, Mapping):
        return {}, [{"path": "$", "message": "DiagramSpec must be a JSON object", "keyword": "type"}]
    schema = load_schema("diagram_spec")
    cleaned = sanitize(dict(spec), schema)
    errors = validate(cleaned, schema)
    return cleaned, [error.as_dict() for error in errors]


_DISPATCH = {
    "geometry": render_geometry,
    "coordinate": render_coordinate,
    "function": render_coordinate,
    "force": render_force,
    "circuit": render_circuit,
    "optics": render_optics,
    "chart": render_chart,
}


def check_references(spec: Mapping[str, Any]) -> list[dict[str, str]]:
    """Catch references to undefined points/nodes before drawing.

    JSON Schema can only check shape; a segment may still name a point that
    does not exist. Reporting it here (instead of as a render crash) gives the
    repair loop a precise, machine-readable error.
    """

    errors: list[dict[str, str]] = []
    kind = str(spec.get("type"))
    if kind == "geometry":
        points = set((spec.get("points") or {}).keys())
        for key in ("segments", "auxiliary_segments", "lines"):
            for index, item in enumerate(spec.get(key) or []):
                for name in item:
                    if str(name) not in points:
                        errors.append(
                            {
                                "path": f"$.{key}[{index}]",
                                "message": f"undefined point {name!r}; defined points: {sorted(points)}",
                                "keyword": "reference",
                            }
                        )
        for index, item in enumerate(spec.get("rays") or []):
            for field in ("from", "to"):
                if str(item.get(field)) not in points:
                    errors.append(
                        {
                            "path": f"$.rays[{index}].{field}",
                            "message": f"undefined point {item.get(field)!r}",
                            "keyword": "reference",
                        }
                    )
        for index, item in enumerate(spec.get("arrows") or []):
            for field in ("from", "to"):
                if str(item.get(field)) not in points:
                    errors.append(
                        {
                            "path": f"$.arrows[{index}].{field}",
                            "message": f"undefined point {item.get(field)!r}",
                            "keyword": "reference",
                        }
                    )
        for index, item in enumerate(spec.get("circles") or []):
            if str(item.get("center")) not in points:
                errors.append(
                    {
                        "path": f"$.circles[{index}].center",
                        "message": f"undefined centre point {item.get('center')!r}",
                        "keyword": "reference",
                    }
                )
            if item.get("through") and str(item["through"]) not in points:
                errors.append(
                    {
                        "path": f"$.circles[{index}].through",
                        "message": f"undefined point {item['through']!r}",
                        "keyword": "reference",
                    }
                )
        for index, item in enumerate(spec.get("polygons") or []):
            for name in item.get("points") or []:
                if str(name) not in points:
                    errors.append(
                        {
                            "path": f"$.polygons[{index}]",
                            "message": f"undefined point {name!r}",
                            "keyword": "reference",
                        }
                    )
        for index, mark in enumerate(spec.get("marks") or []):
            if mark.get("at") and str(mark["at"]) not in points:
                errors.append(
                    {
                        "path": f"$.marks[{index}].at",
                        "message": f"undefined point {mark['at']!r}",
                        "keyword": "reference",
                    }
                )
            for segment in mark.get("segments") or []:
                for name in segment:
                    if str(name) not in points:
                        errors.append(
                            {
                                "path": f"$.marks[{index}].segments",
                                "message": f"undefined point {name!r}",
                                "keyword": "reference",
                            }
                        )
    elif kind == "circuit":
        nodes = set()
        for component in spec.get("components") or []:
            nodes.update({str(component["from"]), str(component["to"])})
        for name in (spec.get("nodes") or {}):
            if str(name) not in nodes:
                errors.append(
                    {
                        "path": "$.nodes",
                        "message": f"layout places node {name!r} that no component uses",
                        "keyword": "reference",
                    }
                )
    return errors


def render_diagram(
    spec: Mapping[str, Any],
    *,
    out_dir: str | Path,
    basename: str = "diagram",
    width: int = 760,
    height: int = 560,
    formats: tuple[str, ...] = ("svg", "png"),
    dpi: int = 140,
) -> RenderResult:
    """Validate and render one DiagramSpec, returning file paths and stats."""

    started = time.perf_counter()
    cleaned, errors = validate_diagram_spec(spec)
    if errors:
        raise SpecError(
            f"DiagramSpec does not validate: {format_errors([_ErrorView(item) for item in errors])}",  # type: ignore[arg-type]
            errors=errors,
            kind="diagram_spec",
        )
    reference_errors = check_references(cleaned)
    if reference_errors:
        raise SpecError(
            f"DiagramSpec references undefined elements: {format_errors([_ErrorView(item) for item in reference_errors])}",  # type: ignore[arg-type]
            errors=reference_errors,
            kind="diagram_spec",
        )

    kind = str(cleaned.get("type"))
    renderer = _DISPATCH.get(kind)
    if renderer is None:
        raise EngineError(f"unsupported diagram type {kind!r}", code="unsupported_diagram_type")

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    result = RenderResult(width=int(width), height=int(height), spec_type=kind)

    try:
        svg_canvas = SVGCanvas(result.width, result.height)
        stats = renderer(cleaned, svg_canvas)
        svg_path = svg_canvas.save_svg(directory / f"{basename}.svg", title=cleaned.get("title") or basename)
        result.svg = str(svg_path)
        result.elements = _stats_to_dict(stats)
        result.warnings.extend(getattr(stats, "warnings", []) or [])
    except RenderError as exc:
        raise EngineError(str(exc), code=exc.code) from exc

    if "png" in formats:
        try:
            png_canvas = MplCanvas(result.width, result.height, dpi=dpi)
            renderer(cleaned, png_canvas)
            png_path = png_canvas.save_png(directory / f"{basename}.png", dpi=dpi)
            result.png = str(png_path)
        except RenderError as exc:
            if exc.code != "matplotlib_unavailable":
                raise
            result.warnings.append("PNG preview skipped: matplotlib is not installed (SVG is still available).")
        except Exception as exc:  # pragma: no cover - raster backend robustness
            result.warnings.append(f"PNG preview failed: {exc}")

    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


def _stats_to_dict(stats: Any) -> dict[str, int]:
    if stats is None:
        return {}
    if hasattr(stats, "__dataclass_fields__"):
        payload: dict[str, int] = {}
        for name in stats.__dataclass_fields__:  # type: ignore[attr-defined]
            value = getattr(stats, name)
            if isinstance(value, int) and name != "bbox":
                payload[name] = value
        return payload
    return {}


class _ErrorView:
    """Adapter so format_errors can render plain dicts."""

    def __init__(self, item: Mapping[str, str]) -> None:
        self.path = item.get("path", "$")
        self.message = item.get("message", "")
        self.keyword = item.get("keyword", "")

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message, "keyword": self.keyword}
