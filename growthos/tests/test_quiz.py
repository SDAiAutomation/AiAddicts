import unittest

from engine.quiz import compile_quiz, validate_quiz
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
        self.assertTrue(compiled["blocks"][2]["reuse_visual_from_previous"])
        validate_script(compiled)

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


if __name__ == "__main__":
    unittest.main()
