"""YouTube Subscriber Growth Intelligence — isolated descriptive analytics.

Inputs are YouTube video-attributed *gross subscribersGained* and cumulative
video viewCount. This is NOT net subscribers, causal lift, or a live recommender.
Never treat a missing metric as zero.
"""
from collections import defaultdict
from datetime import datetime
from statistics import median

MIN_VIEWS = 50
MIN_GROUP_SIZE = 3


def subscribers_gained_per_1000(views, subscribers_gained):
    """Gross subscribers gained per 1,000 cumulative views, or None."""
    if views is None or subscribers_gained is None:
        return None
    try:
        v, gained = int(views), int(subscribers_gained)
    except (TypeError, ValueError, OverflowError):
        return None
    if v <= 0 or gained < 0:
        return None
    return round(gained * 1000 / v, 3)


def _timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def latest_youtube_snapshots(rows):
    """Pick the latest timestamped snapshot for each YouTube video.

    The input must be from the verified YouTube automatic collector, not
    historical manual or TikTok rows; database rows lack source provenance.
    A later incomplete snapshot supersedes earlier complete snapshots.
    """
    latest = {}
    for row in rows:
        if row.get("platform") != "youtube" or row.get("metric_source") != "youtube_auto":
            continue
        video_id = row.get("content_item_id")
        ts = _timestamp(row.get("captured_at"))
        if not video_id or ts is None:
            continue
        previous = latest.get(video_id)
        if previous is None or ts > previous[0]:
            latest[video_id] = (ts, row)
    return [item[1] for item in latest.values()]


def conversion_insights(rows, min_views=MIN_VIEWS, min_group_size=MIN_GROUP_SIZE):
    """Group verified YouTube snapshots; exploratory medians only.

    Each row must explicitly identify platform=youtube and
    metric_source=youtube_auto. Missing values and unclassified features
    are excluded. The caller must validate collector provenance.
    """
    groups = defaultdict(list)
    for row in latest_youtube_snapshots(rows):
        views = row.get("views")
        rate = subscribers_gained_per_1000(views, row.get("followers_delta"))
        try:
            eligible = int(views) >= min_views
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
            "median_subscribers_gained_per_1000_views": round(median(rates), 3),
            "status": "exploratory_not_causal",
        }
        for (kind, label), rates in sorted(groups.items())
        if len(rates) >= min_group_size
    ]
