# FI Validator — RAG sur Fiches d'Instructions Alstom CRL

**Auteur :** Saliou Dia — Ingénieur Méthodes & Outils Digitaux  
**Site :** Alstom CRL, Charleroi  
**Date :** Juin 2026  
**Statut :** POC en cours de développement  
**Branche :** `claude/fi-validator-rag-ksdjI`

---

## 1. Contexte & Problème

Les Fiches d'Instructions (FI) constituent le référentiel opérationnel de la production chez Alstom CRL. Plusieurs centaines de FI sont stockées dans une bibliothèque SharePoint, couvrant l'ensemble des gammes d'assemblage.

**Problèmes identifiés :**

- La validation manuelle des FI est chronophage et sujette à erreurs humaines
- La recherche d'information dans les FI est fastidieuse (pas de moteur sémantique)
- Aucun outil ne permet de vérifier la conformité d'une FI par rapport à un référentiel
- Les nouveaux méthodos ont du mal à naviguer dans le corpus documentaire

**Opportunité :** Les LLM couplés à une architecture RAG permettent d'interroger un corpus documentaire en langage naturel avec une précision élevée, en gardant les données 100 % on-premise.

---

## 2. Objectif du Projet

Développer un outil de validation et d'interrogation intelligent des Fiches d'Instructions Alstom CRL, basé sur une architecture RAG (Retrieval-Augmented Generation), déployé en environnement on-premise pour garantir la confidentialité des données.

---

## 3. Cas d'Usage Cibles

| # | Cas d'usage              | Exemple de question                                       |
|---|--------------------------|-----------------------------------------------------------|
| 1 | Validation de conformité | « Cette FI contient-elle une section sécurité ? »         |
| 2 | Recherche sémantique     | « Quelles FI concernent le serrage des boulons de bogie ? » |
| 3 | Comparaison inter-FI     | « Quelle est la différence entre FI-042 et FI-043 ? »     |
| 4 | Extraction d'information | « Quels sont les outils requis pour l'opération X ? »     |
| 5 | Audit documentaire       | « Lister toutes les FI sans référence de révision »       |

---

## 4. Architecture Technique

### 4.1 Stack technique

| Composant            | Technologie                        | Justification                                      |
|----------------------|------------------------------------|----------------------------------------------------|
| LLM                  | Ollama + Mistral 7B                | On-premise, gratuit, données confidentielles       |
| Embeddings           | nomic-embed-text (Ollama)          | Local, pas d'appel API externe                     |
| Vector Database      | ChromaDB                           | Open source, simple, performant                    |
| Framework IA         | LangChain (Python)                 | Écosystème riche, bien documenté                   |
| Interface POC        | Streamlit                          | Développement rapide                               |
| Interface Prod       | SPFx ou Power Apps                 | Intégration écosystème Alstom                      |
| Source données       | SharePoint (Graph API)             | Bibliothèque FI existante                          |
| Backend Prod         | FastAPI                            | API REST légère                                    |
| Intégration workflow | Power Automate (triggers gratuits) | Flux validation existant — sans connecteur Premium |
| Écriture résultats   | Graph API Python → SharePoint      | Zéro licence supplémentaire                        |

### 4.2 Flux de données — Intégration Power Automate existant

```
SharePoint (nouvelle FI ajoutée / modifiée)
        │
        │  Polling Graph API toutes les 5 min
        ▼
Python Script (surveille la liste SharePoint)
        │
        │  Téléchargement PDF/Word via Graph API
        ▼
    Extraction texte (pypdf / python-docx)
        │
        ▼
    Chunking (500 tokens, overlap 50)
        │
        ▼
    Embeddings (nomic-embed-text local)
        │
        ▼
    ChromaDB (index vectoriel local)
        │
        │  Similarity search + Mistral
        ▼
    Rapport conformité JSON
        │
        │  Écriture via Graph API
        ▼
Colonnes SharePoint mises à jour
(Analyse_IA + Score_Conformite + Statut_IA)
        │
        │  Trigger gratuit « When column changes »
        ▼
Power Automate (flux existant — sans connecteur Premium)
        │
        ▼
Email validateur avec rapport IA intégré
```

### 4.3 Colonnes SharePoint à ajouter

| Colonne            | Type SharePoint  | Rôle                                        |
|--------------------|------------------|---------------------------------------------|
| `Statut_IA`        | Choix            | En attente / En cours / Analysé / Erreur    |
| `Score_Conformite` | Nombre (0-100)   | Score global de conformité                  |
| `Analyse_IA`       | Texte multiligne | Rapport détaillé points conformes/manquants |
| `Date_Analyse`     | Date/Heure       | Horodatage de la dernière analyse           |

