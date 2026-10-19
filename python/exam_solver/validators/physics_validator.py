"""Physics plausibility checks: units, dimensions and magnitudes.

This is a *sanity layer*, not a physics engine. It cannot prove a solution is
correct, but it reliably catches the failure modes that cost exam marks:

* a number with no unit,
* a unit whose dimension does not match the quantity,
* an answer that is dimensionally impossible,
* an absurd order of magnitude (``v = 10^20 m/s``).
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping, Sequence

__all__ = ["validate_physics", "parse_quantities", "parse_unit", "DIMENSIONS"]

# --------------------------------------------------------------------------- units

# Dimension vectors over (L, T, M, I, K). Derived units are spelled out so the
# error messages can say *why* a unit is wrong.
DIMENSIONS: dict[str, dict[str, int]] = {
    "m": {"L": 1},
    "km": {"L": 1},
    "cm": {"L": 1},
    "mm": {"L": 1},
    "s": {"T": 1},
    "ms": {"T": 1},
    "min": {"T": 1},
    "h": {"T": 1},
    "kg": {"M": 1},
    "g": {"M": 1},
    "mg": {"M": 1},
    "A": {"I": 1},
    "mA": {"I": 1},
    "K": {"K": 1},
    "mol": {"N": 1},
    "m/s": {"L": 1, "T": -1},
    "m/s^2": {"L": 1, "T": -2},
    "m/s2": {"L": 1, "T": -2},
    "N": {"L": 1, "T": -2, "M": 1},
    "J": {"L": 2, "T": -2, "M": 1},
    "W": {"L": 2, "T": -3, "M": 1},
    "C": {"T": 1, "I": 1},
    "V": {"L": 2, "T": -3, "M": 1, "I": -1},
    "Ω": {"L": 2, "T": -3, "M": 1, "I": -2},
    "ohm": {"L": 2, "T": -3, "M": 1, "I": -2},
    "F": {"L": -2, "T": 4, "M": -1, "I": 2},
    "H": {"L": 2, "T": -2, "M": 1, "I": -2},
    "T": {"T": -2, "M": 1, "I": -1},
    "Hz": {"T": -1},
    "Pa": {"L": -1, "T": -2, "M": 1},
    "kg·m/s": {"L": 1, "T": -1, "M": 1},
    "N·s": {"L": 1, "T": -1, "M": 1},
    "%": {},
}

DIMENSION_NAMES = {
    "length": {"L": 1},
    "time": {"T": 1},
    "mass": {"M": 1},
    "velocity": {"L": 1, "T": -1},
    "acceleration": {"L": 1, "T": -2},
    "force": {"L": 1, "T": -2, "M": 1},
    "energy": {"L": 2, "T": -2, "M": 1},
    "power": {"L": 2, "T": -3, "M": 1},
    "charge": {"T": 1, "I": 1},
    "current": {"I": 1},
    "voltage": {"L": 2, "T": -3, "M": 1, "I": -1},
    "resistance": {"L": 2, "T": -3, "M": 1, "I": -2},
    "capacitance": {"L": -2, "T": 4, "M": -1, "I": 2},
    "inductance": {"L": 2, "T": -2, "M": 1, "I": -2},
    "magnetic_field": {"T": -2, "M": 1, "I": -1},
    "frequency": {"T": -1},
    "pressure": {"L": -1, "T": -2, "M": 1},
    "momentum": {"L": 1, "T": -1, "M": 1},
    "area": {"L": 2},
    "volume": {"L": 3},
    "dimensionless": {},
}

# Unambiguous quantity letters used to find a dimension mismatch even when the
# solver forgot to declare a unit_check.
SYMBOL_DIMENSIONS: dict[str, str] = {
    "v": "velocity",
    "a": "acceleration",
    "F": "force",
    "N": "force",
    "W": "energy",
    "J": "energy",
    "P": "power",
    "R": "resistance",
    "U": "voltage",
    "I": "current",
    "q": "charge",
    "Q": "charge",
    "B": "magnetic_field",
    "λ": "length",
    "m": "mass",
    "t": "time",
}

MAGNITUDE_LIMITS = {
    "velocity": (3.0e8, 1.0e7),
    "acceleration": (math.inf, 1.0e6),
    "current": (math.inf, 1.0e4),
    "voltage": (math.inf, 1.0e7),
    "force": (math.inf, 1.0e9),
    "energy": (math.inf, 1.0e12),
    "resistance": (math.inf, 1.0e12),
    "mass": (math.inf, 1.0e6),
    "frequency": (math.inf, 1.0e15),
}


def _dim_key(dimension: Mapping[str, int]) -> str:
    keys = ["L", "T", "M", "I", "K", "N"]
    return "·".join(f"{key}^{int(dimension[key])}" for key in keys if dimension.get(key))


def parse_unit(unit: str) -> tuple[dict[str, int], str] | None:
    """Parse a unit expression into a dimension vector.

    Supports products (``kg·m``), division (``m/s``) and exponents
    (``m/s^2``, ``s^-1``). Returns ``None`` when the unit is unknown.
    """

    text = (unit or "").strip().rstrip(",，;；。")
    if not text:
        return ({}, "dimensionless")
    if text in {"1", "无", "-", "—"}:
        return ({}, "dimensionless")
    # Normalise multiplication signs and unicode superscripts.
    text = text.replace("²", "^2").replace("³", "^3").replace("·", "*").replace("⋅", "*")
    text = text.replace("×", "*").replace(" ", "")
    # Split into numerator / denominator on the first '/', keeping the rest.
    if "/" in text:
        numerator_text, _, denominator_text = text.partition("/")
        denominator = _parse_product(denominator_text)
        if denominator is None:
            return None
        dimension, label = denominator
        inverse = {key: -value for key, value in dimension.items()}
        numerator = _parse_product(numerator_text)
        if numerator is None:
            return None
        return _combine(numerator[0], inverse), f"{numerator[1]}/{label}"
    product = _parse_product(text)
    return product


def _parse_product(text: str) -> tuple[dict[str, int], str] | None:
    if not text:
        return ({}, "1")
    dimension: dict[str, int] = {}
    labels = []
    for token in re.split(r"\*", text):
        if not token:
            continue
        base, _, exponent_text = token.partition("^")
        exponent = 1
        if exponent_text:
            try:
                exponent = int(exponent_text)
            except ValueError:
                return None
        base = base.strip()
        if base in DIMENSIONS:
            for key, value in DIMENSIONS[base].items():
                dimension[key] = dimension.get(key, 0) + value * exponent
            labels.append(base if exponent == 1 else f"{base}^{exponent}")
            continue
        # Prefixes such as kΩ, mV, μF.
        match = re.fullmatch(r"(k|M|m|μ|u|n|G)([A-Za-zΩ]+)", base)
        if match and match.group(2) in DIMENSIONS:
            for key, value in DIMENSIONS[match.group(2)].items():
                dimension[key] = dimension.get(key, 0) + value * exponent
            labels.append(f"{base}^{exponent}" if exponent != 1 else base)
            continue
        return None
    return ({key: value for key, value in dimension.items() if value}, "*".join(labels))


def _combine(first: Mapping[str, int], second: Mapping[str, int]) -> dict[str, int]:
    combined = dict(first)
    for key, value in second.items():
        combined[key] = combined.get(key, 0) + value
    return {key: value for key, value in combined.items() if value}


_QUANTITY = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-zα-ωΑ-Ω][A-Za-z0-9_]*)\s*[=＝≈]\s*"
    r"([-+]?\d+(?:\.\d+)?)(?:\s*[×x]\s*10\s*\^?\s*([-+]?\d+))?"
    r"(?:\s*([A-Za-zμΩ°%][A-Za-zΩμ°%/·\^0-9²³]*))?"
)


def parse_quantities(text: str) -> list[dict[str, Any]]:
    """Extract ``symbol = number unit`` quantities from a free-text answer."""

    quantities: list[dict[str, Any]] = []
    for match in _QUANTITY.finditer(text or ""):
        symbol = match.group(1)
        try:
            value = float(match.group(2))
        except (TypeError, ValueError):
            continue
        exponent = match.group(3)
        if exponent is not None:
            try:
                value *= 10 ** int(exponent)
            except ValueError:
                pass
        unit = (match.group(4) or "").strip()
        if unit.lower() in {"或", "and", "or"}:
            unit = ""
        quantities.append({"symbol": symbol, "value": value, "unit": unit})
    return quantities


def _check(name: str, passed: bool, details: str, *, severity: str = "error") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "details": details,
        "method": "unit_analysis",
    }


def _declared_unit_checks(claims: Iterable[Mapping[str, Any]]) -> Iterable[dict[str, Any]]:
    for index, claim in enumerate(claims):
        if str(claim.get("kind")) != "unit_check":
            continue
        name = f"unit_check:{claim.get('value') or index}"
        unit = str(claim.get("unit") or "")
        dimension_name = str(claim.get("dimension") or "")
        parsed = parse_unit(unit)
        if parsed is None:
            yield _check(name, False, f"unrecognised unit {unit!r}")
            continue
        actual, label = parsed
        expected = DIMENSION_NAMES.get(dimension_name)
        if expected is None:
            yield _check(name, True, f"unit {label!r} parsed; unknown dimension label {dimension_name!r}", severity="warning")
            continue
        yield _check(
            name,
            actual == expected,
            f"{label!r} has dimension {_dim_key(actual) or '1'}; {dimension_name} needs {_dim_key(expected) or '1'}",
        )


def _answer_unit_checks(answer_spec: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    final = str(answer_spec.get("final_answer") or "")
    quantities = parse_quantities(final)
    if not quantities:
        yield _check(
            "physics:numeric_answer",
            True,
            "no numeric quantity with a unit found in the final answer",
            severity="warning",
        )
        return
    for quantity in quantities:
        symbol = quantity["symbol"]
        unit = quantity["unit"]
        if not unit:
            expected = SYMBOL_DIMENSIONS.get(symbol)
            yield _check(
                f"physics:unit:{symbol}",
                expected is None,
                f"{symbol} has no unit; expected a {expected} quantity" if expected else f"{symbol} has no unit",
                severity="warning" if expected is None else "error",
            )
            continue
        parsed = parse_unit(unit)
        if parsed is None:
            yield _check(f"physics:unit:{symbol}", False, f"unrecognised unit {unit!r} for {symbol}", severity="warning")
            continue
        dimension, label = parsed
        expected_name = SYMBOL_DIMENSIONS.get(symbol)
        if expected_name is None:
            continue
        expected = DIMENSION_NAMES[expected_name]
        yield _check(
            f"physics:dimension:{symbol}",
            dimension == expected,
            f"{symbol} = {quantity['value']:g} {label} has dimension {_dim_key(dimension) or '1'}; "
            f"{expected_name} needs {_dim_key(expected) or '1'}",
        )


def _magnitude_checks(answer_spec: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    final = str(answer_spec.get("final_answer") or "")
    for quantity in parse_quantities(final):
        symbol = quantity["symbol"]
        expected_name = SYMBOL_DIMENSIONS.get(symbol)
        if not expected_name or expected_name not in MAGNITUDE_LIMITS:
            continue
        value = abs(float(quantity["value"]))
        hard, soft = MAGNITUDE_LIMITS[expected_name]
        if value > hard:
            yield _check(
                f"physics:magnitude:{symbol}",
                False,
                f"{symbol} = {quantity['value']:g} {quantity['unit']} exceeds the physical limit for {expected_name}",
            )
        elif value > soft:
            yield _check(
                f"physics:magnitude:{symbol}",
                False,
                f"{symbol} = {quantity['value']:g} {quantity['unit']} is an implausible {expected_name} for a school problem",
                severity="warning",
            )


def validate_physics(
    problem_spec: Mapping[str, Any],
    answer_spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Run unit/dimension/magnitude checks and return a ValidationReport."""

    checks: list[dict[str, Any]] = []
    is_physics = str(problem_spec.get("subject") or "") == "physics"
    if is_physics:
        checks.extend(_declared_unit_checks(answer_spec.get("verification") or []))
        checks.extend(_answer_unit_checks(answer_spec))
        checks.extend(_magnitude_checks(answer_spec))
    else:
        checks.append(
            _check(
                "physics:applicable",
                True,
                "problem is not classified as physics; physical checks are informational",
                severity="info",
            )
        )

    evaluated = [check for check in checks if check.get("severity") != "info"]
    failures = [check for check in evaluated if not check["passed"] and check.get("severity") == "error"]
    warnings = [check for check in evaluated if not check["passed"] and check.get("severity") != "error"]
    return {
        "passed": not failures,
        "checks": checks,
        "warnings": [f"{check['name']}: {check['details']}" for check in warnings],
        "contradictions": [f"{check['name']}: {check['details']}" for check in failures],
        "recommended_revision": [
            f"Fix the unit or magnitude of {check['name'].split(':')[-1]}: {check['details']}" for check in failures
        ],
        "coverage": {
            "claimed_checks": len([item for item in answer_spec.get("verification") or [] if item.get("kind") == "unit_check"]),
            "executed_checks": len(evaluated),
            "skipped_checks": len(checks) - len(evaluated),
        },
    }


def merge_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Combine several ValidationReports into one."""

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    contradictions: list[str] = []
    recommendations: list[str] = []
    coverage = {"claimed_checks": 0, "executed_checks": 0, "skipped_checks": 0}
    for report in reports:
        checks.extend(report.get("checks") or [])
        warnings.extend(report.get("warnings") or [])
        contradictions.extend(report.get("contradictions") or [])
        recommendations.extend(report.get("recommended_revision") or [])
        for key in coverage:
            coverage[key] += int((report.get("coverage") or {}).get(key) or 0)
    failures = [check for check in checks if not check.get("passed") and check.get("severity") == "error"]
    return {
        "passed": not failures,
        "checks": checks,
        "warnings": _unique(warnings),
        "contradictions": _unique(contradictions),
        "recommended_revision": _unique(recommendations),
        "coverage": coverage,
    }


def _unique(values: Sequence[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
