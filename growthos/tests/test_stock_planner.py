"""Phase 4 — semantic stock planner + deterministic retrieval/ranking.
Every provider call is mocked: no Pexels/OpenAI quota is consumed."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import stock_planner as sp


def cand(cid, slug, w=1080, h=1920, dur=10.0, creator="u1", rank=0):
    return {"id": str(cid), "width": w, "height": h, "duration": dur, "url": f"https://x/{cid}.mp4",
            "slug": slug, "creator": creator, "rank": rank}


PLAN = {
    "visualConcept": "spending rises after salary growth",
    "subject": "young professional", "action": "shopping online", "environment": "modern apartment",
    "shotIntent": "evidence",
    "searchQueries": ["young professional online shopping phone", "credit card shopping apartment",
                      "food delivery young professional"],
    "avoidQueries": ["stock market chart", "business meeting"],
}


def fresh_state():
    return sp.SelectionState()


def rank(cands, query="young professional online shopping phone", level=0, plan=PLAN, block=None, state=None, secs=8.0):
    return sp.rank_candidates(cands, query=query, level=level, plan=plan, block=block or {},
                              state=state or fresh_state(), block_seconds=secs)


class TestPlanParsing(unittest.TestCase):
    def test_valid_plan_is_normalized(self):
        p = sp.normalize_plan({**PLAN, "searchQueries": ["  Young Professional  Shopping ", "young professional shopping"]})
        self.assertEqual(p["searchQueries"], ["young professional shopping"])  # deduped + lowercased
        self.assertEqual(p["subject"], "young professional")

    def test_garbage_and_empty_plans_rejected(self):
        for bad in (None, "x", [], {}, {"searchQueries": []}, {"searchQueries": ["", "   "]}):
            self.assertIsNone(sp.normalize_plan(bad))

    def test_overlong_query_dropped(self):
        p = sp.normalize_plan({"subject": "a", "searchQueries": ["one two three four five six seven eight nine"]})
        self.assertEqual(p["searchQueries"], [])

    def test_missing_optional_fields_ok(self):
        p = sp.normalize_plan({"searchQueries": ["woman using phone"]})
        self.assertEqual(p["avoidQueries"], [])
        self.assertEqual(p["environment"], "")

    def test_llm_response_parsing_drops_invalid_blocks(self):
        content = json.dumps({"blocks": [
            {"index": 1, **PLAN}, {"index": 2, "searchQueries": []}, {"index": 9, **PLAN}, {"index": "x"},
        ]})
        parsed = sp.parse_planning_response(content, 3)
        self.assertEqual(list(parsed), [0])
        self.assertEqual(sp.parse_planning_response("not json", 3), {})


class TestLegacyCompatibility(unittest.TestCase):
    def test_script_without_stock_plan_gets_deterministic_legacy_plan(self):
        block = {"text": "narr", "visual": "Personne qui fait des achats en ligne sur un ordinateur portable."}
        plan = sp.legacy_plan(block, "productivite-business")
        self.assertTrue(plan["legacy"])
        self.assertIn("achats ligne ordinateur portable", plan["searchQueries"][0])
        # the old niche-first-word pollution is not the lead query anymore
        self.assertNotIn("productivite", plan["searchQueries"][0])
        self.assertEqual(plan, sp.legacy_plan(block, "productivite-business"))  # deterministic

    def test_empty_block_still_yields_a_query(self):
        self.assertEqual(sp.legacy_plan({"text": "", "visual": ""})["searchQueries"], ["people lifestyle"])

    def test_plan_blocks_without_llm_uses_legacy_and_no_call(self):
        import os
        old = {k: os.environ.pop(k, None) for k in ("OPENAI_API_KEY", "STOCK_PLANNER_MODEL", "ORIGINALITY_MODEL")}
        try:
            calls = []
            plans, summary = sp.plan_blocks([{"text": "a b c d", "visual": "shopping online"}], "x", "fr",
                                            call_fn=lambda *a: calls.append(a))
            self.assertEqual(calls, [])
            self.assertEqual(summary["llmCalls"], 0)
            self.assertEqual(plans[0]["source"], "legacy")
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v


class TestPlanBlocksLlmStrategy(unittest.TestCase):
    def setUp(self):
        import os
        self._env = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "STOCK_PLANNER_MODEL", "STOCK_PLANNER")}
        os.environ["OPENAI_API_KEY"] = "test"
        os.environ["STOCK_PLANNER_MODEL"] = "m"
        os.environ.pop("STOCK_PLANNER", None)

    def tearDown(self):
        import os
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _blocks(self, n=3):
        return [{"text": f"t{i}", "visual": f"v{i}", "shotType": "medium", "visualPurpose": "action"} for i in range(n)]

    def test_exactly_one_call_for_whole_video_not_per_block(self):
        calls = []

        def fake(messages, model):
            calls.append(model)
            return json.dumps({"blocks": [{"index": i + 1, **PLAN} for i in range(3)]}), {"input": 100, "output": 50}

        plans, summary = sp.plan_blocks(self._blocks(3), "n", "en", call_fn=fake)
        self.assertEqual(len(calls), 1)
        self.assertEqual(summary["llmCalls"], 1)
        self.assertEqual({p["source"] for p in plans}, {"llm"})

    def test_blocks_already_carrying_a_plan_trigger_no_call(self):
        blocks = self._blocks(2)
        for b in blocks:
            b["stockPlan"] = PLAN
        plans, summary = sp.plan_blocks(blocks, "n", "en", call_fn=lambda *a: self.fail("must not call"))
        self.assertEqual(summary["llmCalls"], 0)
        self.assertEqual({p["source"] for p in plans}, {"script"})

    def test_llm_failure_degrades_to_legacy(self):
        import requests

        def boom(messages, model):
            raise requests.RequestException("down")

        plans, summary = sp.plan_blocks(self._blocks(2), "n", "en", call_fn=boom)
        self.assertEqual({p["source"] for p in plans}, {"legacy"})
        self.assertIn("down", summary["error"])

    def test_partial_llm_answer_fills_missing_blocks_with_legacy(self):
        fake = lambda m, model: (json.dumps({"blocks": [{"index": 1, **PLAN}]}), {"input": 1, "output": 1})
        plans, _ = sp.plan_blocks(self._blocks(3), "n", "en", call_fn=fake)
        self.assertEqual([p["source"] for p in plans], ["llm", "legacy", "legacy"])

    def test_plan_is_cached_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            fake = lambda m, model: (json.dumps({"blocks": [{"index": i + 1, **PLAN} for i in range(2)]}), {"input": 1, "output": 1})
            sp.plan_blocks(self._blocks(2), "n", "en", Path(d), call_fn=fake)
            _, summary = sp.plan_blocks(self._blocks(2), "n", "en", Path(d), call_fn=lambda *a: self.fail("cached"))
            self.assertTrue(summary["cached"])
            self.assertEqual(summary["llmCalls"], 0)


class TestQueryLadder(unittest.TestCase):
    def test_order_is_specific_to_broad(self):
        ladder = sp.build_ladder(PLAN)
        self.assertEqual(ladder[0], "young professional online shopping phone")  # Q1 specific
        self.assertEqual(ladder[1], "young professional shopping online")  # Q2 subject+action
        self.assertEqual(ladder[2], "credit card shopping apartment")
        self.assertEqual(len(ladder), sp.MAX_QUERIES_PER_PLAN)

    def test_dedup_and_cap(self):
        plan = {"subject": "a", "action": "b", "searchQueries": ["a b", "a b", "x y", "p q", "r s", "t u"]}
        ladder = sp.build_ladder(plan)
        self.assertEqual(len(ladder), len(set(ladder)))
        self.assertLessEqual(len(ladder), sp.MAX_QUERIES_PER_PLAN)

    def test_minimal_plan_still_has_a_ladder(self):
        self.assertEqual(sp.build_ladder({"searchQueries": ["woman phone"]}), ["woman phone"])


class TestRanking(unittest.TestCase):
    def test_portrait_preferred_over_landscape(self):
        r = rank([cand(1, "young-professional-online-shopping-phone", 1920, 1080),
                  cand(2, "young-professional-online-shopping-phone", 1080, 1920)])
        self.assertEqual(r[0]["id"], "2")
        self.assertGreater(r[0]["score"], r[1]["score"] + 3)

    def test_square_between_portrait_and_landscape(self):
        a, b, c = sp.aspect_score(1080, 1920), sp.aspect_score(1080, 1080), sp.aspect_score(1920, 1080)
        self.assertGreater(a, b)
        self.assertGreater(b, c)

    def test_relevance_beats_pexels_order(self):
        r = rank([cand(1, "sunset-over-mountains", rank=0), cand(2, "woman-online-shopping-with-phone", rank=1)])
        self.assertEqual(r[0]["id"], "2")

    def test_short_clip_penalised_because_it_loops(self):
        r = rank([cand(1, "online-shopping-phone", dur=3.0), cand(2, "online-shopping-phone", dur=12.0)], secs=8.0)
        self.assertEqual(r[0]["id"], "2")

    def test_low_resolution_penalised(self):
        self.assertGreater(sp.resolution_score(1080, 1920), sp.resolution_score(540, 960))

    def test_avoid_queries_penalised(self):
        r = rank([cand(1, "stock-market-chart-shopping", rank=0), cand(2, "online-shopping-phone", rank=1)])
        self.assertEqual(r[0]["id"], "2")

    def test_animated_or_3d_clips_are_penalised_unless_requested(self):
        r = rank([cand(1, "animation-of-a-hand-holding-a-smartphone", rank=0), cand(2, "hand-holding-a-smartphone", rank=1)],
                 query="hand holding smartphone")
        self.assertEqual(r[0]["id"], "2")
        asked = rank([cand(1, "animation-of-a-hand-holding-a-smartphone")], query="hand holding smartphone animation")
        self.assertEqual(asked[0]["breakdown"]["nonFootage"], 0.0)

    def test_shot_hint_is_a_small_tiebreaker(self):
        blk = {"shotType": "close_up"}
        r = rank([cand(1, "woman-phone-shopping", rank=0), cand(2, "close-up-woman-phone-shopping", rank=0)], block=blk)
        self.assertEqual(r[0]["id"], "2")

    def test_ranking_is_deterministic(self):
        pool = [cand(i, f"shopping-phone-{i}") for i in range(6)]
        self.assertEqual([c["id"] for c in rank(pool)], [c["id"] for c in rank(pool)])

    def test_missing_dimension_metadata_does_not_crash(self):
        r = rank([{"id": "1", "width": 0, "height": 0, "duration": 5, "url": "u", "slug": "", "creator": ""}])
        self.assertEqual(len(r), 1)


class TestDiversity(unittest.TestCase):
    def test_same_asset_is_heavily_penalised(self):
        st = fresh_state()
        st.record(cand(1, "woman-online-shopping-phone"))
        r = rank([cand(1, "woman-online-shopping-phone"), cand(2, "man-carrying-groceries")], state=st)
        self.assertEqual(r[0]["id"], "2")
        dup = next(c for c in r if c["id"] == "1")
        self.assertLessEqual(dup["duplicatePenalty"], -30)

    def test_consecutive_semantic_repetition_penalised(self):
        st = fresh_state()
        st.record(cand(1, "person-using-phone-on-sofa", creator="a"))
        r = rank([cand(2, "person-using-phone-on-sofa", creator="b", rank=0),
                  cand(3, "friends-eating-dinner-restaurant", creator="c", rank=1)],
                 query="person using phone", state=st)
        by_id = {c["id"]: c for c in r}
        self.assertLess(by_id["2"]["breakdown"]["repeatPrev"], -1.0)
        self.assertEqual(by_id["3"]["breakdown"]["repeatPrev"], 0.0)

    def test_same_creator_as_previous_is_penalised(self):
        st = fresh_state()
        st.record(cand(1, "a-thing", creator="same"))
        r = rank([cand(2, "online-shopping-phone", creator="same")], state=st)
        self.assertEqual(r[0]["breakdown"]["sameCreator"], -1.0)

    def test_no_clip_is_reused_across_a_full_selection(self):
        # every block's search returns the SAME 3 clips: no duplicate allowed while alternatives remain
        pool = [cand(1, "woman-shopping-online-phone", creator="a"), cand(2, "man-shopping-online-phone", creator="b"),
                cand(3, "girl-shopping-online-phone", creator="c")]
        blocks = [{"text": "t", "visual": "v"} for _ in range(3)]
        plans = [{**PLAN, "source": "llm"} for _ in range(3)]
        with tempfile.TemporaryDirectory() as d:
            paths, reports = sp.select_stock_clips(
                blocks, plans, images_dir=Path(d), search_fn=lambda q, o: list(pool), download_fn=lambda u, o: Path(o).write_bytes(b"x"),
            )
        ids = [r["selectedAssetId"] for r in reports]
        self.assertEqual(len(set(ids)), 3, ids)


class TestFallbackLadder(unittest.TestCase):
    def test_broadens_when_specific_query_yields_nothing_relevant(self):
        def search(q, o):
            if q == "young professional online shopping phone":
                return []  # zero-result search
            if q == "young professional shopping online":
                return [cand(7, "young-professional-shopping-online-laptop")]
            return [cand(8, "unrelated-mountains")]

        chosen, frag = sp.choose_for_block(PLAN, {}, fresh_state(), search, 8.0)
        self.assertEqual(chosen["id"], "7")
        self.assertEqual(chosen["level"], 1)
        self.assertEqual(frag["queriesAttempted"][:2], ["young professional online shopping phone", "young professional shopping online"])
        self.assertEqual(frag["fallback"], "ladder")

    def test_zero_results_everywhere_returns_none(self):
        chosen, frag = sp.choose_for_block(PLAN, {}, fresh_state(), lambda q, o: [], 8.0)
        self.assertIsNone(chosen)
        self.assertEqual(frag["fallback"], "none")
        self.assertEqual(frag["candidateCount"], 0)

    def test_search_count_is_capped(self):
        n = []

        def search(q, o):
            n.append(1)
            return []

        _, frag = sp.choose_for_block(PLAN, {}, fresh_state(), search, 8.0)
        self.assertLessEqual(len(n), sp.MAX_SEARCHES_PER_BLOCK)
        self.assertEqual(frag["searches"], len(n))

    def test_thin_portrait_pool_widens_to_any_orientation(self):
        seen = []

        def search(q, o):
            seen.append(o)
            return [cand(1, "young-professional-online-shopping-phone")] if o == "portrait" else [
                cand(2, "young-professional-online-shopping-phone", 1920, 1080)]

        chosen, frag = sp.choose_for_block(PLAN, {}, fresh_state(), search, 8.0)
        self.assertIn(None, seen)
        self.assertEqual(chosen["id"], "1")  # portrait still wins
        self.assertEqual(frag["candidateCount"], 2)

    def test_unrelated_clip_is_not_silently_accepted(self):
        pool = [cand(i, "sunset-mountains-lake", rank=i) for i in range(5, 10)]
        chosen, frag = sp.choose_for_block(PLAN, {}, fresh_state(), lambda q, o: list(pool), 8.0)
        # rank>=2 results with zero relevance are never trusted; only Pexels' top-2 at level<=1 may be low-confidence
        if chosen:
            self.assertEqual(frag["fallback"], "best_available")
            self.assertLess(chosen["pexelsIndex"], sp.LOW_CONFIDENCE_MAX_RANK)

    def test_legacy_plans_skip_relevance_gate(self):
        plan = sp.legacy_plan({"text": "x", "visual": "achats en ligne ordinateur"})
        chosen, frag = sp.choose_for_block(plan, {}, fresh_state(), lambda q, o: [cand(1, "totally-english-slug")], 8.0)
        self.assertEqual(chosen["id"], "1")
        self.assertEqual(frag["fallback"], "ladder")

    def test_photo_then_flat_color_fallbacks_recorded(self):
        blocks = [{"text": "t", "visual": "v"}, {"text": "t", "visual": "v"}]
        plans = [{**PLAN, "source": "llm"}] * 2
        with tempfile.TemporaryDirectory() as d:
            photo = lambda q, out: str(out) if out.name == "block-01.jpg" else None
            paths, reports = sp.select_stock_clips(
                blocks, plans, images_dir=Path(d), search_fn=lambda q, o: [], download_fn=lambda u, o: None, photo_fn=photo)
        self.assertEqual([r["fallback"] for r in reports], ["photo", "flat_color"])
        self.assertIsNone(paths[1])


class TestMetricsAndCache(unittest.TestCase):
    def _run(self, d, blocks=None):
        blocks = blocks or [{"text": "t", "visual": "v", "shotType": "medium", "visualPurpose": "action"}]
        plans = [{**PLAN, "source": "llm"} for _ in blocks]
        pool = [cand(11, "young-professional-online-shopping-phone-home")]
        return sp.select_stock_clips(blocks, plans, images_dir=Path(d), search_fn=lambda q, o: list(pool),
                                     download_fn=lambda u, o: Path(o).write_bytes(b"x"))

    def test_metrics_shape(self):
        with tempfile.TemporaryDirectory() as d:
            _, reports = self._run(d)
        r = reports[0]
        for key in ("blockIndex", "visualConcept", "queriesAttempted", "selectedQuery", "candidateCount", "selectedAssetId",
                    "selectedAspectRatio", "selectionScore", "fallbackLevel", "duplicatePenalty", "planSource",
                    "shotType", "visualPurpose", "fallback"):
            self.assertIn(key, r)
        self.assertEqual(r["selectedAssetId"], "11")
        self.assertAlmostEqual(r["selectedAspectRatio"], 0.562, places=3)
        self.assertEqual(r["fallbackLevel"], 0)
        self.assertEqual(r["selectedQuery"], "young professional online shopping phone")
        json.dumps(r)  # serialisable, no provider payload

    def test_cached_clip_is_reused_with_original_provenance_and_no_search(self):
        with tempfile.TemporaryDirectory() as d:
            self._run(d)
            paths, reports = sp.select_stock_clips(
                [{"text": "t", "visual": "v"}], [{**PLAN, "source": "llm"}], images_dir=Path(d),
                search_fn=lambda q, o: self.fail("cache hit must not search"), download_fn=lambda u, o: None)
        self.assertTrue(reports[0]["cached"])
        self.assertEqual(reports[0]["selectedAssetId"], "11")
        self.assertTrue(paths[0].endswith("block-01.mp4"))

    def test_reuse_visual_from_previous(self):
        with tempfile.TemporaryDirectory() as d:
            blocks = [{"text": "t", "visual": "v"}, {"text": "t", "visual": "v", "reuse_visual_from_previous": True}]
            paths, reports = sp.select_stock_clips(
                blocks, [{**PLAN, "source": "llm"}] * 2, images_dir=Path(d),
                search_fn=lambda q, o: [cand(1, "young-professional-online-shopping-phone")],
                download_fn=lambda u, o: Path(o).write_bytes(b"x"))
        self.assertEqual(paths[0], paths[1])
        self.assertEqual(reports[1]["fallback"], "reused_previous")


class TestPexelsNormalization(unittest.TestCase):
    RAW = {"id": 3191572, "duration": 12, "url": "https://www.pexels.com/video/woman-shopping-online-3191572/",
           "user": {"id": 5, "name": "A"},
           "video_files": [
               {"file_type": "video/mp4", "link": "sd", "width": 540, "height": 960},
               {"file_type": "video/mp4", "link": "hd", "width": 1080, "height": 1920},
               {"file_type": "video/mp4", "link": "uhd", "width": 2160, "height": 3840}]}

    def test_picks_smallest_file_that_covers_the_frame(self):
        c = sp.normalize_pexels_video(self.RAW)
        self.assertEqual(c["url"], "hd")
        self.assertEqual(c["slug"], "woman-shopping-online")
        self.assertEqual(c["creator"], "5")

    def test_out_of_range_duration_and_missing_files_dropped(self):
        self.assertIsNone(sp.normalize_pexels_video({**self.RAW, "duration": 1}))
        self.assertIsNone(sp.normalize_pexels_video({**self.RAW, "video_files": []}))
        self.assertIsNone(sp.normalize_pexels_video({"duration": 10}))

    def test_landscape_only_picks_largest_when_nothing_covers(self):
        raw = {**self.RAW, "video_files": [{"file_type": "video/mp4", "link": "a", "width": 1280, "height": 720},
                                           {"file_type": "video/mp4", "link": "b", "width": 1920, "height": 1080}]}
        self.assertEqual(sp.normalize_pexels_video(raw)["url"], "b")


if __name__ == "__main__":
    unittest.main()
