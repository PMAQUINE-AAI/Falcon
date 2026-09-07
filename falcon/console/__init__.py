"""Console interactive : `python -m falcon console`.

Menus numerotes sur un flux texte, sans `curses` et sans dependance : la
machine cible est Windows, ou `curses` n'est pas fourni avec CPython.

**Sept domaines, dont un qui ecrit.** La console a ete ecrite au lot 14,
avant le moteur, et n'a longtemps donne acces qu'a ce qui ne touchait a rien.
Elle pilote desormais l'execution — donc elle peut ecrire dans un ERP. Ce qui
en repond n'est pas une consigne de relecture mais deux choses verifiees :

  - une execution reelle exige une CONFIRMATION EN TOUTES LETTRES, precedee
    d'un recapitulatif qui nomme les deux plafonds, le nombre d'items et
    chaque derogation avec son motif. Le mot attendu est le nom de la
    pipeline : on ne peut pas le taper sans avoir lu ce recapitulatif ;
  - rien ici ne touche un `Driver` nu. La branche SAP ne manipule qu'un
    `DriverLecture` — sans `write`, sans `press`, sans `vkey` — et la branche
    d'execution passe le driver au moteur, qui l'enveloppe aussitot dans un
    `DriverGarde`. Un test sur l'AST epingle la frontiere.
"""

from .ecrans import Environnement, racine
from .menu import (
    CONTINUER, ENCODAGE_MINIMAL, QUITTER, RETOUR, VERDICTS, Console, Entree,
    Menu, parcourir, rendre,
)

__all__ = [
    "Console", "Menu", "Entree", "parcourir", "rendre", "racine",
    "Environnement", "CONTINUER", "RETOUR", "QUITTER", "VERDICTS",
    "ENCODAGE_MINIMAL",
]
