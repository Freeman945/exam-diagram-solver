"""Programmatic mathematical verification with SymPy.

The solver attaches machine-checkable claims to every answer
(``AnswerSpec.verification``). This module re-evaluates them independently -
it never trusts the model's own statement that something was checked.

Checks are graded honestly:

* ``passed`` - the claim holds.
* failed with ``severity=error`` - the claim is false; the answer must change.
* skipped with ``severity=info`` - the claim could not be machine-checked and
  the report says why (unparsable notation, too many free symbols, ...).
"""

from __future__ import annotations

import math
import random
import re
from typing import Any, Iterable, Mapping, Sequence

__all__ = ["validate_math", "parse_assignments", "sympy_available"]

_ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)\s*[=＝]\s*([-+]?\d+(?:\.\d+)?(?:/\d+)?)(?!\s*[+\-*/^×÷])"
)
_SPLIT_VALUES = re.compile(r"[、,，;；]|\bor\b|或|和|以及")


def sympy_available() -> bool:
    try:
        import sympy  # noqa: F401

        return True
    except Exception:
        return False


def _sp():
    import sympy as sp

    return sp


def parse_assignments(text: str) -> dict[str, list[str]]:
    """Extract ``x = 2``-style assignments from a free-text final answer."""

    found: dict[str, list[str]] = {}
    for match in _ASSIGNMENT.finditer(text or ""):
        name = match.group(1)
        value = match.group(2).strip()
        found.setdefault(name, []).append(value)
    # "x = 2, 3" style: capture numbers that follow a leading assignment.
    for match in re.finditer(r"([A-Za-z][A-Za-z0-9_]*)\s*[=＝]\s*([^;；\n]+)", text or ""):
        name = match.group(1)
        tail = match.group(2)
        for chunk in _SPLIT_VALUES.split(tail):
            chunk = chunk.strip().rstrip("。.")
            if not chunk:
                continue
            if re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:/\d+)?", chunk):
                values = found.setdefault(name, [])
                literal = chunk
                if literal not in values:
                    values.append(literal)
    return found


def _parse_expression(text: str, variables: Iterable[str] = ()):
    sp = _sp()
    source = str(text).strip()
    if not source:
        raise ValueError("empty expression")
    source = source.replace("^", "**").replace("×", "*").replace("÷", "/").replace("−", "-")
    source = source.replace("π", "pi").replace("√", "sqrt")
    local = {name: sp.Symbol(name, real=True) for name in variables}
    local.update(
        {
            "sin": sp.sin,
            "cos": sp.cos,
            "tan": sp.tan,
            "cot": sp.cot,
            "sec": sp.sec,
            "csc": sp.csc,
            "sqrt": sp.sqrt,
            "log": sp.log,
            "ln": sp.log,
            "lg": lambda value: sp.log(value, 10),
            "exp": sp.exp,
            "abs": sp.Abs,
            "Abs": sp.Abs,
            "pi": sp.pi,
            "e": sp.E,
        }
    )
    return sp.sympify(source, locals=local)


def _symbols(expression) -> set[str]:
    return {str(symbol) for symbol in getattr(expression, "free_symbols", set())}


def _numeric_zero(expression, *, tolerance: float = 1e-9, samples: int = 6) -> tuple[bool, str]:
    """Numerically test that ``expression`` is identically zero.

    Sampling cannot prove an identity, so a "true" result is reported as
    numerical evidence, never as a symbolic proof.
    """

    sp = _sp()
    free = sorted(_symbols(expression))
    if not free:
        try:
            value = complex(sp.N(expression, 15))
        except Exception as exc:
            return False, f"could not evaluate: {exc}"
        return (abs(value) < tolerance, f"value = {value.real:.3e}")
    random.seed(20240601)
    tried = 0
    worst = 0.0
    while tried < samples:
        values = {}
        for name in free:
            candidate = random.choice([-2.7, -1.3, 0.6, 1.9, 3.1, 0.2])
            values[name] = candidate
        try:
            substituted = expression.subs({sp.Symbol(name, real=True): value for name, value in values.items()})
            result = complex(sp.N(substituted, 15))
        except Exception:
            continue
        tried += 1
        worst = max(worst, abs(result))
        if abs(result) > max(tolerance, 1e-7):
            return False, f"fails at {values}: residual {result.real:.3e}"
    if tried == 0:
        return False, "could not evaluate numerically"
    return True, f"numerically consistent over {tried} samples (max residual {worst:.3e})"


