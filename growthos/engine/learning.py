"""Transforme les performances publiées en mémoire éditoriale de compte.

v2 (2026-09-25) :
- regroupement par archétype narratif et type d'accroche (classés une fois
  par `engine/story_features.py`, cache `content_items.story_features`) au
  lieu du titre exact, qui faisait un groupe par vidéo et recommandait de
  refaire la même histoire ;
- chaque groupe est jugé par son écart à la MÉDIANE du compte, pas en
  absolu : une chaîne à 30 % de rétention n'apprend rien d'un seuil fixe ;
- seules les vidéos avec rétention connue et assez de vues comptent, et une
  recommandation exige au moins `MIN_GROUP_SIZE` vidéos dans le groupe.
"""
from collections import defaultdict
from statistics import mean, median
import re

MIN_VIEWS = 50
MIN_GROUP_SIZE = 3
MIN_LIFT = 5.0  # points de score au-dessus/au-dessous de la médiane du compte

_KIND_ORDER = ("archetype", "hook", "format")


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
    """Repli déterministe (fr + en) quand la vidéo n'est pas encore classée
    par le modèle. Mêmes libellés que `story_features.HOOK_TYPES`."""
    lowered = hook.lower().strip()
    if re.search(r"\d", lowered):
        return "liste chiffrée"
    if "?" in hook or lowered.startswith((
        "pourquoi", "comment", "est-ce", "why", "how", "what", "who", "which", "did you", "have you",
    )):
        return "question"
    if any(word in lowered for word in (
        "erreur", "jamais", "évite", "arrête", "attention", "never", "stop", "mistake", "warning", "don't",
    )):
        return "avertissement"
    if any(word in lowered for word in (
        "secret", "personne", "ignore", "vérité", "nobody", "no one", "truth", "mystery", "strange",
    )):
        return "énigme"
    if any(word in lowered for word in (
        "un jour", "hier", "il était", "elle était", "every night", "every day", "every morning",
        "one day", "last night",
    )):
        return "mise en situation"
    return "affirmation choc"


def _hook_text(script: dict) -> str:
    blocks = script.get("blocks") or []
    return next((str(b.get("text") or "").strip() for b in blocks if b.get("role") == "hook"), "")


def _features(row: dict) -> list[tuple[str, str]]:
    content = row.get("content_items") or {}
    script = content.get("script") or {}
    story = content.get("story_features") or {}
    features = []
    if story.get("archetype"):
        features.append(("archetype", str(story["archetype"])))
    hook = _hook_text(script)
    if story.get("hookType"):
        features.append(("hook", str(story["hookType"])))
    elif hook:
        features.append(("hook", hook_pattern(hook)))
    content_format = str(script.get("content_format") or "standard").strip()
    visual_style = str(script.get("visual_style") or "default").strip()
    caption_style = str(script.get("caption_style") or "bold_stroke").strip()
    features.append(("format", f"{content_format} · {visual_style} · {caption_style}"[:180]))
    return features


def _latest_snapshots(rows: list[dict]) -> dict[str, dict]:
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
    return latest


def _eligible(row: dict) -> bool:
    """Sans rétention ou avec trop peu de vues, le score n'est que du bruit."""
    return row.get("watch_time_pct") is not None and int(row.get("views") or 0) >= MIN_VIEWS


def build_insights(rows: list[dict]) -> list[dict]:
    """Agrège le snapshot le plus récent de chaque vidéo éligible par
    caractéristique, avec l'écart (`lift`) à la médiane du compte."""
    videos = [row for row in _latest_snapshots(rows).values() if _eligible(row)]
    if not videos:
        return []
    scores = {id(row): performance_score(row) for row in videos}
    account_median = median(scores.values())

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in videos:
        for feature in _features(row):
            grouped[feature].append(row)

    insights = []
    for (kind, label), members in sorted(grouped.items()):
        group_scores = [scores[id(r)] for r in members]
        avg = round(mean(group_scores), 2)
        insights.append({
            "kind": kind,
            "label": label,
            "performance_score": avg,
            "sample_size": len(members),
            "metadata": {
                "lift": round(avg - account_median, 2),
                "accountMedian": round(account_median, 2),
                "accountVideos": len(videos),
                "avgRetention": round(mean(float(r["watch_time_pct"]) for r in members), 1),
                "examples": [
                    str((r.get("content_items") or {}).get("title") or "")[:120] for r in members
                ][:3],
            },
        })
    return insights


_KIND_LABELS = {
    # (sujet, verbe "mieux", verbe "décroche") accordés au singulier/pluriel.
    "archetype": ("les histoires de type", "performent", "décrochent"),
    "hook": ("les accroches de type", "performent", "décrochent"),
    "format": ("le format", "performe", "décroche"),
}


def build_recommendation(insights: list[dict]) -> dict | None:
    """Une décision pour la prochaine vidéo, ou `None` si aucun groupe n'a
    assez de vidéos ni un écart net à la médiane : mieux vaut aucune
    consigne qu'une conclusion tirée d'une seule vidéo."""
    solid = [
        i for i in insights
        if i.get("kind") in _KIND_ORDER and i.get("sample_size", 0) >= MIN_GROUP_SIZE
        and abs((i.get("metadata") or {}).get("lift", 0)) >= MIN_LIFT
    ]
    if not solid:
        return None

    parts = []
    for kind in _KIND_ORDER:
        of_kind = [i for i in solid if i["kind"] == kind]
        best = max((i for i in of_kind if i["metadata"]["lift"] > 0), key=lambda i: i["metadata"]["lift"], default=None)
        worst = min((i for i in of_kind if i["metadata"]["lift"] < 0), key=lambda i: i["metadata"]["lift"], default=None)
        if best:
            m = best["metadata"]
            subject, better, _ = _KIND_LABELS[kind]
            parts.append(
                f"Sur ce compte, {subject} « {best['label']} » {better} mieux que la médiane "
                f"(rétention {m['avgRetention']} %, {best['sample_size']} vidéos)"
            )
        if worst:
            m = worst["metadata"]
            subject, _, worse = _KIND_LABELS[kind]
            parts.append(
                f"{subject.capitalize()} « {worst['label']} » {worse} "
                f"(rétention {m['avgRetention']} %, {worst['sample_size']} vidéos) : à éviter ou à retravailler"
            )
    if not parts:
        return None

    videos = max((i["metadata"].get("accountVideos", 0) for i in solid), default=0)
    confidence = "high" if videos >= 15 else "medium" if videos >= 6 else "low"
    return {
        "body": ". ".join(parts) + ". Quoi qu'il en soit, change à chaque vidéo de personnage, de lieu et "
                "de retournement : ne refais pas une histoire déjà publiée.",
        "reasoning": f"Calculé sur {videos} vidéo(s) avec rétention et au moins {MIN_VIEWS} vues ; "
                     f"groupes d'au moins {MIN_GROUP_SIZE} vidéos, écart d'au moins {MIN_LIFT:g} points "
                     "à la médiane du compte.",
        "confidence": confidence,
    }
