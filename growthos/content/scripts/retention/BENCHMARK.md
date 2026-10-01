# Retention Engine V1 — benchmark

Généré par `scripts/retention_benchmark.py` : analyse **déterministe** (aucun appel IA, aucun rendu, aucune publication). Les chiffres de durée sont **estimés** depuis le nombre de mots (fr 213, en 172 mots/min) ; ils seront mesurés au rendu. Aucun score de viralité : seulement des caractéristiques structurelles.

## 1. PocketLogic — 5 concepts

### The $1,000 Emergency Fund Rule

- **audiencePromise** : A first savings target small enough to start this month.
- **hookType** : `scenario` — « Your car breaks down tomorrow. Do you have $1,000? »
- **coreQuestion** : Do you have $1,000 when a surprise bill hits?
- **payoff** : Save a $1,000 starter buffer first; at $100 a month it takes ten months.
- **CTA** (next_episode) : « Money Rule #2 is next. »
- **open loop** : « Do you have $1,000 when a surprise bill hits? » ouverte au bloc 1, résolue au bloc 6 (resolved, 21.9 s)
- **série** : Money Rules Nobody Taught You #1 — « Money Rule #2 is next »

| # | rôle | gain | scène | narration |
|---|------|------|-------|-----------|
| 1 | hook | new_question | big_number | Your car breaks down tomorrow. Do you have $1,000? |
| 2 | setup | new_consequence | icon_text | One surprise bill is how a solid budget turns into card debt. |
| 3 | escalation | new_consequence | timeline | The card covers it today, then interest quietly adds to what you owe. |
| 4 | evidence | new_example | comparison | With $1,000 set aside, the same bill is just a bill. You pay it and move on. |
| 5 | reveal | answer | progress_bar | So the rule is simple: before anything else, save your first $1,000. |
| 6 | payoff | answer | before_after | Not a perfect fund, just a starter. At $100 a month, you have your $1,000 in ten months. |
| 7 | cta | cta | icon_text | Money Rule #2 is next. |

Rythme (estimated) : 30.0 s au total (cible 30.0 s), hook 3.1 s, premier exemple chiffré à 11.9 s, payoff à 22.0 s.

Diagnostics : aucun problème détecté

### You Got a Raise... So Why Are You Still Broke?

- **audiencePromise** : See exactly where a raise disappears and how to keep part of it.
- **hookType** : `contradiction` — « You got a raise. So why are you still broke? »
- **coreQuestion** : Why is a raise not leaving you any better off?
- **payoff** : A $1,000 raise had $850 of new spending attached, leaving $150; saving $500 first fixes it.
- **CTA** (next_episode) : « Money Rule #3 is next. »
- **open loop** : « Why is a raise not leaving you any better off? » ouverte au bloc 1, résolue au bloc 5 (resolved, 17.8 s)
- **série** : Money Rules Nobody Taught You #2 — « Money Rule #3 is next »

| # | rôle | gain | scène | narration |
|---|------|------|-------|-----------|
| 1 | hook | new_question | big_number | You got a raise. So why are you still broke? |
| 2 | setup | new_example | icon_text | Say your pay goes up $1,000 a month. Great news, on paper. |
| 3 | escalation | new_example | bar_chart | A pricier apartment adds $400. A car payment adds $300. Dining out adds $150. |
| 4 | evidence | new_fact | big_number | That's $850 a month of new spending, and your lifestyle now costs that much more. |
| 5 | reveal | answer | money_split | So only $150 of your $1,000 raise is left over. |
| 6 | payoff | answer | formula | Your raise didn't vanish, your spending grew to meet it. Save half the raise before it lands: $500. |
| 7 | cta | cta | icon_text | Money Rule #3 is next. |

Rythme (estimated) : 29.3 s au total (cible 30.0 s), hook 3.5 s, premier exemple chiffré à 3.5 s, payoff à 21.3 s.

Diagnostics : `repeats_title` (info)

### The 24-Hour Rule That Stops Impulse Buying

- **audiencePromise** : A one-step habit that stops regret purchases.
- **hookType** : `warning` — « Never buy it the moment you want it. »
- **coreQuestion** : What should you do instead of buying the moment you want something?
- **payoff** : Wait 24 hours; if you still want it, buy it, if not you keep the money.
- **CTA** (follow_for_series) : « Follow for Rule #4. »
- **open loop** : « What should you do instead of buying right away? » ouverte au bloc 1, résolue au bloc 5 (resolved, 14.6 s)
- **série** : Money Rules Nobody Taught You #3 — « Follow for Rule #4 »