def _symbolic_zero(expression) -> tuple[bool, str]:
    sp = _sp()
    try:
        simplified = sp.simplify(expression)
    except Exception as exc:
        return False, f"simplify failed: {exc}"
    if simplified == 0:
        return True, "simplified to 0"
    try:
        expanded = sp.simplify(sp.expand(expression))
        if expanded == 0:
            return True, "expanded to 0"
    except Exception:
        pass
    try:
        trig = sp.trigsimp(simplified)
        if trig == 0:
            return True, "trig-simplified to 0"
    except Exception:
        pass
    return False, f"simplify left {simplified}"


def _prove_zero(expression) -> tuple[bool, str, str]:
    """Return (passed, details, method)."""

    ok, detail = _symbolic_zero(expression)
    if ok:
        return True, detail, "symbolic"
    numeric_ok, numeric_detail = _numeric_zero(expression)
    if numeric_ok:
        return True, f"{detail}; {numeric_detail} (numerical evidence only)", "numeric"
    return False, f"{detail}; {numeric_detail}", "symbolic"


def _check(name: str, passed: bool, details: str, *, severity: str = "error", method: str = "sympy") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "details": details,
        "method": method,
    }


def _skipped(name: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": True,
        "severity": "info",
        "details": f"skipped: {reason}",
        "method": "sympy",
        "skipped": True,
    }


def _equation_substitution(claim: Mapping[str, Any]) -> dict[str, Any]:
    sp = _sp()
    equation = str(claim.get("equation") or "")
    assignments = claim.get("assignments") or {}
    name = f"equation_substitution:{equation}"
    if "=" not in equation and "＝" not in equation:
        return _skipped(name, "no '=' in equation")
    left_text, right_text = re.split(r"[=＝]", equation, maxsplit=1)
    try:
        left = _parse_expression(left_text, assignments.keys())
        right = _parse_expression(right_text, assignments.keys())
    except Exception as exc:
        return _skipped(name, f"cannot parse equation: {exc}")
    substitutions = {}
    for symbol_name, value_text in assignments.items():
        try:
            substitutions[sp.Symbol(symbol_name, real=True)] = _parse_expression(value_text)
        except Exception as exc:
            return _skipped(name, f"cannot parse assignment {symbol_name}={value_text}: {exc}")
    try:
        residual = sp.simplify((left - right).subs(substitutions))
    except Exception as exc:
        return _skipped(name, f"substitution failed: {exc}")
    passed, details, method = _prove_zero(residual)
    detail_text = f"residual = {residual}; {details}"
    return _check(name, passed, detail_text, method=method)


def _identity(claim: Mapping[str, Any]) -> dict[str, Any]:
    sp = _sp()
    name = "identity"
    try:
        left = _parse_expression(str(claim.get("lhs") or ""))
        right = _parse_expression(str(claim.get("rhs") or ""))
    except Exception as exc:
        return _skipped(name, f"cannot parse identity: {exc}")
    passed, details, method = _prove_zero(sp.simplify(left - right))
    return _check(name, passed, f"{claim.get('lhs')} ≡ {claim.get('rhs')}: {details}", method=method)


