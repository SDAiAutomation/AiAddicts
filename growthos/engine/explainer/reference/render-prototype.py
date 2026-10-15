"""Deterministic render: Chromium headless calls renderAt(t) frame by frame, ffmpeg encodes.
usage: render.py page.html out.mp4            -> full MP4 with sound design
       render.py page.html outdir --stills 1.2,8,20  -> PNG keyframes for review
"""
import asyncio, base64, subprocess, sys, os
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
GF = os.path.join(HERE, "gf", "ofl")
FONT_CSS = f"""
@font-face{{font-family:"Bricolage Grotesque";src:url("file://{GF}/bricolagegrotesque/BricolageGrotesque[opsz,wdth,wght].ttf");font-weight:200 800}}
@font-face{{font-family:"JetBrains Mono";src:url("file://{GF}/jetbrainsmono/JetBrainsMono[wght].ttf");font-weight:100 800}}
"""
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


async def main():
    html, out = os.path.abspath(sys.argv[1]), sys.argv[2]
    stills = sys.argv[4].split(",") if len(sys.argv) > 3 and sys.argv[3] == "--stills" else None
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME)
        page = await browser.new_page(viewport={"width": 1080, "height": 1920})
        await page.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
        await page.goto("file://" + html)
        await page.add_style_tag(content=FONT_CSS)
        await page.evaluate("""Promise.all(['500','600','700','800'].map(w=>document.fonts.load(w+' 80px "Bricolage Grotesque"'))
            .concat(['500','700'].map(w=>document.fonts.load(w+' 30px "JetBrains Mono"'))))""")
        await page.evaluate("window.__stop()")
        grab = "(t)=>{renderAt(t);return document.getElementById('c').toDataURL('image/%s',0.95)}"
        if stills:
            os.makedirs(out, exist_ok=True)
            for s in stills:
                data = await page.evaluate(grab % "png", float(s))
                open(os.path.join(out, f"f{float(s):05.1f}.png"), "wb").write(base64.b64decode(data.split(",")[1]))
            await browser.close()
            return
        dur, fps = await page.evaluate("[VIDEO.duration, VIDEO.fps]")
        wav = out + ".wav"
        open(wav, "wb").write(base64.b64decode(await page.evaluate("renderAudio()")))
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                               "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                               "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
        for i in range(int(round(dur * fps))):
            data = await page.evaluate(grab % "jpeg", i / fps)
            ff.stdin.write(base64.b64decode(data.split(",")[1]))
        ff.stdin.close()
        ff.wait()
        os.remove(wav)
        await browser.close()

asyncio.run(main())
