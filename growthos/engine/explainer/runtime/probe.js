/* probe.js — instrumentation de validation (jamais utilisée pour le rendu de production).
   `probeFrame(t)` rend l'image `t` en enregistrant chaque texte dessiné (boîte en pixels écran, opacité, hauteur).
   Les règles (texte coupé par le bord, texte dans une zone de sécurité, chevauchements) sont appliquées côté Python
   (validate.py) pour pouvoir évoluer sans toucher au runtime. */
(function () {
  const P = { on: false, texts: [], shapes: [], errors: [], seq: 0, cur: null };
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
      P.texts.push({ s: String(s).slice(0, 40), seq: P.seq++, order: P.cur ? P.cur.order : -1, x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys), alpha: this.globalAlpha });
    }
    return fillText.call(this, s, x, y, maxWidth);
  };
  /* Formes : boite englobante (pixels ecran) de chaque remplissage / trait, attribuee a l'element de scene en cours de dessin
     (`P.cur`, pose par scene.js). Le chemin courant est suivi point par point : les arcs sont pris par leurs 4 extremes
     (surestimation pour un arc partiel), les courbes par leurs points de controle. */
  let path = [];
  const proto = CanvasRenderingContext2D.prototype;
  const addPt = (c, x, y) => { const t = c.getTransform(); path.push([t.a * x + t.c * y + t.e, t.b * x + t.d * y + t.f]); };
  const wrap = (name, fn) => { const o = proto[name]; proto[name] = function (...a) { if (P.on) fn(this, a); return o.apply(this, a); }; };
  wrap('beginPath', () => { path = []; });
  wrap('moveTo', (c, a) => addPt(c, a[0], a[1]));
  wrap('lineTo', (c, a) => addPt(c, a[0], a[1]));
  wrap('quadraticCurveTo', (c, a) => { addPt(c, a[0], a[1]); addPt(c, a[2], a[3]); });
  wrap('bezierCurveTo', (c, a) => { addPt(c, a[0], a[1]); addPt(c, a[2], a[3]); addPt(c, a[4], a[5]); });
  const box = (c, x, y, w, h) => { addPt(c, x, y); addPt(c, x + w, y); addPt(c, x, y + h); addPt(c, x + w, y + h); };
  wrap('rect', (c, a) => box(c, a[0], a[1], a[2], a[3]));
  wrap('roundRect', (c, a) => box(c, a[0], a[1], a[2], a[3]));
  wrap('arc', (c, a) => box(c, a[0] - a[2], a[1] - a[2], 2 * a[2], 2 * a[2]));
  wrap('ellipse', (c, a) => box(c, a[0] - a[2], a[1] - a[3], 2 * a[2], 2 * a[3]));
  const record = (c, op, pts) => {
    if (!P.cur || P.shapes.length >= 1500 || !pts.length) return;
    const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
    P.shapes.push({ kind: P.cur.kind, order: P.cur.order, seq: P.seq++, op, alpha: c.globalAlpha,
      x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) });
  };
  wrap('fill', (c) => record(c, 'fill', path));
  wrap('stroke', (c) => record(c, 'stroke', path));
  wrap('fillRect', (c, a) => { const keep = path; path = []; box(c, a[0], a[1], a[2], a[3]); record(c, 'fill', path); path = keep; });
  /* Remplissage de l'image, mesure au CONTRASTE LOCAL sur une grille 54 x 96 (un degrade de ciel n'est pas du contenu).
     Renvoie {total, bands} : `bands` = 8 bandes horizontales de 240 px, part de cellules contrastees dans chacune. */
  const small = document.createElement('canvas');
  small.width = 54; small.height = 96;
  function frameCoverage() {
    const g = small.getContext('2d', { willReadFrequently: true });
    g.drawImage(document.getElementById('c'), 0, 0, 54, 96);
    const d = g.getImageData(0, 0, 54, 96).data, at = (x, y) => (y * 54 + x) * 4;
    const bands = new Array(8).fill(0), per = 54 * 12;
    let total = 0;
    for (let y = 0; y < 95; y++) {
      for (let x = 0; x < 53; x++) {
        const i = at(x, y), r = at(x + 1, y), b = at(x, y + 1);
        const c = Math.max(Math.abs(d[i] - d[r]), Math.abs(d[i + 1] - d[r + 1]), Math.abs(d[i + 2] - d[r + 2]),
          Math.abs(d[i] - d[b]), Math.abs(d[i + 1] - d[b + 1]), Math.abs(d[i + 2] - d[b + 2]));
        if (c > 22) { total++; bands[Math.floor(y / 12)]++; }
      }
    }
    return { total: total / (53 * 95), bands: bands.map((n) => n / per) };
  }
  window.addEventListener('error', (e) => P.errors.push(String(e.message)));
  window.probeFrame = function (t) {
    P.texts = [];
    P.shapes = [];
    P.seq = 0;
    P.cur = null;
    P.on = true;
    const started = performance.now();
    try { renderFrame(t); } catch (e) { P.errors.push(String((e && e.message) || e)); }
    const ms = performance.now() - started;
    P.on = false;
    const coverage = frameCoverage();
    const issues = P.texts.filter((r) => r.alpha > 0.05 && (r.x0 < 0 || r.x1 > W || r.y0 < 0 || r.y1 > H)).map((r) => ({ kind: 'offscreen', ...r }));
    return { t, ms, coverage, texts: P.texts, shapes: P.shapes, issues, errors: P.errors.slice() };
  };
})();
