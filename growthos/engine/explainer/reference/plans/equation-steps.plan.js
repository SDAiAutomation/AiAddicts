// Plan « equation-steps » : une équation se résout en étapes, chacune sur son ancre. Gabarit `equation`. Ancres : s1, s2, s3.
S.grid(true);
S.template('equation', { lines: [
  { text: '2x + 3 = 11', t: 0 },
  { text: '2x = 11 − 3', t: S.t('s1'), note: '− 3 des deux côtés' },
  { text: '2x = 8', t: S.t('s2') },
  { text: 'x = 4', t: S.t('s3'), note: '÷ 2 des deux côtés' }] });
S.cam.to(0, S.dur, { x: 540, y: 960, z: 1.06 }, 'io');
