"""Validation et compilation du format quiz vers les blocs du pipeline vidéo."""

from copy import deepcopy


QUIZ_FORMAT = "quiz"
MIN_QUESTIONS = 1
MAX_QUESTIONS = 5
MIN_CHOICES = 2
MAX_CHOICES = 4
DEFAULT_COUNTDOWN_SECONDS = 3
MAX_COUNTDOWN_SECONDS = 10


def is_quiz(script: dict) -> bool:
    return script.get("content_format") == QUIZ_FORMAT


def validate_quiz(quiz: object) -> None:
    if not isinstance(quiz, dict):
        raise ValueError("'quiz' doit être un objet")
    questions = quiz.get("questions")
    if not isinstance(questions, list) or not (MIN_QUESTIONS <= len(questions) <= MAX_QUESTIONS):
        raise ValueError(f"'quiz.questions' doit contenir entre {MIN_QUESTIONS} et {MAX_QUESTIONS} questions")

    for i, question in enumerate(questions):
        prefix = f"quiz.questions[{i}]"
        if not isinstance(question, dict):
            raise ValueError(f"{prefix} doit être un objet")
        if not str(question.get("question") or "").strip():
            raise ValueError(f"{prefix}.question est requis")
        choices = question.get("choices")
        if not isinstance(choices, list) or not (MIN_CHOICES <= len(choices) <= MAX_CHOICES):
            raise ValueError(f"{prefix}.choices doit contenir entre {MIN_CHOICES} et {MAX_CHOICES} réponses")
        cleaned = [str(choice).strip() for choice in choices]
        if any(not choice for choice in cleaned):
            raise ValueError(f"{prefix}.choices ne peut pas contenir de réponse vide")
        if len({choice.casefold() for choice in cleaned}) != len(cleaned):
            raise ValueError(f"{prefix}.choices doit contenir des réponses distinctes")
        correct = question.get("correct_choice")
        if isinstance(correct, bool) or not isinstance(correct, int) or not (0 <= correct < len(choices)):
            raise ValueError(f"{prefix}.correct_choice doit être l'index d'une réponse existante")
        countdown = question.get("countdown_seconds", DEFAULT_COUNTDOWN_SECONDS)
        if isinstance(countdown, bool) or not isinstance(countdown, int) or not (1 <= countdown <= MAX_COUNTDOWN_SECONDS):
            raise ValueError(f"{prefix}.countdown_seconds doit être compris entre 1 et {MAX_COUNTDOWN_SECONDS}")


def compile_quiz(script: dict) -> dict:
    """Retourne une copie avec des blocs narrables enrichis de métadonnées quiz."""
    if not is_quiz(script):
        return script
    validate_quiz(script.get("quiz"))
    if script.get("blocks"):
        return script

    result = deepcopy(script)
    quiz = result["quiz"]
    blocks: list[dict] = []
    hook = str(quiz.get("intro") or f"Teste tes connaissances sur {quiz.get('topic') or result.get('niche') or 'ce sujet'}.").strip()
    blocks.append({"role": "hook", "text": hook, "quiz_phase": "intro"})

    letters = "ABCD"
    for number, item in enumerate(quiz["questions"], start=1):
        choices = [str(choice).strip() for choice in item["choices"]]
        spoken_choices = ". ".join(f"{letters[i]}, {choice}" for i, choice in enumerate(choices))
        blocks.append({
            "role": "point",
            "text": f"Question {number}. {str(item['question']).strip()} {spoken_choices}.",
            "visual": str(item.get("visual") or item["question"]).strip(),
            "quiz_phase": "question",
            "quiz_question_number": number,
            "quiz_question": str(item["question"]).strip(),
            "quiz_choices": choices,
            "quiz_correct_choice": item["correct_choice"],
            "hold_after_seconds": item.get("countdown_seconds", DEFAULT_COUNTDOWN_SECONDS),
        })
        answer = choices[item["correct_choice"]]
        explanation = str(item.get("explanation") or "").strip()
        text = f"La bonne réponse était {letters[item['correct_choice']]}, {answer}."
        if explanation:
            text += f" {explanation}"
        blocks.append({
            "role": "point",
            "text": text,
            "visual": str(item.get("visual") or item["question"]).strip(),
            "quiz_phase": "reveal",
            "quiz_question_number": number,
            "quiz_question": str(item["question"]).strip(),
            "quiz_choices": choices,
            "quiz_correct_choice": item["correct_choice"],
            "reuse_visual_from_previous": True,
        })

    cta = str(quiz.get("outro") or result.get("cta") or "Combien de bonnes réponses as-tu trouvées ?").strip()
    blocks.append({"role": "cta", "text": cta, "quiz_phase": "outro"})
    result["blocks"] = blocks
    return result
