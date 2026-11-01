"""Estimation et plafonnement du coût d'un épisode. Les tarifs viennent de l'ENVIRONNEMENT (comme `assembler`), jamais
codés en dur : si un poste n'a pas de tarif configuré, il est marqué `unpriced` et le budget échoue FERMÉ (aucune
génération payante n'est autorisée sur un coût inconnu). Estimation ≠ facture : les coûts réels sont enregistrés par
`BudgetTracker` à partir de l'usage renvoyé par le fournisseur.

Variables (toutes optionnelles) :
  STORY_IMAGE_USD_EACH            coût mesuré d'une image (prioritaire)
  IMAGE_PRICE_IMAGE_OUT_PER_M     + STORY_IMAGE_OUTPUT_TOKENS (jetons de sortie d'une image) -> coût via le routeur existant
  ELEVENLABS_USD_PER_1K_CHARS     voix
  SCRIPT_PRICE_IN_PER_M / SCRIPT_PRICE_OUT_PER_M, STORY_PLAN_TOKENS_IN / _OUT   écriture du plan
  STORY_RENDER_USD, STORY_STORAGE_USD   rendu / stockage (0 si l'exécuteur est déjà payé)
  STORY_BUDGET_USD (défaut 2.00), STORY_BUDGET_PREFERRED_USD (défaut 1.50)
"""
from __future__ import annotations

import math
import os
import threading
from dataclasses import dataclass, field


DEFAULT_BUDGET_USD = 2.00
PREFERRED_BUDGET_USD = 1.50


def _float(env: dict, name: str) -> float | None:
    raw = (env.get(name) or "").strip()
    try:
        value = float(raw) if raw else None
    except ValueError:
        return None
    return value if value is not None and math.isfinite(value) and value >= 0 else None


def image_unit_cost(env: dict | None = None, purpose: str = "final") -> tuple[float | None, str]:
    """(coût d'une image, source) ; (None, 'unpriced') si rien n'est configuré — jamais 0 par défaut."""
    env = os.environ if env is None else env
    fixed = _float(env, "STORY_IMAGE_USD_EACH")
    if fixed is not None and purpose == "final":
        return fixed, "STORY_IMAGE_USD_EACH"
    tokens = _float(env, "STORY_IMAGE_OUTPUT_TOKENS")
    price = _float(env, "IMAGE_PRICE_IMAGE_OUT_PER_M")
    if tokens and price is not None:
        return tokens * price / 1_000_000, "IMAGE_PRICE_IMAGE_OUT_PER_M x STORY_IMAGE_OUTPUT_TOKENS"
    return None, "unpriced"


@dataclass
class Budget:
    max_usd: float = DEFAULT_BUDGET_USD
    preferred_usd: float = PREFERRED_BUDGET_USD

    def __post_init__(self):
        for value in (self.max_usd, self.preferred_usd):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("budget amounts must be finite and non-negative")
        self.preferred_usd = min(self.preferred_usd, self.max_usd)  # la cible ne dépasse jamais le plafond

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Budget":
        """`STORY_BUDGET_USD=0` est un budget de 0 $ (dépense coupée), pas « valeur par défaut »."""
        env = os.environ if env is None else env
        cap, target = _float(env, "STORY_BUDGET_USD"), _float(env, "STORY_BUDGET_PREFERRED_USD")
        cap = DEFAULT_BUDGET_USD if cap is None else cap
        return cls(cap, PREFERRED_BUDGET_USD if target is None else target)


class BudgetExceeded(RuntimeError):
    pass


def _line(label: str, quantity: float, unit: float | None, source: str) -> dict:
    return {"item": label, "quantity": quantity, "unit_usd": unit, "usd": None if unit is None else round(quantity * unit, 4),
            "source": source}


