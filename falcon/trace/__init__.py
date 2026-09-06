"""Lecture des enregistrements du SAP GUI Recorder.

Ne connait ni SAP, ni le controleur, ni les gardes, et ne peut pas les
importer — meme contrainte de frontiere que `falcon/pipeline/`, verifiee par
`tests/test_frontieres.py`. Une trace est une donnee ; la lire ne doit
donner acces a aucun driver.

**Ce que ce paquet ne fera jamais.** Le recorder enregistre des actions : ni
l'identite des ecrans traverses, ni les champs presents sur chacun. Une trace
ne peut donc pas peupler le catalogue — elle ne produit qu'une *esquisse*, que
`catalogue.Depot.pour_garde` refuse deja de servir.
"""

from .brouillon import Brouillon, BrouillonImpossible, brouillon_de
from .inventaire import rapport
from .modele import (
    AFFECTATION, APPEL, APPEL_ARGUMENT, CONFORT, FENETRE_RACINE, FORMES,
    VERBES, Geste,
    Inventaire, Trace, TraceInvalide, rendre_litteral,
)
from .vbs import decoder, decouper, inventorier, lire, litteral

__all__ = [
    "lire", "inventorier", "rapport",
    "brouillon_de", "Brouillon", "BrouillonImpossible",
    "Trace", "Geste", "Inventaire", "TraceInvalide",
    "APPEL", "AFFECTATION", "APPEL_ARGUMENT", "FORMES", "VERBES", "CONFORT",
    "FENETRE_RACINE",
    "decoder", "decouper", "litteral", "rendre_litteral",
]