def _derivative(claim: Mapping[str, Any]) -> dict[str, Any]:
    sp = _sp()
    variable = str(claim.get("variable") or "x")
    name = f"derivative:{variable}"
    try:
        expression = _parse_expression(str(claim.get("expression") or ""), [variable])
        claimed = _parse_expression(str(claim.get("claimed") or ""), [variable])
    except Exception as exc:
        return _skipped(name, f"cannot parse derivative claim: {exc}")
    symbol = sp.Symbol(variable, real=True)
    try:
        actual = sp.diff(expression, symbol)
    except Exception as exc:
        return _skipped(name, f"differentiation failed: {exc}")
    passed, details, method = _prove_zero(sp.simplify(actual - claimed))
    return _check(name, passed, f"d/d{variable}({expression}) = {actual}; {details}", method=method)


def _integral(claim: Mapping[str, Any]) -> dict[str, Any]:
    sp = _sp()
    variable = str(claim.get("variable") or "x")
    name = f"integral:{variable}"
    try:
        integrand = _parse_expression(str(claim.get("expression") or ""), [variable])
        claimed = _parse_expression(str(claim.get("claimed") or ""), [variable])
    except Exception as exc:
        return _skipped(name, f"cannot parse integral claim: {exc}")
    symbol = sp.Symbol(variable, real=True)
    lower = claim.get("lower")
    upper = claim.get("upper")
    try:
        if lower is not None and upper is not None:
            lower_expr = _parse_expression(str(lower))
            upper_expr = _parse_expression(str(upper))
            actual = sp.integrate(integrand, (symbol, lower_expr, upper_expr))
            difference = sp.simplify(actual - claimed)
        else:
            derivative = sp.diff(claimed, symbol)
            difference = sp.simplify(derivative - integrand)
    except Exception as exc:
        return _skipped(name, f"integration failed: {exc}")
    passed, details, method = _prove_zero(difference)
    return _check(name, passed, details, method=method)


def _numeric(claim: Mapping[str, Any]) -> dict[str, Any]:
    sp = _sp()
    name = "numeric"
    variables = claim.get("variables") or {}
    assignments = {str(key): str(value) for key, value in variables.items()}
    try:
        expression = _parse_expression(str(claim.get("expression") or ""))
        expected = _parse_expression(str(claim.get("expected") or ""))
    except Exception as exc:
        return _skipped(name, f"cannot parse numeric claim: {exc}")
    substitutions = {}
    for symbol_name, value_text in assignments.items():
        try:
            substitutions[sp.Symbol(symbol_name, real=True)] = _parse_expression(value_text)
        except Exception:
            return _skipped(name, f"cannot parse variable {symbol_name}")
    try:
        left = complex(sp.N(expression.subs(substitutions), 15))
        right = complex(sp.N(expected.subs(substitutions), 15))
    except Exception as exc:
        return _skipped(name, f"evaluation failed: {exc}")
    tolerance = float(claim.get("tolerance") or 1e-6)
    scale = max(abs(left), abs(right), 1.0)
    difference = abs(left - right)
    return _check(
        name,
        difference <= tolerance * scale,
        f"|{left.real:.10g} - {right.real:.10g}| = {difference:.3e} (limit {tolerance * scale:.3e})",
        method="numeric",
    )


