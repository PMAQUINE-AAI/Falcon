"""Supervision d'un lot : progression et ETA glissant (§4.6).

Stdlib seule. Le §4.6 nomme *Rich* ; le §6 impose une livraison en fichier
unique, et chaque dependance est une piece a embarquer dans le bundle. La
decision n°16 arrete l'ecart.

Le rendu est une fonction pure — les tests comparent des chaines, jamais une
capture de terminal — et le module ne s'exprime pas hors terminal, sauf a le
lui demander.
"""

from .modele import (
    ENCODAGE_MINIMAL, FENETRE, Estimation, Progres, Suivi, bilan, duree, ligne,
)
from .terminal import Rapporteur, encodable

__all__ = [
    "Progres", "Estimation", "Suivi", "ligne", "bilan", "duree",
    "Rapporteur", "encodable", "FENETRE", "ENCODAGE_MINIMAL",
]
