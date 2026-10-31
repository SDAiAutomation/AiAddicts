"""Comptage de jetons d'entrée AVANT envoi : une ESTIMATION, jamais un majorant garanti.

Le tokenizer exact dépend du MODÈLE CHOISI par le propriétaire, qui ne l'est pas encore. Ce module fournit :
- l'interface `TokenCounter` et l'heuristique `char-heuristic-2cpt` (1 jeton pour 2 caractères, NON exacte, NON démontrée, NON validée) ;
- `register()` pour le tokenizer du modèle ; un identifiant sans compteur enregistré lève `TokenizerRequired` (aucun repli silencieux) ;
- la VALIDATION : un compteur n'est admis pour un appel réel que s'il a été validé sur des échantillons de consommation RÉELLE renvoyée par le fournisseur
  (`validate_counter` -> `ValidationRecord`, produit lors d'une calibration séparée et autorisée) et si l'empreinte de cet enregistrement figure dans l'autorisation.
  Sans enregistrement valide : aucun appel.
Même validé, un compteur reste une estimation : la consommation réelle n'est connue que dans la réponse. Un dépassement de la réservation ou du compteur arrête la campagne.
Aucun tokenizer n'est téléchargé (aucune dépendance, aucun accès réseau).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import platform
import sys
import types
from dataclasses import dataclass
from typing import Callable, Protocol

from .. import contract as c

HEURISTIC_ID = "char-heuristic-2cpt"
CHAT_OVERHEAD_TOKENS = 16   # enveloppe de messages (rôles, séparateurs) : marge forfaitaire, à calibrer sur le modèle choisi
MIN_VALIDATION_SAMPLES = 20


class TokenCounter(Protocol):
    id: str
    exact: bool

    def count(self, text: str) -> int: ...


class CharHeuristic:
    """ESTIMATION : 1 jeton pour 2 caractères. Ce n'est pas un majorant : elle peut sous-estimer (texte non latin, code, nombres, emoji)."""
    id, exact = HEURISTIC_ID, False

    def count(self, text: str) -> int:
        return -(-len(text) // 2)


class TokenizerRequired(c.ReviewError):
    def __init__(self, tokenizer_id: str):
        super().__init__(c.BUDGET_EXHAUSTED, f"no token counter registered for {tokenizer_id!r}: register the chosen model's tokenizer; the heuristic {HEURISTIC_ID!r} is an estimate and must be validated")


class TokenizerNotValidated(c.ReviewError):
    def __init__(self, why: str):
        super().__init__(c.BUDGET_EXHAUSTED, f"tokenizer not validated for this model: {why}; no call")


_registry: dict[str, Callable[[], TokenCounter]] = {HEURISTIC_ID: CharHeuristic}


def register(counter_factory: Callable[[], TokenCounter]) -> None:
    counter = counter_factory()
    if not isinstance(counter.id, str) or not counter.id or (counter.id == HEURISTIC_ID and not isinstance(counter, CharHeuristic)):
        raise ValueError("a token counter needs its own non-empty id")
    _registry[counter.id] = counter_factory


def resolve(tokenizer_id: str) -> TokenCounter:
    try:
        return _registry[tokenizer_id]()
    except KeyError as exc:
        raise TokenizerRequired(tokenizer_id) from exc


def factory_for(tokenizer_id: str) -> Callable[[], TokenCounter]:
    """La fabrique enregistrée MAINTENANT sous cet identifiant (l'objet lui-même, pour comparer son identité plus tard)."""
    try:
        return _registry[tokenizer_id]
    except KeyError as exc:
        raise TokenizerRequired(tokenizer_id) from exc


MAX_DEPTH = 4                      # profondeur de suivi des fonctions appelées depuis `count`
_SIMPLE = (int, float, str, bytes, bool, type(None))


def runtime_identity() -> str:
    """Empreinte de l'ENVIRONNEMENT d'exécution : version et implémentation de Python, plateforme. Une validation de tokenizer n'a de sens que dans l'environnement où elle a été faite."""
    data = {"version": sys.version, "implementation": platform.python_implementation(), "machine": platform.machine(), "system": platform.system()}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def _code_digest(code) -> list:
    consts = [_code_digest(k) if isinstance(k, types.CodeType) else repr(k) for k in code.co_consts]
    return [code.co_code.hex(), consts, list(code.co_names), list(code.co_varnames), list(code.co_freevars)]


def _file_sha(module) -> str | None:
    path = getattr(module, "__file__", None)
    try:
        if path and os.path.getsize(path) <= 5_000_000:
            return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError:
        pass
    return None


def _names_of(code) -> set:
    names = set(code.co_names)
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            names |= _names_of(const)
    return names


def _walk(fn, out: dict, seen: set, depth: int, object_ids: bool) -> None:
    """Enregistre la fonction et tout ce qu'elle atteint dans ses globales : fonctions (suivies), constantes simples, modules (version, fichier, attributs utilisés), classes."""
    if id(fn) in seen or depth > MAX_DEPTH:
        return
    seen.add(id(fn))
    code = getattr(fn, "__code__", None)
    if code is None:
        return
    key = f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', '?')}"
    out[key] = {"code": _code_digest(code), "defaults": repr(getattr(fn, "__defaults__", None)), "kwdefaults": repr(getattr(fn, "__kwdefaults__", None)),
                "closure": [repr(cell.cell_contents) if isinstance(cell.cell_contents, _SIMPLE) else type(cell.cell_contents).__qualname__ for cell in (fn.__closure__ or ())]}
    if object_ids:
        out[key]["id"] = id(fn)
    glob = getattr(fn, "__globals__", {})
    for name in sorted(_names_of(code)):
        if name not in glob:
            continue
        obj = glob[name]
        entry: dict = {"type": type(obj).__qualname__}
        if isinstance(obj, _SIMPLE):
            entry["value"] = repr(obj)
        elif isinstance(obj, types.ModuleType):
            entry.update(version=str(getattr(obj, "__version__", "")), file=_file_sha(obj))
            for attr in sorted(_names_of(code)):
                member = getattr(obj, attr, None)
                if isinstance(member, types.FunctionType):
                    _walk(member, out, seen, depth + 1, object_ids)
                elif isinstance(member, _SIMPLE) and attr not in glob:
                    entry.setdefault("members", {})[attr] = repr(member)
        elif isinstance(obj, types.FunctionType):
            _walk(obj, out, seen, depth + 1, object_ids)
        elif isinstance(obj, type):
            entry["qualname"] = f"{obj.__module__}.{obj.__qualname__}"
        if object_ids:
            entry["id"] = id(obj)
        out[f"{key}::global::{name}"] = entry


def identity(counter: TokenCounter, *, object_ids: bool = False) -> str:
    """Empreinte d'IDENTITÉ du composant de comptage : classe, `id`, `exact`, `version` déclarée, état d'instance, et pour `count` : code octet, constantes, valeurs par défaut,
    PLUS tout ce qu'il atteint (fonctions globales suivies sur %d niveaux, constantes de module, modules importés avec leur version et l'empreinte de leur fichier).

    Deux niveaux : `object_ids=False` est DÉTERMINISTE d'un processus à l'autre (c'est elle qui lie l'enregistrement de validation) ; `object_ids=True` ajoute l'identité des objets
    du processus courant (épingle d'exécution : un objet remplacé par un autre, même identique, est détecté).
    LIMITES : une empreinte Python n'est PAS une garantie d'intégrité. Elle ne voit pas le code natif, les attributs de classes tierces, ni un code hostile du même processus qui altérerait
    cette fonction elle-même. Elle réduit le risque de remplacement accidentel ou simple ; le vrai cloisonnement est un environnement d'exécution contrôlé (autre processus ou autre compte).""" % MAX_DEPTH
    cls, method = type(counter), getattr(type(counter), "count", None)
    reach: dict = {}
    if isinstance(method, types.FunctionType):
        _walk(method, reach, set(), 0, object_ids)
    data = {"module": cls.__module__, "qualname": cls.__qualname__, "id": getattr(counter, "id", None), "exact": getattr(counter, "exact", None),
            "version": getattr(counter, "version", None), "state": repr(sorted(vars(counter).items())) if hasattr(counter, "__dict__") else "", "reach": reach}
    if object_ids:
        data["type_id"] = id(cls)
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), default=repr).encode("utf-8")).hexdigest()


