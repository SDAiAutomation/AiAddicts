// Plan « geometry-golden » : un segment coupé selon le nombre d'or, puis un mot-clé. Gabarit `segment`. Ancres : cut, name.
S.grid(true);
S.template('segment', { tCut: S.t('cut'), aLabel: 'a', bLabel: 'b' });
const kw = S.add('text', { text: 'LE NOMBRE D\u2019OR', x: 540, y: 420, size: 88, weight: 800, color: 'warm', hud: true });
kw.appear(S.t('name'), 0.5, 'up');
S.cam.to(0, S.dur, { x: 540, y: 960, z: 1.12 }, 'io');
S.sfx(S.t('cut'), 'clip');