| # | rôle | gain | scène | narration |
|---|------|------|-------|-----------|
| 1 | hook | new_question | warning | Never buy it the moment you want it. |
| 2 | setup | new_fact | icon_text | Impulse buys feel urgent. That feeling is what you're paying for. |
| 3 | escalation | new_consequence | compound_growth | Four small buys at $45 each is $180 a month, and you barely notice any one of them. |
| 4 | evidence | new_fact | big_number | Over a year, that's $2,160. |
| 5 | reveal | answer | timeline | Instead, use the 24-hour rule: put it in the cart, then wait a full day before buying. |
| 6 | payoff | answer | before_after | If you still want it tomorrow, buy it. If not, you just kept $45. |
| 7 | cta | cta | icon_text | Follow for Rule #4. |

Rythme (estimated) : 27.2 s au total (cible 30.0 s), hook 2.8 s, premier exemple chiffré à 6.6 s, payoff à 20.9 s.

Diagnostics : aucun problème détecté

### What Happens If You Invest $5 a Day?

- **audiencePromise** : See what a tiny daily amount becomes with time.
- **hookType** : `specific_number` — « $5 a day sounds small. Do it for 20 years. »
- **coreQuestion** : What does $5 a day become in 20 years?
- **payoff** : $36,500 contributed becomes about $74,800 at an assumed 7%, with about $38,300 from growth.
- **CTA** (question) : « Where does your $5 a day go? »
- **open loop** : « What does $5 a day become in 20 years? » ouverte au bloc 1, résolue au bloc 6 (resolved, 17.8 s)

| # | rôle | gain | scène | narration |
|---|------|------|-------|-----------|
| 1 | hook | new_question | big_number | $5 a day sounds small. Do it for 20 years. |
| 2 | setup | new_fact | icon_text | Five dollars a day adds up to $1,825 a year. |
| 3 | escalation | new_example | compound_growth | Invest it yearly at an assumed 7% return: about $10,500 after five years, $25,200 after ten. |
| 4 | evidence | new_fact | big_number | After twenty years: about $74,800. |
| 5 | reveal | answer | before_after | And you only put in $36,500. The rest is growth. |
| 6 | payoff | answer | formula | Time did about $38,300 of the work over those 20 years, not you. |
| 7 | cta | cta | icon_text | Where does your $5 a day go? |

Rythme (estimated) : 24.8 s au total (cible 30.0 s), hook 3.5 s, premier exemple chiffré à 3.5 s, payoff à 17.8 s.

Diagnostics : aucun problème détecté

### Why Your First $10,000 Feels So Hard

- **audiencePromise** : Understand why early saving feels slow and why it speeds up.
- **hookType** : `curiosity_gap` — « Why is your first $10,000 so much harder than the next? »
- **coreQuestion** : Why is the first $10,000 so much harder than the next?
- **payoff** : At an assumed 7%, $10,000 earns about $700 a year; every extra $10,000 adds about $700 more.
- **CTA** (save) : « Save this for the slow months. »
- **open loop** : « Why is the first $10,000 so much harder than the next? » ouverte au bloc 1, résolue au bloc 5 (resolved, 16.6 s)

| # | rôle | gain | scène | narration |
|---|------|------|-------|-----------|
| 1 | hook | new_question | big_number | Why is your first $10,000 so much harder than the next? |
| 2 | setup | new_fact | progress_bar | Saving $400 a month, it takes 25 months to get there. |
| 3 | pattern_interrupt | new_consequence | warning | And in that stretch, almost every dollar is your own effort. |
| 4 | evidence | new_example | comparison | At an assumed 7% a year, $10,000 earns about $700. A $100,000 balance earns $7,000. |
| 5 | reveal | answer | before_after | That's the answer: early on, you do the work. Later, your money does too. |
| 6 | payoff | answer | big_number | So keep going: every extra $10,000 adds about $700 a year at the same assumed 7%. |
| 7 | cta | cta | icon_text | Save this for the slow months. |

Rythme (estimated) : 29.3 s au total (cible 30.0 s), hook 3.8 s, premier exemple chiffré à 3.8 s, payoff à 21.6 s.

Diagnostics : aucun problème détecté

## 2. Avant / après sur 3 scripts existants

AVANT = scripts du benchmark Phase 2 tels qu'ils existent. APRÈS = réécriture manuelle selon l'architecture (pas une sortie du LLM : elle ne mesure pas le prompt, seulement ce que la structure change).

### Finance (Motion Graphics)

