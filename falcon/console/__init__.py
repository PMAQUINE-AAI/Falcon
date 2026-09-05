"""Console interactive : `python -m falcon console`.

Menus numerotes sur un flux texte, sans `curses` et sans dependance : la
machine cible est Windows, ou `curses` n'est pas fourni avec CPython. Aucun
ecran de cette console n'ecrit dans SAP — la branche SAP ne manipule qu'un
`DriverLecture`, qui n'a ni `write`, ni `press`, ni `vkey`.
"""

from .ecrans import Environnement, racine
from .menu import (
    CONTINUER, ENCODAGE_MINIMAL, QUITTER, RETOUR, Console, Entree, Menu,
    parcourir, rendre,
)

__all__ = [
    "Console", "Menu", "Entree", "parcourir", "rendre", "racine",
    "Environnement", "CONTINUER", "RETOUR", "QUITTER", "ENCODAGE_MINIMAL",
]
