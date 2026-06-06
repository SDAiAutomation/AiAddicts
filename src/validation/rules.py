from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationRule:
    id: str
    name: str
    description: str
    keywords: tuple[str, ...]
    weight: float       # Contribution to 100-point score
    required: bool = True


VALIDATION_RULES: list[ValidationRule] = [
    ValidationRule(
        id="SECU_001",
        name="Section Sécurité",
        description="La FI doit comporter une section dédiée à la sécurité",
        keywords=("sécurité", "securite", "risque", "danger", "prévention",
                  "consigne de sécurité", "mise en sécurité", "risques identifiés"),
        weight=15.0,
        required=True,
    ),
    ValidationRule(
        id="SECU_002",
        name="EPI requis listés",
        description="Les Équipements de Protection Individuelle doivent être listés",
        keywords=("epi", "équipement de protection", "casque", "gants", "lunettes",
                  "chaussures de sécurité", "gilet", "masque", "bouchons d'oreille",
                  "protection individuelle"),
        weight=10.0,
        required=True,
    ),
    ValidationRule(
        id="OUTIL_001",
        name="Outillage requis",
        description="La liste des outils et équipements nécessaires doit être présente",
        keywords=("outillage", "outil", "clé", "couple de serrage", "dynamomètre",
                  "tournevis", "jauge", "matériel nécessaire", "équipement requis",
                  "liste des outils"),
        weight=15.0,
        required=True,
    ),
    ValidationRule(
        id="META_001",
        name="Numéro de révision",
        description="La FI doit avoir un numéro de révision ou d'indice",
        keywords=("révision", "rev.", "rev ", "indice", "version", "ind.", "rév.",
                  "revision"),
        weight=10.0,
        required=True,
    ),
    ValidationRule(
        id="META_002",
        name="Date de création / révision",
        description="La date de création ou de dernière révision doit être indiquée",
        keywords=("date", "créé le", "modifié le", "mis à jour", "émis le",
                  "établi le", "2025", "2026"),
        weight=5.0,
        required=True,
    ),
    ValidationRule(
        id="META_003",
        name="Auteur / Rédacteur",
        description="L'auteur ou rédacteur de la FI doit être identifié",
        keywords=("auteur", "rédacteur", "rédigé par", "préparé par",
                  "établi par", "créé par"),
        weight=5.0,
        required=False,
    ),
    ValidationRule(
        id="META_004",
        name="Approbateur / Vérificateur",
        description="La FI doit être approuvée par une personne habilitée",
        keywords=("approbateur", "approuvé par", "validé par", "vérificateur",
                  "vérifié par", "visa"),
        weight=5.0,
        required=False,
    ),
    ValidationRule(
        id="SCOPE_001",
        name="Domaine d'application",
        description="Le périmètre d'application de la FI doit être défini",
        keywords=("objet", "domaine d'application", "périmètre", "s'applique à",
                  "concerne", "applicable", "but de", "champ d'application"),
        weight=10.0,
        required=True,
    ),
    ValidationRule(
        id="PROC_001",
        name="Mode opératoire",
        description="Les étapes de réalisation doivent être clairement décrites",
        keywords=("étape", "mode opératoire", "procédure", "opération",
                  "déroulement", "séquence", "étapes de réalisation",
                  "étape 1", "étape 2"),
        weight=15.0,
        required=True,
    ),
    ValidationRule(
        id="QC_001",
        name="Contrôle qualité",
        description="Les points de contrôle et critères d'acceptation doivent être définis",
        keywords=("contrôle", "vérification", "inspection", "critère d'acceptation",
                  "points de contrôle", "autocontrôle", "conformité", "contrôle qualité"),
        weight=10.0,
        required=True,
    ),
]

TOTAL_WEIGHT: float = sum(r.weight for r in VALIDATION_RULES)
