from dataclasses import dataclass, field

from src.validation.rules import VALIDATION_RULES, TOTAL_WEIGHT, ValidationRule


@dataclass
class RuleResult:
    rule_id: str
    rule_name: str
    passed: bool
    score: float
    max_score: float
    matched_keywords: list[str]
    description: str
    required: bool


@dataclass
class ConformityReport:
    source: str
    total_score: float          # 0-100
    status: str                 # Conforme / Partiellement conforme / Non conforme
    rule_results: list[RuleResult]
    recommendations: list[str]

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "total_score": round(self.total_score, 1),
            "status": self.status,
            "rule_results": [
                {
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "passed": r.passed,
                    "score": round(r.score, 1),
                    "max_score": r.max_score,
                    "matched_keywords": r.matched_keywords,
                    "required": r.required,
                }
                for r in self.rule_results
            ],
            "recommendations": self.recommendations,
        }


def _check_rule(text_lower: str, rule: ValidationRule) -> RuleResult:
    matched = [kw for kw in rule.keywords if kw.lower() in text_lower]
    passed = bool(matched)
    return RuleResult(
        rule_id=rule.id,
        rule_name=rule.name,
        passed=passed,
        score=rule.weight if passed else 0.0,
        max_score=rule.weight,
        matched_keywords=matched,
        description=rule.description,
        required=rule.required,
    )


def _build_recommendations(results: list[RuleResult]) -> list[str]:
    recs = []
    for r in results:
        if r.passed:
            continue
        if r.rule_id.startswith("SECU"):
            recs.append(f"⚠️  [CRITIQUE] {r.description}")
        elif r.rule_id.startswith("META"):
            recs.append(f"📋 [Métadonnée] {r.description}")
        elif r.rule_id.startswith("PROC"):
            recs.append(f"🔧 [Procédure] {r.description}")
        elif r.rule_id.startswith("QC"):
            recs.append(f"✅ [Qualité] {r.description}")
        else:
            recs.append(f"📌 {r.description}")
    return recs


def check_conformity(text: str, source: str = "Document") -> ConformityReport:
    text_lower = text.lower()
    results = [_check_rule(text_lower, rule) for rule in VALIDATION_RULES]

    raw_score = sum(r.score for r in results)
    normalized = (raw_score / TOTAL_WEIGHT * 100) if TOTAL_WEIGHT else 0.0

    if normalized >= 80:
        status = "Conforme"
    elif normalized >= 60:
        status = "Partiellement conforme"
    else:
        status = "Non conforme"

    return ConformityReport(
        source=source,
        total_score=normalized,
        status=status,
        rule_results=results,
        recommendations=_build_recommendations(results),
    )
