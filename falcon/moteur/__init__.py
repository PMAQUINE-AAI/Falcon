"""Le moteur : la boucle qui consomme tous les autres sous-systemes.

Ne connait pas SAP. `tests/test_frontieres.py` lui interdit d'importer
`falcon.couture` : il recoit un driver et l'enveloppe aussitot dans un
`DriverGarde`. Rien de ce qu'il execute ne touche un driver nu, et une
pipeline ne peut donc pas contourner une garde en passant par lui.
"""

from .adaptateur import Adaptateur
from .erreurs import ExtractionImpossible
from .boucle import (
    DRY_RUN, INTERROMPU, MODES, PLAFOND, REPRISE, RUN, TERMINE,
    PreparationImpossible, RepetitionManquante, Resultat, executer,
    garde_de_la_repetition,
)
from .chaine import Maillon, enchainer, retour_accueil

__all__ = [
    "executer", "Resultat", "PreparationImpossible", "ExtractionImpossible",
    "RepetitionManquante",
    "RUN", "DRY_RUN", "REPRISE", "MODES",
    "TERMINE", "INTERROMPU", "PLAFOND",
    "enchainer", "Maillon", "retour_accueil", "Adaptateur",
]
