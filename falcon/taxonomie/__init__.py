"""Taxonomie d'erreurs : trois categories, et l'inconnu bloquant par defaut.

N'importe que `falcon.noyau`. Ne connait ni SAP, ni le moteur : on lui donne
une signature, elle rend un verdict.
"""

from .dump import ecrire_dump
from .politique import appliquer
from .registre import (
    ARRET, BENIGNE, CANAUX, CHEMIN_REGISTRE_DEFAUT, DECLARABLES, FAUTIVE,
    INCONNUE, Entree, Politique, Registre, RegistreInvalide, Signature,
    Verdict,
)

__all__ = [
    "Registre", "RegistreInvalide", "Signature", "Verdict", "Entree",
    "Politique", "ARRET", "BENIGNE", "FAUTIVE", "INCONNUE", "DECLARABLES",
    "CANAUX", "CHEMIN_REGISTRE_DEFAUT", "ecrire_dump", "appliquer",
]
