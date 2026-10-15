// Plan « equation-steps » : une équation se résout en étapes, chaque étape tombe sur son ancre. Ancres : s1, s2, s3.
S.grid(true);
const steps = ['2x + 3 = 11', '2x = 11 − 3', '2x = 8', 'x = 4'];
const ys = [620, 860, 1100, 1340];
const times = [0.3, S.t('s1'), S.t('s2'), S.t('s3')];
const notes = ['', '− 3 des deux côtés', '÷ 2 des deux côtés', ''];
steps.forEach((s, i) => {
  const e = S.add('text', { text: s, x: 540, y: ys[i], size: 118, weight: 800, mono: true, color: i === 3 ? 'good' : 'ink', maxW: 860 });
  e.appear(times[i], 0.45, 'up');
  if (i > 0) e.to(times[i], times[i] + 0.25, { glow: 22 });
  if (notes[i]) {
    const n = S.add('text', { text: notes[i], x: 540, y: ys[i] - 92, size: 46, weight: 600, color: 'warm' });
    n.appear(times[i] - 0.1, 0.35, 'up');
    n.hide(times[i] + 1.4);
  }
  S.sfx(times[i], 'pop');
});
const frame = S.add('box', { x: 540, y: 1340, w: 640, h: 170, color: 'bg', stroke: 'good', sw: 5, r: 28, a: 0 });
frame.to(times[3] + 0.3, times[3] + 0.7, { a: 1 }, 'out');
S.sfx(times[3] + 0.3, 'ping');
