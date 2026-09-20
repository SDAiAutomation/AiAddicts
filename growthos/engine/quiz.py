"""Validation et compilation du format quiz vers les blocs du pipeline vidéo."""

from copy import deepcopy


QUIZ_FORMAT = "quiz"
QUIZ_KINDS = {"multiple_choice", "true_false", "riddle", "logo", "image"}
MIN_QUESTIONS = 1
MAX_QUESTIONS = 7
MIN_CHOICES = 2
MAX_CHOICES = 4
DEFAULT_COUNTDOWN_SECONDS = 5
MAX_COUNTDOWN_SECONDS = 10

# Product recipes are deliberately part of the engine contract. The web app can
# expose five simple cards while the renderer still receives explicit settings.
QUIZ_RECIPES = {
    "quick": {"kind": "multiple_choice", "question_count": 5, "countdown_seconds": 5, "difficulty": "medium"},
    "true_false": {"kind": "true_false", "question_count": 7, "countdown_seconds": 3, "difficulty": "medium"},
    "riddle": {"kind": "riddle", "question_count": 3, "countdown_seconds": 8, "difficulty": "medium"},
    "logo": {"kind": "logo", "question_count": 5, "countdown_seconds": 5, "difficulty": "medium"},
    "impossible": {"kind": "multiple_choice", "question_count": 5, "countdown_seconds": 5, "difficulty": "hard"},
}
DIFFICULTIES = {"easy", "medium", "hard", "progressive"}
QUIZ_THEMES = {"studio", "arcade", "education", "sport", "pop", "minimal", "photo", "logo"}
SOUND_EFFECT_MODES = {"automatic", "subtle", "off"}


# Phrases fixes lues par la voix off, par langue du script (défaut : français).
# {topic} = sujet du quiz ; {n} = numéro de question ; {letter}, {answer} = bonne réponse.
_PHRASES = {
    "fr": {"intro": "Teste tes connaissances sur {topic}.", "question": "Question {n}.", "answer": "La bonne réponse était {letter}, {answer}.", "outro": "Combien de bonnes réponses as-tu trouvées ?"},
    "en": {"intro": "Test your knowledge about {topic}.", "question": "Question {n}.", "answer": "The correct answer was {letter}, {answer}.", "outro": "How many did you get right?"},
    "es": {"intro": "Pon a prueba tus conocimientos sobre {topic}.", "question": "Pregunta {n}.", "answer": "La respuesta correcta era {letter}, {answer}.", "outro": "¿Cuántas has acertado?"},
    "de": {"intro": "Teste dein Wissen über {topic}.", "question": "Frage {n}.", "answer": "Die richtige Antwort war {letter}, {answer}.", "outro": "Wie viele hast du richtig?"},
    "it": {"intro": "Metti alla prova le tue conoscenze su {topic}.", "question": "Domanda {n}.", "answer": "La risposta corretta era {letter}, {answer}.", "outro": "Quante ne hai indovinate?"},
    "pt": {"intro": "Teste os teus conhecimentos sobre {topic}.", "question": "Pergunta {n}.", "answer": "A resposta certa era {letter}, {answer}.", "outro": "Quantas acertaste?"},
}
_TOPIC_FALLBACK = {"fr": "ce sujet", "en": "this topic", "es": "este tema", "de": "dieses Thema", "it": "questo argomento", "pt": "este tema"}


def is_quiz(script: dict) -> bool:
    return script.get("content_format") == QUIZ_FORMAT


def normalize_quiz(quiz: object) -> dict:
    """Expand a product recipe into the explicit, stable renderer contract."""
    if not isinstance(quiz, dict):
        raise ValueError("'quiz' doit être un objet")
    result = deepcopy(quiz)
    recipe_id = result.get("recipe", "quick")
    if recipe_id not in QUIZ_RECIPES:
        raise ValueError(f"'quiz.recipe' invalide (attendu : {sorted(QUIZ_RECIPES)})")
    recipe = QUIZ_RECIPES[recipe_id]
    result.setdefault("recipe", recipe_id)
    result.setdefault("kind", recipe["kind"])
    result.setdefault("difficulty", recipe["difficulty"])
    result.setdefault("countdown_seconds", recipe["countdown_seconds"])
    result.setdefault("theme", "studio")
    result.setdefault("sound_effects", "automatic")
    result.setdefault("cover", {"enabled": False})
    for question in result.get("questions") or []:
        if isinstance(question, dict):
            question.setdefault("countdown_seconds", result["countdown_seconds"])
    return result