def estimate_input_tokens(counter: TokenCounter, system: str, user: str, *, safety: float = 1.10) -> int:
    """ESTIMATION des jetons d'entrée d'un appel de chat : mesure du compteur + enveloppe, x marge ; jamais inférieure à l'heuristique par caractères pour un compteur non exact."""
    if not (math.isfinite(safety) and safety >= 1.0):
        raise ValueError("safety must be finite and >= 1")
    measured = math.ceil((counter.count(system) + counter.count(user) + CHAT_OVERHEAD_TOKENS) * safety)
    floor = CharHeuristic().count(system) + CharHeuristic().count(user) if not counter.exact else 0
    return max(measured, floor)


def underestimated(estimate: int, reported_input_tokens: int | None) -> bool:
    """Vrai si le fournisseur a facturé PLUS d'entrée que l'estimation. Inconnu (None) n'est pas « correct » : à traiter à part (usage inconnu = arrêt)."""
    return reported_input_tokens is not None and reported_input_tokens > estimate


@dataclass(frozen=True)
class ValidationRecord:
    tokenizer_id: str
    model: str
    samples: int
    max_reported_over_estimate: float     # <= 1 : sur tous les échantillons, l'estimation couvrait la consommation réelle
    safety: float
    ok: bool
    sha256: str
    impl_sha256: str = ""                 # empreinte d'identité du compteur VALIDÉ (`identity`) : la validation ne vaut que pour cette implémentation
    runtime_sha256: str = ""              # empreinte de l'environnement d'exécution où la validation a eu lieu (`runtime_identity`)
    version: str = ""                     # version déclarée du tokenizer validé


