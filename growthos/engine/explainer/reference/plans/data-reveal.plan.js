// Plan « data-reveal » : un chiffre qui grandit + des barres. Aucune donnée inventée : les valeurs viennent du plan.
// Ancres : start (le chiffre apparaît quand la voix le dit), end.
S.grid(true);
const a = S.t('start'), b = S.t('end');
const big = S.add('counter', { x: 540, y: 520, value: 1000, size: 150, suffix: ' €', color: 'ink', glow: 18 });
big.appear(a - 0.2, 0.4, 'up');
big.to(a, b, { value: 2653 }, 'io');
const years = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const bars = S.add('bars', { x: 540, y: 1360, w: 840, h: 520, color: 'primary',
  values: years.map(y => 1000 * Math.pow(1.1, y)), labels: years.map(y => String(y)), grow: 0, size: 28 });
bars.appear(a - 0.2, 0.3, 'up');
bars.to(a, b, { grow: 1 }, 'out');
const cap = S.add('text', { text: 'après 10 ans', x: 540, y: 1560, size: 64, weight: 700, color: 'dim', hud: true });
cap.appear(b - 0.6, 0.4, 'up');
S.cam.to(0, S.dur, { x: 540, y: 960, z: 1.06 }, 'io');
S.sfx(a, 'whoosh'); S.sfx(b, 'ping');