def estimate_episode(plan: dict, env: dict | None = None, *, edits_per_episode: int = 0, regenerations: int = 0) -> dict:
    """Ventilation par poste. `regenerations` = images régénérées prévues (marge de reprise)."""
    env = os.environ if env is None else env
    scenes = plan["scenes"]
    image_unit, image_source = image_unit_cost(env)
    edit_unit, edit_source = image_unit_cost(env, "edit") if _float(env, "STORY_IMAGE_USD_EACH") is None else (image_unit, image_source)
    chars = sum(len(s["narration"].strip()) for s in scenes)
    voice_rate = _float(env, "ELEVENLABS_USD_PER_1K_CHARS")
    p_in, p_out = _float(env, "SCRIPT_PRICE_IN_PER_M"), _float(env, "SCRIPT_PRICE_OUT_PER_M")
    t_in, t_out = _float(env, "STORY_PLAN_TOKENS_IN"), _float(env, "STORY_PLAN_TOKENS_OUT")
    script_usd = None if None in (p_in, p_out, t_in, t_out) else (t_in * p_in + t_out * p_out) / 1_000_000
    render, storage = _float(env, "STORY_RENDER_USD"), _float(env, "STORY_STORAGE_USD")
    n_images = len(scenes)  # une image par scène (le prompt final dépend aussi de la direction visuelle et des personnages)
    lines = [
        {"item": "script", "quantity": 1, "unit_usd": script_usd, "usd": None if script_usd is None else round(script_usd, 4),
         "source": "SCRIPT_PRICE_* x STORY_PLAN_TOKENS_*" if script_usd is not None else "unpriced"},
        {"item": "research", "quantity": 0, "unit_usd": 0.0, "usd": 0.0, "source": "no paid research in this engine (sources are supplied)"},
        _line("images", n_images + regenerations, image_unit, image_source),
        _line("image_edits", edits_per_episode, edit_unit, edit_source),
        _line("voice_1k_chars", chars / 1000, voice_rate, "ELEVENLABS_USD_PER_1K_CHARS" if voice_rate is not None else "unpriced"),
        _line("render", 1, render, "STORY_RENDER_USD" if render is not None else "unpriced"),
        _line("storage", 1, storage, "STORY_STORAGE_USD" if storage is not None else "unpriced"),
    ]
    unpriced = [l["item"] for l in lines if l["usd"] is None and l["quantity"]]
    return {"estimated": True, "lines": lines, "unpriced": unpriced,
            # somme des seuls postes chiffrés : un total « incomplet » (complete False) ne doit jamais être affiché comme un coût
            "total_usd": round(sum(l["usd"] or 0.0 for l in lines), 4), "complete": not unpriced, "scenes": len(scenes),
            "voice_characters": chars, "images": n_images}


def check_budget(estimate: dict, budget: Budget) -> dict:
    """Décision explicite : 'ok' | 'over_preferred' | 'over_budget' | 'unpriced'. Échoue fermé sur coût inconnu."""
    total = estimate["total_usd"]
    if estimate["unpriced"]:
        status = "unpriced"
    elif total > budget.max_usd:
        status = "over_budget"
    elif total > budget.preferred_usd:
        status = "over_preferred"
    else:
        status = "ok"
    return {"status": status, "allowed": status in ("ok", "over_preferred"), "total_usd": total,
            "max_usd": budget.max_usd, "preferred_usd": budget.preferred_usd,
            "compromises": suggest_compromises(estimate, budget) if status in ("over_budget", "over_preferred") else [],
            "message": _message(status, estimate, budget)}


def _message(status: str, estimate: dict, budget: Budget) -> str:
    if status == "unpriced":
        return "Cost unknown for: " + ", ".join(estimate["unpriced"]) + ". Configure the rates before any paid generation."
    if status == "over_budget":
        return f"Estimated ${estimate['total_usd']:.2f} exceeds the ${budget.max_usd:.2f} budget."
    if status == "over_preferred":
        return f"Estimated ${estimate['total_usd']:.2f} is within budget but above the ${budget.preferred_usd:.2f} target."
    return f"Estimated ${estimate['total_usd']:.2f}, within the ${budget.preferred_usd:.2f} target."


