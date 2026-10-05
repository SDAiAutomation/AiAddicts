"""Exact, bounded verification for one-variable linear equation scenes.

This is intentionally a small verifier, not a computer algebra system. It
accepts rational linear expressions in x and refuses unsupported maths instead
of approving a plausible-looking but unchecked derivation.
"""
from __future__ import annotations

import ast
import math
import re
from fractions import Fraction


class UnsupportedMath(ValueError):
    pass


def _linear(node: ast.AST) -> tuple[Fraction, Fraction]:
    """Return (coefficient of x, constant) for a restricted expression."""
    if isinstance(node, ast.Name) and node.id == "x":
        return Fraction(1), Fraction(0)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Fraction(0), Fraction(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        a, b = _linear(node.operand)
        sign = -1 if isinstance(node.op, ast.USub) else 1
        return sign * a, sign * b
    if isinstance(node, ast.BinOp):
        a, b = _linear(node.left)
        c, d = _linear(node.right)
        if isinstance(node.op, ast.Add):
            return a + c, b + d
        if isinstance(node.op, ast.Sub):
            return a - c, b - d
        if isinstance(node.op, ast.Mult) and not (a and c):
            return a * d + b * c, b * d
        if isinstance(node.op, ast.Div) and c == 0 and d != 0:
            return a / d, b / d
    raise UnsupportedMath("unsupported or nonlinear expression")


def solution_set(equation: str) -> tuple[str, Fraction | None]:
    """A unique root, all rationals, or no solution. Raises for other maths."""
    if not isinstance(equation, str) or len(equation) > 80 or equation.count("=") != 1:
        raise UnsupportedMath("expected one bounded equality")
    normalized = equation.replace("−", "-").replace("×", "*").replace("÷", "/").replace(" ", "")
    normalized = re.sub(r"(?<=\d)(?=x\b)", "*", normalized)
    if not re.fullmatch(r"[0-9x+*/().=\-]+", normalized):
        raise UnsupportedMath("unsupported symbol")
    try:
        left, right = normalized.split("=")
        a, b = _linear(ast.parse(left, mode="eval").body)
        c, d = _linear(ast.parse(right, mode="eval").body)
    except (SyntaxError, ZeroDivisionError, OverflowError, ValueError) as exc:
        raise UnsupportedMath("unparseable equation") from exc
    coefficient, constant = a - c, b - d
    if coefficient:
        return "root", -constant / coefficient
    return ("identity", None) if constant == 0 else ("empty", None)


def verify_steps(steps: object) -> dict:
    """Verify that every step has exactly the same solution set."""
    if not isinstance(steps, list) or not 2 <= len(steps) <= 4:
        return {"status": "unverified", "reason": "expected 2 to 4 equation steps"}
    solutions = []
    try:
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("equation"), str):
                raise UnsupportedMath("missing equation")
            solutions.append(solution_set(step["equation"]))
    except UnsupportedMath as exc:
        return {"status": "unverified", "reason": str(exc)}
    for index, result in enumerate(solutions[1:], start=2):
        if result != solutions[0]:
            return {"status": "invalid", "reason": f"step {index} changes the solution set"}
    return {"status": "verified", "solutionKind": solutions[0][0],
            "solution": str(solutions[0][1]) if solutions[0][1] is not None else None}


def verify_graph(scene: dict) -> dict:
    """Bound a linear graph and derive its highlighted point, if any."""
    try:
        if "slope" not in scene or "intercept" not in scene:
            raise ValueError("slope and intercept are required")
        values = {key: float(scene.get(key, default)) for key, default in (
            ("slope", 0), ("intercept", 0), ("xMin", -5), ("xMax", 5),
            ("yMin", -5), ("yMax", 5),
        )}
        if any(not math.isfinite(value) or abs(value) > 100 for value in values.values()):
            raise ValueError("graph values must be finite and bounded")
        if not 1 <= values["xMax"] - values["xMin"] <= 50 or not 1 <= values["yMax"] - values["yMin"] <= 50:
            raise ValueError("graph range must span 1 to 50 units")
        endpoint_ys = [values["slope"] * x + values["intercept"] for x in (values["xMin"], values["xMax"])]
        if max(endpoint_ys) < values["yMin"] or min(endpoint_ys) > values["yMax"]:
            raise ValueError("line is outside the graph")
        if "highlightX" in scene:
            x = float(scene["highlightX"])
            y = values["slope"] * x + values["intercept"]
            if not math.isfinite(x) or not values["xMin"] <= x <= values["xMax"] or not values["yMin"] <= y <= values["yMax"]:
                raise ValueError("highlighted point is outside the graph")
            return {"status": "verified", "highlightY": y}
    except (TypeError, ValueError, OverflowError) as exc:
        return {"status": "unverified", "reason": str(exc)}
    return {"status": "verified", "highlightY": None}
