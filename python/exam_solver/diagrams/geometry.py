"""Geometry renderer: turns a declarative geometry DiagramSpec into a drawing.

Everything here is presentation logic - where marks go, how labels avoid each
other, how a ray is clipped to the canvas. Mathematical relations are *not*
asserted here; :mod:`exam_solver.validators.diagram_validator` checks that the
coordinates really satisfy the problem statement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .canvas import (
    PALETTE,
    Canvas,
    RenderError,
    Style,
    combined_bbox,
)

__all__ = ["render_geometry", "GeometryRequest", "GeometryStats", "PALETTE", "Style"]

Point = tuple[float, float]

INK = Style()
AUX = Style(stroke=PALETTE["accent2"], width=1.5, dash="7 5")
CIRCLE = Style(stroke=PALETTE["ink"], width=2.0)
THIN = Style(stroke=PALETTE["aux"], width=1.2, dash="5 4")


@dataclass
class GeometryRequest:
    """One geometry diagram, already validated against the JSON Schema."""

    points: dict[str, Point]
    segments: list[tuple[str, str]] = field(default_factory=list)
    auxiliary_segments: list[tuple[str, str]] = field(default_factory=list)
    rays: list[tuple[str, str]] = field(default_factory=list)
    lines: list[tuple[str, str]] = field(default_factory=list)
    polygons: list[dict[str, Any]] = field(default_factory=list)
    circles: list[dict[str, Any]] = field(default_factory=list)
    arcs: list[dict[str, Any]] = field(default_factory=list)
    arrows: list[dict[str, Any]] = field(default_factory=list)
    marks: list[dict[str, Any]] = field(default_factory=list)
    labels: dict[str, bool] = field(default_factory=dict)
    label_offsets: dict[str, Point] = field(default_factory=dict)
    title: str | None = None

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> "GeometryRequest":
        points: dict[str, Point] = {}
        for name, value in (spec.get("points") or {}).items():
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise RenderError("invalid_point", f"point {name!r} must be [x, y]")
            try:
                points[str(name)] = (float(value[0]), float(value[1]))
            except (TypeError, ValueError) as exc:
                raise RenderError("invalid_point", f"point {name!r} is not numeric: {exc}") from exc
        if not points:
            raise RenderError("empty_geometry", "geometry needs at least one point")

        def pairs(key: str) -> list[tuple[str, str]]:
            raw = spec.get(key) or []
            result: list[tuple[str, str]] = []
            for item in raw:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    raise RenderError("invalid_segment", f"{key} entry must be a pair of point names")
                a, b = str(item[0]), str(item[1])
                _require(points, a)
                _require(points, b)
                if a != b:
                    result.append((a, b))
            return result

        rays = []
        for item in spec.get("rays") or []:
            a, b = str(item.get("from")), str(item.get("to"))
            _require(points, a)
            _require(points, b)
            rays.append((a, b))
        arrows = []
        for item in spec.get("arrows") or []:
            a, b = str(item.get("from")), str(item.get("to"))
            _require(points, a)
            _require(points, b)
            arrows.append({"from": a, "to": b, "label": item.get("label"), "style": item.get("style")})

        circles = []
        for item in spec.get("circles") or []:
            center = str(item.get("center"))
            _require(points, center)
            radius = item.get("radius")
            through = item.get("through")
            if radius is None:
                if through is None:
                    raise RenderError("invalid_circle", "circle needs radius or through")
                _require(points, str(through))
                radius = math.dist(points[center], points[str(through)])
            radius = float(radius)
            if radius <= 0:
                raise RenderError("invalid_circle", "circle radius must be positive")
            circles.append(
                {"center": center, "radius": radius, "label": item.get("label"), "style": item.get("style")}
            )

        for item in (spec.get("arcs") or []):
            _require(points, str(item.get("center")))
        for item in (spec.get("polygons") or []):
            for name in item.get("points") or []:
                _require(points, str(name))

        return cls(
            points=points,
            segments=pairs("segments"),
            auxiliary_segments=pairs("auxiliary_segments"),
            rays=rays,
            lines=pairs("lines"),
            polygons=list(spec.get("polygons") or []),
            circles=circles,
            arcs=list(spec.get("arcs") or []),
            arrows=arrows,
            marks=list(spec.get("marks") or []),
            labels={str(k): bool(v) for k, v in (spec.get("labels") or {}).items()},
            label_offsets={str(k): (float(v[0]), float(v[1])) for k, v in (spec.get("label_offsets") or {}).items()},
            title=spec.get("title"),
        )


@dataclass
class GeometryStats:
    points: int = 0
    segments: int = 0
    circles: int = 0
    marks: int = 0
    labels: int = 0
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    warnings: list[str] = field(default_factory=list)


def _require(points: Mapping[str, Point], name: str) -> None:
    if name not in points:
        raise RenderError("unknown_point", f"point {name!r} is not defined in 'points'")


class _LabelPlacer:
    """Greedy screen-space label placement that avoids overlaps."""

    DIRECTIONS = [
        (0.0, -1.0),
        (1.0, -1.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (0.0, 1.0),
        (-1.0, 1.0),
        (-1.0, 0.0),
        (-1.0, -1.0),
    ]

    def __init__(self, canvas: Canvas) -> None:
        self.canvas = canvas
        self.boxes: list[tuple[float, float, float, float]] = []

    def place(
        self,
        at: Point,
        text: str,
        *,
        preferred: tuple[float, float],
        size: float = 16.0,
        fixed_offset: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        x, y = self.canvas.to_screen(at)
        width = max(len(text), 1) * size * 0.56 + 6
        height = size * 1.05
        if fixed_offset is not None:
            offset = fixed_offset
            if self._fits((x + offset[0] - width / 2, y + offset[1] - height / 2, x + offset[0] + width / 2, y + offset[1] + height / 2)):
                self.boxes.append((x + offset[0] - width / 2, y + offset[1] - height / 2, x + offset[0] + width / 2, y + offset[1] + height / 2))
                return (x + offset[0], y + offset[1])
        norm = math.hypot(*preferred)
        if norm > 1e-6:
            # `preferred` is a world-space direction; the candidate offsets are
            # screen-space. Convert (and flip y) before choosing a side.
            base = (preferred[0] * abs(self.canvas.sx), -preferred[1] * abs(self.canvas.sy))
            base_norm = math.hypot(*base)
            base = (base[0] / base_norm, base[1] / base_norm) if base_norm > 1e-9 else (0.0, -1.0)
        else:
            base = (0.0, -1.0)
        ordered = sorted(self.DIRECTIONS, key=lambda d: -(d[0] * base[0] + d[1] * base[1]))
        for radius in (18.0, 26.0, 34.0, 44.0):
            for dx, dy in ordered:
                cx, cy = x + dx * radius, y + dy * radius
                box = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
                if self._fits(box):
                    self.boxes.append(box)
                    return (cx, cy)
        # Give up: place at the preferred direction and accept the overlap.
        cx, cy = x + base[0] * 18.0, y + base[1] * 18.0
        return (cx, cy)

    def _fits(self, box: tuple[float, float, float, float]) -> bool:
        if box[0] < 2 or box[1] < 2 or box[2] > self.canvas.width - 2 or box[3] > self.canvas.height - 2:
            return False
        for other in self.boxes:
            if _overlap(box, other):
                return False
        return True


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def clamp_line_to_box(
    p: Point, q: Point, box: tuple[float, float, float, float]
) -> tuple[Point, Point] | None:
    """Liang-Barsky clip of an infinite line through p,q to an axis-aligned box."""

    x0, y0, x1, y1 = box
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return None
    t_min, t_max = -1e9, 1e9
    for denominator, numerator in ((dx, x0 - p[0]), (-dx, p[0] - x1), (dy, y0 - p[1]), (-dy, p[1] - y1)):
        if abs(denominator) < 1e-12:
            if numerator < 0:
                return None
            continue
        t = numerator / denominator
        if denominator > 0:
            t_max = min(t_max, t)
        else:
            t_min = max(t_min, t)
    if t_min > t_max:
        return None
    return ((p[0] + t_min * dx, p[1] + t_min * dy), (p[0] + t_max * dx, p[1] + t_max * dy))


def render_geometry(spec: Mapping[str, Any], canvas: Canvas) -> GeometryStats:
    """Draw a geometry spec onto ``canvas`` and report what was drawn."""

    request = GeometryRequest.from_spec(spec)
    stats = GeometryStats(points=len(request.points))
    points = request.points

    extents: list[Point] = list(points.values())
    for circle in request.circles:
        cx, cy = points[circle["center"]]
        radius = float(circle["radius"])
        extents.extend([(cx - radius, cy - radius), (cx + radius, cy + radius)])
    for arc in request.arcs:
        cx, cy = points[str(arc["center"])]
        radius = float(arc["radius"])
        start = math.radians(float(arc["start_angle"]))
        end = math.radians(float(arc["end_angle"]))
        extents.extend([(cx + radius * math.cos(start), cy + radius * math.sin(start))])
        extents.extend([(cx + radius * math.cos(end), cy + radius * math.sin(end))])
    bbox = combined_bbox(extents, pad=0.0)
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1], 1e-6)
    # A tiny sketch should not be blown up to full page size.
    canvas.fit(combined_bbox(extents, pad=span * 0.06), margin=72, uniform=True, max_scale=120.0)
    stats.bbox = bbox

    # ---- filled polygons first (behind everything)
    for polygon in request.polygons:
        names = [str(name) for name in polygon["points"]]
        shape = [points[name] for name in names]
        fill = polygon.get("fill") or PALETTE["fill_soft"]
        canvas.polygon(shape, Style(fill=fill, stroke="none", width=0.0, opacity=0.9))

    # ---- circles and arcs
    for circle in request.circles:
        canvas.circle(points[circle["center"]], float(circle["radius"]), CIRCLE)
        stats.circles += 1
        if circle.get("label"):
            cx, cy = points[circle["center"]]
            canvas.text(
                (cx, cy + float(circle["radius"])),
                str(circle["label"]),
                size=14,
                color=PALETTE["muted"],
                offset=(0, -12),
            )
    for arc in request.arcs:
        style = _dash_style(arc.get("style"), CIRCLE)
        canvas.arc(
            points[str(arc["center"])],
            float(arc["radius"]),
            float(arc["start_angle"]),
            float(arc["end_angle"]),
            style,
        )

    # ---- straight elements
    for a, b in request.segments:
        canvas.line(points[a], points[b], INK)
        stats.segments += 1
    for a, b in request.auxiliary_segments:
        canvas.line(points[a], points[b], AUX)

    for a, b in request.lines:
        clipped = clamp_line_to_box(points[a], points[b], bbox)
        if clipped:
            canvas.line(clipped[0], clipped[1], THIN)
    for a, b in request.rays:
        canvas.arrow(points[a], points[b], THIN, head=10.0)

    # ---- polygons outline
    for polygon in request.polygons:
        names = [str(name) for name in polygon["points"]]
        style = _dash_style(polygon.get("style"), INK)
        canvas.polygon([points[name] for name in names], style)

    # ---- arrows (vectors)
    for arrow in request.arrows:
        a, b = arrow["from"], arrow["to"]
        style = Style(stroke=PALETTE["accent"], width=2.0)
        if arrow.get("style"):
            style = _dash_style(arrow["style"], style)
        canvas.arrow(points[a], points[b], style, label=arrow.get("label"), color=PALETTE["accent"])

    # ---- marks
    for mark in request.marks:
        stats.marks += _draw_mark(mark, points, canvas, stats.warnings)

    # ---- labels
    placer = _LabelPlacer(canvas)
    centroid = (
        sum(point[0] for point in points.values()) / len(points),
        sum(point[1] for point in points.values()) / len(points),
    )
    for name, point in points.items():
        show = request.labels.get(name, True)
        if not show:
            continue
        canvas.dot(point, 3.4)
        preferred = (point[0] - centroid[0], point[1] - centroid[1])
        hint = request.label_offsets.get(name)
        if hint is not None and (abs(hint[0]) + abs(hint[1])) > 1e-9:
            # A model-supplied offset is treated as a direction hint, not as an
            # exact pixel position: it still gets collision avoidance.
            preferred = hint
        position = placer.place(point, name, preferred=preferred)
        canvas.text_screen(position, name, size=16, anchor="middle", baseline="middle", color=PALETTE["ink"], bold=True)
        stats.labels += 1

    if request.title:
        canvas.text_screen(
            (24, 28), request.title, size=17, anchor="start", baseline="middle", color=PALETTE["ink"], bold=True
        )

    if len(set(points.values())) < len(points):
        stats.warnings.append("two or more named points share exactly the same coordinates")
    return stats


def _draw_mark(mark: Mapping[str, Any], points: Mapping[str, Point], canvas: Canvas, warnings: list[str]) -> int:
    kind = mark.get("type")
    if kind == "right_angle":
        vertex_name = str(mark.get("at"))
        if vertex_name not in points:
            warnings.append(f"right_angle mark refers to unknown point {vertex_name!r}")
            return 0
        arms = mark.get("arms") or _adjacent(vertex_name, points)
        if len(arms) < 2:
            warnings.append(f"cannot place right_angle mark at {vertex_name!r}: need two adjacent points")
            return 0
        _right_angle(points[vertex_name], points[str(arms[0])], points[str(arms[1])], canvas)
        return 1

    if kind in {"equal_length", "parallel"}:
        placed = 0
        tick = int(mark.get("tick") or 1)
        for pair in mark.get("segments") or []:
            a, b = str(pair[0]), str(pair[1])
            if a not in points or b not in points:
                warnings.append(f"{kind} mark refers to unknown segment {a}{b}")
                continue
            if kind == "equal_length":
                _tick_marks(points[a], points[b], canvas, count=tick)
            else:
                _chevron_marks(points[a], points[b], canvas, count=tick)
            placed += 1
        return placed

    if kind == "angle":
        vertex_name = str(mark.get("at"))
        if vertex_name not in points:
            warnings.append(f"angle mark refers to unknown point {vertex_name!r}")
            return 0
        arms = mark.get("arms") or _adjacent(vertex_name, points)
        if len(arms) < 2:
            return 0
        _angle_arc(points[vertex_name], points[str(arms[0])], points[str(arms[1])], canvas, mark.get("label"))
        return 1

    warnings.append(f"unsupported mark type {kind!r}")
    return 0


def _adjacent(vertex: str, points: Mapping[str, Point]) -> list[str]:
    """Best-effort fallback when a mark omits its arms: pick two other points."""

    others = [name for name in points if name != vertex]
    if len(others) < 2:
        return others
    pivot = points[vertex]
    others.sort(key=lambda name: math.dist(pivot, points[name]))
    return others[:2]


def _unit(a: Point, b: Point) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def _right_angle(vertex: Point, arm_a: Point, arm_b: Point, canvas: Canvas) -> None:
    ua, ub = _unit(vertex, arm_a), _unit(vertex, arm_b)
    size = 13.0 / max(canvas.scale(), 1e-6)
    p0 = (vertex[0] + ua[0] * size, vertex[1] + ua[1] * size)
    p2 = (vertex[0] + ub[0] * size, vertex[1] + ub[1] * size)
    p1 = (p0[0] + ub[0] * size, p0[1] + ub[1] * size)
    canvas.polyline([p0, p1, p2], Style(stroke=PALETTE["accent2"], width=1.5))


def _tick_marks(a: Point, b: Point, canvas: Canvas, *, count: int) -> None:
    dx, dy = _unit(a, b)
    normal = (-dy, dx)
    middle = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    step = 5.0 / max(canvas.scale(), 1e-6)
    for index in range(max(1, min(count, 3))):
        offset = (index - (count - 1) / 2) * step
        center = (middle[0] + dx * offset, middle[1] + dy * offset)
        half = 7.0 / max(canvas.scale(), 1e-6)
        canvas.line(
            (center[0] - normal[0] * half, center[1] - normal[1] * half),
            (center[0] + normal[0] * half, center[1] + normal[1] * half),
            Style(stroke=PALETTE["accent2"], width=1.6),
        )


def _chevron_marks(a: Point, b: Point, canvas: Canvas, *, count: int) -> None:
    dx, dy = _unit(a, b)
    normal = (-dy, dx)
    middle = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    step = 6.0 / max(canvas.scale(), 1e-6)
    for index in range(max(1, min(count, 3))):
        offset = (index - (count - 1) / 2) * step
        center = (middle[0] + dx * offset, middle[1] + dy * offset)
        size = 6.0 / max(canvas.scale(), 1e-6)
        left = (center[0] - dx * size + normal[0] * size, center[1] - dy * size + normal[1] * size)
        right = (center[0] - dx * size - normal[0] * size, center[1] - dy * size - normal[1] * size)
        tip = (center[0] + dx * size, center[1] + dy * size)
        canvas.polyline([left, tip, right], Style(stroke=PALETTE["accent2"], width=1.5, fill="none"))


def _angle_arc(vertex: Point, arm_a: Point, arm_b: Point, canvas: Canvas, label: str | None) -> None:
    angle_a = math.degrees(math.atan2(arm_a[1] - vertex[1], arm_a[0] - vertex[0]))
    angle_b = math.degrees(math.atan2(arm_b[1] - vertex[1], arm_b[0] - vertex[0]))
    delta = (angle_b - angle_a + 540) % 360 - 180
    radius = 26.0 / max(canvas.scale(), 1e-6)
    canvas.arc(vertex, radius, angle_a, angle_a + delta, Style(stroke=PALETTE["accent2"], width=1.4))
    if label:
        middle = angle_a + delta / 2
        position = (
            vertex[0] + (radius + 12 / max(canvas.scale(), 1e-6)) * math.cos(math.radians(middle)),
            vertex[1] + (radius + 12 / max(canvas.scale(), 1e-6)) * math.sin(math.radians(middle)),
        )
        canvas.text(position, label, size=13, color=PALETTE["accent2"])


def _dash_style(value: Any, base: Style) -> Style:
    if value == "dashed":
        return Style(stroke=base.stroke, width=base.width, dash="7 5", fill=base.fill)
    if value == "dotted":
        return Style(stroke=base.stroke, width=base.width, dash="2 4", fill=base.fill)
    return base
