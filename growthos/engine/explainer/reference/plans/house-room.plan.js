// Plan « house-room » : une personne dans une maison en coupe, plein cadre, caméra qui s'approche. Ancre : send.
S.sky('night');
const hs = 1.45, hx = 540, hy = 1300;                  // échelle et position (bas, centre) de la maison
S.add('city', { x: -200, y: hy, count: 12, seed: 3, far: true, par: 0.5 });
S.add('box', { x: 540, y: hy + 450, w: 2000, h: 900, color: '#1a2150', r: 0, layer: -1 });   // la rue, sous la maison
S.add('house', { x: hx, y: hy, s: hs, palette: 'dakar', dark: 0.22 });
// un personnage posé sur le canapé d'une maison d'échelle hs : x = hx - 120*hs, y = hy - 106*hs, s = 1.25*hs
const awa = S.add('person', { x: hx - 120 * hs, y: hy - 106 * hs, s: 1.25 * hs, pose: 'sitPhone', typing: true, glow: 1,
  style: 'braids', skin: '#6b4128', hair: '#150e0c', top: 'accent', pants: '#222a55', pid: 1 });
const send = S.t('send');
const tag = S.add('text', { text: 'DAKAR', x: 220, y: 230, size: 64, mono: true, weight: 800, color: 'accent', ls: 8, hud: true });
tag.appear(0.2, 0.5, 'up');
tag.hide(send - 0.4);
S.cam.set(0, { x: 540, y: 1000, z: 1.0 });
S.cam.to(0, send, { x: 470, y: 1010, z: 1.9 }, 'io');
awa.pulse(send, 0.06, 0.3);
S.sfx(send, 'pop');
