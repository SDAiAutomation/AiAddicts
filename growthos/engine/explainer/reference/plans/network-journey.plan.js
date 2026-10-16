// Plan « network-journey » : trois morceaux de message voyagent du téléphone à l'antenne puis le long du sol. Ancre : go.
S.sky('night');
S.add('city', { x: -300, y: 1500, count: 12, seed: 3, far: true, par: 0.6 });
S.add('city', { x: -200, y: 1500, count: 10, seed: 5 });
S.add('box', { x: 1100, y: 1760, w: 3400, h: 520, color: '#141a38', corner: 0 });
const tower = S.add('tower', { x: 700, y: 1500, h: 520 });
const phone = S.add('miniphone', { x: 160, y: 1400, label: 'toi' });
const path = [[160, 1400], [700, 990], [700, 1490], [1700, 1490]];
const go = S.t('go');
for (let i = 0; i < 3; i++) {
  const p = S.add('chunk', { x: 160, y: 1400, w: 92, h: 44, label: '#' + (i + 1), mono: true, color: 'primary', glow: 26 });
  p.appear(go + i * 0.2 - 0.2, 0.2, 'pop');
  p.follow(path, go + i * 0.2, go + 3.4 + i * 0.2, 'io');
}
tower.to(go + 1.0, go + 1.6, { act: 1 }, 'out');
tower.to(go + 2.6, go + 3.2, { act: 0 }, 'inn');
S.cam.to(0, go + 1.0, { x: 440, y: 1260, z: 1.0 });
S.cam.to(go + 1.0, S.dur, { x: 1000, y: 1380, z: 0.9 });
S.sfx(go, 'whoosh'); S.sfx(go + 1.2, 'ping');
const label = S.add('text', { text: 'ANTENNE', x: 540, y: 1560, size: 72, weight: 800, color: 'primary', hud: true });
label.appear(go + 0.6, 0.4, 'up');