### 4.4 Règles de validation (10 critères, total = 100 pts)

| ID        | Critère                  | Poids | Obligatoire |
|-----------|--------------------------|-------|-------------|
| SECU_001  | Section Sécurité         | 15    | ✅ Oui      |
| SECU_002  | EPI requis listés        | 10    | ✅ Oui      |
| OUTIL_001 | Outillage requis         | 15    | ✅ Oui      |
| META_001  | Numéro de révision       | 10    | ✅ Oui      |
| META_002  | Date de création         | 5     | ✅ Oui      |
| META_003  | Auteur / Rédacteur       | 5     | Non         |
| META_004  | Approbateur              | 5     | Non         |
| SCOPE_001 | Domaine d'application    | 10    | ✅ Oui      |
| PROC_001  | Mode opératoire          | 15    | ✅ Oui      |
| QC_001    | Contrôle qualité         | 10    | ✅ Oui      |

**Niveaux de conformité :**  
- ≥ 80 → ✅ Conforme  
- 60–79 → ⚠️ Partiellement conforme  
- < 60 → ❌ Non conforme

### 4.5 Contraintes techniques

- **Données 100 % on-premise** — aucun appel vers API cloud externe
- **Zéro connecteur Premium** — Power Automate utilise uniquement triggers SharePoint natifs gratuits
- **Environnement WSL2 Ubuntu** pour le développement
- **Serveur réseau Alstom** pour la production (à valider avec IT)
- **Zscaler** — proxy à contourner pour les dépendances Python (hotspot mobile si nécessaire)

---

## 5. Structure du Projet

```
AiAddicts/
├── app.py                           # Interface Streamlit (5 onglets)
├── config/
│   └── settings.py                  # Configuration centralisée (.env)
├── src/
│   ├── ingestion/
│   │   ├── document_loader.py       # Chargement PDF, DOCX, TXT
│   │   └── chunker.py               # Découpage texte (500 tokens / overlap 50)
│   ├── retrieval/
│   │   └── vector_store.py          # ChromaDB — add, search, delete, audit
│   ├── rag/
│   │   └── pipeline.py              # Chaîne Q&A + comparaison inter-FI
│   ├── validation/
│   │   ├── rules.py                 # 10 règles métier pondérées
│   │   └── conformity_checker.py    # Score 0-100 + recommandations
│   └── sharepoint/
│       ├── graph_client.py          # Client OAuth2 Microsoft Graph API
│       └── sync.py                  # Démon de polling SharePoint (Phase 2)
├── scripts/
│   ├── setup.sh                     # Installation Ollama + modèles + deps
│   ├── ingest_documents.py          # CLI d'ingestion
│   └── sharepoint_sync.py           # Lancement démon SharePoint
├── data/
│   ├── fi_samples/                  # 5 FI de démonstration (scores variés)
│   └── chroma_db/                   # Base vectorielle persistante (gitignored)
├── tests/
│   ├── test_ingestion.py            # 8 tests chargement + chunking
│   └── test_validation.py           # 14 tests règles + scorer
├── requirements.txt
└── .env.example
```

---

## 6. Plan de Développement

### Phase 0 — Setup (Semaine 1)

- [x] Créer la structure du projet et les modules Python
- [ ] Installer Ollama sur WSL2 Ubuntu
- [ ] Télécharger Mistral 7B et nomic-embed-text
- [ ] Valider le pipeline avec les FI de démonstration

```bash
bash scripts/setup.sh
python scripts/ingest_documents.py --dir data/fi_samples
streamlit run app.py
```

### Phase 1 — POC Local (Semaines 1-2)

- [x] Implémenter le pipeline RAG complet (ingestion → embeddings → retrieval → génération)
- [x] Moteur de validation de conformité (10 règles, score 0-100)
- [x] Interface Streamlit (Recherche, Validation, Comparaison, Audit)
- [x] 5 FI de démonstration en français
- [x] 22 tests unitaires — 100 % passants
- [ ] Valider la qualité des réponses sur 10 questions de test réelles

**Critère de succès :** L'outil répond correctement à 8/10 questions de test

### Phase 2 — Connexion SharePoint (Semaines 3-4)

- [ ] Configurer l'accès Microsoft Graph API (OAuth2 compte Alstom)
- [ ] Tester `scripts/sharepoint_sync.py --once` sur la bibliothèque FI
- [ ] Valider l'écriture des colonnes `Statut_IA`, `Score_Conformite`, `Analyse_IA`
- [ ] Activer le polling automatique toutes les 5 minutes

