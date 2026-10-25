# Story Studio — voix locale gratuite : vérification des licences (2026-10-25)

P3 de l'audit Gate 0. **Rien n'a été téléchargé ni installé ; aucun audio synthétisé.** Seules des pages publiques ont été lues (modèles, jeux de données, licences). Ce document n'est pas un avis juridique : la validation par un juriste reste nécessaire avant tout usage commercial.

## 1. Pourquoi
Le brief interdit un TTS payant en test. Aujourd'hui la voix passe uniquement par ElevenLabs (`engine/tts.py`). Pour rendre une histoire de 90 s sans dépense, il faut une voix locale dont **la licence autorise l'usage commercial** (le produit est un SaaS).

## 2. Constat principal
Le **logiciel** Piper n'est pas le problème ; **les voix** le sont. Plusieurs voix françaises de Piper sont des modèles *affinés à partir de la voix anglaise « lessac »*, dont le jeu de données (Blizzard 2013, Université d'Édimbourg) est sous une licence **de recherche seulement**.

| Élément | Licence lue | Source | Verdict |
| --- | --- | --- | --- |
| Piper d'origine (`rhasspy/piper`) | MIT ; dépôt **archivé** le 2025-10-06, développement déplacé | [GitHub](https://github.com/rhasspy/piper) | utilisable comme outil interne |
| Piper maintenu (`OHF-Voice/piper1-gpl`) | **GPL-3.0** | [GitHub](https://github.com/OHF-Voice/piper1-gpl) | utilisable comme outil lancé dans notre CI (nous ne le redistribuons pas) ; GPL à signaler au juriste |
| Jeu « lessac » (base de siwis et upmc) | licence **de recherche** : usage commercial exclu, y compris développer ou licencier des produits de synthèse vocale ; les travaux « basés sur » le jeu sont couverts | [licence](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html), [fiche lessac](https://huggingface.co/rhasspy/piper-voices/raw/main/en/en_US/lessac/medium/MODEL_CARD) | **bloquant** pour toute voix affinée à partir de lui |
| `fr_FR-siwis-medium` | jeu SIWIS annoncé CC BY 4.0, **mais affiné à partir de lessac** ; les conditions du jeu SIWIS n'ont pas pu être lues (licence utilisateur en pièce jointe) | [fiche](https://huggingface.co/rhasspy/piper-voices/raw/main/fr/fr_FR/siwis/medium/MODEL_CARD), [jeu](https://datashare.ed.ac.uk/handle/10283/2353) | **à éviter** |
| `fr_FR-upmc-medium` | CC BY-SA 4.0, affiné à partir de lessac | [fiche](https://huggingface.co/rhasspy/piper-voices/raw/main/fr/fr_FR/upmc/medium/MODEL_CARD) | **à éviter** (partage à l'identique + lessac) |
| `fr_FR-tom-medium` | **AGPL-3.0** | [fiche](https://huggingface.co/rhasspy/piper-voices/raw/main/fr/fr_FR/tom/medium/MODEL_CARD) | **à éviter** |
| `fr_FR-gilles-low` | jeu annoncé CC0 (Kaggle, « French Single Speaker Speech Dataset »), provenance des enregistrements non établie, qualité « low » | [fiche](https://huggingface.co/rhasspy/piper-voices/raw/main/fr/fr_FR/gilles/low/MODEL_CARD) | **incertain** |
| `fr_FR-mls-medium` | jeu **MLS** CC BY 4.0, issu de livres audio LibriVox, **entraîné depuis zéro** (pas de lessac), 125 locuteurs | [fiche](https://huggingface.co/rhasspy/piper-voices/raw/main/fr/fr_FR/mls/medium/MODEL_CARD), [jeu](http://openslr.org/94/) | **candidat** : attribution requise ; locuteur et qualité à écouter |
| Kokoro-82M (poids) | **Apache-2.0** ; données « permissives / non protégées », dont deux jeux CC BY (SIWIS CC BY 4.0) et **de l'audio synthétique issu de TTS commerciaux fermés** | [fiche](https://huggingface.co/hexgrad/Kokoro-82M) | **candidat** : attribution CC BY à reprendre ; risque de provenance à faire relire (conditions des fournisseurs des voix synthétiques d'entraînement) |

## 3. Autres points
- **Voix d'une personne réelle** : les voix MLS viennent de bénévoles LibriVox, SIWIS d'une locutrice réelle. Ne jamais présenter la voix comme celle d'une personne identifiée. (Même remarque que dans la fiche d'un autre modèle français lue pendant la recherche.)
- **Aucune voix locale n'a encore été écoutée** : la qualité (intelligibilité, naturel, rythme comique) est **non vérifiée**. Un narrateur robotique ruinerait des histoires dont l'écriture compte avant tout.
- Le débit mesuré (17,1 caractères par seconde) vient d'ElevenLabs ; une autre voix donnera une autre durée. Les cibles de durée se mesurent sur l'audio final.

## 4. Recommandation
1. **Ne pas utiliser** les voix Piper `siwis`, `upmc`, `tom`, ni `gilles` (provenance incertaine).
2. **Tester d'abord `fr_FR-mls-medium`** (Piper) : seule voix Piper française dont la chaîne de licence est lisible de bout en bout (CC BY 4.0, entraînement depuis zéro). Coût : 0 €, téléchargement du modèle (quelques dizaines de Mo) et de Piper.
3. **En second, `Kokoro-82M`** (voix française `ff_siwis`) pour sa qualité probable plus naturelle : à écouter, avec le risque de provenance noté plus haut.
4. **Pour les tests de rendu sans aucune voix nouvelle** : l'audio existant du Gate 3 (`experiments/story_gate1/out/audio`), déjà généré, sans appel.
5. **Rien ne passe en production** sur une voix locale sans validation juridique (licence du jeu, GPL de Piper, attribution) et validation d'écoute.

## 5. Décision demandée (D3)
Autoriser le téléchargement, sur ce poste, de l'outil et d'**une** voix candidate (recommandation : Piper + `fr_FR-mls-medium`) pour un essai d'écoute de 30 s de la « ville sans mots », sans l'intégrer au produit ? Les fichiers seraient placés hors du dépôt Git, avec le nom de la source, la taille et la somme de contrôle notées ici.
