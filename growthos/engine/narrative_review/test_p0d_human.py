"""Prérequis P0-D 5/6 : checklist de validation des sources et protocole d'évaluation à l'aveugle (la coupure OS est dans test_p0d_egress.py)."""
from __future__ import annotations

import copy
import csv
import io
import ipaddress
import json
import random
import tempfile
import unittest
from pathlib import Path

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.harness import corpus as corp
from growthos.engine.narrative_review.harness import runner
from growthos.engine.narrative_review.p0d import evaluation as ev
from growthos.engine.narrative_review.p0d import source_validation as sv


class TestSourceChecklist(unittest.TestCase):
    def setUp(self):
        self.corpus = corp.load_corpus()
        self.template = sv.build_checklist(self.corpus)

    def filled(self):
        rec = copy.deepcopy(self.template)
        rec["status"] = "FILLED_BY_HUMAN"
        rec["verifier"] = {"name": "Relecteur Exemple", "role": "relecteur externe", "independent_of_authors": True, "signed_on": "2026-11-02"}
        for src in rec["sources"]:
            for check in src["checks"].values():
                check["state"] = "verified"
            for claim in src["claims"]:
                claim.update(state="verified", page_quote="Citation textuelle de la page, assez longue.", checked_on="2026-11-02")
            src["decision"] = "human_verified"
        return rec

    def test_only_the_documentary_pilot_subject_needs_human_validation(self):
        self.assertEqual(sv.required_source_ids(self.corpus), ["S01", "S02"])
        self.assertEqual([s["source_id"] for s in self.template["sources"]], ["S01", "S02"])

    def test_the_template_declares_nothing_verified_and_matches_the_committed_file(self):
        self.assertEqual(self.template["status"], "TEMPLATE_NOT_VERIFIED")
        self.assertEqual(self.template["verifier"], {"name": None, "role": None, "independent_of_authors": None, "signed_on": None})
        states = [self.template["sources"][i]["claims"][j]["state"] for i in range(2) for j in range(len(self.template["sources"][i]["claims"]))]
        self.assertTrue(states and set(states) == {"unverified"})
        self.assertTrue(all(ch["state"] == "unverified" for s in self.template["sources"] for ch in s["checks"].values()))
        committed = json.loads((corp.FIXTURES / "p0d" / "source_validation_S01_S02.template.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, self.template)
        # le corpus lui-même n'a JAMAIS été déclaré vérifié par cet outil
        self.assertTrue(all(s["verification"] != "human_verified" and not s["human_verified_by"] for s in self.corpus["sources"].values()))

    def test_the_blank_template_is_not_a_valid_record(self):
        self.assertGreater(len(sv.validate_record(self.template, self.corpus)), 5)

    def test_a_complete_independent_record_is_structurally_valid_but_changes_nothing(self):
        before = copy.deepcopy(self.corpus["sources"])
        self.assertEqual(sv.validate_record(self.filled(), self.corpus), [])
        self.assertEqual(self.corpus["sources"], before)

    def test_incomplete_or_inconsistent_records_are_rejected(self):
        def problems(fn):
            rec = self.filled()
            fn(rec)
            return sv.validate_record(rec, self.corpus)
        cases = {
            "not independent": lambda r: r["verifier"].update(independent_of_authors=False),
            "no name": lambda r: r["verifier"].update(name=""),
            "bad date": lambda r: r["verifier"].update(signed_on="hier"),
            "wrong corpus version": lambda r: r.update(sources_sha256="0" * 64),
            "missing source": lambda r: r["sources"].pop(),
            "claim undecided": lambda r: r["sources"][0]["claims"][0].update(state="unverified"),
            "verified without quote": lambda r: r["sources"][0]["claims"][0].update(page_quote=None),
            "quote too long": lambda r: r["sources"][0]["claims"][0].update(page_quote="x" * 301),
            "no check date": lambda r: r["sources"][0]["claims"][0].update(checked_on=None),
            "check undecided": lambda r: next(iter(r["sources"][0]["checks"].values())).update(state="unverified"),
            "summary edited": lambda r: r["sources"][0]["claims"][0].update(summary_sentence="Phrase réécrite."),
            "human_verified with a failed claim": lambda r: r["sources"][1]["claims"][0].update(state="not_supported"),
            "no decision": lambda r: r["sources"][0].update(decision=None),
            "unknown state": lambda r: r["sources"][0]["claims"][0].update(state="maybe"),
        }
        for label, fn in cases.items():
            self.assertTrue(problems(fn), label)

    def test_a_failed_source_can_be_recorded_honestly_as_needs_fix(self):
        rec = self.filled()
        rec["sources"][1]["claims"][0].update(state="not_supported", page_quote=None)
        rec["sources"][1]["decision"] = "needs_fix"
        self.assertEqual(sv.validate_record(rec, self.corpus), [])


def fake_manifest():
    cases = runner.plan_cases("EVAL", corp.PILOT_IDS, ("standard",))
    return {"campaign_id": "EVAL", "cases": cases}




class TestBlindEvaluation(unittest.TestCase):
    def setUp(self):
        self.corpus = corp.load_corpus()
        self.manifest = fake_manifest()

    def packets(self, tmp):
        paths = ev.build_packets(self.manifest, self.corpus, Path(tmp))
        key = json.loads((Path(tmp) / "PRIVATE" / "unblinding_key.json").read_text(encoding="utf-8"))
        return paths, key

    def test_allocation_is_balanced_and_no_listener_hears_both_variants_of_a_topic(self):
        plan = ev.allocate()
        self.assertEqual(len(plan), 60)
        for listener in {p["listener"] for p in plan}:
            mine = [p for p in plan if p["listener"] == listener]
            self.assertEqual(sorted(p["topic_id"] for p in mine), sorted(corp.PILOT_IDS))          # un passage par sujet
            self.assertEqual(sorted(p["position"] for p in mine), [1, 2, 3, 4, 5])
        for topic in corp.PILOT_IDS:
            variants = [p["variant"] for p in plan if p["topic_id"] == topic]
            self.assertEqual((variants.count("A"), variants.count("B")), (6, 6))                    # 6 auditeurs par variante et par sujet
        orders = {tuple(p["topic_id"] for p in plan if p["listener"] == f"L{r:02d}") for r in range(1, 13)}
        self.assertGreater(len(orders), 5)                                                         # l'ordre des sujets tourne
        self.assertEqual(plan, ev.allocate())                                                      # déterministe

    def test_the_rubric_covers_the_five_requested_dimensions_with_anchored_levels(self):
        self.assertEqual(set(ev.RUBRIC), {"narrative_quality", "causality", "clarity", "payoff", "factuality"})
        for dim, spec in ev.RUBRIC.items():
            self.assertTrue(all(spec.get(level) for level in ("label", "1", "3", "5")), dim)

    def test_distributable_and_private_files_are_physically_separated(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths, key = self.packets(tmp)
            root = Path(tmp)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["DISTRIBUTABLE", "PRIVATE"])
            self.assertEqual(sorted(paths["distributable"]), ["README.txt", "listener_sheets.csv", "pair_votes_template.csv", "recall_24h_template.csv", "scores_template.csv"])
            self.assertEqual(sorted(paths["private"]), [".gitignore", "README.txt", "unblinding_key.json"])
            self.assertFalse(list((root / "DISTRIBUTABLE").glob("*key*")))                      # aucune clé dans le dossier à distribuer
            self.assertEqual((root / "PRIVATE" / ".gitignore").read_text(encoding="utf-8").splitlines()[0], "*")
            self.assertIn("PRIVATE", key["WARNING"])
            self.assertEqual(len(key["blind_to_case"]), 10)
            self.assertEqual({v["condition"] for v in key["blind_to_case"].values()}, {"A", "B"})

    def test_the_distributable_folder_holds_opaque_ids_only_and_the_check_catches_any_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths, key = self.packets(tmp)
            dist = Path(tmp) / "DISTRIBUTABLE"
            secrets = list(corp.PILOT_IDS) + ["standard", "story_visual", "condition", "evaluator_only", "variant"]
            for topic in self.corpus["topics"].values():
                secrets += list(corp._leaf_texts(topic["evaluator_only"])) if hasattr(corp, "_leaf_texts") else list(corp._leaf_strings(topic["evaluator_only"]))
                secrets.append(topic["generator_input"]["topic"])
            for path in dist.iterdir():
                text = path.read_text(encoding="utf-8")
                for secret in secrets:
                    self.assertNotIn(secret.lower(), text.lower(), (path.name, secret))
            self.assertEqual(len(list(csv.DictReader(io.StringIO((dist / "listener_sheets.csv").read_text(encoding="utf-8"))))), 60)
            ev.assert_distributable_clean(dist, key, self.corpus)
            for leak in ("N01", "condition A", "unblinding_key", self.corpus["topics"]["N01"]["generator_input"]["topic"]):
                (dist / "scores_template.csv").write_text("x," + leak + "\n", encoding="utf-8")
                with self.assertRaises(ev.EvaluationFilesError, msg=leak):
                    ev.assert_distributable_clean(dist, key, self.corpus)
            (dist / "scores_template.csv").write_text("clean\n", encoding="utf-8")
            (dist / "unblinding_key.json").write_text("{}", encoding="utf-8")                   # un fichier de plus dans le dossier à distribuer
            with self.assertRaises(ev.EvaluationFilesError):
                ev.assert_distributable_clean(dist, key, self.corpus)

    def test_the_key_can_never_be_written_inside_a_git_repository(self):
        repo = Path(__file__).resolve().parents[3]                                                 # la racine du dépôt contient .git (ou en est un sous-dossier)
        target = Path(tempfile.mkdtemp(dir=repo)) if (repo / ".git").exists() else None
        if target is None:
            self.skipTest("this checkout has no .git folder at its root: cannot exercise the in-repository refusal here")
        self.addCleanup(lambda: __import__("shutil").rmtree(target, ignore_errors=True))
        with self.assertRaises(ev.EvaluationFilesError):
            ev.build_packets(self.manifest, self.corpus, target)
        self.assertEqual(list(target.iterdir()), [])                                              # rien n'a été écrit

    def test_pair_sides_are_mixed_and_every_listener_row_maps_to_a_blind_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, key = self.packets(tmp)
            pairs = list(csv.DictReader(io.StringIO((Path(tmp) / "DISTRIBUTABLE" / "pair_votes_template.csv").read_text(encoding="utf-8"))))
            self.assertEqual(len(pairs), 15)                                                       # 3 relecteurs x 5 paires
            self.assertEqual({key["blind_to_case"][p["left_blind_id"]]["condition"] for p in pairs}, {"A", "B"})   # A n'est pas toujours à gauche
            sheets = list(csv.DictReader(io.StringIO((Path(tmp) / "DISTRIBUTABLE" / "listener_sheets.csv").read_text(encoding="utf-8"))))
            self.assertTrue(all(r["blind_script_id"] in key["blind_to_case"] for r in sheets))

    def filled_scores(self, key, value=lambda dim, i: 3):
        header = list(ev.SCORE_COLUMNS)
        blind_of = {(m["topic_id"], m["condition"]): b for b, m in key["blind_to_case"].items()}
        rows = []
        for i, p in enumerate(key["allocation"]):
            row = {c: "" for c in header}
            row.update(listener_id=p["listener"], blind_script_id=blind_of[(p["topic_id"], p["variant"])], comprehension_code="2")
            row.update({d: str(value(d, i)) for d in ev.RUBRIC})
            rows.append(row)
        return rows

    def to_csv(self, rows):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(ev.SCORE_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    def test_a_complete_valid_entry_parses_and_aggregates_with_medians(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, key = self.packets(tmp)
        by_blind = {b: m["condition"] for b, m in key["blind_to_case"].items()}
        rows = self.filled_scores(key)
        for r in rows:
            r.update({d: ("4" if by_blind[r["blind_script_id"]] == "B" else "2") for d in ev.RUBRIC})
        parsed, problems = ev.parse_scores(self.to_csv(rows), key)
        self.assertEqual((problems, len(parsed)), ([], 60))
        diffs = ev.pair_differences(parsed, key)
        self.assertTrue(all(not d["provisional"] and set(d["differences_B_minus_A"].values()) == {2.0} for d in diffs))

    def test_every_invalid_entry_is_refused_not_corrected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, key = self.packets(tmp)

        def problems_of(mutate):
            rows = self.filled_scores(key)
            mutate(rows)
            return ev.parse_scores(self.to_csv(rows), key)[1]
        cases = {
            "score 0": lambda r: r[0].update(clarity="0"), "score 6": lambda r: r[0].update(payoff="6"), "score -1": lambda r: r[0].update(causality="-1"),
            "score 3.5": lambda r: r[0].update(clarity="3.5"), "score text": lambda r: r[0].update(clarity="bon"), "score 03": lambda r: r[0].update(clarity="03"),
            "score 1e0": lambda r: r[0].update(clarity="1e0"), "unknown listener": lambda r: r[0].update(listener_id="L99"),
            "unknown script": lambda r: r[0].update(blind_script_id="B99"),
            "script not assigned to this listener": lambda r: r[0].update(blind_script_id=r[5]["blind_script_id"]) if r[0]["blind_script_id"] != r[5]["blind_script_id"] else r[0].update(listener_id="L02"),
            "duplicate evaluation": lambda r: r.append(dict(r[0])),
            "bad comprehension code": lambda r: r[0].update(comprehension_code="3"),
        }
        for label, mutate in cases.items():
            self.assertTrue(problems_of(mutate), label)
        self.assertEqual(problems_of(lambda r: None), [])                                           # le jeu de base, lui, est valide
        parsed, problems = ev.parse_scores("wrong,columns\n1,2\n", key)
        self.assertEqual((parsed, len(problems)), ([], 1))

    def test_a_blank_score_is_missing_never_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, key = self.packets(tmp)
        rows = self.filled_scores(key)
        rows[0]["clarity"] = ""
        parsed, problems = ev.parse_scores(self.to_csv(rows), key)
        self.assertEqual((problems, parsed[0]["clarity"]), ([], None))

    def test_aggregation_refuses_invalid_rows_and_never_invents_missing_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, key = self.packets(tmp)
        good = lambda: [dict(r, **{d: 4 for d in ev.RUBRIC}) for r in ev.parse_scores(self.to_csv(self.filled_scores(key)), key)[0]]  # noqa: E731
        for label, mutate in {"out of range": lambda r: r[0].update(clarity=9), "float": lambda r: r[0].update(clarity=3.5), "bool": lambda r: r[0].update(clarity=True),
                              "duplicate": lambda r: r.append(dict(r[0])), "unknown script": lambda r: r[0].update(blind_script_id="B99"),
                              "no listener": lambda r: r[0].update(listener_id="")}.items():
            rows = good()
            mutate(rows)
            with self.assertRaises(ValueError, msg=label):
                ev.pair_differences(ev.ValidatedScores(rows), key)                                   # même un objet « validé » fabriqué est revérifié
            with self.assertRaises(ValueError, msg=label):
                ev.pair_differences(rows, key)                                                      # et une liste brute est refusée d'emblée
        thin = ev.validate_scores([r for r in good() if not (r["blind_script_id"] == next(b for b, m in key["blind_to_case"].items() if m == {"topic_id": "N01", "condition": "B"}))], key)
        by_topic = {d["topic_id"]: d for d in ev.pair_differences(thin, key)}
        self.assertTrue(by_topic["N01"]["provisional"])
        self.assertTrue(all(v is None for v in by_topic["N01"]["differences_B_minus_A"].values()))   # manquant : jamais 0
        self.assertFalse(by_topic["N04"]["provisional"])

    def test_pair_votes_require_unique_reviewers_per_pair_and_matching_sides(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, key = self.packets(tmp)
            template = (Path(tmp) / "DISTRIBUTABLE" / "pair_votes_template.csv").read_text(encoding="utf-8")
        rows = list(csv.DictReader(io.StringIO(template)))
        for r in rows:
            r["preference_left_right_tie_neither"] = "left"

        def parse(rs):
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(ev.PAIR_COLUMNS), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rs)
            return ev.parse_pair_votes(buf.getvalue(), key)[1]
        self.assertEqual(parse(rows), [])
        self.assertTrue(parse(rows + [dict(rows[0])]))                                              # même relecteur deux fois sur la même paire
        self.assertTrue(parse([dict(rows[0], reviewer_id="R9")] + rows[1:]))
        self.assertTrue(parse([dict(rows[0], preference_left_right_tie_neither="gagnant")] + rows[1:]))
        self.assertTrue(parse([dict(rows[0], left_blind_id=rows[0]["right_blind_id"], right_blind_id=rows[0]["left_blind_id"])] + rows[1:]))   # côtés inversés
        self.assertTrue(parse([dict(rows[0], pair_id="P99")] + rows[1:]))


if __name__ == "__main__":
    unittest.main()
