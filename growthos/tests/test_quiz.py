from copy import deepcopy
import unittest

from engine.quiz import compile_quiz, normalize_quiz, same_quiz_fact, validate_quiz
from engine.script import validate_script


QUIZ_SCRIPT = {
    "title": "Quiz espace",
    "niche": "culture-generale",
    "account": "quiz-account",
    "content_format": "quiz",
    "quiz": {
        "topic": "l'espace",
        "questions": [{
            "question": "Quelle planète est la plus proche du Soleil ?",
            "choices": ["Vénus", "Mercure", "Mars"],
            "correct_choice": 1,
            "explanation": "Mercure est la première planète du système solaire.",
            "countdown_seconds": 3,
        }],
    },
}


class TestQuiz(unittest.TestCase):
    def test_compiles_to_pipeline_blocks(self):
        validate_script(QUIZ_SCRIPT)
        compiled = compile_quiz(QUIZ_SCRIPT)
        self.assertEqual([b["quiz_phase"] for b in compiled["blocks"]], ["intro", "question", "reveal", "outro"])
        self.assertEqual(compiled["blocks"][1]["hold_after_seconds"], 3)
        self.assertEqual(compiled["blocks"][2]["quiz_correct_choice"], 1)
        self.assertEqual(compiled["blocks"][1]["quiz_question_total"], 1)
        self.assertEqual(compiled["quiz"]["recipe"], "quick")
        self.assertEqual(compiled["blocks"][1]["quiz_sound_effects"], "automatic")
        self.assertTrue(compiled["blocks"][2]["reuse_visual_from_previous"])
        self.assertIn("Editorial quiz illustration", compiled["blocks"][1]["visual"])
        self.assertNotIn("Mercure", compiled["blocks"][1]["visual"])
        validate_script(compiled)

    def test_existing_blocks_receive_semantic_visuals_without_mutating_source(self):
        compiled = compile_quiz(QUIZ_SCRIPT)
        compiled["blocks"][1]["visual"] = "BrainLoop premium emblem"
        upgraded = compile_quiz(compiled)
        self.assertIn("Quelle plan", upgraded["blocks"][1]["visual"])
        self.assertEqual(compiled["blocks"][1]["visual"], "BrainLoop premium emblem")

    def test_author_scene_drives_the_illustration_for_standard_quizzes(self):
        script = deepcopy(QUIZ_SCRIPT)
        script["quiz"]["questions"][0]["visual"] = "Close-up of a rusty telescope on a rooftop at dusk"
        compiled = compile_quiz(script)
        self.assertIn("rusty telescope", compiled["blocks"][1]["visual"])
        self.assertTrue(compiled["blocks"][1]["visual"].startswith("Editorial quiz illustration"))
        self.assertEqual(compile_quiz(compiled)["blocks"][1]["visual"], compiled["blocks"][1]["visual"])

    def test_generic_brand_scene_falls_back_to_the_question(self):
        script = deepcopy(QUIZ_SCRIPT)
        script["quiz"]["questions"][0]["visual"] = "Flat circular BrainLoop logo over a photo"
        visual = compile_quiz(script)["blocks"][1]["visual"]
        self.assertNotIn("BrainLoop", visual)
        self.assertIn("Quelle plan", visual)

    def test_illustrations_default_on_and_must_be_boolean(self):
        self.assertTrue(normalize_quiz(QUIZ_SCRIPT["quiz"])["illustrations"])
        off = {**QUIZ_SCRIPT["quiz"], "illustrations": False}
        self.assertFalse(normalize_quiz(off)["illustrations"])
        with self.assertRaisesRegex(ValueError, "illustrations"):
            normalize_quiz({**QUIZ_SCRIPT["quiz"], "illustrations": "no"})

    def test_logo_quiz_without_illustrations_needs_no_visual(self):
        quiz = {**QUIZ_SCRIPT["quiz"], "recipe": "logo", "kind": "logo", "illustrations": False,
                "questions": [{k: v for k, v in q.items() if k != "visual"} for q in QUIZ_SCRIPT["quiz"]["questions"]]}
        validate_quiz(quiz)

    def test_logo_quiz_replaces_generic_emblem_but_keeps_specific_visual(self):
        questions = [{**q, "visual": "placeholder"} for q in QUIZ_SCRIPT["quiz"]["questions"]]
        script = {**QUIZ_SCRIPT, "quiz": {**QUIZ_SCRIPT["quiz"], "kind": "logo", "questions": questions}}
        compiled = compile_quiz(script)
        compiled["blocks"][1]["visual"] = "BrainLoop premium emblem, a sleek circular loop icon"
        compiled["blocks"][3]["visual"] = "The Nike swoosh on a white sneaker"
        upgraded = compile_quiz(compiled)
        self.assertIn("Editorial quiz illustration", upgraded["blocks"][1]["visual"])
        self.assertEqual(upgraded["blocks"][3]["visual"], "The Nike swoosh on a white sneaker")

    def test_narration_follows_script_language(self):
        english = {**QUIZ_SCRIPT, "language": "en"}
        blocks = compile_quiz(english)["blocks"]
        self.assertTrue(blocks[1]["text"].startswith("Question 1."))
        self.assertTrue(blocks[2]["text"].startswith("The correct answer was B, Mercure."))
        self.assertEqual(blocks[3]["text"], "How many did you get right?")
        self.assertTrue(compile_quiz(QUIZ_SCRIPT)["blocks"][2]["text"].startswith("La bonne réponse était B"))

    def test_last_question_does_not_claim_unverified_difficulty(self):
        question = QUIZ_SCRIPT["quiz"]["questions"][0]
        texts = ["Quelle planète est la plus proche du Soleil ?", "Quel satellite tourne autour de la Terre ?",
                 "Quelle étoile éclaire notre système solaire ?"]
        questions = [{**question, "question": text} for text in texts]
        script = {**QUIZ_SCRIPT, "language": "en", "quiz": {**QUIZ_SCRIPT["quiz"], "questions": questions}}
        questions = [b for b in compile_quiz(script)["blocks"] if b["quiz_phase"] == "question"]
        self.assertTrue(questions[0]["text"].startswith("Question 1."))
        self.assertTrue(questions[1]["text"].startswith("Question 2."))
        self.assertTrue(questions[2]["text"].startswith("Last question."))
        self.assertNotIn("hardest", questions[2]["text"])

    def test_compile_does_not_mutate_source(self):
        compile_quiz(QUIZ_SCRIPT)
        self.assertNotIn("blocks", QUIZ_SCRIPT)

    def test_rejects_duplicate_choices(self):
        quiz = {"questions": [{
            "question": "Question ?", "choices": ["Oui", "oui"], "correct_choice": 0,
        }]}
        with self.assertRaisesRegex(ValueError, "distinctes"):
            validate_quiz(quiz)

    def test_rejects_invalid_answer_index(self):
        quiz = {"questions": [{
            "question": "Question ?", "choices": ["A", "B"], "correct_choice": 2,
        }]}
        with self.assertRaisesRegex(ValueError, "index"):
            validate_quiz(quiz)

    def test_rejects_more_than_seven_questions(self):
        item = {"question": "Question ?", "choices": ["A", "B"], "correct_choice": 0}
        with self.assertRaisesRegex(ValueError, "entre 1 et 7"):
            validate_quiz({"questions": [dict(item) for _ in range(8)]})

    def test_long_quiz_chapter_metadata(self):
        from engine.quiz import quiz_chapter
        chapters = [quiz_chapter(i, 25) for i in range(1, 26)]
        self.assertEqual([c["quiz_chapter_number"] for c in chapters],
                         [1] * 7 + [2] * 6 + [3] * 6 + [4] * 6)
        self.assertEqual([i for i, c in enumerate(chapters, 1) if c["quiz_chapter_start"]],
                         [1, 8, 14, 20])
        self.assertEqual(quiz_chapter(1, 5), {})
        self.assertEqual(quiz_chapter(0, 25), {})

    def test_long_quiz_compiles_without_standard_script_limits(self):
        questions = [{"question": f"What does biology concept {i} describe?", "choices": [f"Fact {i}", "Other"],
                      "correct_choice": 0, "explanation": f"This is explanation {i}."} for i in range(25)]
        source = {**QUIZ_SCRIPT, "quiz": {"recipe": "long", "topic": "biology", "questions": questions}}
        validate_script(source)
        compiled = compile_quiz(source)
        self.assertEqual(len(compiled["blocks"]), 52)
        self.assertFalse(compiled["quiz"]["illustrations"])
        validate_script(compiled)

    def test_five_level_chapter_boundaries_and_opt_in(self):
        from engine.quiz import quiz_chapter
        chapters = [quiz_chapter(i, 50, "five_levels") for i in range(1, 51)]
        self.assertEqual([c["quiz_chapter_number"] for c in chapters],
                         [1] * 10 + [2] * 10 + [3] * 10 + [4] * 10 + [5] * 10)
        self.assertEqual([i for i, c in enumerate(chapters, 1) if c["quiz_chapter_start"]],
                         [1, 11, 21, 31, 41])
        self.assertEqual([chapters[i]["quiz_chapter_label"] for i in (0, 10, 20, 30, 40)],
                         ["EASY", "MEDIUM", "HARD", "EXPERT", "GENIUS"])
        self.assertEqual(quiz_chapter(50, 50)["quiz_chapter_total"], 4)
        with self.assertRaisesRegex(ValueError, "exactement 50"):
            validate_quiz({"recipe": "long", "chapter_mode": "five_levels",
                           "questions": [{"question": f"Unique question {i}?",
                                          "choices": [f"Answer {i}", "Other"], "correct_choice": 0}
                                         for i in range(25)]})

    def test_five_level_compiled_blocks_have_single_chapter_entries(self):
        questions = [{"question": f"Which unique term {i} is correct?",
                      "choices": [f"Term {i}", f"Alternative {i}"],
                      "correct_choice": 0} for i in range(1, 51)]
        source = {**QUIZ_SCRIPT, "quiz": {"recipe": "long", "topic": "terms",
                                         "chapter_mode": "five_levels",
                                         "questions": questions}}
        compiled = compile_quiz(source)
        blocks = compiled["blocks"]
        self.assertEqual(blocks[0]["quiz_chapter_total"], 5)
        self.assertEqual(blocks[-1]["quiz_chapter_total"], 5)
        starts = [(b["quiz_question_number"], b["quiz_phase"]) for b in blocks
                  if b.get("quiz_chapter_start")]
        self.assertEqual(starts, [(1, "question"), (11, "question"),
                                  (21, "question"), (31, "question"),
                                  (41, "question")])
        self.assertEqual(blocks[-2]["quiz_chapter_number"], 5)

    def test_long_quiz_50_questions_compiles_and_51_rejected(self):
        questions = [{"question": f"Which unique element number {i} is described?",
                      "choices": [f"Element {i}", f"Alternative {i}"],
                      "correct_choice": 0} for i in range(1, 51)]
        source = {**QUIZ_SCRIPT, "quiz": {"recipe": "long", "topic": "elements",
                                         "questions": questions}}
        validate_script(source)
        compiled = compile_quiz(source)
        self.assertEqual(len(compiled["blocks"]), 102)
        self.assertEqual(compiled["blocks"][-2]["quiz_question_number"], 50)
        with self.assertRaisesRegex(ValueError, "entre 10 et 50"):
            validate_quiz({**source["quiz"], "questions": questions + [
                {"question": "Extra distinct fact 51?", "choices": ["Extra 51", "No"],
                 "correct_choice": 0}]})

    def test_rejects_previous_fact_and_reworded_question(self):
        source = {"questions": [{"question": "Which organelle makes ATP?", "choices": ["Mitochondrion", "Nucleus"],
                                 "correct_choice": 0, "fact": "mitochondria ATP"}],
                  "previous_questions": [{"question": "What is the cell powerhouse?", "answer": "Mitochondrion",
                                          "fact": "mitochondria ATP"}]}
        with self.assertRaisesRegex(ValueError, "répète"):
            validate_quiz(source)

    def test_recipe_expands_defaults_without_mutating_input(self):
        source = {"recipe": "riddle", "questions": [{
            "question": "Je monte sans bouger. Qui suis-je ?",
            "choices": ["Un escalier", "Un nuage"], "correct_choice": 0,
        }]}
        normalized = normalize_quiz(source)
        self.assertEqual(normalized["kind"], "riddle")
        self.assertEqual(normalized["difficulty"], "medium")
        self.assertEqual(normalized["questions"][0]["countdown_seconds"], 8)
        self.assertNotIn("kind", source)

    def test_true_false_requires_two_choices(self):
        with self.assertRaisesRegex(ValueError, "exactement 2"):
            validate_quiz({"recipe": "true_false", "questions": [{
                "question": "La Terre est ronde ?", "choices": ["Vrai", "Faux", "Parfois"],
                "correct_choice": 0,
            }]})

    def test_visual_quiz_requires_visual(self):
        with self.assertRaisesRegex(ValueError, "visual est requis"):
            validate_quiz({"recipe": "logo", "questions": [{
                "question": "Quelle marque ?", "choices": ["A", "B"], "correct_choice": 0,
            }]})

    def test_verification_states_are_explicit_and_legacy_questions_still_load(self):
        validate_quiz(QUIZ_SCRIPT["quiz"])
        for state in ("verified", "review_required", "rejected", "unverified"):
            quiz = deepcopy(QUIZ_SCRIPT["quiz"])
            quiz["questions"][0]["verification"] = {"status": state}
            validate_quiz(quiz)
        quiz["questions"][0]["verification"] = {"status": "ok"}
        with self.assertRaisesRegex(ValueError, "verification.status"):
            validate_quiz(quiz)

    def test_missing_choices_and_invalid_answer_indices_fail(self):
        for patch in ({"choices": []}, {"correct_choice": 3}, {"correct_choice": True}):
            quiz = deepcopy(QUIZ_SCRIPT["quiz"])
            quiz["questions"][0].update(patch)
            with self.assertRaises(ValueError):
                validate_quiz(quiz)

    def test_duplicate_fact_contract_in_french_and_english(self):
        cases = [
            ({"question": "Quelle planète est la plus proche du Soleil ?", "answer": "Mercure"},
             {"question": "Quelle planète est la plus proche du soleil?", "answer": "Venus"}, True),
            ({"question": "Quelle planète est la plus proche du Soleil ?", "answer": "Mercure", "fact": "planet-mercury"},
             {"question": "Quelle est la première planète ?", "answer": "Mercure", "fact": "planet-mercury"}, True),
            ({"question": "Which planet is closest to the Sun?", "answer": "Mercury"},
             {"question": "Which planet is closest to the sun", "answer": "Mercury"}, True),
            ({"question": "Quelle ville a accueilli les Jeux olympiques de 2012 ?", "answer": "Londres"},
             {"question": "Quelle ville abrite Big Ben ?", "answer": "Londres"}, False),
            ({"question": "What organ pumps blood?", "answer": "Heart"},
             {"question": "What organ filters blood?", "answer": "Kidney"}, False),
        ]
        for first, second, expected in cases:
            self.assertEqual(same_quiz_fact(first, second), expected)


