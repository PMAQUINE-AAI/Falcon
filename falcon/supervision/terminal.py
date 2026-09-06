"""Ou et comment la progression s'ecrit — et quand elle se tait.

**Muet hors terminal, par defaut.** Un lot dont la sortie part dans un fichier
ou dans un journal de CI n'a rien a gagner a recevoir une ligne de progression
par item : ca noie ce qu'on est venu lire. Le redessin, lui, n'a de sens que
sur un terminal, ou le retour chariot repositionne le curseur.

`forcer=True` existe pour le cas ou on veut quand meme la trace — un lot long
lance dans un `nohup`, typiquement. C'est un choix explicite, pas un defaut.

**Le redessin n'utilise aucune sequence ANSI.** Un simple retour chariot et du
remplissage : ca marche dans `cmd`, dans PowerShell, a travers RDP. Une
sequence ANSI marcherait sur la moitie de ces terminaux et laisserait des
caracteres parasites sur l'autre.
"""

from __future__ import annotations

import sys
from typing import Any, TextIO

from .modele import ENCODAGE_MINIMAL, Estimation, Progres, Suivi, bilan, ligne


class Rapporteur:
    """Observateur de progression, branchable sur `moteur.executer`.

    S'utilise directement comme `observateur=` : `__call__` prend un `Progres`.
    """

    def __init__(self, flux: TextIO | None = None, *, forcer: bool = False,
                 fenetre: int | None = None):
        self._flux = flux if flux is not None else sys.stderr
        self._suivi = Suivi(fenetre) if fenetre else Suivi()
        self._largeur = 0
        self._dernier = Estimation()
        self._dernier_progres: Progres | None = None
        self.actif = bool(forcer or self._interactif())

    def _interactif(self) -> bool:
        try:
            return bool(self._flux.isatty())
        except Exception:
            # Un flux qui ne sait pas dire s'il est interactif ne l'est pas.
            return False

    def __call__(self, progres: Progres) -> None:
        self._dernier = self._suivi.ajouter(progres)
        self._dernier_progres = progres
        if not self.actif:
            return
        self._ecrire(ligne(progres, self._dernier))

    def _ecrire(self, texte: str) -> None:
        # Remplissage jusqu'a la largeur precedente : sans lui, une ligne plus
        # courte laisserait la queue de la precedente a l'ecran.
        rembourre = texte.ljust(self._largeur)
        self._largeur = max(self._largeur, len(texte))
        self._flux.write("\r" + rembourre)
        self._flux.flush()

    def clore(self) -> None:
        """A appeler en fin de lot : passe a la ligne et pose le bilan."""
        if not self.actif or self._dernier_progres is None:
            return
        self._flux.write("\r" + " " * self._largeur + "\r")
        self._flux.write(bilan(self._dernier_progres, self._dernier) + "\n")
        self._flux.flush()

    def __enter__(self) -> "Rapporteur":
        return self

    def __exit__(self, *_: Any) -> None:
        self.clore()


def encodable(texte: str) -> bool:
    """Le rendu tient-il dans l'encodage d'une console Windows redirigee."""
    try:
        texte.encode(ENCODAGE_MINIMAL)
    except UnicodeEncodeError:
        return False
    return True
