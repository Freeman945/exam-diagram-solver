"""Deterministic part of the Examiner: a transparent scoring rubric.

The LLM examiner adds qualitative judgement, but these rules are what make the
score reproducible. They check what a marker mechanically checks: the final
answer, units, required diagram, key steps and unsupported shortcuts.

Every number produced here is an *internal estimate* used to drive revision.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

__all__ = ["grade_answer", "DEFAULT_MAX_SCORE"]

DEFAULT_MAX_SCORE = {
    "multiple_choice": 3.0,
    "fill_blank": 4.0,
    "written_solution": 12.0,
    "proof": 12.0,
    "unknown": 10.0,
}

SHORTCUT_PATTERNS = [
    r"显然",
    r"易得",
    r"易知",
    r"很明显",
    r"obviously",
    r"\bclearly\b",
    r"trivially",
]

LOGIC_CONNECTORS = ["因为", "所以", "因此", "由", "可得", "从而", "∵", "∴", "⇒", "→", "hence", "therefore", "since"]


def _loss(reason: str, points: float, fix: str) -> dict[str, Any]:
    return {"reason": reason, "estimated_loss": round(points, 2), "fix": fix}


def grade_answer(
    problem_spec: Mapping[str, Any],
    answer_spec: Mapping[str, Any],
    validation_report: Mapping[str, Any] | None = None,
    *,
    max_score: float | None = None,
    diagram: Mapping[str, Any] | None = None,
    answer_mode: str = "exam",
) -> dict[str, Any]:
    """Score an AnswerSpec with the mechanical rubric.

    ``diagram`` describes a rendered/planned diagram: ``{"rendered": bool,
    "role": "auxiliary"|"final_answer"|"both"|"none"}``.
    """

    question_format = str(problem_spec.get("question_format") or "unknown")
    total = float(max_score or DEFAULT_MAX_SCORE.get(question_format, 10.0))
    losses: list[dict[str, Any]] = []
    strengths: list[str] = []
    instructions: list[str] = []
    notes: list[str] = []

    final = str(answer_spec.get("final_answer") or "").strip()
    steps = list(answer_spec.get("steps") or [])
    validation = validation_report or {}
    contradictions = list(validation.get("contradictions") or [])
    failures = [
        check
        for check in validation.get("checks") or []
        if not check.get("passed") and check.get("severity") == "error"
    ]

    # ---- correctness (heaviest weight)
    if failures:
        penalty = min(total * 0.45, 2.0 + 1.5 * len(failures))
        losses.append(
            _loss(
                f"程序验证未通过（{len(failures)} 项）：{failures[0].get('name')}",
                penalty,
                "按验证报告修正错误结论后重新求解。",
            )
        )
        instructions.append("修正验证失败的结论：" + "；".join(str(item.get("name")) for item in failures[:3]))
    elif validation.get("passed"):
        strengths.append("程序验证通过，结论与题目条件一致。")

    # ---- final answer
    if not final:
        losses.append(_loss("没有给出明确的最终答案", total * 0.5, "在结尾用一句话写出最终答案。"))
        instructions.append("补写明确的最终答案。")
    elif final.rstrip().endswith(("？", "?")) or len(final.strip()) < 3:
        losses.append(_loss("最终答案不是一个明确的结论", 0.5, "用“故……”“答：……”收束答案。"))
        instructions.append("用规范的结论句收束最终答案。")
    elif re.search(r"(答|故|所以|因此|综上|结论|即|final|answer|therefore|hence)", final):
        strengths.append("最终答案以结论句呈现，指向明确。")

    # ---- units (physics)
    if str(problem_spec.get("subject")) == "physics" and re.search(r"\d", final):
        if not re.search(r"\d\s*(m/s(?:\^?2|²)?|N|J|W|V|A|Ω|C|T|Hz|kg|Pa|mol|K|%|m|s)\b", final):
            losses.append(_loss("最终答案缺少单位", 1.0, "在数值后写出国际单位。"))
            instructions.append("为最终答案补充单位。")

    # ---- diagram
    role = str((diagram or {}).get("role") or problem_spec.get("diagram_role") or "none")
    rendered = bool((diagram or {}).get("rendered"))
    needs_diagram = role in {"final_answer", "both"}
    if needs_diagram and not rendered:
        losses.append(_loss("题目要求作图，但答案中没有图", min(total * 0.2, 2.0), "补画题目要求的图并标注关键点。"))
        instructions.append("补画正式作答图。")
    elif needs_diagram and rendered:
        strengths.append("已给出题目要求的作答图。")
    if answer_spec.get("diagram_refs"):
        strengths.append("答案引用了图。" )

    # ---- steps / expression
    if question_format in {"written_solution", "proof"}:
        if len(steps) < 3:
            losses.append(_loss("关键步骤过少，过程不完整", 1.5, "补出建立方程/受力分析等关键步骤。"))
            instructions.append("补全关键推导步骤。")
        key_steps = [step for step in steps if str(step.get("score_relevance")) == "key"]
        if not key_steps:
            losses.append(_loss("未标记得分关键步骤", 0.5, "确保关键公式或定理单独成步。"))
        if len(steps) >= 4:
            strengths.append("步骤分层清晰，具备过程分。")

    if question_format == "proof":
        body = " ".join(str(step.get("content") or "") + " " + str(step.get("reason") or "") for step in steps)
        if not any(connector in body for connector in LOGIC_CONNECTORS):
            losses.append(_loss("证明缺少逻辑连接词，推理链不明显", 1.0, "用“因为……所以……”“由……可得”显式连接推导。"))
            instructions.append("补齐证明的逻辑连接。")

    shortcut_hits = []
    for step in steps:
        content = str(step.get("content") or "")
        for pattern in SHORTCUT_PATTERNS:
            if re.search(pattern, content):
                shortcut_hits.append(pattern)
                break
    if shortcut_hits:
        penalty = min(1.5, 0.5 * len(shortcut_hits))
        losses.append(_loss("出现“显然/易得”等跳步表述", penalty, "把跳过的推导写出来，或说明依据。"))
        instructions.append("消除跳步表述。")

    # ---- consistency with stated uncertainties
    uncertainties = problem_spec.get("uncertainties") or []
    if uncertainties:
        try:
            confidence = float(answer_spec.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        if confidence >= 0.9:
            notes.append("题目存在识别不确定项，但答案置信度偏高；最终呈现时应保留不确定说明。")

    lost = sum(item["estimated_loss"] for item in losses)
    estimated = max(0.0, min(total, total - lost))
    ratio = estimated / total if total else 0.0
    revision_required = bool(
        any(item["estimated_loss"] >= 1.0 for item in losses) or ratio < 0.85
    )

    if answer_mode == "concise":
        # Short answers are not expected to show full derivation.
        revision_required = revision_required and bool(failures)

    return {
        "estimated_score": round(estimated, 2),
        "max_score": round(total, 2),
        "score_ratio": round(ratio, 4),
        "lost_points": losses,
        "strengths": strengths,
        "revision_required": revision_required,
        "revision_instructions": _unique(instructions),
        "source": "internal_estimate",
        "notes": notes,
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
