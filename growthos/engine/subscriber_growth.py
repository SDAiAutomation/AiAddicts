"""Subscriber Growth Intelligence v0 — independent, read-only analytics.

No change to the existing performance score or recommendations. The caller
must supply snapshots from one consistent observation window per video.
Missing follower data is never interpreted as zero.
"""
from collections import defaultdict
from statistics import median

MIN_VIEWS = 50
MIN_GROUP_SIZE = 3


def subscribers_per_1000(views, followers_delta):
    """Signed net subscribers per 1,000 views; None if data is incomplete."""
    if views is None or followers_delta is None:
        return None
    try:
        v = int(views)
        f = int(followers_delta)
    except (TypeError, ValueError, OverflowError):
        return None
    if v <= 0:
        return None
    return round(1000 * f / v, 3)


def conversion_insights(rows, min_views=MIN_VIEWS, min_group_size=MIN_GROUP_SIZE):
    """Describe conversion by narrative features without ranking small samples.

    rows must contain one snapshot per video, with views and followers_delta
    measured over the SAME window. A cumulative view count paired with a
    period-only subscriber delta is not comparable and must not be supplied.
    This function intentionally does not merge snapshots across dates.
    """
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        video_id = row.get("content_item_id")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        views = row.get("views")
        rate = subscribers_per_1000(views, row.get("followers_delta"))
        try:
            eligible = views is not None and int(views) >= min_views
        except (TypeError, ValueError, OverflowError):
            eligible = False
        if not eligible or rate is None:
            continue
        content = row.get("content_items") or {}
        features = content.get("story_features") or {}
        for kind, label in (
            ("archetype", features.get("archetype")),
            ("hook", features.get("hookType")),
        ):
            if isinstance(label, str) and label.strip() and label != "autre":
                groups[(kind, label.strip())].append(rate)
    return [
        {
            "kind": kind,
            "label": label,
            "sample_size": len(rates),
            "median_net_subscribers_per_1000_views": round(median(rates), 3),
            "status": "exploratory_not_causal",
        }
        for (kind, label), rates in sorted(groups.items())
        if len(rates) >= min_group_size
    ]
