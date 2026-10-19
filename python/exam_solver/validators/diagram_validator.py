"""Validate that a DiagramSpec's coordinates really satisfy the problem.

The renderer is intentionally dumb: it draws what the coordinates say. This
module is the independent check that the coordinates encode the *stated*
relations (collinear, perpendicular, parallel, equal length, concyclic, ...).

All checks are numerical and use a tolerance derived from the figure size, so
a hand-made rounded coordinate like ``(1.73, 1)`` still counts as ``sqrt(3)``.
Every relation is reported as passed, failed, or skipped (with a reason).
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

__all__ = ["validate_diagram", "build_figure"]

Point = (float, float)


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _cos_angle(a: Point, b: Point, c: Point) -> float | None:
    """Cosine of angle ABC."""

    ba = _sub(a, b)
    bc = _sub(c, b)
    norm = math.hypot(*ba) * math.hypot(*bc)
    if norm < 1e-12:
        return None
    return max(-1.0, min(1.0, _dot(ba, bc) / norm))


class Figure:
    """Indexed view of a geometry DiagramSpec."""

    def __init__(self, spec: Mapping[str, Any]) -> None:
        raw_points = spec.get("points") or {}
        self.points: dict[str, Point] = {
            str(name): (float(value[0]), float(value[1]))
            for name, value in raw_points.items()
            if isinstance(value, (list, tuple)) and len(value) == 2
        }
        if len(self.points) >= 2:
            xs = [point[0] for point in self.points.values()]
            ys = [point[1] for point in self.points.values()]
            self.diagonal = max(math.hypot(max(xs) - min(xs), max(ys) - min(ys)), 1e-6)
        else:
            self.diagonal = 1.0
        self.segments: set[frozenset[str]] = set()
        for key in ("segments", "auxiliary_segments", "lines"):
            for item in spec.get(key) or []:
                self.segments.add(frozenset((str(item[0]), str(item[1]))))
        self.circles: dict[str, dict[str, Any]] = {}
        for circle in spec.get("circles") or []:
            center = str(circle.get("center"))
            radius = circle.get("radius")
            through = circle.get("through")
            if radius is None and through and center in self.points and str(through) in self.points:
                radius = _distance(self.points[center], self.points[str(through)])
            entry = {"center": center, "radius": float(radius) if radius else None}
            self.circles[center] = entry
            if circle.get("label"):
                self.circles[str(circle["label"])] = entry
            self.circles[f"circle_{center}"] = entry

    def tolerance(self, factor: float = 0.01) -> float:
        return max(self.diagonal * factor, 1e-9)

    def segment(self, token: str) -> tuple[Point, Point] | None:
        """Resolve ``"AB"`` / ``"A-B"`` to a pair of points when both exist."""

        cleaned = token.replace(" ", "").replace("_", "")
        if len(cleaned) == 2 and cleaned[0] in self.points and cleaned[1] in self.points:
            return self.points[cleaned[0]], self.points[cleaned[1]]
        for separator in ("-", "—"):
            if separator in token:
                left, _, right = token.partition(separator)
                if left in self.points and right in self.points:
                    return self.points[left], self.points[right]
        return None

    def point(self, token: str) -> Point | None:
        return self.points.get(token.strip())


def build_figure(spec: Mapping[str, Any]) -> Figure:
    """Public helper used by the tests and the renderer pipeline."""

    return Figure(spec)


def _check(
    name: str,
    passed: bool,
    details: str,
    *,
    skipped: bool = False,
    severity: str = "error",
    method: str = "geometry",
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": True if skipped else passed,
        "severity": "info" if skipped else severity,
        "details": details,
        "method": method,
        "skipped": skipped,
    }


def _relation_points(objects: Sequence[str], figure: Figure) -> list[Point] | None:
    resolved = [figure.point(token) for token in objects]
    if any(point is None for point in resolved):
        return None
    return [point for point in resolved if point is not None]


def _check_relation(relation: Mapping[str, Any], figure: Figure) -> dict[str, Any]:
    kind = str(relation.get("type"))
    objects = [str(item) for item in relation.get("objects") or []]
    label = f"relation:{kind}:{'-'.join(objects)}"
    tolerance = figure.tolerance()
    angle_tolerance = 2e-3

    if kind == "collinear":
        points = _relation_points(objects, figure)
        if not points or len(points) < 3:
            return _check(label, False, "needs at least three known points", skipped=True)
        base = points[1]
        worst = 0.0
        for point in points[2:]:
            ab = _sub(base, points[0])
            ac = _sub(point, points[0])
            norm = math.hypot(*ab) * math.hypot(*ac)
            if norm < 1e-12:
                continue
            worst = max(worst, abs(_cross(ab, ac)) / norm)
        return _check(label, worst <= angle_tolerance, f"max |sin(angle)| = {worst:.3e} (limit {angle_tolerance:g})")

    if kind in {"perpendicular", "parallel"}:
        segments = []
        if len(objects) == 2:
            for token in objects:
                pair = figure.segment(token)
                if pair:
                    segments.append(_sub(pair[1], pair[0]))
        if len(segments) != 2:
            points = _relation_points(objects, figure)
            if points and len(points) == 3:
                segments = [_sub(points[1], points[0]), _sub(points[2], points[0])]
        if len(segments) != 2:
            return _check(label, False, "could not resolve two segments", skipped=True)
        first, second = segments
        norm = math.hypot(*first) * math.hypot(*second)
        if norm < 1e-12:
            return _check(label, False, "a segment has zero length", skipped=True)
        sine = abs(_cross(first, second)) / norm
        cosine = abs(_dot(first, second)) / norm
        if kind == "perpendicular":
            return _check(label, cosine <= angle_tolerance, f"|cos(angle)| = {cosine:.3e} (limit {angle_tolerance:g})")
        return _check(label, sine <= angle_tolerance, f"|sin(angle)| = {sine:.3e} (limit {angle_tolerance:g})")

    if kind == "equal_length":
        lengths = []
        for token in objects:
            pair = figure.segment(token)
            if not pair:
                return _check(label, False, f"unknown segment {token!r}", skipped=True)
            lengths.append(_distance(*pair))
        if len(lengths) < 2:
            return _check(label, False, "needs two segments", skipped=True)
        spread = max(lengths) - min(lengths)
        return _check(label, spread <= tolerance, f"lengths = {[round(v, 4) for v in lengths]}, spread = {spread:.3e}")

    if kind == "point_on_segment":
        # Accept ["D","BC"] or ["D","B","C"].
        if len(objects) == 2:
            pair = figure.segment(objects[1])
        elif len(objects) == 3:
            pair = (figure.point(objects[1]), figure.point(objects[2]))
        else:
            pair = None
        target = figure.point(objects[0])
        if not pair or pair[0] is None or pair[1] is None or target is None:
            return _check(label, False, "could not resolve point/segment", skipped=True)
        a, b = pair  # type: ignore[misc]
        ab = _sub(b, a)
        at = _sub(target, a)
        length_sq = _dot(ab, ab)
        if length_sq < 1e-12:
            return _check(label, False, "segment has zero length", skipped=True)
        parameter = _dot(at, ab) / length_sq
        closest = (a[0] + ab[0] * parameter, a[1] + ab[1] * parameter)
        distance = _distance(target, closest)
        inside = -1e-9 <= parameter <= 1 + 1e-9
        return _check(
            label,
            inside and distance <= tolerance,
            f"t = {parameter:.4f}, distance to line = {distance:.3e} (limit {tolerance:.3e})",
        )

    if kind == "point_on_circle":
        if len(objects) != 2:
            return _check(label, False, "needs a point and a circle", skipped=True)
        target = figure.point(objects[0])
        circle = figure.circles.get(objects[1]) or figure.circles.get(objects[1].replace("circle_", ""))
        if target is None or not circle or circle.get("radius") is None:
            return _check(label, False, "could not resolve point/circle", skipped=True)
        center = figure.points.get(circle["center"])
        if center is None:
            return _check(label, False, "circle centre is not a point", skipped=True)
        delta = abs(_distance(center, target) - float(circle["radius"]))
        return _check(label, delta <= tolerance, f"|distance - r| = {delta:.3e} (limit {tolerance:.3e})")

    if kind == "right_angle":
        vertex: Point | None = None
        arms: list[Point] = []
        if len(objects) == 1:
            vertex = figure.point(objects[0])
            arms = [figure.points[name] for name in list(figure.points)[:2]] if vertex else []
        elif len(objects) == 2:
            segments = [figure.segment(token) for token in objects]
            if all(segments):
                shared = set(objects[0].replace("-", "")) & set(objects[1].replace("-", ""))
                if shared:
                    name = shared.pop()
                    vertex = figure.point(name)
                    for token in objects:
                        for other in token.replace("-", ""):
                            if other != name and other in figure.points:
                                arms.append(figure.points[other])
        if vertex is None or len(arms) < 2:
            return _check(label, False, "could not resolve vertex and arms", skipped=True)
        cosine = _cos_angle(arms[0], vertex, arms[1])
        if cosine is None:
            return _check(label, False, "degenerate angle", skipped=True)
        return _check(label, abs(cosine) <= angle_tolerance, f"|cos(angle)| = {abs(cosine):.3e}")

    if kind == "midpoint":
        if len(objects) < 2:
            return _check(label, False, "needs a point and a segment", skipped=True)
        target = figure.point(objects[0])
        pair = figure.segment(objects[1]) if len(objects) == 2 else None
        if len(objects) == 3:
            pair = (figure.point(objects[1]), figure.point(objects[2]))
        if target is None or not pair or pair[0] is None or pair[1] is None:
            return _check(label, False, "could not resolve midpoint", skipped=True)
        middle = ((pair[0][0] + pair[1][0]) / 2, (pair[0][1] + pair[1][1]) / 2)
        distance = _distance(target, middle)
        return _check(label, distance <= tolerance, f"distance to midpoint = {distance:.3e}")

    if kind == "concyclic":
        if len(objects) < 3:
            return _check(label, False, "needs at least three points", skipped=True)
        points = _relation_points(objects, figure)
        if not points:
            return _check(label, False, "unknown point", skipped=True)
        centre = _circumcentre(points[0], points[1], points[2])
        if centre is None:
            return _check(label, False, "first three points are collinear", skipped=True)
        radii = [_distance(centre, point) for point in points]
        spread = max(radii) - min(radii)
        return _check(label, spread <= tolerance, f"radii spread = {spread:.3e}")

    if kind == "angle_equals":
        if len(objects) < 2:
            return _check(label, False, "needs two angle tokens", skipped=True)
        return _check(label, False, "angle_equals needs explicit arms; not machine-checkable from tokens", skipped=True)

    return _check(label, False, f"unsupported relation type {kind!r}", skipped=True)


def _circumcentre(a: Point, b: Point, c: Point) -> Point | None:
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
    return (ux, uy)


def _self_checks(figure: Figure, spec: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    """Structural checks that do not depend on the problem statement."""

    if len(figure.points) >= 2:
        duplicates = []
        names = list(figure.points)
        for index, first in enumerate(names):
            for second in names[index + 1 :]:
                if _distance(figure.points[first], figure.points[second]) < figure.tolerance(0.0005):
                    duplicates.append(f"{first}={second}")
        yield _check(
            "geometry:distinct_points",
            not duplicates,
            "all named points are distinct" if not duplicates else f"coincident points: {', '.join(duplicates)}",
            severity="warning",
        )
    for token in spec.get("segments") or []:
        a, b = str(token[0]), str(token[1])
        if a in figure.points and b in figure.points and _distance(figure.points[a], figure.points[b]) < figure.tolerance(0.0005):
            yield _check("geometry:nondegenerate_segment", False, f"segment {a}{b} has zero length", severity="warning")
            break
    else:
        yield _check("geometry:nondegenerate_segment", True, "no zero-length segments")

    referenced = set()
    for key in ("segments", "auxiliary_segments", "lines"):
        for item in spec.get(key) or []:
            referenced.update(str(name) for name in item)
    for mark in spec.get("marks") or []:
        if mark.get("at"):
            referenced.add(str(mark["at"]))
        for segment in mark.get("segments") or []:
            referenced.update(str(name) for name in segment)
    for name in referenced:
        if name not in figure.points:
            yield _check("geometry:known_points", False, f"element references undefined point {name!r}")
            break
    else:
        yield _check("geometry:known_points", True, "every referenced point is defined")


def validate_diagram(
    diagram_spec: Mapping[str, Any],
    problem_spec: Mapping[str, Any] | None = None,
    *,
    relations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate one geometry DiagramSpec against ProblemSpec relations."""

    if diagram_spec.get("type") != "geometry":
        return {
            "passed": True,
            "checks": [
                _check(
                    "diagram:relation_check",
                    True,
                    f"no coordinate relations to verify for diagram type {diagram_spec.get('type')!r}",
                    skipped=True,
                )
            ],
            "warnings": [],
            "contradictions": [],
            "recommended_revision": [],
            "coverage": {"claimed_checks": 0, "executed_checks": 0, "skipped_checks": 1},
        }

    figure = build_figure(diagram_spec)
    checks: list[dict[str, Any]] = []
    selected = list(relations if relations is not None else (problem_spec or {}).get("visual_relations") or [])
    for relation in selected:
        checks.extend([_check_relation(relation, figure)])
    checks.extend(_self_checks(figure, diagram_spec))

    # Only geometry relations belong here; force/circuit relations are not
    # checkable from a coordinate drawing.
    evaluated = [check for check in checks if not check.get("skipped")]
    failures = [check for check in evaluated if not check["passed"] and check.get("severity") == "error"]
    warnings = [
        str(check["details"]) for check in checks if check.get("skipped") and check.get("severity") == "info"
    ]
    contradictions = [f"{check['name']}: {check['details']}" for check in failures]
    recommendations = [
        f"Adjust DiagramSpec coordinates so that {check['name'].split(':', 2)[-1]} holds ({check['details']})."
        for check in failures
    ]
    return {
        "passed": not failures,
        "checks": checks,
        "warnings": warnings,
        "contradictions": contradictions,
        "recommended_revision": recommendations,
        "coverage": {
            "claimed_checks": len(selected),
            "executed_checks": len(evaluated),
            "skipped_checks": len(checks) - len(evaluated),
        },
    }
