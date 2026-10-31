"""Le prompt Standard de production (growthos-web, privé) n'est PAS stocké dans ce dépôt public, et ne peut pas y revenir sans casser un test.

Ce qui reste dans le dépôt : le manifeste (commit, empreintes des 5 sources, SHA-256 du rendu), des empreintes irréversibles de fenêtres du texte
(`standard_A_shingles.json`) et la procédure de reconstruction. Le texte est rendu à la demande, en mémoire, depuis un checkout de growthos-web.
Limite : ces tests protègent l'état actuel et les futurs commits ; ils ne retirent pas le texte de l'historique git déjà publié (commit da0ea7e).
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from growthos.engine.narrative_review.harness import pilot, policy
from growthos.engine.narrative_review.harness import rebuild_baseline as rb
from growthos.engine.narrative_review.harness.corpus import FIXTURES, sha256_text

PACKAGE = Path(rb.__file__).resolve().parents[1]          # growthos/engine/narrative_review
GROWTHOS = PACKAGE.parents[1]                              # growthos/
SCANNED_ROOTS = [PACKAGE, GROWTHOS / "docs"]               # le paquet (fixtures, tests, outils) et la documentation de la PR
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".zip", ".mp4", ".wav"}
STAND_IN = FIXTURES / "synthetic_standard_A.txt"

# Texte inventé (aucun rapport avec le prompt de production) pour éprouver le détecteur sans jamais manipuler le vrai texte.
PROBE = ("Un chat de gouttière attend chaque matin devant la boulangerie fermée ; un enfant lui laisse une miette, puis une autre, et le quartier "
         "finit par comprendre que l'animal ne réclame pas du pain mais de la compagnie, ce qui change la façon dont chacun passe devant la porte.")


def scanned_files():
    for root in SCANNED_ROOTS:
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() not in SKIP_SUFFIXES and "__pycache__" not in path.parts:
                    yield path


class TestProductionPromptIsNotStoredHere(unittest.TestCase):
    def setUp(self):
        self.shingles = rb.load_shingles()
        self.manifest = policy.load_manifest()

    def test_the_text_fixture_is_gone_and_the_manifest_says_so(self):
        self.assertEqual(list(FIXTURES.glob("standard_A_fr_*.txt")), [])
        std = self.manifest["standard"]
        self.assertNotIn("rendered_file", std)
        self.assertIs(std["stored_in_public_repo"], False)
        self.assertEqual(std["non_reintroduction"]["fingerprints_file"], rb.SHINGLES_FILE)
        self.assertIn("NOT stored", std["reproduction"])

    def test_no_scanned_file_contains_a_window_of_the_production_prompt(self):
        scanned, offenders = 0, []
        for path in scanned_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            scanned += 1
            if path.name == rb.SHINGLES_FILE:
                continue                                           # les empreintes elles-mêmes : hexadécimal uniquement (testé plus bas)
            if rb.contains_shingle(text, self.shingles):
                offenders.append(path.relative_to(GROWTHOS).as_posix())
        self.assertGreater(scanned, 40)                            # le balayage a réellement couvert le paquet et les docs
        self.assertEqual(offenders, [])

    SKIP_DIRS = {".git", ".worktrees", ".artifacts", "venv", ".venv", "node_modules", "__pycache__", "output", "dist", "build", ".mypy_cache", ".pytest_cache"}

    def scan_tree(self):
        """Balayage du SYSTÈME DE FICHIERS (jamais de `git ls-files`) : vaut dans un clone, un worktree, une copie d'archive hors dépôt ou dans un dépôt parent.
        Retourne (fichiers lus, fichiers contenant une fenêtre du prompt de production)."""
        hashes, offenders, scanned = rb.load_shingles(), [], set()
        for dirpath, dirnames, filenames in os.walk(GROWTHOS):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            for filename in filenames:
                path = Path(dirpath) / filename
                try:
                    if path.suffix.lower() in SKIP_SUFFIXES or path.stat().st_size > 1_500_000:
                        continue
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                rel = path.relative_to(GROWTHOS).as_posix()
                scanned.add(rel)
                if path.name != rb.SHINGLES_FILE and rb.contains_shingle(text, hashes):
                    offenders.append(rel)
        return scanned, offenders

    def test_no_file_anywhere_under_growthos_contains_a_window_of_the_production_prompt(self):
        """Ancien défaut de test (relevé par le contre-audit, copie d'archive) : le balayage listait `git ls-files` ; dans une archive placée DANS un autre dépôt, git ne voit aucun
        fichier (scanned = 0, échec) et hors de tout dépôt le test se sautait en silence. Ce n'était pas une régression du produit mais une hypothèse fausse du test. Il n'a plus
        aucune dépendance à git, ne peut plus être sauté, et exige un minimum de fichiers réellement lus."""
        scanned, offenders = self.scan_tree()
        self.assertGreater(len(scanned), 100, "the scan read too few files: it would prove nothing")
        self.assertEqual(offenders, [])

    def test_in_a_real_git_checkout_the_scan_covers_every_tracked_text_file(self):
        """Recoupement avec Git, exécuté dans un VRAI checkout : chaque fichier suivi (hors types binaires) est bien lu par le balayage du système de fichiers, et aucun n'est fautif.
        Hors dépôt git (archive), ce test est sauté de façon VISIBLE ; le balayage ci-dessus, lui, tourne toujours."""
        try:
            top = subprocess.run(["git", "-C", str(GROWTHOS), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True, timeout=60).stdout.strip()
            tracked = [f for f in subprocess.run(["git", "-C", str(GROWTHOS), "ls-files", "-z", "."], capture_output=True, text=True, check=True, timeout=60).stdout.split(chr(0)) if f]
        except (OSError, subprocess.SubprocessError):
            self.skipTest("not a git checkout (archive copy): the filesystem scan above still ran; run this test in a real checkout")
        if not tracked or Path(top).resolve() == Path("/").resolve():
            self.skipTest("git lists no tracked file under growthos/ (archive nested in another repository)")
        scanned, offenders = self.scan_tree()
        missing = []
        for rel in tracked:
            path = GROWTHOS / rel
            if any(part in self.SKIP_DIRS for part in Path(rel).parts) or path.suffix.lower() in SKIP_SUFFIXES or not path.is_file() or path.stat().st_size > 1_500_000:
                continue
            try:
                path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if rel not in scanned:
                missing.append(rel)
        self.assertEqual(missing, [], "tracked text files the filesystem scan did not read")
        self.assertEqual(offenders, [])
        self.assertGreater(len(tracked), 100)

    def test_the_scan_does_not_depend_on_git_and_works_in_an_archive_copy_outside_any_repository(self):
        """Reproduit la copie d'archive : arbre SANS .git, en dehors de tout dépôt. Le balayage doit lire les fichiers (pas zéro, pas de saut) et trouver une fenêtre réintroduite."""
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            copy_root = Path(tmp) / "growthos"
            shutil.copytree(GROWTHOS / "engine" / "narrative_review", copy_root / "engine" / "narrative_review", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(GROWTHOS / "docs", copy_root / "docs", ignore=shutil.ignore_patterns("__pycache__"))
            self.assertFalse((Path(tmp) / ".git").exists() or (copy_root / ".git").exists())
            seen = [p for p in copy_root.rglob("*") if p.is_file()]
            self.assertGreater(len(seen), 40)
            planted = "# réintroduit\n" + PROBE
            (copy_root / "docs" / "leak.md").write_text(planted, encoding="utf-8")
            probe_hashes = set(rb.shingle_hashes(PROBE))
            hits = [p.name for p in copy_root.rglob("*") if p.is_file() and p.suffix == ".md" and rb.contains_shingle(p.read_text(encoding="utf-8"), probe_hashes)]
            self.assertEqual(hits, ["leak.md"])

    def test_no_scanned_file_is_the_whole_prompt(self):
        whole = self.manifest["standard"]["rendered_sha256"]
        self.assertEqual([p.name for p in scanned_files() if p.suffix in (".txt", ".md", ".json") and sha256_text(p.read_text(encoding="utf-8", errors="ignore")) == whole], [])

    def test_the_stand_in_is_invented_labelled_and_shares_nothing_with_the_production_prompt(self):
        text = STAND_IN.read_text(encoding="utf-8")
        self.assertIn("SYNTHÉTIQUE", text)
        self.assertIn("PAS le prompt de production", text)
        self.assertFalse(rb.contains_shingle(text, self.shingles))
        for marker in (policy._STRUCTURE_START, policy._STRUCTURE_END.strip(), policy._JSON_TAIL, '{"blocks"'):   # assez pour exercer le diff A/B
            self.assertIn(marker, text)
        self.assertEqual(sha256_text(text) == self.manifest["standard"]["rendered_sha256"], False)

    def test_fingerprint_file_holds_only_irreversible_hashes_and_metadata(self):
        raw = json.loads((FIXTURES / rb.SHINGLES_FILE).read_text(encoding="utf-8"))
        self.assertEqual(set(raw), {"window", "stride", "normalization", "whole_sha256", "hashes"})
        self.assertEqual((raw["window"], raw["stride"]), (rb.SHINGLE_WINDOW, rb.SHINGLE_STRIDE))
        self.assertEqual(raw["whole_sha256"], self.manifest["standard"]["rendered_sha256"])
        self.assertGreater(len(raw["hashes"]), 400)
        self.assertEqual(raw["hashes"], sorted(set(raw["hashes"])))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", h) for h in raw["hashes"]))

    def test_the_manifest_never_embeds_prompt_text(self):
        blob = json.dumps(self.manifest, ensure_ascii=False)
        self.assertLess(len(blob), 12_000)                          # un manifeste, pas un prompt (le prompt fait environ 20 000 caractères)
        self.assertFalse(rb.contains_shingle(blob, self.shingles))


class TestTheDetectorActuallyDetects(unittest.TestCase):
    """Sans ces tests, un détecteur cassé laisserait le prompt revenir en silence."""

    def setUp(self):
        self.hashes = set(rb.shingle_hashes(PROBE))

    def test_it_finds_the_whole_text_a_fragment_a_reformatted_copy_and_embedding(self):
        self.assertTrue(rb.contains_shingle(PROBE, self.hashes))
        self.assertTrue(rb.contains_shingle("avant " + PROBE[30:200] + " après", self.hashes))                # fragment contigu >= 120 caractères
        self.assertTrue(rb.contains_shingle(PROBE.upper().replace(" ", "\n   "), self.hashes))                  # casse et espaces changés
        self.assertTrue(rb.contains_shingle(f'{{"note": "{PROBE}"}}', self.hashes))                             # inséré dans un JSON
        self.assertTrue(rb.contains_shingle(PROBE.replace("\n", " ") * 2, self.hashes))

    def test_it_does_not_flag_unrelated_text_or_short_fragments(self):
        self.assertFalse(rb.contains_shingle("Un tout autre texte, sans rapport avec la sonde, long de plus de quatre-vingts caractères pour le balayage.", self.hashes))
        self.assertFalse(rb.contains_shingle(PROBE[:70], self.hashes))     # < 80 caractères : sous la fenêtre, jamais signalé
        self.assertFalse(rb.contains_shingle("", self.hashes))

    def test_a_scanned_file_that_reintroduces_the_text_would_be_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            leak = Path(tmp) / "fixtures" / "copie.txt"
            leak.parent.mkdir()
            leak.write_text("# réintroduit\n" + PROBE, encoding="utf-8")
            self.assertTrue(rb.contains_shingle(leak.read_text(encoding="utf-8"), self.hashes))

    def test_the_hashes_do_not_reveal_the_text(self):
        for h in self.hashes:
            self.assertFalse(any(word in h for word in ("chat", "enfant")))
        self.assertTrue(all(len(h) == 64 for h in self.hashes))


class TestNoSilentFallback(unittest.TestCase):
    def test_without_a_checkout_the_production_baseline_is_unavailable_not_synthetic(self):
        previous = os.environ.pop(policy.WEB_CHECKOUT_ENV, None)
        try:
            with self.assertRaises(policy.BaselineUnavailable) as ctx:
                policy.standard_baseline()
            self.assertIn(policy.WEB_CHECKOUT_ENV, str(ctx.exception))
            with self.assertRaises(policy.BaselineUnavailable):
                pilot.rehearse(Path(tempfile.mkdtemp()))            # pas de repli silencieux vers le prompt synthétique
            with self.assertRaises(SystemExit):
                pilot.main(["--out", tempfile.mkdtemp()])
        finally:
            if previous is not None:
                os.environ[policy.WEB_CHECKOUT_ENV] = previous

    def test_a_wrong_or_modified_checkout_is_refused(self):
        previous = os.environ.get(policy.WEB_CHECKOUT_ENV)
        with tempfile.TemporaryDirectory() as tmp:
            os.environ[policy.WEB_CHECKOUT_ENV] = tmp               # dossier vide : sources absentes
            try:
                with self.assertRaises(policy.BaselineError):
                    policy.standard_baseline()
            finally:
                if previous is None:
                    os.environ.pop(policy.WEB_CHECKOUT_ENV, None)
                else:
                    os.environ[policy.WEB_CHECKOUT_ENV] = previous

    def test_the_synthetic_rehearsal_is_labelled_in_the_audit_dossier(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pilot.rehearse(Path(tmp), synthetic_baseline=True)
            manifest = json.loads((Path(tmp) / "campaign_manifest.json").read_text(encoding="utf-8"))
            inputs = [json.loads(p.read_text(encoding="utf-8")) for p in (Path(tmp) / "inputs").glob("B*.json")]
        self.assertEqual(manifest["baseline_kinds"]["standard"], "synthetic_test_stand_in")
        self.assertEqual(out["summary"]["baseline_kinds"]["standard"], "synthetic_test_stand_in")
        self.assertEqual({i["baseline_kind"] for i in inputs}, {"synthetic_test_stand_in"})
        self.assertEqual({i["baseline_commit"] for i in inputs}, {policy.SYNTHETIC_LABEL})
        self.assertTrue(all(i["system_stored"] and i["system"] for i in inputs))      # le substitut synthétique, lui, est archivé en clair


@unittest.skipUnless(os.environ.get("GROWTHOS_WEB_CHECKOUT"), "GROWTHOS_WEB_CHECKOUT not set: production rebuild not exercised (private repo)")
class TestProductionRebuildFromThePrivateRepository(unittest.TestCase):
    def test_the_prompt_is_rendered_in_memory_matches_the_manifest_and_nothing_is_written(self):
        before = sorted(p.name for p in FIXTURES.iterdir())
        text, kind = policy.standard_baseline()
        self.assertEqual(kind, policy.PRODUCTION_KIND)
        self.assertEqual(sha256_text(text), policy.load_manifest()["standard"]["rendered_sha256"])
        self.assertEqual(rb.shingle_hashes(text), json.loads((FIXTURES / rb.SHINGLES_FILE).read_text(encoding="utf-8"))["hashes"])
        self.assertTrue(rb.contains_shingle(text, rb.load_shingles()))    # le détecteur reconnaît bien le vrai texte (preuve de sensibilité)
        self.assertEqual(sorted(p.name for p in FIXTURES.iterdir()), before)

    def test_a_production_campaign_dossier_never_contains_the_production_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pilot.rehearse(Path(tmp))                           # baseline de production, rendue depuis le checkout
            self.assertEqual(out["summary"]["baseline_kinds"]["standard"], policy.PRODUCTION_KIND)
            hashes = rb.load_shingles()
            files = [p for p in Path(tmp).rglob("*") if p.is_file()]
            self.assertGreater(len(files), 20)
            for path in files:                                        # aucun fichier du dossier (entrées, manifeste, journal) ne contient le texte
                self.assertFalse(rb.contains_shingle(path.read_text(encoding="utf-8"), hashes), path.name)
            for path in (Path(tmp) / "inputs").glob("B*.json"):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual((data["system"], data["system_stored"]), (None, False))
                self.assertRegex(data["system_sha256"], r"^[0-9a-f]{64}$")
            manifest = json.loads((Path(tmp) / "campaign_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["baseline_kinds"]["standard"], policy.PRODUCTION_KIND)

    def test_a_manifest_with_a_different_hash_is_refused(self):
        bad = copy.deepcopy(policy.load_manifest())
        bad["standard"]["rendered_sha256"] = "0" * 64
        with self.assertRaises(policy.BaselineError):
            policy.standard_baseline(bad)

if __name__ == "__main__":
    unittest.main()