def validate_counter(counter: TokenCounter, model: str, samples: list[tuple[str, str, int]], *, safety: float = 1.10) -> ValidationRecord:
    """Compare l'estimation du compteur à la consommation RÉELLE d'entrée renvoyée par le fournisseur pour `samples` = [(système, utilisateur, jetons d'entrée facturés)].

    Fonction pure : elle ne fait aucun appel. Les échantillons viennent d'une calibration séparée et autorisée (non faite). `ok` exige au moins
    `MIN_VALIDATION_SAMPLES` échantillons, tous valides, et que l'estimation couvre la consommation réelle sur CHACUN d'eux."""
    worst, valid = 0.0, True
    for system, user, reported in samples:
        if not (isinstance(reported, int) and not isinstance(reported, bool) and reported > 0 and isinstance(system, str) and isinstance(user, str)):
            valid = False
            continue
        worst = max(worst, reported / estimate_input_tokens(counter, system, user, safety=safety))
    ok = valid and len(samples) >= MIN_VALIDATION_SAMPLES and worst <= 1.0
    impl, runtime, version = identity(counter), runtime_identity(), str(getattr(counter, "version", "") or "")
    canonical = json.dumps({"tokenizer_id": counter.id, "model": model, "samples": len(samples), "worst": round(worst, 9), "safety": safety, "ok": ok, "impl": impl,
                            "runtime": runtime, "version": version}, sort_keys=True, separators=(",", ":"))
    return ValidationRecord(counter.id, model, len(samples), worst, safety, ok, hashlib.sha256(canonical.encode("utf-8")).hexdigest(), impl, runtime, version)


def require_validated(record: ValidationRecord | None, *, model: str, tokenizer_id: str, expected_sha256: str, counter: TokenCounter | None = None) -> None:
    """Refus (aucun appel) sans enregistrement de validation valide, du bon modèle et du bon tokenizer, dont l'empreinte est celle approuvée dans l'autorisation,
    ET (si `counter` est fourni) validé pour CETTE implémentation : l'identité du compteur résolu doit être celle qui a été validée."""
    if record is None:
        raise TokenizerNotValidated("no validation record was provided")
    if not record.ok:
        raise TokenizerNotValidated(f"the validation record is not ok ({record.samples} samples, worst reported/estimate ratio {record.max_reported_over_estimate:.3f})")
    if (record.model, record.tokenizer_id) != (model, tokenizer_id):
        raise TokenizerNotValidated("the validation record is for another model or tokenizer")
    if record.sha256 != expected_sha256:
        raise TokenizerNotValidated("the validation record is not the one approved in the authorization")
    if counter is not None and (not record.impl_sha256 or record.impl_sha256 != identity(counter)):
        raise TokenizerNotValidated("the token counter is not the implementation that was validated (identity differs)")
    if counter is not None and (not record.runtime_sha256 or record.runtime_sha256 != runtime_identity()):
        raise TokenizerNotValidated("the runtime environment is not the one the tokenizer was validated in (Python version or platform differs)")
