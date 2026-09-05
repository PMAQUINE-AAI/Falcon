"""Ligne de commande : `python -m falcon`.

Deux commandes seulement, et aucune n'ecrit dans SAP. `diagnostiquer` ne
recoit qu'un `DriverLecture` — une facade qui n'a ni `write`, ni `press`, ni
`vkey` : le premier contact reel du projet est en lecture seule par
construction, pas par discipline.
"""

from .diagnostic import cataloguer, diagnostiquer, rapport
from .principal import COMMANDES, analyseur, main

__all__ = ["main", "analyseur", "COMMANDES",
           "diagnostiquer", "rapport", "cataloguer"]