def suggest_compromises(estimate: dict, budget: Budget) -> list[str]:
    by_item = {l["item"]: l for l in estimate["lines"]}
    out = []
    images = by_item["images"]
    if images["unit_usd"]:
        over = estimate["total_usd"] - budget.max_usd
        out.append(f"Reuse or merge scenes: each image saved lowers the cost by ${images['unit_usd']:.3f} "
                   f"({max(0, int(over / images['unit_usd']) + 1)} fewer images to meet the budget).")
        out.append("Use the lower image quality for scenes without a character.")
    out.append("Shorten the narration (voice is billed per character).")
    out.append("Reduce the target duration (fewer scenes).")
    return out


# nature d'un montant enregistré : jamais confondre mesuré, estimé et non chiffré
MEASURED, ESTIMATED, UNPRICED, CACHED = "measured", "estimated", "unpriced", "cache"


@dataclass
class BudgetTracker:
    """Dépense d'un épisode. `reserve` POSE UNE RETENUE (atomique) : le plafond est vérifié contre dépense + retenues en cours,
    donc deux appels concurrents ne passent pas ensemble sous le plafond. `record` solde la retenue ; `release` l'annule.
    Chaque montant porte sa nature : `measured` (usage réel x tarif configuré), `estimated`, `unpriced` (appel fait, coût
    inconnu : 0 $ comptabilisé mais signalé), `cache` (réutilisé, 0 $)."""
    budget: Budget
    spent: dict = field(default_factory=dict)
    kinds: dict = field(default_factory=dict)
    holds: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def total(self) -> float:
        return round(sum(self.spent.values()), 6)

    @property
    def committed(self) -> float:
        return round(self.total + sum(self.holds.values()), 6)

    def total_by_kind(self) -> dict:
        out: dict = {}
        for item, usd in self.spent.items():
            kind = self.kinds.get(item, MEASURED)
            out[kind] = round(out.get(kind, 0.0) + usd, 6)
        return out

    @property
    def has_unpriced(self) -> bool:
        return UNPRICED in self.kinds.values()

    def seed(self, item: str, usd: float | None, kind: str) -> None:
        """Reprend une dépense déjà faite (lue dans un manifeste) : idempotent, un item n'est jamais compté deux fois."""
        with self._lock:
            if item not in self.spent:
                self.spent[item] = round(max(0.0, usd or 0.0), 6)
                self.kinds[item] = UNPRICED if usd is None and kind != CACHED else kind

    def reserve(self, item: str, expected_usd: float | None) -> None:
        if (expected_usd is None or isinstance(expected_usd, bool) or not isinstance(expected_usd, (int, float))
                or not math.isfinite(expected_usd) or expected_usd < 0):
            raise BudgetExceeded(f"{item}: cost unknown or invalid, refusing a paid call")
        with self._lock:
            held = sum(v for k, v in self.holds.items() if k != item)
            if self.total + held + expected_usd > self.budget.max_usd + 1e-9:
                raise BudgetExceeded(f"{item}: ${self.total + held + expected_usd:.2f} would exceed the ${self.budget.max_usd:.2f} budget")
            self.holds[item] = float(expected_usd)

    def release(self, item: str) -> None:
        with self._lock:
            self.holds.pop(item, None)

    def record(self, item: str, actual_usd: float | None, kind: str = MEASURED) -> None:
        """`actual_usd=None` : l'appel a eu lieu mais son coût est inconnu -> 0 $ comptabilisé, nature `unpriced`.
        Un coût réel supérieur à la retenue est enregistré tel quel : le `reserve` suivant refusera (plafond dépassé)."""
        if actual_usd is None or not math.isfinite(actual_usd):
            actual_usd, kind = 0.0, UNPRICED
        with self._lock:
            self.holds.pop(item, None)
            self.spent[item] = round(self.spent.get(item, 0.0) + max(0.0, actual_usd), 6)
            self.kinds[item] = kind
