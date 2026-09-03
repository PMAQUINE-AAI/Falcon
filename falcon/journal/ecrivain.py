"""Ecriture du journal : ajout en fin de fichier, et rien d'autre.

Chaque ligne est poussee sur le disque avant que l'appel ne rende la main.
C'est plus lent qu'un tampon, et c'est le prix a payer : un journal qui perd
ses dernieres lignes au moment ou le poste se bloque est precisement inutile
au moment ou il servirait — la reprise rejouerait des items deja traites.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import TracebackType

from falcon.noyau import Horloge, maintenant

from .enregistrement import Enregistrement


class Ecrivain:
    """Ajoute des enregistrements a un journal JSONL.

        with Ecrivain("sorties/ma_pipeline/journal.jsonl") as journal:
            journal.ecrire(ItemDebut(run_id=..., item_id=...))
    """

    def __init__(self, chemin: str | Path, horloge: Horloge = maintenant):
        self.chemin = Path(chemin)
        self._horloge = horloge
        self._fichier = None

    # -- cycle de vie ---------------------------------------------------

    def ouvrir(self) -> "Ecrivain":
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._fichier = open(self.chemin, "a", encoding="utf-8", newline="\n")
        return self

    def fermer(self) -> None:
        if self._fichier is not None:
            self._fichier.close()
            self._fichier = None

    def __enter__(self) -> "Ecrivain":
        return self.ouvrir()

    def __exit__(self, type_: type[BaseException] | None,
                 valeur: BaseException | None,
                 trace: TracebackType | None) -> None:
        self.fermer()

    # -- ecriture --------------------------------------------------------

    def ecrire(self, enregistrement: Enregistrement) -> Enregistrement:
        """Ajoute une ligne. Rend l'enregistrement effectivement ecrit.

        L'horodatage est pose ici s'il est vide : c'est le seul endroit qui
        sait quand la ligne part sur le disque.
        """
        if self._fichier is None:
            raise RuntimeError("journal non ouvert : utiliser `with Ecrivain(...)`")

        if not enregistrement.horodatage:
            enregistrement = enregistrement.date(self._horloge())

        ligne = json.dumps(enregistrement.vers_dict(), ensure_ascii=False,
                           separators=(",", ":"), sort_keys=False)
        self._fichier.write(ligne + "\n")
        self._fichier.flush()
        os.fsync(self._fichier.fileno())
        return enregistrement
