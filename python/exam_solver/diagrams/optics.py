"""Optics renderer: mirrors, interfaces, lenses, optical axis and ray paths."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .canvas import PALETTE, Canvas, Style, combined_bbox

__all__ = ["render_optics", "OpticsStats"]

Point = tuple[float, float]

RAY = Style(stroke=PALETTE["accent"], width=2.0)
NORMAL = Style(stroke=PALETTE["aux"], width=1.2, dash="5 5")
MIRROR = Style(stroke=PALETTE["ink"], width=3.0)
SURFACE = Style(stroke=PALETTE["ink"], width=2.0)
AXIS = Style(stroke=PALETTE["muted"], width=1.2, dash="8 5")
LENS_FILL = "#dbeafe"


@dataclass
class OpticsStats:
    surfaces: int = 0
    rays: int = 0
    warnings: list[str] = field(default_factory=list)


def _unit(p: Point, q: Point) -> Point:
    dx, dy = q[0] - p[0], q[1] - p[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def _hatch(canvas: Canvas, p: Point, q: Point, *, side: Point = (0.0, -1.0), count: int = 9, size: float = 0.18) -> None:
    """Short parallel strokes along a segment, on one side."""

    for index in range(1, count):
        t = index / count
        base = (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
        tip = (base[0] + side[0] * size, base[1] + side[1] * size)
        canvas.line(base, tip, Style(stroke=PALETTE["muted"], width=1.0))


def _lens(canvas: Canvas, p: Point, q: Point, *, bulge: float = 0.55, samples: int = 28) -> None:
    ux, uy = _unit(p, q)
    normal = (-uy, ux)
    left = []
    right = []
    for index in range(samples + 1):
        t = index / samples
        centre = (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
        width = bulge * math.sin(math.pi * t)
        left.append((centre[0] + normal[0] * width, centre[1] + normal[1] * width))
        right.append((centre[0] - normal[0] * width, centre[1] - normal[1] * width))
    canvas.polygon(left + list(reversed(right)), Style(fill=LENS_FILL, stroke=PALETTE["ink"], width=2.0, opacity=0.85))
    canvas.line(p, q, Style(stroke=PALETTE["ink"], width=0.8))


def render_optics(spec: Mapping[str, Any], canvas: Canvas) -> OpticsStats:
    stats = OpticsStats()
    surfaces = list(spec.get("surfaces") or [])
    rays = list(spec.get("rays") or [])
    if not surfaces:
        stats.warnings.append("optics diagram has no surfaces")

    extents: list[Point] = []
    for surface in surfaces:
        extents.append((float(surface["from"][0]), float(surface["from"][1])))
        extents.append((float(surface["to"][0]), float(surface["to"][1])))
    for ray in rays:
        for point in ray["points"]:
            extents.append((float(point[0]), float(point[1])))
    for item in spec.get("normals") or []:
        extents.append((float(item["from"][0]), float(item["from"][1])))
        extents.append((float(item["to"][0]), float(item["to"][1])))
    axis = spec.get("axis")
    if axis:
        extents.append((float(axis["from"][0]), float(axis["from"][1])))
        extents.append((float(axis["to"][0]), float(axis["to"][1])))
    for focal in spec.get("focal_points") or []:
        extents.append((float(focal["at"][0]), float(focal["at"][1])))
    if not extents:
        extents = [(-1.0, -1.0), (1.0, 1.0)]
    canvas.fit(combined_bbox(extents, pad=0.6), margin=70, uniform=True)

    if axis:
        start = (float(axis["from"][0]), float(axis["from"][1]))
        end = (float(axis["to"][0]), float(axis["to"][1]))
        canvas.arrow(start, end, AXIS, head=9.0)

    for surface in surfaces:
        p = (float(surface["from"][0]), float(surface["from"][1]))
        q = (float(surface["to"][0]), float(surface["to"][1]))
        kind = str(surface.get("kind"))
        ux, uy = _unit(p, q)
        normal = (-uy, ux)
        if kind == "mirror":
            canvas.line(p, q, MIRROR)
            _hatch(canvas, p, q, side=normal, count=10, size=0.18)
        elif kind == "lens":
            _lens(canvas, p, q)
        elif kind == "screen":
            canvas.line(p, q, Style(stroke=PALETTE["ink"], width=2.4))
            _hatch(canvas, p, q, side=normal, count=12, size=0.14)
        else:
            canvas.line(p, q, Style(stroke=PALETTE["ink"], width=1.6, dash="8 5"))
        if surface.get("label"):
            anchor = p if p[1] <= q[1] else q
            canvas.text(
                anchor,
                str(surface["label"]),
                size=13,
                color=PALETTE["muted"],
                offset=(0, 20),
                background="#ffffff",
            )
        stats.surfaces += 1

    for normal in spec.get("normals") or []:
        canvas.line(
            (float(normal["from"][0]), float(normal["from"][1])),
            (float(normal["to"][0]), float(normal["to"][1])),
            NORMAL,
        )

    for ray in rays:
        points = [(float(point[0]), float(point[1])) for point in ray["points"]]
        style = RAY
        if ray.get("style") == "dashed":
            style = Style(stroke=RAY.stroke, width=RAY.width, dash="7 5")
        canvas.polyline(points, style)
        for index in range(len(points) - 1):
            start, end = points[index], points[index + 1]
            if math.dist(start, end) < 0.4:
                continue
            # Arrow head near the end of every segment shows propagation direction.
            ux, uy = _unit(start, end)
            head_base = (end[0] - ux * 0.18, end[1] - uy * 0.18)
            canvas.arrow(head_base, end, style, head=9.0)
        if ray.get("label"):
            last = points[-1]
            canvas.text(last, str(ray["label"]), size=13, color=RAY.stroke, offset=(8, -12), anchor="start")
        stats.rays += 1

    for focal in spec.get("focal_points") or []:
        at = (float(focal["at"][0]), float(focal["at"][1]))
        canvas.dot(at, 4.2, PALETTE["highlight"])
        canvas.text(at, str(focal.get("label") or "F"), size=13, color=PALETTE["highlight"], offset=(0, 16))

    for label in spec.get("labels") or []:
        canvas.text(
            (float(label["at"][0]), float(label["at"][1])),
            str(label["text"]),
            size=13,
            color=PALETTE["ink"],
            anchor="start",
            offset=(6, -6),
        )

    if spec.get("title"):
        canvas.text_screen((24, 26), str(spec["title"]), size=16, anchor="start", baseline="middle", bold=True)
    return stats