class SameQuizFactTests(unittest.TestCase):
    BOYLE = {"question": "Which law states that pressure is inversely proportional to volume at constant temperature?",
             "answer": "Boyle's law", "fact": "boyle law pv constant"}

    def test_paraphrases_of_the_same_fact_are_detected(self):
        from engine.quiz import same_quiz_fact
        self.assertTrue(same_quiz_fact(self.BOYLE, dict(self.BOYLE)))
        self.assertTrue(same_quiz_fact(self.BOYLE, {
            "question": "At constant temperature, which gas law links pressure and volume inversely?",
            "answer": "Boyle's law", "fact": "gaz pression volume inverse"}))
        self.assertTrue(same_quiz_fact(self.BOYLE, {
            "question": "What is the name of the law relating pressure and volume of a gas at fixed temperature?",
            "answer": "Boyle's law", "fact": ""}))

    def test_distinct_questions_and_true_false_are_not_flagged(self):
        from engine.quiz import same_quiz_fact
        self.assertFalse(same_quiz_fact(self.BOYLE, {
            "question": "Which law relates the volume of a gas to its temperature at constant pressure?",
            "answer": "Charles's law"}))
        self.assertFalse(same_quiz_fact(self.BOYLE, {"question": "What is the chemical symbol for sodium?", "answer": "Na"}))
        self.assertFalse(same_quiz_fact(
            {"question": "Water boils at 100 degrees Celsius at sea level.", "answer": "True"},
            {"question": "Iron rusts when exposed to water and oxygen.", "answer": "True"}))

    def test_validate_quiz_rejects_a_reworded_repeat(self):
        quiz = {"recipe": "long", "questions": [
            {"question": q, "choices": ["Boyle's law", "Charles's law"], "correct_choice": 0}
            for q in (self.BOYLE["question"],
                      "At constant temperature, which gas law links pressure and volume inversely?")
        ] + [{"question": f"Distinct subject{n} alpha{n} beta{n} gamma{n}?", "choices": [f"A{n}", f"B{n}"], "correct_choice": 0}
             for n in range(10)]}
        with self.assertRaisesRegex(ValueError, "répète un fait"):
            validate_quiz(quiz)


if __name__ == "__main__":
    unittest.main()
