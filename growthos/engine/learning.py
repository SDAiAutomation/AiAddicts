"""Transforme les performances publiées en mémoire éditoriale de compte."""
from collections import defaultdict
import re


def performance_score(metrics: dict) -> float:
    """Score 0–100 orienté rétention, engagement et conversion."""
    views = max(int(metrics.get("views") or 0), 0)
    watch = min(max(float(metrics.get("watch_time_pct") or 0), 0), 100)
    score = watch * 0.60
    if views:
        weighted_engagement = (
            max(int(metrics.get("likes") or 0), 0)
            + 2 * max(int(metrics.get("comments") or 0), 0)
            + 3 * max(int(metrics.get("shares") or 0), 0)
        )
        score += min(weighted_engagement / views / 0.10, 1) * 25
        score += min(max(int(metrics.get("followers_delta") or 0), 0) / views / 0.02, 1) * 10
        score += min(max(int(metrics.get("leads") or 0), 0) / views / 0.01, 1) * 5
    return round(min(max(score, 0), 100), 2)


def hook_pattern(hook: str) -> str:
    lowered = hook.lower().strip()
    if re.search(r"\d", lowered):
        return "liste chiffrée"
    if "?" in hook or lowered.startswith(("pourquoi", "comment", "est-ce")):
        return "question"
    if any(word in lowered for word in ("erreur", "jamais", "évite", "arrête", "attention")):
        return "avertissement"
    if any(word in lowered for word in ("secret", "personne", "ignore", "vérité")):
        return "curiosité"
    if any(word in lowered for word in ("un jour", "hier", "il était", "elle était")):
        return "histoire"
    return "affirmation"


def _features(row: dict) -> list[tuple[str, str]]:
    content = row.get("content_items") or {}
    script = content.get("script") or {}
    blocks = script.get("blocks") or []
    hook = next((str(b.get("text") or "").strip() for b in blocks if b.get("role") == "hook"), "")
    topic = str(content.get("title") or script.get("title") or "").strip()
    visual_style = str(script.get("visual_style") or "default").strip()
    caption_style = str(script.get("caption_style") or "bold_stroke").strip()
    content_goal = str(script.get("content_goal") or "reach").strip()
    features = []
    if hook:
        features.append(("hook", hook_pattern(hook)))
    if topic:
        features.append(("topic", topic[:180]))
    features.append(("format", f"{visual_style} · {caption_style} · {content_goal}"[:180]))
    return features


def build_insights(rows: list[dict]) -> list[dict]:
    """Agrège le snapshot le plus récent de chaque vidéo par caractéristique."""
    latest: dict[str, dict] = {}
    metric_fields = (
        "views", "watch_time_pct", "likes", "comments", "shares",
        "followers_delta", "leads",
    )
    for row in sorted(rows, key=lambda item: str(item.get("captured_at") or "")):
        item_id = str(row.get("content_item_id") or "")
        if not item_id:
            continue
        # Un relevé ultérieur peut ne contenir que les vues. On conserve alors
        # la dernière valeur connue des autres métriques au lieu de les perdre.
        merged = dict(latest.get(item_id) or {})
        merged.update({k: v for k, v in row.items() if k not in metric_fields})
        merged.update({k: row.get(k) for k in metric_fields if row.get(k) is not None})
        latest[item_id] = merged

    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    examples: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in latest.values():
        score = performance_score(row)
        for feature in _features(row):
            grouped[feature].append(score)
            if feature[0] == "hook":
                blocks = (row.get("content_items") or {}).get("script", {}).get("blocks") or []
                hook = next((str(b.get("text") or "") for b in blocks if b.get("role") == "hook"), "")
                if hook and hook not in examples[feature]:
                    examples[feature].append(hook[:180])

    return [
        {
            "kind": kind,
            "label": label,
            "performance_score": round(sum(scores) / len(scores), 2),
            "sample_size": len(scores),
            "metadata": {"examples": examples[(kind, label)][:3]} if kind == "hook" else {},
        }
        for (kind, label), scores in sorted(grouped.items())
    ]


def build_recommendation(insights: list[dict]) -> dict | None:
    """Résume les meilleurs signaux en une décision pour la prochaine vidéo."""
    if not insights:
        return None
    ranked = sorted(insights, key=lambda item: (-item["performance_score"], -item["sample_size"]))
    best_by_kind = {}
    for insight in ranked:
        best_by_kind.setdefault(insight["kind"], insight)
    parts = []
    for kind, prefix in (("hook", "Réutiliser la mécanique du hook"), ("topic", "Approfondir le sujet"), ("format", "Conserver le format")):
        if kind in best_by_kind:
            parts.append(f"{prefix} « {best_by_kind[kind]['label']} »")
    samples = max((item["sample_size"] for item in insights), default=0)
    total_items = max(sum(item["sample_size"] for item in insights if item["kind"] == "topic"), 0)
    confidence = "high" if total_items >= 15 else "medium" if total_items >= 5 else "low"
    return {
        "body": ". ".join(parts) + ".",
        "reasoning": f"Décision calculée sur {total_items} vidéo(s), meilleur signal avec {samples} observation(s).",
        "confidence": confidence,
    }