| Critère | AVANT (script actuel) | APRÈS (Retention Engine, écrit à la main) |
|---|---|---|
| Hook | « Si tu gagnes 3 000 dollars par mois, l'epargne ne devrait pas etre ce qui reste a la fin. » (19 mots) | « 3 000 dollars par mois. Pourquoi rien ne reste ? » (9 mots) |
| Durée du hook | 5.4 s | 2.5 s |
| Premier élément chiffré | 9.0 s | 9.0 s |
| Payoff à | 15.8 s | 14.6 s |
| Durée totale (estimée) | 21.7 s | 20.3 s |
| Progression narrative | hook > setup > evidence > escalation > payoff > cta | hook > setup > escalation > evidence > reveal > payoff > cta |
| Boucles ouvertes déclarées | 0 | 1 |
| Informations répétées | aucune détectée | aucune détectée |
| Payoff | « La regle est simple : revenu moins epargne egale budget de depense. » — valeur concrète : False | « Revenu moins épargne égale budget : épargne d'abord, et il reste toujours quelque chose. » — valeur concrète : False |
| CTA | « Tu epargnes en premier, ou tu epargnes ce qu'il reste ? » (question) | « Tu épargnes en premier ou en dernier ? » (question) |
| Progression visuelle | 4 scène(s)/cadrage(s) distincts : big_number, icon_text, big_number, big_number, formula, checklist | 5 scène(s)/cadrage(s) distincts : big_number, icon_text, progress_bar, big_number, money_split, formula, icon_text |
| Problèmes détectés | hook_too_long, hook_slow | aucun |

### Storytelling (images IA)

| Critère | AVANT (script actuel) | APRÈS (Retention Engine, écrit à la main) |
|---|---|---|
| Hook | « Nour trouva une boite a musique cassee, oubliee depuis des annees. » (11 mots) | « Quelle famille se cachait dans cette boîte à musique cassée ? » (10 mots) |
| Durée du hook | 3.1 s | 2.8 s |
| Premier élément chiffré | aucun | 12.4 s |
| Payoff à | 12.4 s | 16.1 s |
| Durée totale (estimée) | 20.0 s | 23.1 s |
| Progression narrative | hook > setup > evidence > escalation > reveal > cta | hook > setup > escalation > pattern_interrupt > reveal > payoff > cta |
| Boucles ouvertes déclarées | 0 | 1 |
| Informations répétées | aucune détectée | aucune détectée |
| Payoff | « A l'interieur, une petite photo montrait une famille de renards qu'elle n'avait jamais vue. » — valeur concrète : False | « Au dos, un nom : sa grand-mère. Cette famille était la sienne, et la mélodie, sa berceuse. » — valeur concrète : False |
| CTA | « Aurais-tu ouvert la boite tout de suite, ou attendu le bon moment ? » (question) | « Tu aurais ouvert la boîte tout de suite ? » (question) |
| Progression visuelle | 4 scène(s)/cadrage(s) distincts : close_up, wide, insert, medium, close_up, medium | 4 scène(s)/cadrage(s) distincts : close_up, wide, insert, medium, close_up, medium, wide |
| Problèmes détectés | payoff_not_resolving_hook, cta_too_long | aucun |

### Explainer (stock footage)

| Critère | AVANT (script actuel) | APRÈS (Retention Engine, écrit à la main) |
|---|---|---|
| Hook | « La plupart des gens ignorent combien l'inflation du style de vie leur coute vraiment. » (14 mots) | « Ton salaire a augmenté. Pourquoi ton solde n'a pas bougé ? » (10 mots) |
| Durée du hook | 3.9 s | 2.8 s |
| Premier élément chiffré | aucun | 2.8 s |
| Payoff à | 14.4 s | 16.3 s |
| Durée totale (estimée) | 21.1 s | 24.5 s |
| Progression narrative | hook > evidence > evidence > escalation > reveal > cta | hook > setup > escalation > evidence > reveal > payoff > cta |
| Boucles ouvertes déclarées | 0 | 1 |
| Informations répétées | aucune détectée | aucune détectée |
| Payoff | « Resultat : le solde bancaire ne bouge presque jamais, malgre les augmentations. » — valeur concrète : False | « Ton salaire a monté, ton niveau de vie l'a rattrapé. Mets 150 euros de côté dès le premier virement. » — valeur concrète : True |
| CTA | « Ton niveau de vie a-t-il grimpe aussi vite que ton salaire ? » (question) | « Ton niveau de vie a-t-il rattrapé ton salaire ? » (question) |
| Progression visuelle | 4 scène(s)/cadrage(s) distincts : close_up, medium, insert, wide, close_up, medium | 4 scène(s)/cadrage(s) distincts : close_up, medium, insert, close_up, wide, medium, medium |
| Problèmes détectés | payoff_not_resolving_hook, cta_too_long, unsupported_empirical_claim | aucun |

