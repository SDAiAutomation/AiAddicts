// Plan « equation-guide » : une équation en étapes + un guide qui salue, montre et applaudit. Gabarit `equation` + `guide`. Ancres : s1, s2, s3.
S.grid(true);
S.template('equation', { lines: [
  { text: '2x + 3 = 11', t: 0 },
  { text: '2x = 11 − 3', t: S.t('s1'), note: '− 3 des deux côtés' },
  { text: '2x = 8', t: S.t('s2') },
  { text: 'x = 4', t: S.t('s3'), note: '÷ 2 des deux côtés' }] });
S.template('guide', { who: 'awa', side: 'left', size: 0.8,
  poses: [{ t: 0, pose: 'wave' }, { t: S.t('s1'), pose: 'point' }, { t: S.t('s3'), pose: 'cheer' }],
  say: [{ t: 0.3, text: 'Salut !', until: 1.6 }, { t: S.t('s3'), text: 'x = 4 !', until: S.t('s3') + 1.8 }] });
S.cam.to(0, S.dur, { x: 540, y: 960, z: 1.04 }, 'io');
