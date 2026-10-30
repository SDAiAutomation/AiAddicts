"""Fournisseurs FACTICES déterministes pour la simulation hors ligne. Ils ne jugent rien : aucune conclusion éditoriale n'en sort.

Le critique factice lit le MÊME prompt que lirait un vrai critique (il ne voit ni la condition ni le sujet numéroté) et renvoie
une couverture complète sans défaut : il sert à exercer le harness, pas à mesurer la qualité d'une politique.
"""
from __future__ import annotations

import json

from ..providers import ProviderResult

_TAIL = "Données :\n"


def simulated_generator(*, usage=None, fail_on=None, no_output_on=None, invalid_json_on=None):
    """Retourne un fournisseur. `fail_on`/`no_output_on`/`invalid_json_on` : ensembles de (stratum, nombre d'appel) à faire échouer."""
    calls = {"n": 0}

    def provider(request: dict) -> ProviderResult:
        calls["n"] += 1
        n = calls["n"]
        provider.requests.append(request)
        if fail_on and n in fail_on:
            raise TimeoutError("simulated timeout")
        if no_output_on and n in no_output_on:
            return ProviderResult(text=None, usage=usage or {"input": 900, "output": 50}, error="simulated empty output")
        if invalid_json_on and n in invalid_json_on:
            return ProviderResult(text='{"blocks": [', usage=usage or {"input": 900, "output": 40}, latency_s=1.0)
        user = request["user"]
        topic = user.split("\n", 1)[0].removeprefix("Sujet : ")
        standard = '{"blocks"' in request["system"]  # le prompt Standard décrit la forme {"blocks": [...]}
        if standard:
            blocks = [{"role": "hook", "text": f"{topic[:40]} : pourquoi ?"}] + [
                {"role": "point", "text": f"Étape {i} de la démonstration simulée."} for i in range(1, 5)]
            payload = {"title": topic, "blocks": blocks}
        else:
            beats = ("hook", "setup", "conflict", "development", "revelation", "resolution")
            payload = {"title": topic, "factuality": "fiction", "scenes": [
                {"id": f"s{i + 1}", "beat": b, "narration": f"Scène simulée {i + 1}."} for i, b in enumerate(beats)]}
        return ProviderResult(text=json.dumps(payload, ensure_ascii=False), usage=usage or {"input": 2000, "output": 600}, latency_s=2.0)
    provider.requests = []
    return provider


def simulated_critic(*, usage=None, fail_on=None, invalid_on=None):
    calls = {"n": 0}

    def provider(request: dict) -> ProviderResult:
        calls["n"] += 1
        provider.requests.append(request)
        if fail_on and calls["n"] in fail_on:
            raise TimeoutError("simulated timeout")
        if invalid_on and calls["n"] in invalid_on:
            return ProviderResult(text="not json", usage=usage or {"input": 1500, "output": 20}, latency_s=1.0)
        data = json.loads(request["prompt"].split(_TAIL, 1)[1])
        ids = [u["unit_id"] for u in data["units"]]
        coverage = [{"dimension": d, "status": "evaluated", "reason": "simulated coverage", "inspected_unit_ids": ids}
                    for d in data["required_dimensions"]]
        body = {"schema_version": "narrative-review:0.1", "coverage": coverage, "claims": [], "findings": []}
        return ProviderResult(text=json.dumps(body), usage=usage or {"input": 1500, "output": 400}, latency_s=1.5)
    provider.requests = []
    return provider
