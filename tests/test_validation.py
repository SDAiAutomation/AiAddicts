"""Tests for the conformity checker and validation rules."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.validation.rules import VALIDATION_RULES, TOTAL_WEIGHT
from src.validation.conformity_checker import check_conformity, ConformityReport


COMPLETE_FI = """\
FICHE D'INSTRUCTIONS — ALSTOM CRL
Titre : Serrage boulons bogie
Révision : Rev. 03
Date : 15/05/2026
Auteur : Jean-Pierre Dubois
Approbateur : Marie Lambert

1. Objet et domaine d'application
Cette fiche s'applique à l'assemblage du bogie T3000.

2. Sécurité
Risques identifiés : chute, coincement.
EPI obligatoires : casque, gants, lunettes, chaussures de sécurité, bouchons d'oreille.
Mise en sécurité : consigner l'armoire avant intervention.

3. Outillage requis
Clé dynamométrique 0-400 Nm, tournevis, douille 30 mm.

4. Mode opératoire
Étape 1 : préparer l'outillage.
Étape 2 : positionner le bogie.
Étape 3 : pré-serrage en croix.
Étape 4 : serrage final au couple.

5. Contrôle qualité
Autocontrôle obligatoire.
Points de contrôle : CQ-01 couple de serrage, CQ-02 témoin de serrage.
Critère d'acceptation : 310 à 320 Nm.
"""

MINIMAL_FI = """\
Instructions pose vitrage.
Coller le vitrage avec la colle SIKA.
Attendre 72h avant de toucher.
"""

PARTIAL_FI = """\
FICHE D'INSTRUCTIONS
Numéro : FI-999
Révision : Rev. 01
Date : 2026

Objet : cette fiche concerne le contrôle visuel des soudures.

Mode opératoire
Étape 1 : inspecter visuellement les soudures.
Étape 2 : noter les défauts.

Contrôle qualité : vérification selon critère d'acceptation ISO 5817.
"""


class TestValidationRules:
    def test_total_weight_is_100(self):
        assert abs(TOTAL_WEIGHT - 100.0) < 0.01

    def test_all_rules_have_weight(self):
        for rule in VALIDATION_RULES:
            assert rule.weight > 0

    def test_rule_ids_are_unique(self):
        ids = [r.id for r in VALIDATION_RULES]
        assert len(ids) == len(set(ids))


class TestConformityChecker:
    def test_complete_fi_high_score(self):
        report = check_conformity(COMPLETE_FI, source="FI-COMPLETE.txt")
        assert report.total_score >= 80
        assert report.status == "Conforme"

    def test_minimal_fi_low_score(self):
        report = check_conformity(MINIMAL_FI, source="FI-MINIMAL.txt")
        assert report.total_score < 60
        assert report.status == "Non conforme"

    def test_partial_fi_medium_score(self):
        report = check_conformity(PARTIAL_FI, source="FI-PARTIAL.txt")
        assert 40 <= report.total_score <= 80

    def test_report_has_all_rules(self):
        report = check_conformity(COMPLETE_FI)
        assert len(report.rule_results) == len(VALIDATION_RULES)

    def test_recommendations_for_missing(self):
        report = check_conformity(MINIMAL_FI)
        assert len(report.recommendations) > 0

    def test_no_recommendations_when_all_pass(self):
        report = check_conformity(COMPLETE_FI)
        assert len(report.recommendations) == 0

    def test_source_preserved(self):
        report = check_conformity(COMPLETE_FI, source="test_source.txt")
        assert report.source == "test_source.txt"

    def test_to_dict_structure(self):
        report = check_conformity(COMPLETE_FI)
        d = report.to_dict()
        assert "total_score" in d
        assert "status" in d
        assert "rule_results" in d
        assert "recommendations" in d
        for r in d["rule_results"]:
            assert "rule_id" in r
            assert "passed" in r
            assert "score" in r

    def test_score_between_0_and_100(self):
        for text in [COMPLETE_FI, MINIMAL_FI, PARTIAL_FI]:
            report = check_conformity(text)
            assert 0 <= report.total_score <= 100

    def test_security_rule_detected(self):
        report = check_conformity(COMPLETE_FI)
        secu_result = next(r for r in report.rule_results if r.rule_id == "SECU_001")
        assert secu_result.passed

    def test_missing_epi_flagged(self):
        fi_without_epi = "Mode opératoire : serrer les boulons. Contrôle : vérifier le couple."
        report = check_conformity(fi_without_epi)
        epi_result = next(r for r in report.rule_results if r.rule_id == "SECU_002")
        assert not epi_result.passed