```bash
# Copier .env.example → .env, renseigner les credentials Azure AD
python scripts/sharepoint_sync.py --once   # test unitaire
python scripts/sharepoint_sync.py          # démon continu
```

### Phase 3 — Interface & Démo (Semaine 5)

- [ ] Affiner les prompts en français pour Mistral
- [ ] Ajouter filtres par type de FI / ligne de production dans l'audit
- [ ] Préparer la démo pour le management (slides + démo live)
- [ ] Documenter le ROI (heures gagnées mesurées vs. estimées)

### Phase 4 — Déploiement Pilote (Mois 2-3)

- [ ] Valider avec l'IT la disponibilité d'un serveur dédié (Ollama + ChromaDB)
- [ ] Déployer sur serveur réseau interne Alstom
- [ ] Former 2-3 méthodos pilotes
- [ ] Collecter les retours et itérer

### Phase 5 — Production (Mois 3-6)

- [ ] Migrer vers FastAPI + SPFx (intégration SharePoint native)
- [ ] Évaluation qualité RAG avec le framework RAGAs
- [ ] Extension à d'autres types de documents (gammes, plans qualité)
- [ ] Documentation technique pour transfert IT

---

## 7. Estimation des Charges

| Phase                 | Charge estimée | Période      |
|-----------------------|----------------|--------------|
| Setup + POC local     | 3-4 jours      | Semaines 1-2 |
| Connexion SharePoint  | 3-4 jours      | Semaines 3-4 |
| Interface & Démo      | 2 jours        | Semaine 5    |
| Déploiement pilote    | 3 jours        | Mois 2       |
| Production SPFx       | 5-7 jours      | Mois 3-6     |
| **Total**             | **~20 jours**  | **6 mois**   |

---

## 8. ROI Estimé

| Indicateur                      | Valeur actuelle   | Avec FI Validator |
|---------------------------------|-------------------|-------------------|
| Temps recherche info dans FI    | ~30 min/recherche | ~2 min            |
| Temps validation conformité FI  | ~2 h/FI           | ~15 min           |
| Nombre de méthodos concernés    | ~10               | ~10               |
| Gain temps/semaine/personne     | —                 | ~3-4 h            |
| **Gain annuel équipe**          | —                 | **~1 500-2 000 h**|

---

## 9. Risques & Mitigations

| Risque                           | Probabilité | Impact | Mitigation                                               |
|----------------------------------|-------------|--------|----------------------------------------------------------|
| IT bloque le déploiement serveur | Moyenne     | Élevé  | Argument on-premise + données confidentielles protégées  |
| Qualité réponses insuffisante    | Faible      | Élevé  | Tester plusieurs modèles, optimiser le chunking          |
| Adoption faible des users        | Moyenne     | Moyen  | Intégrer dans flux Power Automate existant               |
| Performance CPU trop lente       | Moyenne     | Moyen  | Quantification Q4, ou Phi-3 mini 3.8B                   |
| FI mal structurées (scan)        | Faible      | Moyen  | OCR preprocessing avec pytesseract                       |
| Connecteurs Premium requis       | ❌ Écarté   | —      | Architecture Python + Graph API évite tout connecteur    |

---

## 10. Parcours de Montée en Compétence

```
Phase 1 (0-6 mois)    → RAG + LangChain + Agents          [CE PROJET]
Phase 2 (6-12 mois)   → ML classique + Prédiction pannes
Phase 3 (12-18 mois)  → Fine-tuning Mistral sur corpus FI
Phase 4 (18-24 mois)  → SaaS IA documentaire industriel
```

**Profil cible :** AI Engineer applicatif spécialisé Manufacturing  
**TJM cible à 12 mois :** 550-650 €/jour

---

## 11. Démarrage Rapide

```bash
# 1. Cloner et se placer sur la branche
git checkout claude/fi-validator-rag-ksdjI

# 2. Installation complète (Ollama + modèles + dépendances Python)
bash scripts/setup.sh

# 3. Lancer Ollama en arrière-plan
ollama serve &

# 4. Indexer les FI de démonstration
python scripts/ingest_documents.py --dir data/fi_samples

# 5. Lancer l'interface
streamlit run app.py
```

**Configuration SharePoint (Phase 2) :**

```bash
cp .env.example .env
# Renseigner SP_TENANT_ID, SP_CLIENT_ID, SP_CLIENT_SECRET, SP_SITE_URL
python scripts/sharepoint_sync.py --once   # test
python scripts/sharepoint_sync.py          # démon continu
```

---

*Document vivant — mis à jour à chaque fin de phase.*
