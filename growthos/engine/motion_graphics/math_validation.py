"""Exact, bounded verification for selected one-variable equation scenes.

This is intentionally a small verifier, not a computer algebra system. It
accepts rational linear expressions and factorable quadratics in x; it refuses unsupported maths instead
of approving a plausible-looking but unchecked derivation.
"""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from fractions import Fraction


class UnsupportedMath(ValueError):
    pass


_VULGAR_FRACTIONS = {
    "½": "(1/2)", "⅓": "(1/3)", "⅔": "(2/3)", "¼": "(1/4)",
    "¾": "(3/4)", "⅛": "(1/8)", "⅜": "(3/8)", "⅝": "(5/8)", "⅞": "(7/8)",
}


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
        if isinstance(node.op, ast.Div) and c == 0:
            if d == 0:
                raise UnsupportedMath("division par zéro")
            return a / d, b / d
    raise UnsupportedMath("expression non linéaire ou non prise en charge")


def _parse_nodes(equation: str) -> tuple[ast.AST, ast.AST]:
    """Normalize bounded school notation and return restricted AST nodes."""
    if not isinstance(equation, str) or len(equation) > 80 or equation.count("=") != 1:
        raise UnsupportedMath("une seule égalité de 80 caractères maximum est attendue")
    normalized = (equation.replace("−", "-").replace("×", "*").replace("²", "**2").replace("^", "**")
                  .replace("·", "*").replace("÷", "/").replace("⁄", "/")
                  .replace(":", "/").replace("[", "(").replace("]", ")"))
    for glyph, fraction in _VULGAR_FRACTIONS.items():
        normalized = re.sub(
            rf"(?<![0-9.])(\d+)\s*{re.escape(glyph)}",
            lambda match: f"({match[1]}+{fraction})",
            normalized,
        )
        normalized = normalized.replace(glyph, fraction)
    # A space between a whole number and a proper fraction denotes a mixed
    # number; preserve it before removing ordinary whitespace.
    normalized = re.sub(
        r"(?<![0-9x.])(\d+)\s+(\d+)\s*/\s*(\d+)(?![0-9.])",
        lambda match: f"({match[1]}+{match[2]}/{match[3]})",
        normalized,
    )
    normalized = re.sub(r"(?<=\d),(?=\d)", ".", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    # 1/2x could mean (1/2)x or 1/(2x); require grouping rather than
    # silently certifying one interpretation. Chained divisions need grouping.
    if re.search(r"\d+(?:\.\d+)?/\d+(?:\.\d+)?(?=x|\()", normalized) or re.search(
        r"(?:\d+|x)/\d+/\d+", normalized
    ):
        raise UnsupportedMath("fraction ambiguë : entourer le coefficient ou le dénominateur de parenthèses")
    # Only these adjacent forms denote implicit multiplication in this domain.
    normalized = re.sub(r"(?<=\d)(?=x|\()|(?<=x)(?=\()|(?<=\))(?=x|\d|\()", "*", normalized)
    if not re.fullmatch(r"[0-9x+*/().=\-]+", normalized):
        raise UnsupportedMath("symbole non pris en charge dans une équation du premier degré")
    try:
        left, right = normalized.split("=")
        parsed = (ast.parse(left, mode="eval").body, ast.parse(right, mode="eval").body)
        if sum(1 for node in parsed for _ in ast.walk(node)) > 64:
            raise UnsupportedMath("équation trop complexe pour le vérificateur")
        return parsed
    except UnsupportedMath:
        raise
    except ZeroDivisionError as exc:
        raise UnsupportedMath("division par zéro") from exc
    except (SyntaxError, OverflowError, RecursionError, ValueError) as exc:
        raise UnsupportedMath("écriture non reconnue : vérifier parenthèses et opérateurs") from exc


def _parse_equation(equation: str) -> tuple[tuple[Fraction, Fraction], tuple[Fraction, Fraction]]:
    """Parse a linear equality into exact coefficients."""
    left, right = _parse_nodes(equation)
    return _linear(left), _linear(right)


@dataclass(frozen=True)
class _Rational:
    numerator: tuple[Fraction, Fraction]  # ax + b
    denominator: tuple[Fraction, Fraction]  # cx + d
    forbidden: frozenset[Fraction] = frozenset()


_ONE = (Fraction(0), Fraction(1))


def _poly(pair: tuple[Fraction, Fraction]) -> tuple[Fraction, Fraction]:
    return pair[1], pair[0]  # low degree first


def _multiply(first: tuple[Fraction, ...], second: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    values = [Fraction(0)] * (len(first) + len(second) - 1)
    for i, a in enumerate(first):
        for j, b in enumerate(second):
            values[i + j] += a * b
    return tuple(values)


def _subtract(first: tuple[Fraction, ...], second: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    return tuple((first[i] if i < len(first) else 0) - (second[i] if i < len(second) else 0)
                 for i in range(max(len(first), len(second))))


def _is_zero(poly: tuple[Fraction, ...]) -> bool:
    return not any(poly)


def _quadratic_expr(node: ast.AST) -> tuple[Fraction, Fraction, Fraction]:
    """Exact polynomial coefficients, low degree first, capped at degree two."""
    if isinstance(node, ast.Name) and node.id == "x":
        return Fraction(0), Fraction(1), Fraction(0)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Fraction(str(node.value)), Fraction(0), Fraction(0)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        values = _quadratic_expr(node.operand)
        return tuple(-v for v in values) if isinstance(node.op, ast.USub) else values
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            if not isinstance(node.right, ast.Constant) or node.right.value != 2:
                raise UnsupportedMath("seul le carré est pris en charge")
            values = _quadratic_expr(node.left)
            product = _multiply(values, values)
        else:
            left, right = _quadratic_expr(node.left), _quadratic_expr(node.right)
            if isinstance(node.op, ast.Add):
                return tuple(a + b for a, b in zip(left, right))
            if isinstance(node.op, ast.Sub):
                return tuple(a - b for a, b in zip(left, right))
            if isinstance(node.op, ast.Mult):
                product = _multiply(left, right)
            elif isinstance(node.op, ast.Div) and right[1:] == (0, 0) and right[0]:
                return tuple(v / right[0] for v in left)
            else:
                raise UnsupportedMath("expression du second degré non prise en charge")
        if any(product[3:]):
            raise UnsupportedMath("degré supérieur à deux")
        return tuple(product[:3])
    raise UnsupportedMath("expression du second degré non prise en charge")


def _quadratic_equation(equation: str) -> tuple[tuple[Fraction, Fraction, Fraction], tuple[Fraction, Fraction, Fraction]]:
    left, right = _parse_nodes(equation)
    return _quadratic_expr(left), _quadratic_expr(right)


def _quadratic_roots(parsed: tuple) -> tuple[Fraction, ...]:
    left, right = parsed
    c, b, a = (x - y for x, y in zip(left, right))
    if not a:
        raise UnsupportedMath("équation non quadratique")
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return ()
    numerator_root = math.isqrt(discriminant.numerator)
    denominator_root = math.isqrt(discriminant.denominator)
    if numerator_root ** 2 != discriminant.numerator or denominator_root ** 2 != discriminant.denominator:
        raise UnsupportedMath("racines irrationnelles : revue nécessaire")
    root = Fraction(numerator_root, denominator_root)
    return tuple(sorted({(-b - root) / (2 * a), (-b + root) / (2 * a)}))


def _rat_equal(first: _Rational, second: _Rational) -> bool:
    return _is_zero(_subtract(
        _multiply(_poly(first.numerator), _poly(second.denominator)),
        _multiply(_poly(second.numerator), _poly(first.denominator)),
    ))


def _rational(node: ast.AST) -> _Rational:
    """One linear numerator over one linear denominator; no general CAS."""
    try:
        return _Rational(_linear(node), _ONE)
    except UnsupportedMath:
        pass
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _rational(node.operand)
        sign = -1 if isinstance(node.op, ast.USub) else 1
        return _Rational(tuple(sign * v for v in value.numerator), value.denominator, value.forbidden)
    if isinstance(node, ast.BinOp):
        left, right = _rational(node.left), _rational(node.right)
        if isinstance(node.op, ast.Div):
            if right.denominator != _ONE or right.forbidden or left.denominator != _ONE:
                raise UnsupportedMath("fractions imbriquées avec x au dénominateur non prises en charge")
            a, b = right.numerator
            if a == 0:
                if b == 0:
                    raise UnsupportedMath("division par zéro")
                return _Rational(tuple(v / b for v in left.numerator), _ONE)
            return _Rational(left.numerator, right.numerator, frozenset({-b / a}))
        left_has_den = left.denominator[0] != 0
        right_has_den = right.denominator[0] != 0
        if isinstance(node.op, (ast.Add, ast.Sub)):
            sign = -1 if isinstance(node.op, ast.Sub) else 1
            if left_has_den and not right_has_den and right.numerator[0] == 0:
                amount = right.numerator[1] / right.denominator[1] * sign
                return _Rational(tuple(left.numerator[i] + amount * left.denominator[i] for i in (0, 1)),
                                 left.denominator, left.forbidden | right.forbidden)
            if right_has_den and not left_has_den and left.numerator[0] == 0:
                amount = left.numerator[1] / left.denominator[1]
                return _Rational(tuple(amount * right.denominator[i] + sign * right.numerator[i] for i in (0, 1)),
                                 right.denominator, left.forbidden | right.forbidden)
        if isinstance(node.op, ast.Mult):
            if left_has_den and not right_has_den and right.numerator[0] == 0:
                amount = right.numerator[1] / right.denominator[1]
                return _Rational(tuple(amount * v for v in left.numerator), left.denominator, left.forbidden)
            if right_has_den and not left_has_den and left.numerator[0] == 0:
                amount = left.numerator[1] / left.denominator[1]
                return _Rational(tuple(amount * v for v in right.numerator), right.denominator, right.forbidden)
    raise UnsupportedMath("fraction rationnelle hors du domaine linéaire vérifiable")


def _parse_rational_equation(equation: str) -> tuple[_Rational, _Rational]:
    left, right = _parse_nodes(equation)
    return _rational(left), _rational(right)


def _rational_solution(parsed: tuple[_Rational, _Rational]) -> tuple[tuple[str, Fraction | None], frozenset[Fraction]]:
    left, right = parsed
    forbidden = left.forbidden | right.forbidden
    difference = _subtract(
        _multiply(_poly(left.numerator), _poly(right.denominator)),
        _multiply(_poly(right.numerator), _poly(left.denominator)),
    )
    constant, coefficient = difference[:2]
    if any(difference[2:]):
        raise UnsupportedMath("la réduction donne une équation quadratique, non vérifiée ici")
    if coefficient:
        root = -constant / coefficient
        return (("empty", None) if root in forbidden else ("root", root)), forbidden
    if constant:
        return ("empty", None), forbidden
    if forbidden:
        raise UnsupportedMath("infinité de solutions avec valeurs interdites : revue nécessaire")
    return ("identity", None), forbidden


def _rational_operation(before: tuple[_Rational, _Rational], after: tuple[_Rational, _Rational]) -> str | None:
    """A rewrite, equal shift, or common nonzero scaling as rational functions."""
    if (_rat_equal(before[0], after[0]) and _rat_equal(before[1], after[1])) or (
        _rat_equal(before[0], after[1]) and _rat_equal(before[1], after[0])
    ):
        return "rewrite"
    def difference(value: _Rational, previous: _Rational) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
        return (_subtract(_multiply(_poly(value.numerator), _poly(previous.denominator)),
                          _multiply(_poly(previous.numerator), _poly(value.denominator))),
                _multiply(_poly(value.denominator), _poly(previous.denominator)))
    ld, rd = difference(after[0], before[0]), difference(after[1], before[1])
    if _is_zero(_subtract(_multiply(ld[0], rd[1]), _multiply(rd[0], ld[1]))):
        return "add_to_both_sides"
    # Compare after_left/before_left with after_right/before_right.
    lhs = _multiply(_multiply(_poly(after[0].numerator), _poly(before[0].denominator)),
                    _multiply(_poly(after[1].denominator), _poly(before[1].numerator)))
    rhs = _multiply(_multiply(_poly(after[1].numerator), _poly(before[1].denominator)),
                    _multiply(_poly(after[0].denominator), _poly(before[0].numerator)))
    if not _is_zero(_poly(before[0].numerator)) and not _is_zero(_poly(before[1].numerator)):
        if _is_zero(_subtract(lhs, rhs)):
            return "scale_both_sides"
    return None


def _solution(parsed: tuple[tuple[Fraction, Fraction], tuple[Fraction, Fraction]]) -> tuple[str, Fraction | None]:
    (a, b), (c, d) = parsed
    coefficient, constant = a - c, b - d
    if coefficient:
        return "root", -constant / coefficient
    return ("identity", None) if constant == 0 else ("empty", None)


def solution_set(equation: str) -> tuple[str, Fraction | tuple[Fraction, ...] | None]:
    """Exact real solution set for the supported domain; raise otherwise."""
    try:
        return _solution(_parse_equation(equation))
    except UnsupportedMath:
        try:
            return _rational_solution(_parse_rational_equation(equation))[0]
        except UnsupportedMath:
            if not ("^" in equation or "²" in equation or "**" in equation or re.search(r"x\s*\*\s*x|x\s*\(|\)\s*\(", equation)):
                raise
            roots = _quadratic_roots(_quadratic_equation(equation))
            return ("empty", None) if not roots else ("root", roots[0]) if len(roots) == 1 else ("roots", roots)


def same_equation(first: str, second: str) -> bool:
    """Whether two displayed equalities have the same expressions on each side."""
    try:
        return _parse_equation(first) == _parse_equation(second)
    except UnsupportedMath:
        try:
            left = _parse_rational_equation(first)
            right = _parse_rational_equation(second)
            return all(_rat_equal(a, b) and a.forbidden == b.forbidden for a, b in zip(left, right))
        except UnsupportedMath:
            return _quadratic_equation(first) == _quadratic_equation(second)


def _single_operation(before: tuple, after: tuple) -> tuple[str, object] | None:
    """Recognize one reversible operation applied to both sides, or a rewrite."""
    if before == after or before == (after[1], after[0]):
        return "rewrite", None
    left_delta = tuple(new - old for old, new in zip(before[0], after[0]))
    right_delta = tuple(new - old for old, new in zip(before[1], after[1]))
    if left_delta == right_delta:
        return "add_to_both_sides", left_delta
    old_values = (*before[0], *before[1])
    new_values = (*after[0], *after[1])
    factor = next((new / old for old, new in zip(old_values, new_values) if old), None)
    if factor is not None and factor != 0 and all(new == old * factor for old, new in zip(old_values, new_values)):
        return "scale_both_sides", factor
    return None


def _symbolic_explanation_matches(explanation: object, operation: tuple[str, object]) -> bool:
    """Check an explicit numeric operation label; free-form prose needs review."""
    if not isinstance(explanation, str):
        return True
    claim = re.match(r"^\s*([+−\-×*÷/])\s*(\d+(?:[.,]\d+)?(?:/\d+)?)", explanation)
    if claim is None:
        return True
    symbol, raw_amount = claim.groups()
    try:
        amount = Fraction(raw_amount.replace(",", "."))
    except (ValueError, ZeroDivisionError):
        return False
    kind, value = operation
    if symbol in ("+", "-", "−"):
        signed = -amount if symbol in ("-", "−") else amount
        return kind == "add_to_both_sides" and value == (Fraction(0), signed)
    if amount == 0:
        return False
    factor = 1 / amount if symbol in ("÷", "/") else amount
    return kind == "scale_both_sides" and value == factor


def _factored_zero(equation: str) -> bool:
    left, right = _parse_nodes(equation)
    def factored(node: ast.AST) -> bool:
        if not isinstance(node, ast.BinOp):
            return False
        if isinstance(node.op, ast.Mult):
            factors = (node.left, node.right)
        elif isinstance(node.op, ast.Pow) and isinstance(node.right, ast.Constant) and node.right.value == 2:
            factors = (node.left, node.left)
        else:
            return False
        try:
            return all(_linear(factor)[0] != 0 for factor in factors)
        except UnsupportedMath:
            return False
    return (factored(left) and _quadratic_expr(right) == (0, 0, 0)) or (
        factored(right) and _quadratic_expr(left) == (0, 0, 0))


def _verify_quadratic_steps(steps: list[dict]) -> dict:
    parsed = []
    branch_roots = None
    try:
        for index, step in enumerate(steps):
            equation = step["equation"]
            if " ou " in equation.lower():
                if index != len(steps) - 1 or branch_roots is not None:
                    raise UnsupportedMath("les deux racines doivent terminer la démonstration")
                branch_roots = tuple(sorted({solution_set(part.strip())[1] for part in re.split(r"\s+ou\s+", equation, flags=re.I)}))
                if any(not isinstance(root, Fraction) for root in branch_roots):
                    raise UnsupportedMath("branches finales invalides")
            else:
                try:
                    parsed.append(_quadratic_equation(equation))
                except UnsupportedMath:
                    if index != len(steps) - 1:
                        raise
                    root = solution_set(equation)
                    if root[0] != "root" or not isinstance(root[1], Fraction):
                        raise UnsupportedMath("conclusion finale non vérifiable")
                    branch_roots = (root[1],)
        if not parsed or parsed[0][0][2] == parsed[0][1][2]:
            raise UnsupportedMath("la première équation doit être du second degré")
        expected = _quadratic_roots(parsed[0])
        operations = []
        for index, current in enumerate(parsed[1:], start=1):
            try:
                current_roots = _quadratic_roots(current)
            except UnsupportedMath as exc:
                if "non quadratique" not in str(exc):
                    raise
                # Étape du premier degré après un second degré : on compare les solutions au lieu de
                # refuser sans explication. Diviser x(x − 2) = 0 par x fait disparaître x = 0.
                c0, b0, a0 = (u - w for u, w in zip(current[0], current[1]))
                if a0 == 0 and b0 != 0:
                    kept = (-c0 / b0,)
                    lost = [value for value in expected if value not in kept]
                    if lost:
                        shown = ", ".join(f"x = {value}" for value in lost)
                        return {"status": "invalid",
                                "reason": f"étape {index + 1} : l'ensemble des solutions change (solution perdue : {shown})"}
                raise
            if current_roots != expected:
                return {"status": "invalid", "reason": f"étape {index + 1} : l'ensemble des solutions change"}
            previous = parsed[index - 1]
            if current == previous or current == previous[::-1]:
                operation = ("rewrite", None)
            else:
                deltas = [tuple(b - a for a, b in zip(old, new)) for old, new in zip(previous, current)]
                if deltas[0] == deltas[1]:
                    operation = ("add_to_both_sides", deltas[0])
                else:
                    old_values = previous[0] + previous[1]
                    new_values = current[0] + current[1]
                    factor = next((new / old for old, new in zip(old_values, new_values) if old), None)
                    operation = ("scale_both_sides", factor) if factor and all(
                        new == old * factor for old, new in zip(old_values, new_values)) else None
            if operation is None:
                return {"status": "unverified", "reason": f"étape {index + 1} : opération non reconnue"}
            operations.append(operation[0])
        if branch_roots is not None:
            if not _factored_zero(steps[len(parsed) - 1]["equation"]):
                raise UnsupportedMath("la propriété du produit nul exige une forme factorisée égale à zéro")
            if branch_roots != expected:
                return {"status": "invalid", "reason": "les racines finales ne correspondent pas aux facteurs"}
            operations.append("zero_product")
        return {"status": "verified", "solutionKind": "roots" if len(expected) > 1 else "root" if expected else "empty",
                "solution": [str(value) for value in expected] if len(expected) > 1 else str(expected[0]) if expected else None,
                "operations": operations, "excludedValues": []}
    except (UnsupportedMath, TypeError, ValueError) as exc:
        return {"status": "unverified", "reason": str(exc)}


def verify_steps(steps: object) -> dict:
    """Verify that every step has exactly the same solution set."""
    if not isinstance(steps, list) or not 2 <= len(steps) <= 4:
        return {"status": "unverified", "reason": "2 à 4 étapes sont attendues"}
    if any(isinstance(step, dict) and isinstance(step.get("equation"), str) and (
        "^" in step["equation"] or "²" in step["equation"] or "**" in step["equation"] or " ou " in step["equation"].lower()
        or re.search(r"\)\s*\(|x\s*\(|x\s*\*\s*x", step["equation"])
    ) for step in steps):
        return _verify_quadratic_steps(steps)
    parsed_steps = []
    rational_steps = []
    try:
        for index, step in enumerate(steps, start=1):
            try:
                if not isinstance(step, dict) or not isinstance(step.get("equation"), str):
                    raise UnsupportedMath("équation manquante")
                try:
                    parsed_steps.append(_parse_equation(step["equation"]))
                except UnsupportedMath:
                    parsed_steps.append(None)
                rational_steps.append(_parse_rational_equation(step["equation"]))
            except UnsupportedMath as exc:
                raise UnsupportedMath(f"étape {index} : {exc}") from exc
    except UnsupportedMath as exc:
        return {"status": "unverified", "reason": str(exc)}
    use_rational = any(parsed is None for parsed in parsed_steps)
    try:
        if use_rational:
            if parsed_steps[0] is not None:
                raise UnsupportedMath("une valeur interdite ne doit pas apparaître après la première étape")
            results = [_rational_solution(parsed) for parsed in rational_steps]
            solutions = [result[0] for result in results]
        else:
            solutions = [_solution(parsed) for parsed in parsed_steps]
            results = []
    except UnsupportedMath as exc:
        return {"status": "unverified", "reason": str(exc)}
    operations = []
    for index, result in enumerate(solutions[1:], start=2):
        if result != solutions[0]:
            return {"status": "invalid", "reason": f"étape {index} : l'ensemble des solutions change"}
        operation = (_rational_operation(rational_steps[index - 2], rational_steps[index - 1]), None) if use_rational else _single_operation(parsed_steps[index - 2], parsed_steps[index - 1])
        if operation is None or operation[0] is None:
            return {"status": "unverified", "reason": f"étape {index} : plusieurs opérations algébriques sont sautées"}
        if not use_rational and not _symbolic_explanation_matches(steps[index - 1].get("explanation"), operation):
            return {"status": "invalid", "reason": f"étape {index} : le libellé de l'opération contredit l'équation"}
        operations.append(operation[0])
    return {"status": "verified", "solutionKind": solutions[0][0],
            "solution": str(solutions[0][1]) if solutions[0][1] is not None else None,
            "operations": operations,
            "excludedValues": sorted((str(value) for value in results[0][1]), key=lambda value: Fraction(value)) if use_rational else []}


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


# ---------------------------------------------------------------------------
# Description structurée d'une étape (consommée par math_steps / l'animation)
# ---------------------------------------------------------------------------

def _fraction_tex(value: Fraction) -> str:
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    return rf"\frac{{{value.numerator}}}{{{value.denominator}}}"


def _fraction_text(value: Fraction) -> str:
    value = Fraction(value)
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def describe_operation(before: str, after: str) -> dict:
    """Opération appliquée aux DEUX membres entre deux égalités du premier degré.

    Renvoie `{"kind": "add"|"mul"|"div"|"rewrite"|"unknown", ...}`. Seule la forme « une même
    opération sur les deux membres » est décrite ; `rewrite` (simple réécriture) et `unknown`
    (non décrit : rationnelles, quadratiques, plusieurs opérations) n'ont pas d'étape intermédiaire
    animée. Le calcul s'appuie sur les mêmes coefficients exacts que `verify_steps`."""
    try:
        parsed_before, parsed_after = _parse_equation(before), _parse_equation(after)
    except UnsupportedMath:
        return {"kind": "unknown"}
    operation = _single_operation(parsed_before, parsed_after)
    if operation is None:
        return {"kind": "unknown"}
    kind, value = operation
    if kind == "rewrite":
        return {"kind": "rewrite"}
    if kind == "add_to_both_sides":
        delta_x, delta_c = value
        if bool(delta_x) == bool(delta_c):  # les deux non nuls : plusieurs termes, non décrit
            return {"kind": "unknown"}
        amount = delta_x or delta_c
        sign = "+" if amount > 0 else "-"
        magnitude = abs(Fraction(amount))
        suffix_tex, suffix_text = ("x", "x") if delta_x else ("", "")
        shown = "" if (delta_x and magnitude == 1) else None
        return {
            "kind": "add", "sign": sign, "amount": str(magnitude), "withX": bool(delta_x),
            "tex": f"{sign} {'' if shown == '' else _fraction_tex(magnitude)}{suffix_tex}".replace("+ ", "+").replace("- ", "-"),
            "display": f"{'+' if sign == '+' else '−'}{'' if shown == '' else _fraction_text(magnitude)}{suffix_text}",
        }
    factor = Fraction(value)
    if factor.numerator in (1, -1) and factor.denominator != 1:
        divisor = factor.denominator * factor.numerator
        return {"kind": "div", "amount": str(divisor), "tex": rf"\div {divisor}" if divisor > 0 else rf"\div ({divisor})",
                "display": f"÷{divisor}" if divisor > 0 else f"÷({divisor})".replace("-", "−")}
    return {"kind": "mul", "amount": str(factor), "tex": rf"\times {_fraction_tex(factor)}" if factor > 0
            else rf"\times ({_fraction_tex(factor)})",
            "display": f"×{_fraction_text(factor)}" if factor > 0 else f"×({_fraction_text(factor)})".replace("-", "−")}


def substitution_check(equation: str, value: Fraction) -> dict | None:
    """Substitue `value` à x dans l'équation d'origine : textes d'affichage + égalité exacte.

    Renvoie None hors du premier degré (non vérifié ici, jamais inventé)."""
    try:
        (a, b), (c, d) = _parse_equation(equation)
    except UnsupportedMath:
        return None
    value = Fraction(value)
    left_value, right_value = a * value + b, c * value + d

    def substitute(side: str) -> str:
        shown = _fraction_tex(value) if value >= 0 else rf"({_fraction_tex(value)})"
        side = side.replace("−", "-").replace("×", r"\times")
        side = re.sub(r"(?<=[0-9)])\s*x", lambda _m: r" \times " + shown, side)
        side = re.sub(r"x", lambda _m: shown, side)
        return side.strip()

    left, right = (part.strip() for part in equation.split("="))
    return {
        "left": substitute(left), "right": substitute(right),
        "leftValue": _fraction_tex(left_value), "rightValue": _fraction_tex(right_value),
        "ok": left_value == right_value,
    }
