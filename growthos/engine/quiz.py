"""Validation et compilation du format quiz vers les blocs du pipeline vidéo."""

import re
import unicodedata
from difflib import SequenceMatcher
from copy import deepcopy


QUIZ_FORMAT = "quiz"
QUIZ_KINDS = {"multiple_choice", "true_false", "riddle", "logo", "image"}
MIN_QUESTIONS = 1
MAX_QUESTIONS = 7
MAX_LONG_QUESTIONS = 30
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
    "long": {"kind": "multiple_choice", "question_count": 25, "countdown_seconds": 7, "difficulty": "progressive"},
}
DIFFICULTIES = {"easy", "medium", "hard", "progressive"}
QUIZ_THEMES = {"studio", "arcade", "education", "sport", "pop", "minimal", "photo", "logo"}
SOUND_EFFECT_MODES = {"automatic", "subtle", "off"}
PRESENTATION_MODES = {"classic", "motion"}


# Phrases fixes lues par la voix off, par langue du script (défaut : français).
# {topic} = sujet du quiz ; {n} = numéro de question ; {letter}, {answer} = bonne réponse.
_PHRASES = {
    "fr": {"last": "Dernière question.", "intro": "Teste tes connaissances sur {topic}.", "question": "Question {n}.", "answer": "La bonne réponse était {letter}, {answer}.", "outro": "Combien de bonnes réponses as-tu trouvées ?"},
    "en": {"last": "Last question.", "intro": "Test your knowledge about {topic}.", "question": "Question {n}.", "answer": "The correct answer was {letter}, {answer}.", "outro": "How many did you get right?"},
    "es": {"last": "Última pregunta.", "intro": "Pon a prueba tus conocimientos sobre {topic}.", "question": "Pregunta {n}.", "answer": "La respuesta correcta era {letter}, {answer}.", "outro": "¿Cuántas has acertado?"},
    "de": {"last": "Letzte Frage.", "intro": "Teste dein Wissen über {topic}.", "question": "Frage {n}.", "answer": "Die richtige Antwort war {letter}, {answer}.", "outro": "Wie viele hast du richtig?"},
    "it": {"last": "Ultima domanda.", "intro": "Metti alla prova le tue conoscenze su {topic}.", "question": "Domanda {n}.", "answer": "La risposta corretta era {letter}, {answer}.", "outro": "Quante ne hai indovinate?"},
    "pt": {"last": "Última pergunta.", "intro": "Teste os teus conhecimentos sobre {topic}.", "question": "Pergunta {n}.", "answer": "A resposta certa era {letter}, {answer}.", "outro": "Quantas acertaste?"},
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
    if "illustrations" in result and not isinstance(result["illustrations"], bool):
        raise ValueError("'quiz.illustrations' doit être un booléen")
    if "backdrops" in result and not isinstance(result["backdrops"], bool):
        raise ValueError("'quiz.backdrops' doit être un booléen")
    result.setdefault("recipe", recipe_id)
    result.setdefault("kind", recipe["kind"])
    result.setdefault("difficulty", recipe["difficulty"])
    result.setdefault("countdown_seconds", recipe["countdown_seconds"])
    result.setdefault("theme", "studio")
    result.setdefault("sound_effects", "automatic")
    result.setdefault("presentation", "classic")
    result.setdefault("cover", {"enabled": False})
    result.setdefault("illustrations", True)
    result.setdefault("backdrops", False)  # fond illustré (4 images) : opt-in, voir engine/quiz_backdrop.py
    if recipe_id == "long" and "illustrations" not in quiz:
        result["illustrations"] = False
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
    if not isinstance(quiz.get("presentation"), str) or quiz["presentation"] not in PRESENTATION_MODES:
        raise ValueError(f"'quiz.presentation' invalide (attendu : {sorted(PRESENTATION_MODES)})")
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
    maximum = MAX_LONG_QUESTIONS if quiz["recipe"] == "long" else MAX_QUESTIONS
    minimum = 10 if quiz["recipe"] == "long" else MIN_QUESTIONS
    if not isinstance(questions, list) or not (minimum <= len(questions) <= maximum):
        raise ValueError(f"'quiz.questions' doit contenir entre {minimum} et {maximum} questions")

    previous = quiz.get("previous_questions", [])
    if not isinstance(previous, list) or len(previous) > 500 or any(
        not isinstance(item, dict) or not isinstance(item.get("question"), str)
        or not isinstance(item.get("answer"), str) for item in previous
    ):
        raise ValueError("'quiz.previous_questions' doit contenir au plus 500 questions et réponses")
    seen = list(previous)
    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            continue
        choices = item.get("choices")
        correct = item.get("correct_choice")
        if not isinstance(choices, list) or isinstance(correct, bool) or not isinstance(correct, int) or not 0 <= correct < len(choices):
            continue
        current = {"question": str(item.get("question") or ""), "answer": str(choices[correct]),
                   "fact": str(item.get("fact") or "")}
        if any(same_quiz_fact(current, earlier) for earlier in seen):
            raise ValueError(f"quiz.questions[{index}] répète un fait déjà testé ; remplace cette question")
        seen.append(current)

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
        if kind in {"logo", "image"} and quiz["illustrations"] and not str(question.get("visual") or "").strip():
            raise ValueError(f"{prefix}.visual est requis pour un quiz visuel")
        correct = question.get("correct_choice")
        if isinstance(correct, bool) or not isinstance(correct, int) or not (0 <= correct < len(choices)):
            raise ValueError(f"{prefix}.correct_choice doit être l'index d'une réponse existante")
        countdown = question.get("countdown_seconds", DEFAULT_COUNTDOWN_SECONDS)
        if isinstance(countdown, bool) or not isinstance(countdown, int) or not (1 <= countdown <= MAX_COUNTDOWN_SECONDS):
            raise ValueError(f"{prefix}.countdown_seconds doit être compris entre 1 et {MAX_COUNTDOWN_SECONDS}")


def _question_lead(phrases: dict, number: int, total: int) -> str:
    """Announce progress without making an unverified difficulty claim."""
    if total >= 3 and number == total:
        return phrases["last"]
    return phrases["question"].format(n=number)


def _canonical(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", value))


# Mots interrogatifs ignorés ; miroir de src/lib/quiz-duplicates.ts (growthos-web) : garder les deux identiques.
_QUESTION_WORDS = {
    "which", "what", "that", "this", "with", "from", "have", "does", "quel", "quelle", "quels", "quelles",
    "dans", "pour", "sont", "avec", "plus", "welche", "welcher", "welches", "cual", "cuales", "quale", "quali",
    "qual", "quais", "esta", "este", "como", "comment", "quand", "when", "where", "wann",
}
# Réponses d'un vrai/faux (ou oui/non) : toutes les affirmations partagent la même « réponse ».
_BINARY_ANSWERS = {
    "true", "false", "yes", "no", "vrai", "faux", "oui", "non", "verdadero", "falso", "si", "wahr", "falsch",
    "ja", "nein", "vero", "verdadeiro", "sim", "nao",
}


def _content_words(value: str) -> set[str]:
    # Les nombres et dates comptent même courts : « 1998 » et « 2002 » distinguent deux questions.
    return {word for word in _canonical(value).split()
            if (len(word) > 3 or any(c.isdigit() for c in word)) and word not in _QUESTION_WORDS}


def same_quiz_fact(first: dict, second: dict) -> bool:
    """Deux questions qui testent le même fait, reformulation comprise.

    Même question, même identifiant de fait, quasi-même vocabulaire (85 %), ou
    même bonne réponse avec la moitié des mots clés en commun."""
    left, right = _canonical(str(first.get("question") or "")), _canonical(str(second.get("question") or ""))
    if not left or not right:
        return False
    if left == right:
        return True
    fact_left, fact_right = _canonical(str(first.get("fact") or "")), _canonical(str(second.get("fact") or ""))
    if fact_left and fact_right and fact_left == fact_right:
        return True
    words_left, words_right = _content_words(left), _content_words(right)
    smallest = min(len(words_left), len(words_right))
    if smallest < 3:
        return False
    overlap = len(words_left & words_right) / smallest
    if overlap >= .85:
        return True
    answer = _canonical(str(first.get("answer") or ""))
    return bool(answer and answer not in _BINARY_ANSWERS
                and answer == _canonical(str(second.get("answer") or "")) and overlap >= .5)


_GENERIC_VISUAL = re.compile(r"brainloop|emblem", re.IGNORECASE)


_QUIZ_PROMPT_PREFIX = "Editorial quiz illustration"
_QUIZ_PROMPT_RULES = (
    "Photorealistic editorial style in one strong composition. "
    "Never draw abstract shapes, rings, gradients, 3D renders, or generic office objects. "
    "Leave calm negative space near the top and lower half for the quiz interface. "
    "Do not show the answer, answer choices, text, letters, numbers, labels, logos, or watermarks."
)


def _quiz_visual_prompt(question: str, scene: str = "") -> str:
    """Describe the subject while keeping every glyph in the ASS overlay.

    `scene` is the concrete shot the author (or the quiz generator) wrote for
    this question; when usable it drives the picture, otherwise the question
    itself does.
    """
    scene = scene.strip()
    if scene and not scene.startswith(_QUIZ_PROMPT_PREFIX) and not _GENERIC_VISUAL.search(scene):
        return f"{_QUIZ_PROMPT_PREFIX} showing this scene: {scene} {_QUIZ_PROMPT_RULES}"
    return (
        f"{_QUIZ_PROMPT_PREFIX} about: {question.strip()} "
        "Depict the concrete, recognisable subject of the question (the real place, event, person, "
        "object, or historical scene it refers to), even when the question asks for a date, a number or a name. "
        f"{_QUIZ_PROMPT_RULES}"
    )


def _prepare_existing_quiz_blocks(script: dict, normalized_quiz: dict) -> dict:
    """Upgrade web-authored quiz blocks to the current visual contract."""
    result = deepcopy(script)
    result["quiz"] = normalized_quiz
    for block in result.get("blocks") or []:
        if block.get("quiz_phase"):
            block["quiz_presentation"] = normalized_quiz["presentation"]
            block["quiz_topic"] = str(normalized_quiz.get("topic") or "QUIZ")
            if normalized_quiz["presentation"] == "motion":
                from .quiz_motion import REVEAL_BEAT_SECONDS, VERSION
                block["quiz_motion_version"] = VERSION
                if block.get("quiz_phase") == "question" and (block.get("hold_after_seconds") or 0) > 0:
                    block["quiz_reveal_beat_seconds"] = REVEAL_BEAT_SECONDS
                else:
                    block.pop("quiz_reveal_beat_seconds", None)
                block["quiz_theme"] = normalized_quiz["theme"]
            else:
                block.pop("quiz_motion_version", None)
        if block.get("quiz_phase") not in {"question", "reveal"}:
            continue
        kind = str(block.get("quiz_kind") or normalized_quiz.get("kind") or "multiple_choice")
        question = str(block.get("quiz_question") or "").strip()
        # Logo and image quizzes depend on the creator-supplied asset. Other
        # quiz kinds get a semantic illustration instead of branded filler or
        # narration rendered as text inside the background.
        # A logo/image block still carrying the generic BrainLoop emblem has no
        # real creator asset: it would frame the same filler on every question.
        generic = bool(_GENERIC_VISUAL.search(str(block.get("visual") or "")))
        current = str(block.get("visual") or "").strip()
        if question and (kind not in {"logo", "image"} or generic) and not current.startswith(_QUIZ_PROMPT_PREFIX):
            block["visual"] = _quiz_visual_prompt(question, current)
    return result


def compile_quiz(script: dict) -> dict:
    """Retourne une copie avec des blocs narrables enrichis de métadonnées quiz."""
    if not is_quiz(script):
        return script
    normalized_quiz = normalize_quiz(script.get("quiz"))
    validate_quiz(normalized_quiz)
    if script.get("blocks"):
        result = _prepare_existing_quiz_blocks(script, normalized_quiz)
        validate_motion_blocks(result)
        return result

    result = deepcopy(script)
    result["quiz"] = normalized_quiz
    quiz = result["quiz"]
    blocks: list[dict] = []
    lang = result.get("language") if result.get("language") in _PHRASES else "fr"
    phrases = _PHRASES[lang]
    topic = quiz.get("topic") or result.get("niche") or _TOPIC_FALLBACK[lang]
    hook = str(quiz.get("intro") or phrases["intro"].format(topic=topic)).strip()
    blocks.append({"role": "hook", "text": hook, "quiz_phase": "intro", "quiz_question_total": len(quiz["questions"])})

    letters = "ABCD"
    for number, item in enumerate(quiz["questions"], start=1):
        choices = [str(choice).strip() for choice in item["choices"]]
        spoken_choices = ". ".join(f"{letters[i]}, {choice}" for i, choice in enumerate(choices))
        blocks.append({
            "role": "point",
            "text": f"{_question_lead(phrases, number, len(quiz['questions']))} {str(item['question']).strip()} {spoken_choices}.",
            "visual": (
                str(item.get("visual")).strip()
                if quiz["kind"] in {"logo", "image"}
                else _quiz_visual_prompt(str(item["question"]), str(item.get("visual") or ""))
            ),
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
            "visual": (
                str(item.get("visual")).strip()
                if quiz["kind"] in {"logo", "image"}
                else _quiz_visual_prompt(str(item["question"]), str(item.get("visual") or ""))
            ),
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
    blocks.append({"role": "cta", "text": cta, "quiz_phase": "outro", "quiz_question_total": len(quiz["questions"])})
    result["blocks"] = blocks
    return _prepare_existing_quiz_blocks(result, normalized_quiz)


def validate_motion_blocks(script: dict) -> None:
    """Reject inconsistent saved Motion blocks before any paid generation."""
    quiz = script.get("quiz") or {}
    if not is_quiz(script) or quiz.get("presentation") != "motion":
        return
    blocks = script.get("blocks") or []
    questions = quiz.get("questions") or []
    expected = ["intro", *[p for _ in questions for p in ("question", "reveal")], "outro"]
    if [b.get("quiz_phase") for b in blocks] != expected:
        raise ValueError("Quiz Motion : blocs incomplets ou hors ordre ; recompiler les questions.")
    for number, item in enumerate(questions, 1):
        for offset in (number * 2 - 1, number * 2):
            block = blocks[offset]
            expected_fields = {
                "quiz_question": str(item["question"]).strip(),
                "quiz_choices": [str(c).strip() for c in item["choices"]],
                "quiz_correct_choice": item["correct_choice"],
                "quiz_question_number": number,
                "quiz_question_total": len(questions),
            }
            if any(block.get(key) != value for key, value in expected_fields.items()):
                raise ValueError(f"Quiz Motion : la question {number} et ses blocs ne correspondent plus ; recompiler le Quiz.")
            if block["quiz_phase"] == "question" and block.get("hold_after_seconds") != item["countdown_seconds"]:
                raise ValueError(f"Quiz Motion : temps de réflexion incohérent pour la question {number}.")
            if block["quiz_phase"] == "reveal" and block.get("hold_after_seconds", 0) != 0:
                raise ValueError(f"Quiz Motion : pause inattendue dans la révélation {number}.")
    if any(b.get("hold_after_seconds", 0) != 0 for b in (blocks[0], blocks[-1])):
        raise ValueError("Quiz Motion : pause inattendue dans l'ouverture ou la conclusion.")
