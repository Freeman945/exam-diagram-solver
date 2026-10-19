"""Simulated marking: transparent rubric plus optional model judgement."""

from .scorer import DEFAULT_MAX_SCORE, grade_answer

__all__ = ["grade_answer", "DEFAULT_MAX_SCORE"]
