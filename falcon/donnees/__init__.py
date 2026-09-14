"""Lecture des jeux de donnees et ecriture des fichiers de sortie.

N'importe rien d'autre de FALCON : lire un CSV ne demande de connaitre ni SAP,
ni les gardes, ni le journal.
"""

from .entree import (
    PREFIXE_DIAGNOSTIC, Dialecte, Item, JeuInvalide, empreinte_jeu, grouper,
    identifiant, lire, lire_items,
)
from .sortie import COLONNES_DIAGNOSTIC, ecrire_items

__all__ = [
    "Dialecte", "Item", "JeuInvalide", "PREFIXE_DIAGNOSTIC",
    "lire", "lire_items", "grouper", "identifiant", "empreinte_jeu",
    "ecrire_items", "COLONNES_DIAGNOSTIC",
]
