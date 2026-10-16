// Plan « chat-send » : un message est tapé puis envoyé (gros plan sur l'écran). Ancre utilisée : send.
S.grid(true);
const msg = 'On mange ce soir ?';
const phone = S.add('phone', { x: 540, y: 930, s: 0.9, contact: 'Léa', avatar: 'primary', input: '',
  bubbles: [{ edge: -244, y: -300, text: 'Tu es où ?', side: 'left', col: 'chip', tc: 'ink' }] });
// le téléphone est visible dès la première image (pas d'appear sur le sujet principal)
const t0 = 0.8, t1 = S.t('send') - 0.3;
for (let i = 1; i <= msg.length; i++) {
  const t = t0 + (t1 - t0) * (i / msg.length);
  phone.set(t, { input: msg.slice(0, i) });
  S.sfx(t, 'tick');
}
const send = S.t('send');
phone.to(send, send + 0.15, { press: 1 }, 'out');
phone.to(send + 0.15, send + 0.35, { press: 0 }, 'io');
phone.set(send + 0.2, { input: '', bubbles: [
  { edge: -244, y: -300, text: 'Tu es où ?', side: 'left', col: 'chip', tc: 'ink' },
  { edge: 244, y: -110, text: msg, side: 'right', col: 'accent' }] });
S.sfx(send, 'pop');
const kw = S.add('text', { text: 'ENVOYER', x: 540, y: 330, size: 84, weight: 800, color: 'accent', mono: false, hud: true });
kw.appear(send - 0.1, 0.4, 'up');
S.cam.to(0, S.dur, { x: 540, y: 930, z: 1.08 }, 'io');
