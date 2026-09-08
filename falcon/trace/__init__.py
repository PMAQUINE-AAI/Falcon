"""Lecture des enregistrements du SAP GUI Recorder.

Ne connait ni SAP, ni le controleur, ni les gardes, et ne peut pas les
importer — meme contrainte de frontiere que `falcon/pipeline/`, verifiee par
`tests/test_frontieres.py`. Une trace est une donnee ; la lire ne doit
donner acces a aucun driver.

**Ce que ce paquet ne fera jamais.** Le recorder enregistre des actions : ni
l'identite des ecrans traverses, ni les champs presents sur chacun. Une trace
LUE ne peut donc pas peupler le catalogue — elle ne produit qu'une *esquisse*,
que `catalogue.Depot.pour_garde` refuse deja de servir.

La nuance, depuis `falcon.exploration` : une trace REJOUEE peuple bel et bien
la quarantaine, mais de RELEVES observes sur un vrai systeme, pas de
conjectures. Ce qui vient de la lecture seule reste une esquisse ; ce qui
vient du rejeu est un releve. Les deux se distinguent a l'oeil nu dans le
YAML — `programme: "?"` d'un cote, le vrai triplet de l'autre.
"""

from .brouillon import Brouillon, BrouillonImpossible, brouillon_de
from .esquisse import (
    NON_RENSEIGNE, Visite, apercu, code_transaction, deposer, esquisse_de,
    esquisses, vise_le_champ_de_commande, visites,
)
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
    "visites", "Visite", "esquisse_de", "esquisses", "deposer", "apercu",
    "code_transaction", "vise_le_champ_de_commande", "NON_RENSEIGNE",
]