def _answer_checks(
    problem_spec: Mapping[str, Any],
    answer_spec: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Structural checks that do not need SymPy."""

    checks: list[dict[str, Any]] = []
    final = str(answer_spec.get("final_answer") or "").strip()
    steps = answer_spec.get("steps") or []
    checks.append(_check("answer:final_present", bool(final), "final answer is non-empty" if final else "final answer is empty", method="rules"))
    checks.append(
        _check(
            "answer:steps_present",
            len(steps) >= 1,
            f"{len(steps)} step(s) provided",
            severity="warning",
            method="rules",
        )
    )
    key_steps = [step for step in steps if str(step.get("score_relevance") or "normal") == "key"]
    checks.append(
        _check(
            "answer:key_steps",
            len(key_steps) >= 1,
            f"{len(key_steps)} key step(s) marked",
            severity="warning",
            method="rules",
        )
    )
    subject = str(problem_spec.get("subject") or "")
    declares_dimensionless = any(
        str(claim.get("kind")) == "unit_check" and str(claim.get("dimension")) == "dimensionless"
        for claim in answer_spec.get("verification") or []
    )
    if subject == "physics" and re.search(r"\d", final) and not declares_dimensionless:
        has_unit = bool(
            re.search(r"\d\s*(m/s(?:\^?2|²)?|N|J|W|V|A|Ω|C|T|Hz|kg|Pa|mol|K|%|m|s|g)\b", final)
        )
        checks.append(
            _check(
                "answer:units_present",
                has_unit,
                "a unit is present in the final answer" if has_unit else "final answer has a number but no recognisable unit",
                severity="error",
                method="rules",
            )
        )
    return checks


def _auto_checks(problem_spec: Mapping[str, Any], answer_spec: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    """Derive checks directly from the problem when the solver did not."""

    assignments = parse_assignments(str(answer_spec.get("final_answer") or ""))
    if not assignments:
        return
    for equation in problem_spec.get("equations") or []:
        text = str(equation.get("text") or "")
        if "=" not in text and "＝" not in text:
            continue
        try:
            left_text, right_text = re.split(r"[=＝]", text, maxsplit=1)
            left = _parse_expression(left_text)
            right = _parse_expression(right_text)
            free = _symbols(left - right)
        except Exception:
            continue
        if len(free) != 1:
            continue
        symbol = next(iter(free))
        values = assignments.get(symbol)
        if not values:
            continue
        for value in values[:6]:
            yield _equation_substitution(
                {
                    "equation": text,
                    "assignments": {symbol: value},
                    "kind": "equation_substitution",
                }
            )


def validate_math(
    problem_spec: Mapping[str, Any],
    answer_spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Run every declared and auto-derived mathematical check."""

    checks: list[dict[str, Any]] = []
    if not sympy_available():
        checks.append(
            _check(
                "environment:sympy",
                False,
                "SymPy is not installed, so symbolic verification is unavailable",
                severity="warning",
                method="rules",
            )
        )
        return _report(checks)

    claims = list(answer_spec.get("verification") or [])
    for claim in claims:
        kind = str(claim.get("kind"))
        if kind == "equation_substitution":
            checks.append(_equation_substitution(claim))
        elif kind == "identity":
            checks.append(_identity(claim))
        elif kind == "derivative":
            checks.append(_derivative(claim))
        elif kind == "integral":
            checks.append(_integral(claim))
        elif kind == "numeric":
            checks.append(_numeric(claim))
        elif kind == "unit_check":
            # Unit analysis lives in the physics validator; record that it is
            # handled elsewhere instead of silently dropping it.
            checks.append(_skipped("unit_check", "evaluated by the physics validator"))
        else:
            checks.append(_skipped(f"verification:{kind}", "unsupported claim kind"))

    checks.extend(_answer_checks(problem_spec, answer_spec))
    if not any(str(claim.get("kind")) == "equation_substitution" for claim in claims):
        # Derive substitution checks from the problem itself only when the
        # solver did not declare them, to avoid duplicate noise.
        checks.extend(_auto_checks(problem_spec, answer_spec))
    report = _report(checks)
    report["coverage"]["claimed_checks"] = len(claims)
    return report


def _report(checks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evaluated = [check for check in checks if not check.get("skipped")]
    failures = [check for check in evaluated if not check["passed"] and check.get("severity") == "error"]
    warnings = [check for check in evaluated if not check["passed"] and check.get("severity") != "error"]
    skipped = [check for check in checks if check.get("skipped")]
    recommendations = []
    for check in failures:
        recommendations.append(f"Re-check and correct '{check['name']}': {check['details']}")
    return {
        "passed": not failures,
        "checks": [dict(check) for check in checks],
        "warnings": [f"{check['name']}: {check['details']}" for check in warnings],
        "contradictions": [f"{check['name']}: {check['details']}" for check in failures],
        "recommended_revision": recommendations,
        "coverage": {
            "claimed_checks": 0,
            "executed_checks": len(evaluated),
            "skipped_checks": len(skipped),
        },
    }
