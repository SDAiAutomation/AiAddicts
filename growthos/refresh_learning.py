"""Recalcule la mémoire éditoriale (insights + recommandation en attente) de
chaque compte ayant des relevés de performance.

Lancé chaque matin par `.github/workflows/growthos-metrics.yml`, juste après
le relevé automatique des métriques YouTube. Classe au passage (une seule
fois, cache `content_items.story_features`) les vidéos pas encore classées.

Usage:
    python refresh_learning.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from engine import db, learning, repo, story_features, recommendation_tracking


def _classify_missing(client, rows: list[dict]) -> int:
    """Nombre de vidéos effectivement classées pendant ce passage."""
    done: set[str] = set()
    classified = 0
    for row in rows:
        item_id = str(row.get("content_item_id") or "")
        content = row.get("content_items") or {}
        cached = content.get("story_features") or {}
        # Reclasse quand la consigne du classifieur a changé (VERSION).
        fingerprint = recommendation_tracking.script_fingerprint(content.get("script") or {})
        if not item_id or item_id in done or (cached.get("version") == story_features.VERSION
                                             and cached.get("input_fingerprint") == fingerprint):
            continue
        done.add(item_id)
        features = story_features.classify(str(content.get("title") or ""), content.get("script") or {})
        if features is None:
            continue
        features["input_fingerprint"] = fingerprint
        repo.save_story_features(client, item_id, features)
        classified += 1
        # Même objet partagé par toutes les lignes de cette vidéo : le calcul
        # qui suit voit la classification sans relire la base.
        content["story_features"] = features
        for other in rows:
            if str(other.get("content_item_id")) == item_id:
                (other.get("content_items") or {})["story_features"] = features
    return classified


def refresh_recommendation_reports(client, account_id: str, rows: list[dict]) -> int:
    count = 0
    for item in repo.get_account_recommendation_items(client, account_id):
        report = recommendation_tracking.build_report(item, rows)
        if report is not None and repo.save_recommendation_report(client, item, report):
            count += 1
    return count


def main() -> int:
    client = db.get_service_client()
    failures = 0
    for account_id in repo.get_accounts_with_performance(client):
        try:
            rows = repo.get_account_performance(client, account_id)
            classified = _classify_missing(client, rows)
            insights = learning.build_insights(rows)
            repo.replace_account_insights(client, account_id, insights)
            recommendation = learning.build_recommendation(insights)
            if recommendation:
                repo.save_pending_recommendation(client, account_id, recommendation)
            else:
                repo.clear_pending_recommendation(client, account_id)
            tracked = refresh_recommendation_reports(client, account_id, rows)
            print(
                f"{account_id}: {classified} vidéo(s) classée(s), {len(insights)} insight(s), "
                f"recommandation : {recommendation['confidence'] if recommendation else 'aucune (données insuffisantes)'}, "
                f"{tracked} test(s) suivi(s)"
            )
            if recommendation:
                print(f"    {recommendation['body']}")
        except Exception as exc:
            failures += 1
            print(f"{account_id}: échec du recalcul ({exc})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
