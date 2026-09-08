"""Ligne de commande : `python -m falcon`.

Cinq commandes, et aucune n'ecrit dans SAP. `diagnostiquer` ne recoit qu'un
`DriverLecture` — une facade qui n'a ni `write`, ni `press`, ni `vkey` : le
premier contact reel du projet est en lecture seule par construction, pas par
discipline. Les quatre autres ne voient meme pas de session.

`console`, elle, mene a des ecrans qui ecrivent — la confirmation en toutes
lettres et le recapitulatif sont dans `falcon/console/`.
"""

from .diagnostic import cataloguer, diagnostiquer, rapport
from .principal import COMMANDES, analyseur, main

__all__ = ["main", "analyseur", "COMMANDES",
           "diagnostiquer", "rapport", "cataloguer"]
