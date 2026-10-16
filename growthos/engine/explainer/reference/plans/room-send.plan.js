// Plan « room-send » : Awa tape et envoie son message ; la caméra plonge dans l'écran. Scène type `room`. Ancres : send.
S.template('room', { place: 'dakar', who: 'awa', tag: 'DAKAR', contact: 'Léa', message: 'On mange ce soir ?',
  sendAt: S.t('send'), zoomPhone: { t0: S.t('send') + 1.4, t1: S.dur - 0.2 } });
