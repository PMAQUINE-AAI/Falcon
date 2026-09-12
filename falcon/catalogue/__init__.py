"""Catalogue d'ecrans : l'actif reutilisable qui grossit a chaque projet.

Le decouplage catalogue / pipeline est le point cle de l'architecture : le
catalogue est un actif qui se capitalise, la pipeline est jetable.

N'importe que `falcon.noyau`. Un catalogue se lit et s'ecrit sans savoir ce
qu'est SAP.
"""

from .depot import ATTRIBUTS, VERSION, Depot
from .inventaire import (
    ATTRIBUTS_COMPARES, CHAMP, CHERCHE_DANS_CHAMP, CHERCHE_DANS_ECRAN, CURE,
    TYPE_SANS_CHANGEABLE,
    ECRAN, PORTEES, QUARANTAINE, RAYONS, TOUS, Comparaison, ComparaisonRefusee,
    Critere, Ecart, Fiche, Inventaire, Trouvaille, charger, comparer,
    fenetres_citees, filtrer, parcourues, rapports, sans_mesure,
)
from .modele import (
    ESQUISSE, OBSERVEE, SOURCES, CatalogueInvalide, ClefVariante, Variante,
    clef_de, variante_de,
)

__all__ = [
    "Depot", "ClefVariante", "Variante", "CatalogueInvalide",
    "clef_de", "variante_de", "OBSERVEE", "ESQUISSE", "SOURCES",
    "ATTRIBUTS", "VERSION",
    # l'inventaire : le catalogue relu, cherche et compare — en DONNEES
    "Inventaire", "Fiche", "charger", "Critere", "Trouvaille", "filtrer",
    "Comparaison", "Ecart", "comparer", "ComparaisonRefusee",
    "fenetres_citees", "sans_mesure", "rapports", "parcourues",
    "CURE", "QUARANTAINE", "TOUS", "RAYONS", "ECRAN", "CHAMP", "PORTEES",
    "ATTRIBUTS_COMPARES", "CHERCHE_DANS_ECRAN", "CHERCHE_DANS_CHAMP",
    "TYPE_SANS_CHANGEABLE",
]
