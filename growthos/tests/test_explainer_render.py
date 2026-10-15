"""Golden de la phase 1 de l'Explainer : le runtime extrait rend EXACTEMENT les mêmes images que le prototype
(contexte 2D réinitialisé à chaque image dans les deux cas : le prototype laissait fuir un réglage d'une scène à l'autre).

Comparaison octet à octet sur la même machine (prototype et port passent par le même Chromium, les mêmes polices) :
pas de hash figé en dur, donc rien qui dépende du système d'exploitation. Les tests sont ignorés si Playwright ou
son Chromium sont absents (installation facultative, voir docs/explainer-plan.md).
"""
import asyncio
import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.explainer import render  # noqa: E402

try:
    from playwright.async_api import async_playwright  # noqa: E402
    HAVE_PLAYWRIGHT = True
except ImportError:  # pragma: no cover
    HAVE_PLAYWRIGHT = False

REFERENCE = render.HERE / "reference"
PROTOTYPE_HTML = REFERENCE / "voyage-message.html"
TIMELINE = REFERENCE / "voyage-message.timeline.js"
# Un instant par scène, plus les raccords (coupes noires) et des instants non entiers.
TIMES = [0.0, 1.2, 3.0, 5.9, 8.0, 20.0, 30.9, 36.2, 44.1, 50.5, 53.0, 56.0, 58.0]


async def _frames(html: Path, times, inject_fonts: bool, stop_loop: bool = False):
    async with async_playwright() as p:
        try:
            browser, page = await render.open_page(p, html, inject_fonts=inject_fonts)
        except Exception as exc:  # Chromium non installé
            raise unittest.SkipTest(f"Chromium indisponible : {str(exc)[:80]}")
        if stop_loop:
            # Prototype d'origine : boucle d'animation arretee, et meme contexte vierge par image que le runtime
            # (le prototype laissait fuir lineCap de la scene 3 : voir core.js renderFrame).
            await page.evaluate("window.__stop()")
            out = [
                base64.b64decode((await page.evaluate(
                    "(t)=>{const c=document.getElementById('c');c.getContext('2d').reset();renderAt(t);return c.toDataURL('image/png')}", t
                )).split(",", 1)[1])
                for t in times
            ]
        else:
            out = [await render.grab(page, t, "png") for t in times]
        await browser.close()
    return out


def _run(coro):
    return asyncio.run(coro)


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright non installé")
class TestExplainerGolden(unittest.TestCase):
    def test_runtime_matches_prototype_pixel_for_pixel(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = render.build_stage_html(TIMELINE, tmp)
            ported = _run(_frames(stage, TIMES, inject_fonts=False))
        original = _run(_frames(PROTOTYPE_HTML, TIMES, inject_fonts=True, stop_loop=True))
        for t, a, b in zip(TIMES, ported, original):
            self.assertEqual(render.frame_hash(a), render.frame_hash(b), f"image différente à t={t}")

    def test_render_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = render.build_stage_html(TIMELINE, tmp)
            # Deux passes, dans un ordre différent : renderAt(t) ne dépend ni de l'historique ni du temps réel.
            first = _run(_frames(stage, [12.3, 40.0, 12.3], inject_fonts=False))
            second = _run(_frames(stage, [40.0, 12.3], inject_fonts=False))
        self.assertEqual(first[0], first[2])
        self.assertEqual(first[0], second[1])
        self.assertEqual(first[1], second[0])

    def test_page_has_no_network_and_probe_is_clean(self):
        async def run(stage):
            async with async_playwright() as p:
                try:
                    browser, page = await render.open_page(p, stage)
                except Exception as exc:
                    raise unittest.SkipTest(f"Chromium indisponible : {str(exc)[:80]}")
                fetch = await page.evaluate(
                    "fetch('https://example.com/').then(()=>'ouvert').catch(()=>'bloque')"
                )
                reports = [await page.evaluate("(t)=>probeFrame(t)", t) for t in TIMES]
                await browser.close()
            return fetch, reports

        with tempfile.TemporaryDirectory() as tmp:
            fetch, reports = _run(run(render.build_stage_html(TIMELINE, tmp)))
        self.assertEqual(fetch, "bloque")
        for report in reports:
            self.assertEqual(report["errors"], [], f"erreur JS à t={report['t']}")


class TestStageHtml(unittest.TestCase):
    def test_stage_loads_runtime_in_order_then_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = render.build_stage_html(TIMELINE, tmp).read_text(encoding="utf-8")
        positions = [html.index(name) for name in (*render.RUNTIME_FILES, TIMELINE.name)]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))
        self.assertNotIn("https://", html)

    def test_runtime_files_exist(self):
        for name in render.RUNTIME_FILES:
            self.assertTrue((render.RUNTIME_DIR / name).is_file(), name)
        for rel in (rel for _, rel, _ in render._FONT_FACES):
            self.assertTrue((render.FONTS_DIR / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
