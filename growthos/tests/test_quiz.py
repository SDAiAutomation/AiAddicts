import unittest

from engine.quiz import compile_quiz, normalize_quiz, validate_quiz
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
        validate_script(compiled)

    def test_narration_follows_script_language(self):
        english = {**QUIZ_SCRIPT, "language": "en"}
        blocks = compile_quiz(english)["blocks"]
        self.assertTrue(blocks[1]["text"].startswith("Question 1."))
        self.assertTrue(blocks[2]["text"].startswith("The correct answer was B, Mercure."))
        self.assertEqual(blocks[3]["text"], "How many did you get right?")
        self.assertTrue(compile_quiz(QUIZ_SCRIPT)["blocks"][2]["text"].startswith("La bonne réponse était B"))

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


if __name__ == "__main__":
    unittest.main()
