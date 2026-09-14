"""Cartographie : rejouer une trace en OBSERVATION, pour peupler le catalogue.

Etape 2 du cycle de vie (SPEC_FALCON.md). Ce paquet ne connait pas SAP et
n'importe pas `falcon.couture` : il RECOIT un driver, comme
`moteur.executer(pipeline, jeu, brut, ...)`. La regle est verifiee par
`tests/test_frontieres.py` (`COUCHES_SANS_COUTURE`).

Aucune ligne de ce depot n'a jamais parle a un SAP reel : ce qui est teste
ici l'est contre `couture.double.DriverScripte`.
"""

from .gestes import (
    ARGUMENT_REFUSE, ECARTE_CONFORT, SANS_COUTURE, TABLE, TRADUIT,
    VERBE_INCONNU, Appel, Regle, TableIncoherente, Traduction, traduire,
    traduire_tous,
)
from .parcours import (
    CODES_DE_SESSION, ETATS, INTERROMPUE, MODE, MOTIFS, PLAFOND,
    PLAFOND_SAUVEGARDES, TERMINEE, ACTION_AVEUGLE, Branche, Exploration,
    ExplorationImpossible, Previsualisation, Reprise, SauvegardeRefusee,
    explorer, previsualiser,
)
from .rapport import (
    ATTEINTE, ETATS_DE_VISITE, NON_EXPLOREE, SAUTEE, esquisses_manquantes,
    etat_des_visites, ordres_manquants, previsualisation, rendre,
    visites_manquantes,
)

__all__ = [
    "TABLE", "Regle", "Appel", "Traduction", "TableIncoherente",
    "traduire", "traduire_tous",
    "TRADUIT", "ECARTE_CONFORT", "SANS_COUTURE", "ARGUMENT_REFUSE",
    "VERBE_INCONNU",
    "explorer", "previsualiser", "Exploration", "Previsualisation",
    "Branche", "Reprise", "SauvegardeRefusee", "ExplorationImpossible",
    "MODE", "PLAFOND_SAUVEGARDES", "ETATS", "TERMINEE", "INTERROMPUE",
    "PLAFOND", "MOTIFS", "CODES_DE_SESSION", "ACTION_AVEUGLE",
    "rendre", "previsualisation", "etat_des_visites", "visites_manquantes",
    "esquisses_manquantes", "ordres_manquants",
    "ATTEINTE", "SAUTEE", "NON_EXPLOREE", "ETATS_DE_VISITE",
]
