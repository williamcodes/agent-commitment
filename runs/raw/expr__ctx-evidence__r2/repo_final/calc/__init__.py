"""calc package. See SPEC.md."""

from .expr import ExprError, evaluate, evaluate_many

__all__ = ["ExprError", "evaluate", "evaluate_many"]
