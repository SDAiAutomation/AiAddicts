"""Contrat interne `narrative-review:0.1` (P0-B). EXPÉRIMENTAL : jamais branché au worker, aux jobs ni aux prompts de production.

Le fournisseur (modèle) n'émet que des observations et des preuves. Le serveur valide puis calcule la décision. Aucun
endpoint, état public, table ou contrat de rendu n'est ajouté ici.
"""
from __future__ import annotations

SCHEMA_VERSION = "narrative-review:0.1"
POLICY_VERSION = "faceloop-editorial:0.1"
CRITIC_VERSION = "narrative-critic:0.1"
PROMPT_VERSION = "narrative-critic-prompt:0.1"

SOURCE_FORMATS = ("standard", "story_dialogue", "story_visual")
TRUTH_MODES = ("fiction", "inspired", "fact", "unknown")
ILLUSTRATION_MODES = ("none", "metaphor", "hypothetical")
CHANNELS = ("title", "spoken", "on_screen")
VERIFICATIONS = ("prepared_for_benchmark", "human_verified", "unknown")
CONTENT_KINDS = ("source_excerpt", "curated_summary")

DIMENSIONS = ("truth", "promise", "causality", "narrator", "clarity", "ending", "pacing", "originality")
PILOT_REQUIRED_DIMENSIONS = ("truth", "promise", "causality", "narrator", "clarity", "ending")
COVERAGE_STATUSES = ("evaluated", "partial", "not_applicable", "unavailable")
CLAIM_ASSESSMENTS = ("supported", "contradicted", "unverified", "not_factual")
SEVERITIES = ("blocker", "warning")
ASSESSMENTS = ("established", "uncertain")
REPAIR_SCOPES = ("local_text", "whole_story", "needs_sources", "needs_author")

# code -> (dimension, sévérité autorisée). Liste fermée de la politique P0 (01_POLITIQUE_EDITORIALE.md).
CODES: dict[str, tuple[str, tuple[str, ...]]] = {
    "FACT_CONTRADICTED": ("truth", ("blocker",)),
    "FABRICATED_ATTRIBUTION": ("truth", ("blocker",)),
    "FACT_UNVERIFIED": ("truth", ("blocker",)),
    "TRUTH_MODE_MISMATCH": ("truth", ("blocker",)),
    "PROMISE_UNFULFILLED": ("promise", ("blocker",)),
    "CAUSAL_CONTRADICTION": ("causality", ("blocker",)),
    "NARRATOR_DISCONTINUITY": ("narrator", ("blocker", "warning")),  # warning = simple réserve de clarté
    "ENDING_UNEARNED": ("ending", ("blocker",)),
    "ENDING_SUBSTITUTED": ("ending", ("blocker",)),
    "ENDING_REDUNDANT": ("ending", ("warning",)),
    "EXPOSITION_HEAVY": ("clarity", ("warning",)),
    "TRANSITION_WEAK": ("clarity", ("warning",)),
    "ORAL_DENSITY": ("clarity", ("warning",)),
    "REPETITION_LOCAL": ("pacing", ("warning",)),
    "HOOK_GENERIC": ("promise", ("warning",)),
    "HISTORY_SIMILARITY": ("originality", ("warning",)),
}
TWO_ANCHOR_CODES = {"CAUSAL_CONTRADICTION", "NARRATOR_DISCONTINUITY", "PROMISE_UNFULFILLED", "ENDING_SUBSTITUTED"}
ABSENCE_CODES = {"PROMISE_UNFULFILLED", "ENDING_SUBSTITUTED"}  # une absence alléguée exige d'avoir examiné TOUTES les unités parlées

# Codes d'erreur internes
INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
INVALID_RESPONSE = "INVALID_RESPONSE"
INVALID_ANCHOR = "INVALID_ANCHOR"
INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
STALE_REVIEW = "STALE_REVIEW"
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
TENANT_MISMATCH = "TENANT_MISMATCH"

# Bornes du pilote (jamais de troncature silencieuse : un dépassement est un refus)
MAX_TEXT_CHARS = 24_000
MAX_SOURCE_CHARS = 24_000
MAX_UNITS = 64
MAX_SOURCES = 12
MAX_HISTORY = 20
MAX_FINDINGS = 20
MAX_ANCHORS = 8
MAX_CLAIMS = 64
QUOTE_MAX = 300
TEXT_MAX = 600


class ReviewError(Exception):
    """Erreur du contrat. `code` est l'un des codes internes ci-dessus."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message
