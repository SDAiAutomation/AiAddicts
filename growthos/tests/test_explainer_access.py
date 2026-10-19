"""Accès à l'Explainer vérifié par le worker : l'auteur doit être administrateur (échec fermé)."""
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from engine import assembler
from engine.explainer import access

ADMIN = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
RAW = f"{ADMIN}, not-a-uuid admin@example.com"


class FakeClient:
    """Imite `client.table(t).select(c).eq(k, v).limit(1).execute().data` sur des lignes en mémoire."""
    def __init__(self, tables, broken=()):
        self.tables, self.broken = tables, set(broken)

    def table(self, name):
        if name in self.broken:
            raise RuntimeError("column created_by does not exist")
        rows = self.tables.get(name, [])

        class Query:
            def __init__(self):
                self.match = {}
            def select(self, _columns):
                return self
            def eq(self, key, value):
                self.match[key] = value
                return self
            def limit(self, _n):
                return self
            def execute(self):
                data = [r for r in rows if all(r.get(k) == v for k, v in self.match.items())]
                return Mock(data=data)
        return Query()


def item(**fields):
    return {"id": "item", "requested_by": None, "series_id": None, **fields}


class ParseTests(unittest.TestCase):
    def test_only_uuids_count_never_emails(self):
        self.assertEqual(access.parse_admin_ids(RAW.upper()), {ADMIN})
        self.assertEqual(access.parse_admin_ids(None), set())
        self.assertEqual(access.parse_admin_ids(f"{ADMIN};{OTHER}"), {ADMIN, OTHER})


class AuthorizeTests(unittest.TestCase):
    def test_admin_requester_is_allowed(self):
        client = FakeClient({"content_items": [item(requested_by=ADMIN)]})
        self.assertEqual(access.authorize(client, "item", RAW), ADMIN)

    def test_other_requester_is_refused_even_when_a_series_belongs_to_an_admin(self):
        client = FakeClient({"content_items": [item(requested_by=OTHER, series_id="s")], "series": [{"id": "s", "created_by": ADMIN}]})
        with self.assertRaisesRegex(access.ExplainerAccessDenied, "administrateurs"):
            access.authorize(client, "item", RAW)

    def test_queued_by_sql_uses_the_series_author(self):
        client = FakeClient({"content_items": [item(series_id="s")], "series": [{"id": "s", "created_by": ADMIN}]})
        self.assertEqual(access.authorize(client, "item", RAW), ADMIN)
        client = FakeClient({"content_items": [item(series_id="s")], "series": [{"id": "s", "created_by": OTHER}]})
        with self.assertRaises(access.ExplainerAccessDenied):
            access.authorize(client, "item", RAW)

    def test_unknown_author_missing_admin_list_and_unreadable_series_fail_closed(self):
        with self.assertRaisesRegex(access.ExplainerAccessDenied, "inconnu"):
            access.authorize(FakeClient({"content_items": [item()]}), "item", RAW)
        with self.assertRaisesRegex(access.ExplainerAccessDenied, "inconnu"):
            access.authorize(FakeClient({"content_items": [item(series_id="s")], "series": [{"id": "s", "created_by": None}]}), "item", RAW)
        with self.assertRaisesRegex(access.ExplainerAccessDenied, "ADMIN_USER_IDS"):
            access.authorize(FakeClient({"content_items": [item(requested_by=ADMIN)]}), "item", "")
        with self.assertRaisesRegex(access.ExplainerAccessDenied, "migration"):
            access.authorize(FakeClient({"content_items": [item(series_id="s")]}, broken={"series"}), "item", RAW)

    def test_environment_is_the_default_source(self):
        client = FakeClient({"content_items": [item(requested_by=ADMIN)]})
        with patch.dict("os.environ", {"ADMIN_USER_IDS": ADMIN}):
            self.assertEqual(access.authorize(client, "item"), ADMIN)
        with patch.dict("os.environ", {"ADMIN_USER_IDS": ""}), self.assertRaises(access.ExplainerAccessDenied):
            access.authorize(client, "item")


class WorkerGuardTests(unittest.TestCase):
    def harness(self, visual_style, denied):
        stack = ExitStack()
        self.addCleanup(stack.close)
        script = {"title": "t", "niche": "n", "account": "a", "platform": "tiktok", "visual_style": visual_style,
                  "blocks": [{"role": "hook", "text": "Bonjour"}]}
        stack.enter_context(patch("engine.assembler.db.get_service_client", return_value=Mock()))
        stack.enter_context(patch("engine.assembler.repo.get_script", return_value=script))
        stack.enter_context(patch("engine.assembler.moderation.check_script"))
        reserve = stack.enter_context(patch("engine.assembler.repo.reserve_generation_credit", return_value=True))
        authorize = stack.enter_context(patch("engine.assembler.explainer_access.authorize",
                                              side_effect=access.ExplainerAccessDenied("refusé") if denied else None))
        stack.enter_context(patch("engine.assembler.events.organization_id_of", return_value="org"))
        stack.enter_context(patch("engine.assembler.events.record"))
        stack.enter_context(patch("engine.assembler.asset_store.configure"))
        stack.enter_context(patch("engine.assembler.asset_store.reset"))
        stack.enter_context(patch("engine.assembler.repo.refund_generation_credit"))
        stack.enter_context(patch("engine.assembler._generate", side_effect=RuntimeError("stop ici")))
        return reserve, authorize

    def test_denied_explainer_never_reserves_a_credit_nor_renders(self):
        reserve, authorize = self.harness("explainer", denied=True)
        with self.assertRaises(access.ExplainerAccessDenied):
            assembler.run_for_content_item("item")
        authorize.assert_called_once()
        reserve.assert_not_called()

    def test_other_styles_are_not_checked(self):
        reserve, authorize = self.harness("motion_graphics", denied=True)
        with self.assertRaisesRegex(RuntimeError, "stop ici"):
            assembler.run_for_content_item("item")
        authorize.assert_not_called()
        reserve.assert_called_once()


if __name__ == "__main__":
    unittest.main()
