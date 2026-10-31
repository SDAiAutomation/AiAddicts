"""Mission 1 (3e audit Codex) : un champ NUMÉRIQUE inconnu imbriqué dans un motion_graphic était ignoré sans provoquer `review`.

Reproduction exacte : un champ inconnu `{"badge": 7}` imbriqué dans un motion_graphic (bloc ou racine) donnait `accept` / `can_auto_accept=True`.
Ces tests n'importent que des symboles déjà présents avant le correctif : ils échouent sur l'assertion contre l'ancien code.
"""
from __future__ import annotations

import copy
import itertools
import unittest

from growthos.engine.narrative_review import snapshot as snap
from growthos.engine.narrative_review.test_review import ACC, ORG, NetworkBlocked, good_response, run


def with_mg(mg, *, place="block"):
    if place == "block":
        return {"title": "T", "blocks": [{"role": "hook", "text": "Une phrase claire.", "motion_graphic": mg}, {"role": "point", "text": "Fin."}]}
    return {"title": "T", "blocks": [{"role": "hook", "text": "Une phrase claire."}, {"role": "point", "text": "Fin."}], "motion_graphic": mg}


def snap_of(script):
    return snap.from_standard(script, organization_id=ORG, account_id=ACC, truth_mode="fiction")


class TestMission1NestedNumericGap(NetworkBlocked):
    def test_exact_reproduction_nested_unknown_number_is_a_gap_and_forces_review(self):
        script = with_mg({"sceneType": "icon_text", "displayText": "Les petits achats", "meta": {"badge": 7}})
        before = copy.deepcopy(script)
        s = snap_of(script)
        self.assertEqual(script, before)
        self.assertEqual(s["coverage_gaps"], ["/blocks/0/motion_graphic/meta/badge"])
        report = run(s, good_response(s))   # couverture complète de ce qui a été lu, aucun défaut
        self.assertEqual((report["decision"], report["can_auto_accept"]), ("review", False))
        self.assertIn("unread_displayed_content", report["reasons"])
        self.assertIn("unread_content:/blocks/0/motion_graphic/meta/badge", report["limits"])

    def test_numbers_under_unknown_keys_in_every_nesting_are_gaps(self):
        shapes = {
            "top-level unknown number": {"sceneType": "x", "badge": 7},
            "float": {"badge": 7.5},
            "negative": {"badge": -3},
            "zero": {"badge": 0},
            "nested object": {"a": {"b": {"c": 42}}},
            "list of numbers": {"counts": [1, 2, 3]},
            "list of objects": {"items": [{"label": "ok", "rank": 1}]},
            "list in list": {"grid": [[1, 2], [3]]},
            "orphan number in list root": [1, 2],
        }
        for label, mg in shapes.items():
            for place in ("block", "root"):
                s = snap_of(with_mg(mg, place=place))
                self.assertTrue(s["coverage_gaps"], (label, place))
                report = run(s, good_response(s))
                self.assertEqual((report["decision"], report["can_auto_accept"]), ("review", False), (label, place))
                self.assertIn("unread_displayed_content", report["reasons"], (label, place))

    def test_known_plot_parameters_and_the_displayed_value_are_interpreted_not_gaps(self):
        mg = {"sceneType": "function_graph", "title": "Courbe", "slope": 2, "intercept": -1, "xMin": -5, "xMax": 5, "yMin": 0, "yMax": 10,
              "highlightX": 1, "targetRatio": 0.5, "maxValue": 100, "value": 150, "_duration": 3, "_reveals": [1, 2]}
        s = snap_of(with_mg(mg))
        self.assertEqual(s["coverage_gaps"], [])
        self.assertEqual(sorted(u["text"] for u in s["units"] if u["channel"] == "on_screen"), ["150", "Courbe"])
        self.assertTrue(run(s, good_response(s))["can_auto_accept"])      # un cas INTERPRÉTÉ en totalité peut être accepté

    def test_values_under_value_including_lists_are_read_as_displayed_text(self):
        s = snap_of(with_mg({"sceneType": "bars", "items": [{"label": "A", "value": 6}, {"label": "B", "value": 2.5}], "value": [1, 2]}))
        self.assertEqual(s["coverage_gaps"], [])
        self.assertEqual(sorted(u["text"] for u in s["units"] if u["channel"] == "on_screen"), ["1", "2", "2.5", "6", "A", "B"])

    def test_booleans_and_nulls_carry_no_text_and_are_not_gaps(self):
        for mg in ({"sceneType": "x", "displayText": "ok", "flag": True}, {"sceneType": "x", "displayText": "ok", "note": None},
                   {"displayText": "ok", "nested": {"on": False, "none": None, "list": [True, None]}}):
            s = snap_of(with_mg(mg))
            self.assertEqual(s["coverage_gaps"], [], mg)
            self.assertTrue(run(s, good_response(s))["can_auto_accept"], mg)

    def test_unexpected_types_and_non_string_keys_inside_the_overlay_are_gaps(self):
        for mg in ({"displayText": "ok", "blob": b"xx"}, {"displayText": "ok", "x": {7: "TEXTE"}}, {"displayText": "ok", "t": (1, 2)},
                   {"displayText": "ok", "s": {1, 2}}, {"displayText": "ok", "o": object()}):
            s = snap_of(with_mg(mg))
            self.assertTrue(s["coverage_gaps"], mg)
            self.assertFalse(run(s, good_response(s))["can_auto_accept"], mg)

    def test_strings_nested_anywhere_are_always_read_not_gaps(self):
        s = snap_of(with_mg({"a": {"b": [{"c": "profond"}]}, "list": ["x", "y"], "sceneType": "z"}))
        self.assertEqual(s["coverage_gaps"], [])
        self.assertEqual(sorted(u["text"] for u in s["units"] if u["channel"] == "on_screen"), ["profond", "x", "y"])

    def test_internal_and_skipped_keys_are_never_gaps_even_with_numbers(self):
        s = snap_of(with_mg({"displayText": "ok", "_anchor": 5, "_plan": {"k": 1}, "rhythm": 3, "spoken": "mille", "icon": 2}))
        self.assertEqual(s["coverage_gaps"], [])

    def test_property_no_potentially_displayed_uninterpreted_content_can_auto_accept(self):
        """Toute combinaison clé inconnue x valeur contenant un nombre, à toutes les profondeurs, interdit l'acceptation automatique."""
        leaves = [7, 7.5, -1, 0, [1], {"n": 2}, [{"n": 3}], {"a": [{"b": 4}]}]
        wrappers = [lambda v: {"k": v}, lambda v: {"outer": {"k": v}}, lambda v: {"items": [{"label": "ok", "k": v}]},
                    lambda v: {"displayText": "ok", "deep": {"deeper": {"k": v}}}]
        checked = 0
        for leaf, wrap, place in itertools.product(leaves, wrappers, ("block", "root")):
            s = snap_of(with_mg(wrap(copy.deepcopy(leaf)), place=place))
            self.assertTrue(s["coverage_gaps"], (leaf, place))
            report = run(s, good_response(s))
            self.assertFalse(report["can_auto_accept"], (leaf, place))
            self.assertEqual(report["decision"], "review", (leaf, place))
            self.assertIsNone(report["error"], (leaf, place))                       # pas un refus pour une autre raison (locataire, format...)
            self.assertIn("unread_displayed_content", report["reasons"], (leaf, place))
            checked += 1
        self.assertEqual(checked, 64)


if __name__ == "__main__":
    unittest.main()


