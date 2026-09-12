"""Console interactive : `python -m falcon console`.

Menus numerotes sur un flux texte, sans `curses` et sans dependance : la
machine cible est Windows, ou `curses` n'est pas fourni avec CPython. Ce refus
n'est plus une prose : `tests/test_frontieres.py` porte `MODULES_INTERDITS`, et
c'est ce qui compte, parce que la CI est Linux — OU CURSES EXISTE. Une console
`curses` aurait passe la suite au vert et serait morte a l'import sur la seule
machine ou elle sert.

Les menus eux-memes n'emettent aucune sequence : `rendre` produit des lignes
nues, gelees par une fixture. La couleur, quand le terminal l'a PROUVEE, est
posee par `falcon/toile/peintre.py` par-dessus ces lignes-la, sans en changer
ni le nombre ni le contenu.

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
