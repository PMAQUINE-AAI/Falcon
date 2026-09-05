"""Catalogue d'ecrans : l'actif reutilisable qui grossit a chaque projet.

Le decouplage catalogue / pipeline est le point cle de l'architecture : le
catalogue est un actif qui se capitalise, la pipeline est jetable.

N'importe que `falcon.noyau`. Un catalogue se lit et s'ecrit sans savoir ce
qu'est SAP.
"""

from .depot import ATTRIBUTS, VERSION, Depot
from .modele import (
    ESQUISSE, OBSERVEE, SOURCES, CatalogueInvalide, ClefVariante, Variante,
    clef_de, variante_de,
)

__all__ = [
    "Depot", "ClefVariante", "Variante", "CatalogueInvalide",
    "clef_de", "variante_de", "OBSERVEE", "ESQUISSE", "SOURCES",
    "ATTRIBUTS", "VERSION",
]
