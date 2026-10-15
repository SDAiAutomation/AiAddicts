/* probe.js — instrumentation de validation (jamais utilisée pour le rendu de production).
   `probeFrame(t)` rend l'image `t` en enregistrant chaque texte dessiné (boîte en pixels écran, opacité, hauteur).
   Les règles (texte coupé par le bord, texte dans une zone de sécurité, chevauchements) sont appliquées côté Python
   (validate.py) pour pouvoir évoluer sans toucher au runtime. */
(function () {
  const P = { on: false, texts: [], errors: [] };
  window.__probe = P;
  const fillText = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText = function (s, x, y, maxWidth) {
    if (P.on && s && P.texts.length < 400) {
      const m = this.measureText(String(s));
      const w = m.width, asc = m.actualBoundingBoxAscent || 0, desc = m.actualBoundingBoxDescent || 0;
      const x0 = this.textAlign === 'center' ? x - w / 2 : this.textAlign === 'right' ? x - w : x;
      const tr = this.getTransform();
      const xs = [], ys = [];
      for (const [px, py] of [[x0, y - asc], [x0 + w, y - asc], [x0, y + desc], [x0 + w, y + desc]]) {
        xs.push(tr.a * px + tr.c * py + tr.e);
        ys.push(tr.b * px + tr.d * py + tr.f);
      }
      P.texts.push({ s: String(s).slice(0, 40), x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys), alpha: this.globalAlpha });
    }
    return fillText.call(this, s, x, y, maxWidth);
  };
  /* Part de l'image qui n'est pas le fond dominant (grille 54 x 96) : mesure grossiere du « cadre vide ». */
  const small = document.createElement('canvas');
  small.width = 54; small.height = 96;
  function frameCoverage() {
    const g = small.getContext('2d');
    g.drawImage(document.getElementById('c'), 0, 0, 54, 96);
    const d = g.getImageData(0, 0, 54, 96).data, counts = new Map();
    for (let i = 0; i < d.length; i += 4) {
      const key = (d[i] >> 4) + ',' + (d[i + 1] >> 4) + ',' + (d[i + 2] >> 4);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return 1 - Math.max(...counts.values()) / (54 * 96);
  }
  window.addEventListener('error', (e) => P.errors.push(String(e.message)));
  window.probeFrame = function (t) {
    P.texts = [];
    P.on = true;
    const started = performance.now();
    try { renderFrame(t); } catch (e) { P.errors.push(String((e && e.message) || e)); }
    const ms = performance.now() - started;
    P.on = false;
    const coverage = frameCoverage();
    const issues = P.texts.filter((r) => r.alpha > 0.05 && (r.x0 < 0 || r.x1 > W || r.y0 < 0 || r.y1 > H)).map((r) => ({ kind: 'offscreen', ...r }));
    return { t, ms, coverage, texts: P.texts, issues, errors: P.errors.slice() };
  };
})();
