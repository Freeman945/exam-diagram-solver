"""Circuit renderer with real topology handling.

Circuits are drawn from a node/component graph, never from a hand-placed
picture. When the model supplies node coordinates they are used as-is;
otherwise a deterministic layout is derived from the graph shape:

* two nodes joined by several branches -> parallel ladder,
* a single cycle -> rectangular loop,
* a path -> series chain closed by a return wire,
* anything else -> circular placement in traversal order.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .canvas import PALETTE, Canvas, RenderError, Style

__all__ = ["render_circuit", "CircuitStats"]

Point = tuple[float, float]

WIRE = Style(stroke=PALETTE["ink"], width=2.0)
SYMBOL = Style(stroke=PALETTE["ink"], width=2.0)
SYMBOL_FILL = Style(stroke=PALETTE["ink"], width=2.0, fill="#ffffff")
CURRENT = Style(stroke=PALETTE["highlight"], width=1.8)

COMPONENT_NAMES = {
    "battery": "电源",
    "resistor": "电阻",
    "ammeter": "电流表",
    "voltmeter": "电压表",
    "switch": "开关",
    "lamp": "灯泡",
    "capacitor": "电容",
    "inductor": "电感",
    "rheostat": "滑动变阻器",
}


@dataclass
class CircuitStats:
    nodes: int = 0
    components: int = 0
    layout: str = "auto"
    warnings: list[str] = field(default_factory=list)


def _unit(p: Point, q: Point) -> Point:
    dx, dy = q[0] - p[0], q[1] - p[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        raise RenderError("degenerate_edge", "circuit edge has zero length")
    return (dx / length, dy / length)


def _offset(point: Point, u: Point, v: Point, a: float, b: float) -> Point:
    return (point[0] + u[0] * a + v[0] * b, point[1] + u[1] * a + v[1] * b)


def _component_symbol(kind: str, center: Point, u: Point, v: Point, component: Mapping[str, Any], canvas: Canvas) -> None:
    """Draw one IEC-style symbol centred at ``center``, oriented along ``u``."""

    def line(a: float, b: float, c: float, d: float, style: Style = SYMBOL) -> None:
        canvas.line_screen(_offset(center, u, v, a, b), _offset(center, u, v, c, d), style)

    def poly(points: Sequence[tuple[float, float]], style: Style = SYMBOL) -> None:
        canvas.polyline_screen([_offset(center, u, v, a, b) for a, b in points], style)

    if kind == "resistor":
        poly([(-22, 0), (-16, 0), (-12, 7), (-6, -7), (0, 7), (6, -7), (12, 0), (22, 0)])
    elif kind == "rheostat":
        poly([(-22, 0), (-16, 0), (-12, 7), (-6, -7), (0, 7), (6, -7), (12, 0), (22, 0)])
        canvas.arrow_screen(
            _offset(center, u, v, -10, -22), _offset(center, u, v, 12, 8), Style(stroke=PALETTE["accent"], width=1.6), head=7
        )
    elif kind == "battery":
        reversed_polarity = component.get("polarity") == "reversed"
        sign = -1.0 if reversed_polarity else 1.0
        line(-3 * sign, -13, -3 * sign, 13, Style(stroke=PALETTE["ink"], width=2.6))
        line(3 * sign, -7, 3 * sign, 7, Style(stroke=PALETTE["ink"], width=1.4))
        line(-22, 0, -3 * sign, 0)
        line(3 * sign, 0, 22, 0)
        canvas.text_screen(_offset(center, u, v, -3 * sign, -18), "+", size=13, color=PALETTE["ink"])
    elif kind in {"ammeter", "voltmeter", "lamp"}:
        line(-22, 0, -12, 0)
        line(12, 0, 22, 0)
        canvas.circle_screen(center, 12, SYMBOL_FILL)
        if kind == "lamp":
            line(-8, -8, 8, 8, Style(stroke=PALETTE["ink"], width=1.6))
            line(-8, 8, 8, -8, Style(stroke=PALETTE["ink"], width=1.6))
        else:
            canvas.text_screen(center, "A" if kind == "ammeter" else "V", size=14, bold=True)
    elif kind == "switch":
        line(-22, 0, -9, 0)
        line(9, 0, 22, 0)
        canvas.dot_screen(_offset(center, u, v, -9, 0), 2.6, PALETTE["ink"])
        canvas.dot_screen(_offset(center, u, v, 9, 0), 2.6, PALETTE["ink"])
        line(-9, 0, 8, -12, Style(stroke=PALETTE["ink"], width=2.0))
    elif kind == "capacitor":
        line(-22, 0, -4, 0)
        line(4, 0, 22, 0)
        line(-4, -12, -4, 12, Style(stroke=PALETTE["ink"], width=2.4))
        line(4, -12, 4, 12, Style(stroke=PALETTE["ink"], width=2.4))
    elif kind == "inductor":
        line(-22, 0, -16, 0)
        line(16, 0, 22, 0)
        for index in range(3):
            base = -16 + index * 11
            points = []
            for step in range(13):
                angle = math.pi * step / 12
                points.append((base + 5.5 * step / 12 * 2, -6.5 * math.sin(angle)))
            canvas.polyline_screen([_offset(center, u, v, a, b) for a, b in points], SYMBOL)
    else:
        raise RenderError("unknown_component", f"unsupported circuit component {kind!r}")


def _layout_nodes(nodes: Sequence[str], edges: Sequence[tuple[str, str, int]]) -> tuple[dict[str, Point], str]:
    """Deterministic layout in a 12 x 8 design space."""

    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    for a, b, _ in edges:
        adjacency[a].append(b)
        adjacency[b].append(a)

    if len(nodes) == 2 and len(edges) > 1:
        return _parallel_layout(nodes, len(edges))

    degrees = {node: len(neighbors) for node, neighbors in adjacency.items()}
    if len(nodes) >= 3 and all(degree == 2 for degree in degrees.values()):
        order = _walk_cycle(nodes[0], adjacency)
        if len(order) == len(nodes):
            return _ring_layout(order, rectangle=True), "cycle"

    if all(degree <= 2 for degree in degrees.values()):
        ends = [node for node in nodes if degrees[node] == 1]
        if len(ends) == 2:
            order = _walk_path(ends[0], adjacency)
            if len(order) == len(nodes):
                return _series_layout(order), "series"

    order = _bfs_order(nodes[0], adjacency)
    for node in nodes:
        if node not in order:
            order.append(node)
    return _circle_layout(order), "graph"


def _walk_cycle(start: str, adjacency: Mapping[str, list[str]]) -> list[str]:
    order = [start]
    previous = None
    current = start
    while True:
        options = [neighbor for neighbor in adjacency[current] if neighbor != previous]
        if not options:
            break
        nxt = options[0]
        if nxt == start:
            break
        if nxt in order:
            break
        order.append(nxt)
        previous, current = current, nxt
    return order


def _walk_path(start: str, adjacency: Mapping[str, list[str]]) -> list[str]:
    order = [start]
    previous = None
    current = start
    while True:
        options = [neighbor for neighbor in adjacency[current] if neighbor != previous]
        if not options:
            break
        nxt = options[0]
        if nxt in order:
            break
        order.append(nxt)
        previous, current = current, nxt
    return order


def _bfs_order(start: str, adjacency: Mapping[str, list[str]]) -> list[str]:
    seen = {start}
    order = [start]
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                order.append(neighbor)
                queue.append(neighbor)
    return order


def _ring_layout(order: Sequence[str], *, rectangle: bool = True) -> dict[str, Point]:
    count = len(order)
    position: dict[str, Point] = {}
    if rectangle and count >= 4:
        # Distribute along the rectangle perimeter starting at the top-left.
        perimeter = 2 * (12.0 + 8.0)
        step = perimeter / count
        for index, node in enumerate(order):
            distance = index * step
            if distance < 12.0:
                position[node] = (distance, 7.0)
            elif distance < 20.0:
                position[node] = (12.0, 7.0 - (distance - 12.0))
            elif distance < 32.0:
                position[node] = (12.0 - (distance - 20.0), -1.0)
            else:
                position[node] = (0.0, -1.0 + (distance - 32.0))
        return position
    return _circle_layout(order)


def _circle_layout(order: Sequence[str]) -> dict[str, Point]:
    count = max(len(order), 1)
    position: dict[str, Point] = {}
    for index, node in enumerate(order):
        angle = math.pi / 2 - 2 * math.pi * index / count
        position[node] = (6.0 + 5.0 * math.cos(angle), 3.0 + 3.2 * math.sin(angle))
    return position


def _series_layout(order: Sequence[str]) -> dict[str, Point]:
    count = max(len(order) - 1, 1)
    return {node: (1.0 + 10.0 * index / count, 6.0) for index, node in enumerate(order)}


def _parallel_layout(nodes: Sequence[str], branches: int) -> tuple[dict[str, Point], str]:
    left, right = nodes[0], nodes[1]
    return {left: (1.0, 3.5), right: (11.0, 3.5)}, "parallel"


def render_circuit(spec: Mapping[str, Any], canvas: Canvas) -> CircuitStats:
    stats = CircuitStats()
    components = list(spec.get("components") or [])
    if not components:
        raise RenderError("empty_circuit", "circuit needs at least one component")

    nodes: list[str] = []
    for component in components:
        for key in ("from", "to"):
            name = str(component[key])
            if name not in nodes:
                nodes.append(name)
    explicit = spec.get("nodes") or {}
    for name in explicit:
        if name not in nodes:
            nodes.append(str(name))

    edges: list[tuple[str, str, int]] = []
    for index, component in enumerate(components):
        edges.append((str(component["from"]), str(component["to"]), index))

    if explicit:
        layout = {str(name): (float(value[0]), float(value[1])) for name, value in explicit.items()}
        for name in nodes:
            if name not in layout:
                raise RenderError("incomplete_layout", f"nodes layout is missing {name!r}")
        stats.layout = "explicit"
    else:
        layout, kind = _layout_nodes(nodes, edges)
        stats.layout = kind

    xs = [point[0] for point in layout.values()]
    ys = [point[1] for point in layout.values()]
    pad = 0.9
    canvas.fit((min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad), margin=86, uniform=True, max_scale=90.0)

    # ---- return wire for series chains so the circuit is closed
    if stats.layout == "series":
        order = list(layout.keys())
        first, last = order[0], order[-1]
        bottom = min(point[1] for point in layout.values()) - 2.6
        canvas.line_screen(canvas.to_screen((layout[last][0], layout[last][1] - 0.0)), canvas.to_screen((layout[last][0], bottom)))
        canvas.line_screen(canvas.to_screen((layout[last][0], bottom)), canvas.to_screen((layout[first][0], bottom)))
        canvas.line_screen(canvas.to_screen((layout[first][0], bottom)), canvas.to_screen((layout[first][0], layout[first][1])))

    # ---- wires and symbols
    for index, component in enumerate(components):
        a, b = str(component["from"]), str(component["to"])
        p = canvas.to_screen(layout[a])
        q = canvas.to_screen(layout[b])
        kind = str(component["kind"])
        vector = _unit(p, q)
        perpendicular = (-vector[1], vector[0])
        if len(nodes) == 2 and len(components) > 1 and not explicit:
            # Route parallel branches through distinct horizontal lanes.
            lane = (index - (len(components) - 1) / 2) * 96.0
            corner_a = (p[0], p[1] + lane)
            corner_b = (q[0], q[1] + lane)
            canvas.line_screen(p, corner_a, WIRE)
            canvas.line_screen(corner_b, q, WIRE)
            start, end = corner_a, corner_b
            vector = _unit(start, end)
            perpendicular = (-vector[1], vector[0])
        else:
            start, end = p, q
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        lead = min(30.0, length * 0.36)
        terminal_a = (mid[0] - vector[0] * lead, mid[1] - vector[1] * lead)
        terminal_b = (mid[0] + vector[0] * lead, mid[1] + vector[1] * lead)
        canvas.line_screen(start, terminal_a, WIRE)
        canvas.line_screen(terminal_b, end, WIRE)
        _component_symbol(kind, mid, vector, perpendicular, component, canvas)
        stats.components += 1

        label = str(component.get("label") or "")
        value = str(component.get("value") or "")
        caption = " ".join(part for part in (label, value) if part)
        if caption:
            upward = perpendicular if perpendicular[1] < 0 else (-perpendicular[0], -perpendicular[1])
            canvas.text_screen(
                (mid[0] + upward[0] * 32.0, mid[1] + upward[1] * 32.0),
                caption,
                size=13,
                anchor="middle",
                color=PALETTE["ink"],
                background="#ffffff",
            )

    # ---- junctions
    degree: dict[str, int] = {name: 0 for name in nodes}
    for a, b, _ in edges:
        degree[a] += 1
        degree[b] += 1
    for name, count in degree.items():
        if count >= 3:
            canvas.dot_screen(canvas.to_screen(layout[name]), 3.4, PALETTE["ink"])
    stats.nodes = len(nodes)

    # ---- current arrows
    for arrow in spec.get("current_arrows") or []:
        a, b = str(arrow["from"]), str(arrow["to"])
        if a not in layout or b not in layout:
            stats.warnings.append(f"current arrow references unknown node {a!r}/{b!r}")
            continue
        p = canvas.to_screen(layout[a])
        q = canvas.to_screen(layout[b])
        start = (p[0] + (q[0] - p[0]) * 0.32, p[1] + (q[1] - p[1]) * 0.32)
        end = (p[0] + (q[0] - p[0]) * 0.55, p[1] + (q[1] - p[1]) * 0.55)
        canvas.arrow_screen(start, end, CURRENT, head=9.0, label=arrow.get("label"), label_offset=(0, -14), label_size=12)

    for note_index, note in enumerate(spec.get("notes") or []):
        canvas.text_screen(
            (24, canvas.height - 22 - 18 * note_index), str(note), size=12, anchor="start", color=PALETTE["muted"]
        )
    if spec.get("title"):
        canvas.text_screen((24, 26), str(spec["title"]), size=16, anchor="start", baseline="middle", bold=True)
    return stats
