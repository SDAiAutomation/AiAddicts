---
name: blotato-product-reference
description: Blotato (blotato.com) as a product-scope reference for GrowthOS — not a design reference
metadata: 
  node_type: memory
  type: reference
  originSessionId: 1eb6e9dc-22f7-4600-b6d4-fc59b845c078
  modified: 2026-09-03T20:51:55.008Z
---

Le 2026-09-03 l'utilisateur a donné **blotato.com** comme référence « inspire-toi mais fais mieux côté design ».

**À retenir : le périmètre produit, pas le style.** Le site marketing de Blotato est exactement l'anti-pattern décrit dans [[growthos-web-frontend]] / `docs/design-system.md` : gradients magenta→purple, texte en dégradé néon, boutons glossy. On garde le système restreint (light, accent `#2563EB` unique, Linear/Stripe-grade).

Périmètre Blotato (informe la roadmap GrowthOS, pas le prochain commit) :
- **Publish** : 1 appel → 9 plateformes (X, LinkedIn, Facebook, Instagram, TikTok, YouTube, Threads, Bluesky, Pinterest), pas de SDK ni d'app OAuth par plateforme à faire approuver.
- **Schedule** : queue, « prochain créneau libre », créneaux hebdo récurrents par plateforme/compte.
- **Comments & DMs** : lire l'inbox, répondre depuis l'agent ; automations DM (mot-clé → lien).
- **Analytics** : vues / likes / commentaires par post.
- **Adaptation par plateforme** : un contenu source → posts taillés pour chaque réseau.

GrowthOS aujourd'hui : publication **manuelle** (pas d'OAuth, choix assumé du plan semaines 1-2). La partie « Publishing » multi-plateforme de Blotato = cible des phases ultérieures, pas du MVP.
