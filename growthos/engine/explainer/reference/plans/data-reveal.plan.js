// Plan « data-reveal » : un chiffre qui grandit puis un histogramme. Gabarits `bignumber` et `bars`. Aucune donnée inventée :
// les valeurs viennent du plan. Ancres : start (le chiffre apparaît quand la voix le dit), end, bars.
S.grid(true);
const a = S.t('start'), b = S.t('end');
const years = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
S.template('bignumber', { from: 1000, to: 2594, t0: a, t1: b, suffix: ' €', label: 'après 10 ans', labelT: b, y: 640 });
S.template('bars', { values: years.map(y => 1000 * Math.pow(1.1, y)), labels: years.map(y => String(y)), t0: S.t('bars'), t1: b, title: '' });
S.cam.to(0, S.dur, { x: 540, y: 960, z: 1.05 }, 'io');
S.sfx(a, 'whoosh'); S.sfx(b, 'ping');
