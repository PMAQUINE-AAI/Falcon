"""Definition declarative d'une automatisation.

Ne connait ni SAP, ni le controleur, ni les gardes — et ne peut pas les
importer. Une pipeline declare une intention ; le controleur applique les
regles. Ne pouvant nommer aucun driver, elle ne peut en desactiver aucune
garde : la separation du modele de securite est ici une contrainte d'import,
pas une convention.
"""

from .chargeur import (
    CLES_ETAPE, CLES_PIPELINE, MARQUEUR_BROUILLON, PipelineInvalide, charger,
)
from .extension import (
    ExtensionInconnue, connues, etape_python, oublier_tout, resoudre,
)
from .modele import (
    ACTIONS, AVEC_CIBLE, AVEC_SOURCE, CLASSES, GENRES_SOURCE,
    DerogationDeclaree, Etape, Pipeline, Source,
)

__all__ = [
    "Pipeline", "Etape", "Source", "DerogationDeclaree",
    "ACTIONS", "AVEC_CIBLE", "AVEC_SOURCE", "CLASSES", "GENRES_SOURCE",
    "charger", "PipelineInvalide", "MARQUEUR_BROUILLON",
    "CLES_PIPELINE", "CLES_ETAPE",
    "etape_python", "resoudre", "connues", "oublier_tout", "ExtensionInconnue",
]