def validate_quiz(quiz: object) -> None:
    quiz = normalize_quiz(quiz)
    kind = quiz.get("kind")
    if kind not in QUIZ_KINDS:
        raise ValueError(f"'quiz.kind' invalide (attendu : {sorted(QUIZ_KINDS)})")
    if quiz.get("difficulty") not in DIFFICULTIES:
        raise ValueError(f"'quiz.difficulty' invalide (attendu : {sorted(DIFFICULTIES)})")
    if quiz.get("theme") not in QUIZ_THEMES:
        raise ValueError(f"'quiz.theme' invalide (attendu : {sorted(QUIZ_THEMES)})")
    if quiz.get("sound_effects") not in SOUND_EFFECT_MODES:
        raise ValueError(f"'quiz.sound_effects' invalide (attendu : {sorted(SOUND_EFFECT_MODES)})")
    cover = quiz.get("cover")
    if not isinstance(cover, dict) or not isinstance(cover.get("enabled"), bool):
        raise ValueError("'quiz.cover.enabled' doit être un booléen")
    if cover.get("enabled"):
        title = str(cover.get("title") or "").strip()
        duration = cover.get("duration_seconds", 0.8)
        if not title or len(title) > 48:
            raise ValueError("'quiz.cover.title' doit contenir entre 1 et 48 caractères")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not (0.5 <= duration <= 1.0):
            raise ValueError("'quiz.cover.duration_seconds' doit être compris entre 0.5 et 1.0")
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
        if kind == "true_false" and len(choices) != 2:
            raise ValueError(f"{prefix}.choices doit contenir exactement 2 réponses pour un vrai/faux")
        if kind in {"logo", "image"} and not str(question.get("visual") or "").strip():
            raise ValueError(f"{prefix}.visual est requis pour un quiz visuel")
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
    normalized_quiz = normalize_quiz(script.get("quiz"))
    validate_quiz(normalized_quiz)
    if script.get("blocks"):
        return script

    result = deepcopy(script)
    result["quiz"] = normalized_quiz
    quiz = result["quiz"]
    blocks: list[dict] = []
    lang = result.get("language") if result.get("language") in _PHRASES else "fr"
    phrases = _PHRASES[lang]
    topic = quiz.get("topic") or result.get("niche") or _TOPIC_FALLBACK[lang]
    hook = str(quiz.get("intro") or phrases["intro"].format(topic=topic)).strip()
    blocks.append({"role": "hook", "text": hook, "quiz_phase": "intro"})

    letters = "ABCD"
    for number, item in enumerate(quiz["questions"], start=1):
        choices = [str(choice).strip() for choice in item["choices"]]
        spoken_choices = ". ".join(f"{letters[i]}, {choice}" for i, choice in enumerate(choices))
        blocks.append({
            "role": "point",
            "text": f"{phrases['question'].format(n=number)} {str(item['question']).strip()} {spoken_choices}.",
            "visual": str(item.get("visual") or item["question"]).strip(),
            "quiz_phase": "question",
            "quiz_question_number": number,
            "quiz_question_total": len(quiz["questions"]),
            "quiz_kind": quiz["kind"],
            "quiz_theme": quiz["theme"],
            "quiz_sound_effects": quiz["sound_effects"],
            "quiz_question": str(item["question"]).strip(),
            "quiz_choices": choices,
            "quiz_correct_choice": item["correct_choice"],
            "hold_after_seconds": item.get("countdown_seconds", DEFAULT_COUNTDOWN_SECONDS),
        })
        answer = choices[item["correct_choice"]]
        explanation = str(item.get("explanation") or "").strip()
        text = phrases["answer"].format(letter=letters[item["correct_choice"]], answer=answer)
        if explanation:
            text += f" {explanation}"
        blocks.append({
            "role": "point",
            "text": text,
            "visual": str(item.get("visual") or item["question"]).strip(),
            "quiz_phase": "reveal",
            "quiz_question_number": number,
            "quiz_question_total": len(quiz["questions"]),
            "quiz_kind": quiz["kind"],
            "quiz_theme": quiz["theme"],
            "quiz_question": str(item["question"]).strip(),
            "quiz_choices": choices,
            "quiz_correct_choice": item["correct_choice"],
            "reuse_visual_from_previous": True,
        })

    cta = str(quiz.get("outro") or result.get("cta") or phrases["outro"]).strip()
    blocks.append({"role": "cta", "text": cta, "quiz_phase": "outro"})
    result["blocks"] = blocks
    return result
