"""Mission 2 (3e audit Codex) : la baseline A ne dépend d'aucun chemin local ou temporaire et se reconstruit depuis des sources figées.

La vérification complète exige l'accès aux deux dépôts (growthos-web est privé : ses sources ne sont pas copiées ici). Elle s'exécute si
GROWTHOS_WEB_CHECKOUT (commit figé) et/ou GROWTHOS_ENGINE_CHECKOUT (commit figé de la PR #103) sont définis, sinon elle est SAUTÉE avec un message
explicite : un test sauté n'est jamais une preuve. La preuve exécutée est consignée dans le rapport de préparation.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from growthos.engine.narrative_review.harness import rebuild_baseline as rb
from growthos.engine.narrative_review.harness.corpus import FIXTURES, sha256_text
from growthos.engine.narrative_review.harness.policy import frozen_visual_A, load_manifest

LOCAL_PATH = re.compile(r"[A-Za-z]:[\\/]+(?:Users|Windows|Temp)|/Users/|/home/|AppData|scratchpad|\\Temp\\|/tmp/|\.claude[\\/]|node_modules", re.I)


class TestNoLocalPathsInFixtures(unittest.TestCase):
    def test_no_fixture_or_tool_mentions_a_local_or_temporary_path(self):
        harness = Path(rb.__file__).parent
        files = [p for p in list(FIXTURES.iterdir()) + list(harness.glob("*.py")) if p.suffix in (".txt", ".json", ".csv", ".mjs", ".js", ".py")]
        self.assertGreater(len(files), 8)
        offenders = []
        for path in files:
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if LOCAL_PATH.search(line) and path.name != "rebuild_baseline.py":
                    offenders.append(f"{path.name}:{n}: {line.strip()[:90]}")
        self.assertEqual(offenders, [])
        self.assertFalse((FIXTURES / "render_standard_A.js").exists())     # l'ancien script dépendait d'un node_modules et d'un fichier temporaires

    def test_manifest_pins_commits_hashes_and_tooling(self):
        m = load_manifest()
        self.assertEqual(m["version"], "narrative-baseline-manifest:0.2")
        self.assertEqual(len(m["standard"]["source_files_sha256"]), 5)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", h) for h in m["standard"]["source_files_sha256"].values()))
        self.assertEqual(m["standard"]["source_commit"], "c61480d6")
        self.assertRegex(m["story_visual"]["source_commit"], r"^57af0ae[0-9a-f]{33}$")
        self.assertEqual(m["tooling"]["render_script_sha256"], rb.file_sha256(FIXTURES / rb.RENDER_SCRIPT))
        self.assertNotIn("rendered_file", m["standard"])       # le texte de production n'est pas stocké dans ce dépôt public
        self.assertFalse(m["standard"]["stored_in_public_repo"])
        self.assertEqual(len(frozen_visual_A("N01", m)["prompt"]) > 1000, True)

    def test_the_render_script_only_takes_its_checkout_as_input(self):
        text = (FIXTURES / rb.RENDER_SCRIPT).read_text(encoding="utf-8")
        self.assertIn("--checkout", text)
        self.assertNotRegex(text, r"https?://")                    # aucun accès réseau
        self.assertNotIn("process.env", text)                      # aucune dépendance à l'environnement
        self.assertIn("stripTypeScriptTypes", text)                # aucune dépendance npm


class TestVerificationDetectsDrift(unittest.TestCase):
    def test_a_modified_or_missing_source_file_is_reported(self):
        manifest = load_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            problems = rb.check_sources(root, manifest["standard"]["source_files_sha256"], "web")
            self.assertEqual(len(problems), 5)                      # tout manque
            for rel in manifest["standard"]["source_files_sha256"]:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("contenu modifié", encoding="utf-8")
            problems = rb.check_sources(root, manifest["standard"]["source_files_sha256"], "web")
            self.assertEqual(len(problems), 5)
            self.assertTrue(all("differs" in p for p in problems))

    def test_line_endings_do_not_change_the_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            lf, crlf = Path(tmp) / "a.ts", Path(tmp) / "b.ts"
            lf.write_bytes("ligne 1\nligne é\n".encode("utf-8"))
            crlf.write_bytes("ligne 1\r\nligne é\r\n".encode("utf-8"))
            self.assertEqual(rb.file_sha256(lf), rb.file_sha256(crlf))

    def test_a_changed_render_script_hash_is_reported_without_any_checkout(self):
        manifest = copy.deepcopy(load_manifest())
        manifest["tooling"]["render_script_sha256"] = "0" * 64
        self.assertIn("render_standard_A.mjs changed since the manifest was written", rb.verify(None, None, manifest))
        self.assertEqual(rb.verify(None, None, load_manifest()), [])

    def test_a_wrong_commit_is_reported_for_a_git_checkout_and_noted_otherwise(self):
        with tempfile.TemporaryDirectory() as tmp:
            problems = rb.check_commit(Path(tmp), "c61480d6", "web")
            self.assertEqual(len(problems), 1)
            self.assertIn("not a git checkout", problems[0])


@unittest.skipUnless(os.environ.get("GROWTHOS_WEB_CHECKOUT"), "GROWTHOS_WEB_CHECKOUT not set: Standard A rebuild not exercised (private repo)")
class TestStandardRebuildFromFrozenSources(unittest.TestCase):
    def test_rebuild_is_byte_identical(self):
        problems = rb.verify(Path(os.environ["GROWTHOS_WEB_CHECKOUT"]), None)
        self.assertEqual(problems, [])


@unittest.skipUnless(os.environ.get("GROWTHOS_ENGINE_CHECKOUT"), "GROWTHOS_ENGINE_CHECKOUT not set: Story Visual A rebuild not exercised")
class TestStoryVisualRebuildFromFrozenSources(unittest.TestCase):
    def test_rebuild_is_identical(self):
        problems = rb.verify(None, Path(os.environ["GROWTHOS_ENGINE_CHECKOUT"]))
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
